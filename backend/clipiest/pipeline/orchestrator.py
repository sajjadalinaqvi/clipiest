"""Clipiest Master Pipeline Orchestrator.
Unifies PeakCut's extraction, progressive chunking, and game rules with
NeonClipping's optical flow, visual heuristics, 11 layouts, and self-learning feedback.
"""
import json
import math
import os
import re
import shutil
import time
import uuid
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from ..config import DATA_DIR, FAST_OVER_SEC, PAD_SEC
from ..audio.transcribe import transcribe_audio_segment, youtube_words_from_info, window_words
from ..audio.highlights import rank_highlights
from ..audio.excite import seconds_signal, window_score
from ..vision.action import analyze_action
from ..vision.facecam import detect_facecam
from ..ai.brain import evaluate_moment, snap_clip_to_sentences
from ..ai.games import detect_game
from ..ai.learn import load_weights, compute_rank_score
from ..rendering.render import render_clip, probe_video
from ..rendering.translit import to_roman
from .downloader import get_ytdl, download_video_section, find_exact_section_start

def run_clip_pipeline(body: dict, state: dict, job_id: str):
    """Executes full clipping pipeline asynchronously in the background."""
    save_fn = lambda d: state[job_id].update(d)
    url = str(body.get("url", "")).strip()
    source_id = str(body.get("id", "")).strip()
    
    count = max(1, min(12, int(body.get("count", 4))))
    max_len = max(10, min(180, float(body.get("max_len", body.get("length", 60)))))
    min_len = max(5, min(max_len, float(body.get("min_len", 30))))
    mode = "deep" if body.get("mode") == "deep" else "fast"
    layout = body.get("layout", "stack")
    caption_style = body.get("caption_style", "bounce")
    top_h = float(body.get("top", 0.32))
    
    # Creator workspace integration
    creator_id = str(body.get("creator_id") or body.get("creator") or "").strip()
    creator_info = None
    c_videos_dir = None
    c_clips_dir = None
    if creator_id:
        try:
            from ..creators import get_creator, get_creator_dirs
            creator_info = get_creator(creator_id)
            if creator_info:
                if not body.get("layout"):
                    layout = creator_info.get("default_layout") or layout
                if not body.get("caption_style"):
                    caption_style = creator_info.get("default_caption_style") or caption_style
                _, c_videos_dir, c_clips_dir = get_creator_dirs(creator_id)
        except Exception:
            pass

    # User crop boxes (default to preset or full)
    cam_in = body.get("cam", {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.30})
    game_in = body.get("game", {"x": 0.25, "y": 0.0, "w": 0.75, "h": 1.0})
    
    save_fn({"status": "running", "stage": "Initializing", "progress": 0.01, "clips": []})
    began = time.monotonic()
    
    try:
        title = ""
        uploader = ""
        yt_words = None
        info = {}
        
        if url:
            save_fn({"stage": "Analyzing video metadata...", "progress": 0.05})
            with get_ytdl({"skip_download": True}) as y:
                info = y.extract_info(url, download=False)
            if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
                raise RuntimeError("Stream is currently live. Use the Live Clipping panel.")
            title = info.get("title") or "Video"
            uploader = info.get("uploader") or info.get("channel") or ""
            duration = float(info.get("duration") or 0)
            
            # YouTube caption scraping (instant, ~1s)
            yt_words = youtube_words_from_info(info)
            save_fn({"transcript_source": "YouTube captions" if yt_words else "AI Speech Model"})
        else:
            # Uploaded local video
            src_file = DATA_DIR / f"{source_id}.mp4"
            if not src_file.exists():
                for sub in DATA_DIR.iterdir():
                    if sub.is_dir() and (sub / f"{source_id}.mp4").exists():
                        src_file = sub / f"{source_id}.mp4"
                        break
            meta = probe_video(src_file)
            duration = meta["duration"]
            title = "Uploaded Video"

        game_name, hashtags = detect_game(title, uploader)
        
        # Decide Fast Mode vs Deep Mode
        is_fast = (duration > FAST_OVER_SEC and mode == "fast" and url)
        
        safe_title = re.sub(r"[^\w\- ]", "_", title).strip()[:40].strip(" _") or "video"
        if creator_info and c_clips_dir:
            vdir = c_clips_dir
        else:
            vdir = DATA_DIR / f"{safe_title}_{job_id[:8]}"
            vdir.mkdir(parents=True, exist_ok=True)
        
        learned_weights = load_weights(DATA_DIR)
        
        if is_fast:
            # Fast Mode: Audio-first download
            save_fn({"stage": "Downloading audio track...", "progress": 0.10})
            audio_path = vdir / f"{job_id}.audio.m4a"
            with get_ytdl({"format": "ba[ext=m4a]/ba/worst", "outtmpl": str(vdir / f"{job_id}.audio.%(ext)s")}) as y:
                y.download([url])
            audio_file = next(f for f in vdir.glob(f"{job_id}.audio.*") if f.suffix not in (".part", ".ytdl"))
            
            save_fn({"stage": "Finding highlights in audio & speech...", "progress": 0.25})
            excite_sig = seconds_signal(yt_words, duration) if yt_words else None
            candidates = rank_highlights(audio_file, duration, count * 2, max_len, motion_on=False, extra_excite=excite_sig)
            
            # Visual action check on top candidates using tiny 144p snippets
            save_fn({"stage": "Evaluating visual action & emotion...", "progress": 0.40})
            from yt_dlp.utils import download_range_func
            for c in candidates:
                lr_name = f"lr_{uuid.uuid4().hex[:8]}"
                try:
                    with get_ytdl({
                        "format": "worst[ext=mp4]/bv*[height<=240][ext=mp4]/worst",
                        "outtmpl": str(vdir / f"{lr_name}.%(ext)s"),
                        "merge_output_format": "mp4",
                        "download_ranges": download_range_func(None, [(max(0, c["start"]), c["end"])])
                    }) as y:
                        y.download([url])
                    lr_file = next((f for f in vdir.glob(f"{lr_name}.*") if f.suffix == ".mp4"), None)
                    if lr_file:
                        c["action"] = analyze_action(lr_file, 0, c["end"] - c["start"])
                        lr_file.unlink(missing_ok=True)
                except Exception:
                    c["action"] = {"motion": 0.2, "flash": 0.0, "strobe": 0.0, "cuts": 0.1}

            # LLM Evaluation & Sentence Snapping
            save_fn({"stage": "Generating AI titles, hooks & transcripts...", "progress": 0.55})
            for c in candidates:
                if yt_words:
                    c["words"] = window_words(yt_words, c["start"], c["end"])
                else:
                    res = transcribe_audio_segment(audio_file, c["start"], c["end"], vdir, report_fn=lambda m: None)
                    c["words"] = res["words"]
                    
                snap_clip_to_sentences(c, c["words"], min_len, max_len)
                txt = " ".join(w["text"] for w in c["words"])
                eval_data = evaluate_moment(txt, title, game_name)
                c.update(eval_data)
                
                feats = {
                    **c.get("features", {}),
                    **c.get("action", {}),
                    "words": window_score(c["words"], c["end"] - c["start"]),
                    "llm": c["score"] / 100.0
                }
                c["rank"] = compute_rank_score(feats, learned_weights)

            candidates.sort(key=lambda x: -x.get("rank", 0))
            chosen = candidates[:count]
            
            # Fetch only the chosen video sections in parallel
            save_fn({"stage": "Fetching chosen video clips...", "progress": 0.65})
            sections = []
            for i, c in enumerate(chosen):
                sec_id = uuid.uuid4().hex[:12]
                sec_file = download_video_section(url, vdir, sec_id, c["start"], c["end"])
                # Keyframe offset correction via audio correlation
                real_start = find_exact_section_start(audio_file, sec_file, max(0.0, c["start"] - PAD_SEC))
                sections.append((sec_file, real_start))
        else:
            # Deep Mode or Local Upload: download complete video
            save_fn({"stage": "Downloading high-resolution source...", "progress": 0.15})
            if url:
                src_tmpl = str(vdir / "source.%(ext)s")
                with get_ytdl({"format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]", "merge_output_format": "mp4", "outtmpl": src_tmpl}) as y:
                    y.download([url])
                src_file = next(f for f in vdir.glob("source.*") if f.suffix == ".mp4")
            meta = probe_video(src_file)
            duration = meta["duration"]
            
            save_fn({"stage": "Scanning optical flow, audio & motion...", "progress": 0.35})
            excite_sig = seconds_signal(yt_words, duration) if yt_words else None
            candidates = rank_highlights(src_file, duration, count * 3, max_len, motion_on=True, extra_excite=excite_sig)
            
            save_fn({"stage": "Evaluating moments with AI...", "progress": 0.55})
            for c in candidates:
                if yt_words:
                    c["words"] = window_words(yt_words, c["start"], c["end"])
                else:
                    res = transcribe_audio_segment(src_file, c["start"], c["end"], vdir, report_fn=lambda m: None)
                    c["words"] = res["words"]
                snap_clip_to_sentences(c, c["words"], min_len, max_len)
                txt = " ".join(w["text"] for w in c["words"])
                eval_data = evaluate_moment(txt, title, game_name)
                c.update(eval_data)
                
                act = analyze_action(src_file, c["start"], c["end"] - c["start"])
                feats = {
                    **c.get("features", {}),
                    **act,
                    "words": window_score(c["words"], c["end"] - c["start"]),
                    "llm": c["score"] / 100.0
                }
                c["rank"] = compute_rank_score(feats, learned_weights)

            candidates.sort(key=lambda x: -x.get("rank", 0))
            chosen = candidates[:count]
            sections = [(src_file, 0.0)] * len(chosen)

        # Automated Facecam Detection check if user kept default boxes
        detected_cam = None
        if url and not is_fast:
            try:
                cam_res = detect_facecam(src_file)
                if cam_res.get("detected"):
                    detected_cam = cam_res["box"]
            except Exception:
                pass
        
        # Render Vertical Clips
        rendered_clips = []
        save_fn({"stage": "Rendering vertical 9:16 clips...", "progress": 0.70})
        
        for i, c in enumerate(chosen):
            clip_id = uuid.uuid4().hex[:12]
            sec_file, real_offset = sections[i]
            
            c_meta = probe_video(sec_file)
            vw, vh = c_meta["w"], c_meta["h"]
            
            cam_box = detected_cam if detected_cam and body.get("auto_facecam") else cam_in
            cam_rect = (
                max(0, min(vw - 2, int(cam_box["x"] * vw))),
                max(0, min(vh - 2, int(cam_box["y"] * vh))),
                max(2, min(vw, int(cam_box["w"] * vw))),
                max(2, min(vh, int(cam_box["h"] * vh)))
            )
            game_rect = (
                max(0, min(vw - 2, int(game_in["x"] * vw))),
                max(0, min(vh - 2, int(game_in["y"] * vh))),
                max(2, min(vw, int(game_in["w"] * vw))),
                max(2, min(vh, int(game_in["h"] * vh)))
            )
            
            clip_start = max(0.0, c["start"] - real_offset) if is_fast else c["start"]
            clip_end = min(c_meta["duration"], clip_start + (c["end"] - c["start"]))
            
            res = render_clip(
                src_path=sec_file,
                out_dir=vdir,
                name=clip_id,
                start=clip_start,
                end=clip_end,
                layout=layout,
                top=top_h,
                cam_rect=cam_rect,
                game_rect=game_rect,
                words=c["words"],
                caption_style=caption_style,
                hook=c.get("hook", "")
            )
            
            clip_rel_file = f"/media/creators/{creator_id}/clips/{clip_id}.mp4" if creator_info else f"{clip_id}.mp4"
            clip_rel_cover = f"/media/creators/{creator_id}/clips/{clip_id}.jpg" if creator_info else f"{clip_id}.jpg"

            clip_record = {
                "id": clip_id,
                "title": c.get("title", f"Clip {i+1}"),
                "hook": c.get("hook", ""),
                "score": int(c.get("score", 70)),
                "start": c["start"],
                "end": c["end"],
                "category": c.get("category", "other"),
                "hashtags": hashtags,
                "file": clip_rel_file,
                "cover": clip_rel_cover,
                "srt": f"{clip_id}.srt",
                "features": c.get("features", {}),
                "creator": creator_id if creator_info else None
            }
            
            # Save metadata JSON for re-editing
            (vdir / f"{clip_id}.json").write_text(json.dumps({
                "source": sec_file.stem,
                "settings": {
                    "id": sec_file.stem,
                    "start": clip_start,
                    "end": clip_end,
                    "layout": layout,
                    "top": top_h,
                    "cam": cam_box,
                    "game": game_in,
                    "caption_style": caption_style,
                    "hook": c.get("hook", ""),
                    "title": c.get("title", ""),
                    "words": c["words"],
                    "source_url": url,
                    "batch_id": job_id,
                    "creator": creator_id if creator_info else None
                },
                "result": {**res, "status": "done"}
            }, indent=2), encoding="utf-8")
            
            rendered_clips.append(clip_record)
            save_fn({
                "clips": list(rendered_clips),
                "progress": round(0.70 + 0.30 * (i + 1) / len(chosen), 2),
                "stage": f"Rendered {i + 1}/{len(chosen)} clips"
            })
            
        if creator_info:
            try:
                from ..creators import log_creator_event
                log_creator_event(creator_id, f"Generated {len(rendered_clips)} viral clips from '{title}'", action="clipped")
            except Exception:
                pass

        save_fn({
            "status": "done",
            "stage": "Clips ready!",
            "progress": 1.0,
            "clips": rendered_clips,
            "elapsed_seconds": round(time.monotonic() - began, 1)
        })
    except Exception as e:
        save_fn({"status": "error", "error": str(e)})
