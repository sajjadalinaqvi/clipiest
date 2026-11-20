"""Live session management: Streamlink recording and chat spike trigger for Clipiest."""
import os
import re
import sys
import time
import uuid
import threading
import subprocess
from pathlib import Path
from collections import Counter
from .chat import ChatWatcher
from ..rendering.render import render_clip, probe_video
from ..audio.transcribe import transcribe_audio_segment
from ..ai.brain import evaluate_moment

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

BUCKET_SEC = 10
BASELINE_BUCKETS = 30  # 5 minutes
SPIKE_SIGMA = 2.5
SPIKE_RATIO = 2.5
COOLDOWN_SEC = 60

class LiveStreamSession:
    def __init__(self, url: str, data_dir: Path, opts: dict):
        self.url = url
        self.data_dir = data_dir
        self.opts = opts
        self.session_id = uuid.uuid4().hex[:12]
        self.work_dir = data_dir / f"live_{self.session_id}"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.rec_file = self.work_dir / "stream.ts"
        
        self.platform, self.target = self._parse_target(url)
        self.chat = ChatWatcher(self.platform, self.target)
        self.stop_ev = threading.Event()
        self.proc = None
        self.t0 = None
        self.clips = []
        self.state = {
            "id": self.session_id,
            "status": "starting",
            "stage": "Connecting to stream...",
            "clips": [],
            "spikes": 0,
            "chat_velocity": 0
        }

    def _parse_target(self, url: str) -> tuple[str, str]:
        if "twitch.tv" in url:
            m = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", url)
            channel = m.group(1).lower() if m else "twitch"
            return "twitch", channel
        elif "youtu" in url:
            m = re.search(r"(?:v=|/live/|youtu\.be/)([A-Za-z0-9_-]{11})", url)
            vid = m.group(1) if m else "live"
            return "youtube", vid
        return "custom", "live"

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.stop_ev.set()
        self.chat.stop()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.state.update({"status": "stopped", "stage": "Recording stopped."})

    def clip_now(self, seconds: float = 30.0):
        """Immediately clips the past N seconds from the live recording buffer."""
        if not self.t0:
            raise RuntimeError("Stream has not started yet.")
        cur = time.time() - self.t0
        start = max(0.0, cur - seconds)
        threading.Thread(target=self._render_moment, args=(start, seconds, "Instant clip"), daemon=True).start()

    def _render_moment(self, start: float, duration: float, reason: str):
        clip_id = uuid.uuid4().hex[:12]
        out_mp4 = self.work_dir / f"{clip_id}.mp4"
        
        # Cut chunk from live TS
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start:.2f}",
            "-i", str(self.rec_file),
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", str(out_mp4)
        ]
        r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0 or not out_mp4.exists():
            return
            
        trans = transcribe_audio_segment(out_mp4, 0, duration, self.work_dir, report_fn=lambda m: None)
        words = trans["words"]
        txt = " ".join(w["text"] for w in words)
        eval_data = evaluate_moment(txt, "Live Stream")
        
        meta = probe_video(out_mp4)
        vw, vh = meta["w"], meta["h"]
        cam = self.opts.get("cam", {"x": 0, "y": 0, "w": 0.25, "h": 0.3})
        game = self.opts.get("game", {"x": 0.25, "y": 0, "w": 0.75, "h": 1.0})
        cam_rect = (int(cam["x"] * vw), int(cam["y"] * vh), int(cam["w"] * vw), int(cam["h"] * vh))
        game_rect = (int(game["x"] * vw), int(game["y"] * vh), int(game["w"] * vw), int(game["h"] * vh))
        
        final_res = render_clip(
            src_path=out_mp4,
            out_dir=self.work_dir,
            name=f"final_{clip_id}",
            start=0,
            end=duration,
            layout=self.opts.get("layout", "stack"),
            top=float(self.opts.get("top", 0.32)),
            cam_rect=cam_rect,
            game_rect=game_rect,
            words=words,
            caption_style=self.opts.get("caption_style", "bounce"),
            hook=eval_data.get("hook", "")
        )
        
        item = {
            "id": clip_id,
            "title": eval_data.get("title", "Live Highlight"),
            "hook": eval_data.get("hook", ""),
            "score": eval_data.get("score", 75),
            "start": round(start),
            "end": round(start + duration),
            "file": f"final_{clip_id}.mp4",
            "reason": reason
        }
        self.clips.append(item)
        self.state["clips"] = list(self.clips)

    def _run(self):
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "streamlink", "--loglevel", "warning", "--stdout", self.url, "best"],
                stdout=open(self.rec_file, "wb"), stderr=subprocess.DEVNULL, creationflags=NO_WINDOW
            )
            deadline = time.time() + 60
            while self.t0 is None:
                if self.rec_file.exists() and self.rec_file.stat().st_size > 0:
                    self.t0 = time.time()
                elif time.time() > deadline or self.proc.poll() is not None:
                    raise RuntimeError("Unable to connect to live stream.")
                time.sleep(0.5)

            self.chat.start()
            self.state.update({"status": "recording", "stage": "Recording and monitoring chat spikes"})
            
            last_spike_time = -999.0
            seen_bucket = None
            
            while not self.stop_ev.is_set() and self.proc.poll() is None:
                time.sleep(1)
                now_sec = time.time()
                cur_bucket = int(now_sec // BUCKET_SEC) - 1
                
                # Check chat velocity
                cnt = self.chat.counts.get(int(now_sec), 0)
                self.state["chat_velocity"] = cnt
                
                if cur_bucket == seen_bucket:
                    continue
                seen_bucket = cur_bucket
                
                hist = [self.chat.counts.get(b * BUCKET_SEC, 0) for b in range(cur_bucket - BASELINE_BUCKETS, cur_bucket)]
                c_count = self.chat.counts.get(cur_bucket * BUCKET_SEC, 0)
                
                if len([h for h in hist if h > 0]) >= 6:
                    import statistics
                    mu = statistics.mean(hist)
                    sd = statistics.pstdev(hist) or 1.0
                    stream_time = cur_bucket * BUCKET_SEC + BUCKET_SEC / 2 - self.t0
                    
                    if c_count >= 8 and c_count > mu + SPIKE_SIGMA * sd and c_count >= SPIKE_RATIO * max(mu, 1.0):
                        if stream_time - last_spike_time > COOLDOWN_SEC:
                            last_spike_time = stream_time
                            self.state["spikes"] += 1
                            # Trigger clip backdating 24s before the spike
                            start_clip = max(0.0, stream_time - 24.0)
                            dur_clip = 38.0
                            why = f"Chat velocity spike: {c_count} msgs/10s (baseline: {mu:.1f})"
                            threading.Timer(16.0, lambda s=start_clip, d=dur_clip, w=why: self._render_moment(s, d, w)).start()
        except Exception as e:
            self.state.update({"status": "error", "error": str(e)})
        finally:
            self.stop()

class LiveClipManager:
    def __init__(self, data_dir: Path, session_id: str, url: str, channel: str = "", opts: dict = None):
        self.data_dir = data_dir
        self.session_id = session_id
        self.url = url
        self.opts = opts or {}
        self.session = LiveStreamSession(url, data_dir, self.opts)

    def start(self):
        self.session.start()

    def stop(self):
        self.session.stop()

    def clip_buffer(self, duration_sec: float = 60.0) -> Path | None:
        self.session.clip_now(seconds=duration_sec)
        return self.session.rec_file if self.session.rec_file.exists() else None

    def get_status(self) -> dict:
        cur_time = time.time() - self.session.t0 if self.session.t0 else 0
        cur_bucket = int(time.time() // BUCKET_SEC)
        chat_now = self.session.chat.counts.get(cur_bucket * BUCKET_SEC, 0)
        return {
            "session_id": self.session_id,
            "status": self.session.state.get("status", "unknown"),
            "stage": self.session.state.get("stage", ""),
            "chat_speed": chat_now,
            "buffer_seconds": round(cur_time, 1),
            "spikes_detected": self.session.state.get("spikes", 0),
            "clips": self.session.clips
        }
