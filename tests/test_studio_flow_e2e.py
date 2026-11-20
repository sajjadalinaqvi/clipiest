"""End-to-end test suite for the new 4-step Studio workflow and Storage Manager."""
import unittest
import sys
import shutil
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.server import app
from clipiest.config import DATA_DIR, DOWNLOADS_DIR

class TestStudioFlowE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_dir = DATA_DIR / "test_studio_e2e"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.test_video = cls.test_dir / "sample_source.mp4"

        # Generate a lightweight 5-second test MP4 with video and audio
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=5:size=1280x720:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
            "-c:v", "libx264", "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            str(cls.test_video)
        ]
        subprocess.run(cmd, check=True)

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_step_1_preview_frame(self):
        """Tests that preview frame extraction works on source video."""
        res = self.client.get(f"/api/preview/frame?id={self.test_video.stem}&sec=1.5")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "image/jpeg")
        self.assertGreater(len(res.content), 500)

    def test_step_2_scout_moments_fallback(self):
        """Tests moments scout endpoint on source video."""
        payload = {
            "id": self.test_video.stem,
            "count": 2,
            "min_len": 2,
            "max_len": 4
        }
        res = self.client.post("/api/moments/scout", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("moments", data)
        self.assertGreaterEqual(len(data["moments"]), 1)
        m = data["moments"][0]
        self.assertIn("start", m)
        self.assertIn("end", m)
        self.assertIn("title", m)
        self.assertIn("score", m)

    def test_step_3_slice_fetch_and_captions(self):
        """Tests slicing 2 seconds from the video without full download."""
        # 1. Fetch slice
        slice_payload = {
            "id": self.test_video.stem,
            "start": 1.0,
            "end": 3.0,
            "quality": 720
        }
        res = self.client.post("/api/slice/fetch", json=slice_payload)
        self.assertEqual(res.status_code, 200)
        slice_data = res.json()
        self.assertTrue(slice_data.get("success"))
        slice_id = slice_data.get("slice_id")
        self.assertTrue(slice_id)

        # Verify slice exists on disk
        slice_file = DATA_DIR / "slices" / f"{slice_id}.mp4"
        self.assertTrue(slice_file.exists())

        # 2. Extract preview frame from the newly created slice
        frame_res = self.client.get(f"/api/preview/frame?slice_id={slice_id}&sec=0.5")
        self.assertEqual(frame_res.status_code, 200)
        self.assertEqual(frame_res.headers.get("content-type"), "image/jpeg")

        # 3. Transcribe / caption slice
        cap_payload = {
            "slice_id": slice_id,
            "hook": "TEST HOOK TITLE"
        }
        cap_res = self.client.post("/api/slice/captions", json=cap_payload)
        self.assertEqual(cap_res.status_code, 200)
        cap_data = cap_res.json()
        self.assertTrue(cap_data.get("success"))
        self.assertEqual(cap_data.get("hook"), "TEST HOOK TITLE")

        # 4. Clean up slice
        slice_file.unlink(missing_ok=True)

    def test_step_4_manual_export_to_downloads(self):
        """Tests rendering a clip from source video and verifying output in Downloads folder."""
        payload = {
            "id": self.test_video.stem,
            "start": 0.0,
            "end": 1.5,
            "layout": "stack",
            "top": 0.32,
            "caption_style": "bounce",
            "hook_style": "punch",
            "caption_y": 1450,
            "hook_y": 260,
            "hook": "VIRAL HOOK",
            "cam": {"x": 0.0, "y": 0.0, "w": 0.3, "h": 0.3},
            "game": {"x": 0.3, "y": 0.0, "w": 0.7, "h": 1.0}
        }
        res = self.client.post("/export", json=payload)
        self.assertEqual(res.status_code, 200)
        job_id = res.json().get("job_id")
        clip_id = res.json().get("clip_id")

        # Poll job until done
        import time
        for _ in range(30):
            time.sleep(0.5)
            status_res = self.client.get(f"/jobs/{job_id}")
            if status_res.status_code == 200:
                s_data = status_res.json()
                if s_data.get("status") in ("done", "error"):
                    self.assertEqual(s_data.get("status"), "done", f"Render failed: {s_data.get('error')}")
                    break

        # Verify saved in Downloads directory
        expected_download = DOWNLOADS_DIR / f"{clip_id}.mp4"
        self.assertTrue(expected_download.exists(), f"File {expected_download} was not saved to Downloads folder!")
        self.assertGreater(expected_download.stat().st_size, 1000)

        # Test download endpoint
        dl_res = self.client.get(f"/api/download/{clip_id}.mp4")
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.headers.get("content-type"), "video/mp4")

        # Clean up exported test file
        expected_download.unlink(missing_ok=True)
        (DATA_DIR / "exports" / f"{clip_id}.mp4").unlink(missing_ok=True)
        (DATA_DIR / "exports" / f"{clip_id}.json").unlink(missing_ok=True)
        (DATA_DIR / "exports" / f"{clip_id}.jpg").unlink(missing_ok=True)
        (DATA_DIR / "exports" / f"{clip_id}.srt").unlink(missing_ok=True)
        (DATA_DIR / "exports" / f"{clip_id}.ass").unlink(missing_ok=True)

    def test_step_5_storage_manager_actions(self):
        """Tests Storage Manager listing, categorized aggregation, and deletion."""
        dummy_file = DATA_DIR / "dummy_sample.json"
        dummy_file.write_text('{"test": true}', encoding="utf-8")

        # 1. List files
        res = self.client.get("/api/storage/files")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("files", data)
        names = [f["name"] for f in data["files"]]
        self.assertIn("dummy_sample.json", names)

        # Verify category detection
        dummy_meta = next(f for f in data["files"] if f["name"] == "dummy_sample.json")
        self.assertEqual(dummy_meta["category"], "metadata")

        # 2. Delete file
        del_res = self.client.post("/api/storage/delete", json={"path": "dummy_sample.json"})
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json().get("success"))
        self.assertFalse(dummy_file.exists())

        # 3. Clean temporary files
        tmp_dummy = DATA_DIR / "tmp" / "temp_e2e.txt"
        tmp_dummy.write_text("temp", encoding="utf-8")
        clean_res = self.client.post("/api/storage/clean-tmp")
        self.assertEqual(clean_res.status_code, 200)
        self.assertFalse(tmp_dummy.exists())

if __name__ == "__main__":
    unittest.main()
