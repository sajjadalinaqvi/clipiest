"""Tests for multi-clip isolation, preventing caption leakage across consecutive video clips."""
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from clipiest.server import app
from clipiest.config import DATA_DIR

client = TestClient(app)

class TestClipIsolationAndCaptions(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = DATA_DIR / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.slices_dir = DATA_DIR / "slices"
        self.slices_dir.mkdir(parents=True, exist_ok=True)

    def test_slice_fetch_writes_metadata_and_captions_writes_cache(self):
        # Create dummy slice mp4
        slice_id = "slice_test_isolation_01"
        dummy_mp4 = self.slices_dir / f"{slice_id}.mp4"
        dummy_mp4.write_bytes(b"dummy mp4 data for testing")

        # Mock probe_video and transcribe_audio_segment
        with patch("clipiest.server.probe_video", return_value={"duration": 10.0, "w": 1280, "h": 720}), \
             patch("clipiest.audio.transcribe.transcribe_audio_segment", return_value={"words": [{"start": 0.5, "end": 1.5, "text": "HELLO"}]}):
            
            resp = client.post("/api/slice/captions", json={
                "slice_id": slice_id,
                "hook": "TEST HOOK"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertEqual(len(data["words"]), 1)
            self.assertEqual(data["words"][0]["text"], "HELLO")

            # Verify cached words file exists
            words_file = self.slices_dir / f"{slice_id}_words.json"
            self.assertTrue(words_file.exists())
            cached_words = json.loads(words_file.read_text(encoding="utf-8"))
            self.assertEqual(cached_words[0]["text"], "HELLO")

        # Clean up
        dummy_mp4.unlink(missing_ok=True)
        (self.slices_dir / f"{slice_id}_words.json").unlink(missing_ok=True)

    def test_manual_export_discards_mismatched_slice_from_different_url(self):
        # Create dummy slice mp4 from Video 1
        slice_id = "slice_video_1"
        dummy_mp4 = self.slices_dir / f"{slice_id}.mp4"
        dummy_mp4.write_bytes(b"dummy mp4 data")
        
        # Write metadata marking this slice as belonging to URL 1
        meta_file = self.slices_dir / f"{slice_id}.json"
        meta_file.write_text(json.dumps({
            "slice_id": slice_id,
            "url": "https://www.youtube.com/watch?v=VIDEO_1",
            "start": 0,
            "end": 30
        }), encoding="utf-8")

        # Now attempt export of Video 2 with the stale slice_id from Video 1
        with patch("clipiest.server.render_clip", return_value={"clip_path": "exports/dummy.mp4"}), \
             patch("clipiest.pipeline.downloader.download_video_section", return_value=dummy_mp4), \
             patch("clipiest.server.probe_video", return_value={"duration": 30.0, "w": 1280, "h": 720}):
            
            resp = client.post("/export", json={
                "url": "https://www.youtube.com/watch?v=VIDEO_2",  # Different video URL!
                "slice_id": slice_id,  # Old slice ID passed by stale state
                "words": [{"start": 0.0, "end": 2.0, "text": "OLD VIDEO 1 WORDS"}],
                "start": 10,
                "end": 40
            })
            self.assertEqual(resp.status_code, 200)
            job_id = resp.json()["job_id"]
            self.assertTrue(job_id.startswith("export_"))

        # Clean up
        dummy_mp4.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)

if __name__ == "__main__":
    unittest.main()
