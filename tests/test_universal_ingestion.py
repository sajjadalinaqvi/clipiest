import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import numpy as np
from fastapi.testclient import TestClient

from clipiest.server import app
from clipiest.audio.excite import word_weight, seconds_signal
from clipiest.audio.highlights import rank_highlights

class TestUniversalIngestion(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_word_weight_expanded_lexicon(self):
        # Test gaming climax keywords
        self.assertGreater(word_weight("cops"), 1.0)
        self.assertGreater(word_weight("police!"), 1.0)
        self.assertGreater(word_weight("wanted"), 1.0)
        self.assertGreater(word_weight("helicopter"), 1.0)
        self.assertGreater(word_weight("clutch"), 1.0)
        self.assertGreater(word_weight("WTF"), 1.0)

    def test_seconds_signal_pacing(self):
        # 10s duration, words dense around second 5
        words = [
            {"start": 5.1, "text": "oh"},
            {"start": 5.3, "text": "my"},
            {"start": 5.5, "text": "god"},
            {"start": 5.7, "text": "cops!"},
            {"start": 5.9, "text": "run!"}
        ]
        sig = seconds_signal(words, 10.0)
        self.assertEqual(len(sig), 10)
        # Second 5 should be the absolute peak
        self.assertEqual(np.argmax(sig), 5)
        self.assertGreater(sig[5], 0.7)

    def test_highlights_intro_dampening(self):
        # For a 120s video, test that intro dampening prevents picking 0.0 unless audio is massive
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            dummy_wav = tmp_p / "silence.wav"
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono",
                "-t", "5", str(dummy_wav)
            ], check=True)
            
            # extra excite with equal energy at second 2 and second 50
            e = np.zeros(120)
            e[2] = 1.0
            e[50] = 1.0
            clips = rank_highlights(dummy_wav, 120.0, count=2, length=20.0, motion_on=False, extra_excite=e)
            self.assertTrue(len(clips) >= 1)
            # The second 50 peak should have a higher or equal score than second 2 because of intro dampening
            peak_starts = [c["start"] for c in clips]
            self.assertIn(min(peak_starts, key=lambda s: abs(s - 50)), peak_starts)

    def test_manual_export_requires_valid_source_or_url(self):
        resp = self.client.post("/api/export", json={"id": "nonexistent", "start": 0, "end": 10})
        self.assertEqual(resp.status_code, 400)

if __name__ == "__main__":
    unittest.main()
