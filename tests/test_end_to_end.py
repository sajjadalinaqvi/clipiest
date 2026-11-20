"""End-to-End Real-World Pipeline Integration Test for Clipiest.
Runs complete video ingestion, facecam detection, framing, ASS burning,
re-edit, feedback rating, and library management on real generated media.
"""
import io
import json
import time
import shutil
import unittest
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.server import app
from clipiest.config import DATA_DIR
from clipiest.rendering.render import probe_video

class TestEndToEndPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_dir = DATA_DIR / "test_e2e_run"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate 4-second synthetic video with audio tone
        cls.sample_video = cls.test_dir / "sample_input.mp4"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=640x360:rate=20",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "128k",
            str(cls.sample_video)
        ]
        subprocess.run(cmd, check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        # Clean any test renders
        for p in DATA_DIR.glob("*test*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

    def test_full_pipeline_lifecycle(self):
        # 1. Upload video
        with open(self.sample_video, "rb") as f:
            res = self.client.post("/upload", files={"file": ("sample_input.mp4", f, "video/mp4")})
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn("id", data)
        source_id = data["id"]
        self.assertEqual(data["w"], 640)
        self.assertEqual(data["h"], 360)
        self.assertAlmostEqual(data["duration"], 4.0, delta=0.5)

        # 2. Extract Storyboard Frames
        sb_res = self.client.get(f"/preview/{source_id}/storyboard")
        self.assertEqual(sb_res.status_code, 200, sb_res.text)
        sb_data = sb_res.json()
        self.assertGreaterEqual(len(sb_data["frames"]), 1)

        # 3. Detect Facecam
        cam_res = self.client.post(f"/preview/{source_id}/autocam")
        self.assertEqual(cam_res.status_code, 200, cam_res.text)
        self.assertIn("detected", cam_res.json())

        # 4. Export 9:16 Vertical Cut with ASS captions
        export_payload = {
            "id": source_id,
            "start": 0.5,
            "end": 2.5,
            "layout": "stack",
            "top": 0.32,
            "caption_style": "bounce",
            "hook": "TEST CLAMP HOOK",
            "words": [
                {"start": 0.6, "end": 1.2, "text": "Clipiest"},
                {"start": 1.2, "end": 2.0, "text": "Engine"}
            ],
            "cam": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.30},
            "game": {"x": 0.25, "y": 0.0, "w": 0.75, "h": 1.0}
        }
        exp_res = self.client.post("/export", json=export_payload)
        self.assertEqual(exp_res.status_code, 200, exp_res.text)
        job_id = exp_res.json()["job_id"]
        clip_id = exp_res.json()["clip_id"]

        # 5. Poll job status until done
        for _ in range(30):
            status_res = self.client.get(f"/jobs/{job_id}")
            self.assertEqual(status_res.status_code, 200)
            status_data = status_res.json()
            if status_data.get("status") in ("done", "error"):
                break
            time.sleep(0.5)

        self.assertEqual(status_data.get("status"), "done", f"Export failed: {status_data}")

        # 6. Verify rendered clip with ffprobe (dimensions must be 1080x1920)
        rendered_mp4 = next(DATA_DIR.rglob(f"{clip_id}.mp4"), None)
        self.assertIsNotNone(rendered_mp4, f"Rendered MP4 {clip_id}.mp4 not found on disk")
        meta = probe_video(rendered_mp4)
        self.assertEqual(meta["w"], 1080)
        self.assertEqual(meta["h"], 1920)
        self.assertGreater(meta["duration"], 1.5)

        # 7. Verify media and text endpoints
        media_res = self.client.get(f"/media/{clip_id}.mp4")
        self.assertEqual(media_res.status_code, 200)

        srt_res = self.client.get(f"/text/{clip_id}/srt")
        self.assertEqual(srt_res.status_code, 200)
        self.assertIn("Clipiest", srt_res.text)

        # 8. Test Non-Destructive Re-Edit
        reedit_payload = {
            "file": clip_id,
            "scope": "clip",
            "changes": {
                "layout": "blur",
                "caption_style": "mrbeast",
                "hook": "REEDITED HOOK"
            }
        }
        reedit_res = self.client.post("/api/clips/reedit", json=reedit_payload)
        self.assertEqual(reedit_res.status_code, 200, reedit_res.text)
        reedit_job = reedit_res.json()["job"]

        for _ in range(30):
            r_status = self.client.get(f"/jobs/{reedit_job}")
            if r_status.json().get("status") in ("done", "error"):
                break
            time.sleep(0.5)

        self.assertEqual(r_status.json().get("status"), "done")

        # 9. Test Self-Learning Feedback Rating
        fb_res = self.client.post("/api/feedback", json={"clip_id": clip_id, "rating": 5, "features": {"loud": 0.9, "motion": 0.8}})
        self.assertEqual(fb_res.status_code, 200)
        self.assertIn("weights", fb_res.json())

        # 10. Delete clip
        del_res = self.client.delete(f"/api/library/{clip_id}")
        self.assertEqual(del_res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
