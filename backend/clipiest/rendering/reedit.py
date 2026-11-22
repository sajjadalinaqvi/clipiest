"""Fast non-destructive saved clip re-editing for Clipiest.
Never re-downloads, re-discovers moments, or invokes ASR in this path.
"""
import json
import math
import re
import time
import uuid
import threading
from pathlib import Path
from fastapi import HTTPException
from .layouts import CATALOG, LAYOUT_IDS, geometry
from .render import render_clip, probe_video

CHANGE_KEYS = {"layout", "top", "cam", "game", "caption_style", "caption_y", "captions", "hook", "title", "words", "background", "hook_x", "hook_size"}

def find_file(data_dir: Path, name: str) -> Path | None:
    p = data_dir / name
    if p.exists():
        return p
    try:
        for sub in data_dir.iterdir():
            if sub.is_dir() and sub.name != "models":
                cand = sub / name
                if cand.exists():
                    return cand
                if sub.name == "creators":
                    for c_dir in sub.iterdir():
                        if c_dir.is_dir():
                            for child_dir in (c_dir / "clips", c_dir / "videos"):
                                cand2 = child_dir / name
                                if cand2.exists():
                                    return cand2
    except OSError:
        pass
    return None

def read_clip_record(data_dir: Path, clip_id: str) -> dict:
    if not isinstance(clip_id, str) or not re.match(r"^[\w\-]+$", clip_id):
        raise HTTPException(400, "Invalid clip identifier.")
    p = find_file(data_dir, f"{clip_id}.json")
    if not p or not p.exists():
        raise HTTPException(404, f"Saved clip '{clip_id}' not found.")
    record = json.loads(p.read_text(encoding="utf-8"))
    if record.get("result", {}).get("status") != "done":
        raise HTTPException(400, "This clip has not finished exporting.")
    return record

def get_saved_words(data_dir: Path, clip_id: str, record: dict) -> list:
    settings = record.get("settings", {})
    if isinstance(settings.get("words"), list) and settings["words"]:
        return settings["words"]
    
    # Check if SRT file exists for legacy fallback
    srt_p = find_file(data_dir, f"{clip_id}.srt")
    if not srt_p or not srt_p.exists():
        return []
    
    def parse_time(v):
        h, m, s = v.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    
    words = []
    for block in srt_p.read_text(encoding="utf-8-sig").strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        a_str, b_str = lines[1].split("-->")
        a, b = parse_time(a_str.strip()), parse_time(b_str.strip())
        tokens = " ".join(lines[2:]).split()
        for i, text in enumerate(tokens):
            words.append({
                "start": round(a + (b - a) * i / max(1, len(tokens)), 3),
                "end": round(a + (b - a) * (i + 1) / max(1, len(tokens)), 3),
                "text": text
            })
    return words

def attach_reedit(app, data_dir: Path, state: dict):
    """Mounts re-edit API endpoints on FastAPI app."""

    @app.get("/clips/{clip_id}/edit")
    @app.get("/api/clips/{clip_id}/edit")
    def get_clip_for_edit(clip_id: str):
        record = read_clip_record(data_dir, clip_id)
        settings = record["settings"]
        source_id = record["source"]
        src_p = find_file(data_dir, f"{source_id}.mp4") or find_file(data_dir, f"{clip_id}.mp4")
        if not src_p or not src_p.exists():
            raise HTTPException(409, "Original source video or clip is unavailable. Cannot re-edit without source.")
        
        words = get_saved_words(data_dir, clip_id, record)
        meta = probe_video(src_p)
        return {
            "file": clip_id,
            "settings": {**settings, "words": words},
            "source": {"id": source_id, **meta},
            "source_url": settings.get("source_url", "")
        }

    @app.post("/clips/reedit")
    @app.post("/api/clips/reedit")
    def apply_reedit(body: dict):
        anchor = str(body.get("file", ""))
        base = read_clip_record(data_dir, anchor)
        changes = body.get("changes", {})
        if not isinstance(changes, dict) or set(changes) - CHANGE_KEYS:
            raise HTTPException(400, "Invalid settings for re-edit.")
        
        scope = body.get("scope", "clip")
        files = body.get("files")
        if files is None:
            files = [anchor]
            if scope == "video":
                source_url = base.get("settings", {}).get("source_url")
                batch_id = base.get("settings", {}).get("batch_id")
                files = []
                for p in data_dir.glob("*.json"):
                    if p.name.endswith((".state.json", ".words.json", ".request.json")):
                        continue
                    try:
                        rec = read_clip_record(data_dir, p.stem)
                        if rec.get("superseded_by"):
                            continue
                        cand_url = rec.get("settings", {}).get("source_url")
                        cand_batch = rec.get("settings", {}).get("batch_id")
                        if (source_url and cand_url == source_url) or (batch_id and cand_batch == batch_id):
                            files.append(p.stem)
                    except Exception:
                        pass
        
        if not files or len(files) > 100:
            raise HTTPException(400, "Select between 1 and 100 saved clips to edit.")
        
        # Prepare and validate all files
        prepared = []
        for fid in list(dict.fromkeys(files)):
            record = read_clip_record(data_dir, fid)
            settings = dict(record["settings"])
            settings.update(changes)
            
            # Anchor clip can update its own wording
            if fid == anchor and "words" in body:
                settings["words"] = body["words"]
            else:
                settings["words"] = get_saved_words(data_dir, fid, record)
                
            source_id = record["source"]
            src_p = find_file(data_dir, f"{source_id}.mp4")
            if not src_p or not src_p.exists():
                raise HTTPException(409, f"Source video for clip '{fid}' is missing.")
            
            # Validate geometry and timings
            try:
                geometry(settings.get("layout", "stack"), settings.get("top", 0.32))
                meta = probe_video(src_p)
                w, h = meta["w"], meta["h"]
                
                # Check crop boxes
                cam = settings.get("cam", {"x": 0, "y": 0, "w": 0.25, "h": 0.3})
                game = settings.get("game", {"x": 0.25, "y": 0, "w": 0.75, "h": 1.0})
                cam_rect = (
                    max(0, min(w - 2, int(cam["x"] * w))),
                    max(0, min(h - 2, int(cam["y"] * h))),
                    max(2, min(w, int(cam["w"] * w))),
                    max(2, min(h, int(cam["h"] * h)))
                )
                game_rect = (
                    max(0, min(w - 2, int(game["x"] * w))),
                    max(0, min(h - 2, int(game["y"] * h))),
                    max(2, min(w, int(game["w"] * w))),
                    max(2, min(h, int(game["h"] * h)))
                )
            except Exception as e:
                raise HTTPException(400, f"Validation failed: {e}")
                
            prepared.append({
                "clip_id": fid,
                "record": record,
                "settings": settings,
                "src_path": src_p,
                "cam_rect": cam_rect,
                "game_rect": game_rect
            })
            
        job_id = uuid.uuid4().hex
        state[job_id] = {
            "id": job_id,
            "kind": "reedit",
            "status": "running",
            "stage": "Applying edits",
            "progress": 0.0,
            "clips": []
        }
        
        def work():
            done = []
            try:
                for i, item in enumerate(prepared):
                    old_id = item["clip_id"]
                    new_id = uuid.uuid4().hex
                    s = item["settings"]
                    old_p = find_file(data_dir, f"{old_id}.json")
                    target_dir = old_p.parent if old_p else item["src_path"].parent
                    
                    res = render_clip(
                        src_path=item["src_path"],
                        out_dir=target_dir,
                        name=new_id,
                        start=float(s["start"]),
                        end=float(s["end"]),
                        layout=s.get("layout", "stack"),
                        top=float(s.get("top", 0.32)),
                        cam_rect=item["cam_rect"],
                        game_rect=item["game_rect"],
                        words=s.get("words", []),
                        caption_style=s.get("caption_style", "bounce"),
                        caption_y=int(s.get("caption_y", 1450)),
                        hook=s.get("hook", ""),
                        hook_y=int(s["hook_y"]) if s.get("hook_y") is not None else None,
                        background=s.get("background", "default"),
                        hook_x=int(s.get("hook_x", 540)),
                        hook_size=int(s["hook_size"]) if s.get("hook_size") is not None else None
                    )
                    
                    # Mark previous record as superseded
                    old_record = item["record"]
                    old_record["superseded_by"] = new_id
                    old_p = find_file(data_dir, f"{old_id}.json")
                    if old_p:
                        old_p.write_text(json.dumps(old_record, indent=2), encoding="utf-8")
                        
                    # Save new record
                    new_record = {
                        "source": old_record["source"],
                        "settings": {**s, "revision_of": old_id},
                        "result": res
                    }
                    (target_dir / f"{new_id}.json").write_text(json.dumps(new_record, indent=2), encoding="utf-8")
                    
                    try:
                        rel_folder = str(target_dir.relative_to(data_dir)).replace("\\", "/")
                        prefix = f"/media/{rel_folder}" if rel_folder and rel_folder != "." else "/media"
                    except ValueError:
                        prefix = "/media"

                    done.append({
                        "file": f"{prefix}/{new_id}.mp4",
                        "id": new_id,
                        "previous": old_id,
                        "title": s.get("title", "Clip"),
                        "srt": f"/text/{new_id}/srt"
                    })
                    state[job_id].update({
                        "clips": list(done),
                        "progress": (i + 1) / len(prepared),
                        "stage": f"Updated {i + 1}/{len(prepared)}"
                    })
                state[job_id].update({"status": "done", "stage": "Edits completed."})
            except Exception as e:
                state[job_id].update({"status": "error", "error": str(e)})

        threading.Thread(target=work, daemon=True).start()
        return {"job": job_id, "clips": len(prepared)}
