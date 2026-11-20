import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from clipiest.ai.brain import find_viral_moments_ai
from clipiest.server import api_llm_ping

class TestMomentScoutOptimization(unittest.TestCase):
    def test_viral_moments_scout_caps_llm_queries_on_long_video(self):
        """Verifies that a 2-hour video (7544s) does not execute 10 sequential window queries, but caps at 1-2."""
        words = []
        # Generate 2 hours of synthetic words
        for t in range(0, 7200, 5):
            words.append({
                "start": float(t),
                "end": float(t + 2.5),
                "text": "Crazy clutch play right here!" if t % 60 == 0 else "hello world"
            })
        db = np.zeros(7200)
        # Add excitement spikes at specific seconds
        db[500:530] = 3.5
        db[3600:3630] = 4.0

        mock_moments = [
            {
                "start": 502.0,
                "end": 535.0,
                "score": 92,
                "hook": "NO WAY HE CLUTCHED",
                "title": "Insane Clutch",
                "category": "clutch"
            },
            {
                "start": 3605.0,
                "end": 3638.0,
                "score": 90,
                "hook": "WHAT A SHOT",
                "title": "Shocking Play",
                "category": "action"
            }
        ]

        query_counts = [0]
        def fake_ask_llm(prompt, *args, **kwargs):
            query_counts[0] += 1
            if "max_tokens" in kwargs:
                self.assertLessEqual(kwargs["max_tokens"], 1024)
            return mock_moments

        with patch("clipiest.ai.brain.ask_llm", side_effect=fake_ask_llm):
            moments = find_viral_moments_ai(
                words=words,
                db=db,
                duration=7544.0,
                title="Epic Stream GTA 6",
                uploader="ProGamer",
                max_clips=2,
                min_len=25.0,
                max_len=60.0
            )

            # Crucial assertion: Must NOT run 10 window queries; early break on max_clips satisfied
            self.assertEqual(query_counts[0], 1)
            self.assertGreaterEqual(len(moments), 2)
            self.assertEqual(moments[0]["hook"], "NO WAY HE CLUTCHED")

    def test_llm_ping_endpoint_returns_dict(self):
        """Verifies /api/llm/ping executes without generating tokens or crashing."""
        with patch("clipiest.server.fetch_models_with_url", return_value=(["qwen/qwen3.5-9b"], "http://localhost:1235/v1")):
            res = api_llm_ping()
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("models_count"), 1)

    def test_hook_stays_on_screen_whole_clip(self):
        """Verifies hook is active across the entire clip duration instead of vanishing after 3s."""
        import tempfile
        from pathlib import Path
        from clipiest.rendering.captions import write_subtitles

        with tempfile.TemporaryDirectory() as td:
            out_p = Path(td)
            ass_fn, _ = write_subtitles(
                words=[{"start": 0.0, "end": 2.0, "text": "Hello"}],
                style_key="bounce",
                out_dir=out_p,
                name="test_whole_hook",
                hook="TEST HOOK ON SCREEN",
                duration=45.0
            )
            content = (out_p / ass_fn).read_text(encoding="utf-8")
            # Hook dialogue line should show end time 0:00:45.00
            self.assertIn("Dialogue: 2,0:00:00.00,0:00:45.00,Hook", content)
            self.assertIn(r"\fad(150,0)", content)

if __name__ == "__main__":
    unittest.main()
