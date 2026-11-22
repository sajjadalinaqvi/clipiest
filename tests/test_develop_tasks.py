"""Unit tests for develop branch requirements:
1. English-only Whisper captions & rejection of Hindi captions.
2. Gameplay box whole-screen 16:9 fit in 9:16 layout without side cropping.
3. LLM timestamps output middle coverage, parsing timecodes, and scores >= 85.
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.audio.transcribe import youtube_words_from_info, transcribe_audio_segment
from clipiest.rendering.layouts import render_graph
from clipiest.ai.brain import find_viral_moments_ai, parse_timestamp, evaluate_moment, fallback_by_loudness

class TestDevelopRequirements(unittest.TestCase):
    
    # -------------------------------------------------------------
    # 1. English-only captions / Remove Hindi
    # -------------------------------------------------------------
    def test_youtube_captions_rejects_hindi(self):
        """Verifies that Hindi automatic captions or subtitles are rejected, only English accepted."""
        # Info dict with only Hindi captions
        info_hindi = {
            "automatic_captions": {
                "hi": [{"ext": "json3", "url": "https://example.com/hindi.json3"}],
                "hi-orig": [{"ext": "json3", "url": "https://example.com/hindi_orig.json3"}]
            },
            "subtitles": {}
        }
        words = youtube_words_from_info(info_hindi)
        self.assertIsNone(words, "Hindi captions must be rejected and return None")

    def test_youtube_captions_accepts_english(self):
        """Verifies that English tracks are accepted."""
        info_en = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "https://example.com/en.json3"}]
            },
            "subtitles": {}
        }
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"events": [{"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "Hello world"}]}]}'
            mock_url.return_value = mock_resp
            words = youtube_words_from_info(info_en)
            self.assertIsNotNone(words)
            self.assertEqual(words[0]["text"], "Hello")

    # -------------------------------------------------------------
    # 2. Gameplay box whole screen 16:9 fit in 9:16 layout
    # -------------------------------------------------------------
    def test_gameplay_box_whole_screen_fit(self):
        """When gameplay box is selected as whole screen, render_graph must use decrease+pad to fit full screen."""
        rects = [(0, 0, 480, 270), (0, 0, 1920, 1080)]
        # Whole screen gameplay
        graph = render_graph("stack", rects, top=0.32, is_whole_game=True)
        self.assertIn("force_original_aspect_ratio=decrease", graph)
        self.assertIn("pad=1080:", graph)

    def test_gameplay_box_tight_crop_fill(self):
        """When gameplay box is a small custom crop, render_graph uses increase+crop."""
        rects = [(0, 0, 480, 270), (500, 200, 400, 700)]
        graph = render_graph("stack", rects, top=0.32, is_whole_game=False)
        self.assertIn("force_original_aspect_ratio=increase,crop=1080:", graph)

    # -------------------------------------------------------------
    # 3. LLM timestamps: middle timestamps, timecode parsing, score >= 85
    # -------------------------------------------------------------
    def test_parse_timestamp_formats(self):
        """Verifies seconds, mm:ss, and hh:mm:ss parsing."""
        self.assertEqual(parse_timestamp(120.5), 120.5)
        self.assertEqual(parse_timestamp("120.5"), 120.5)
        self.assertEqual(parse_timestamp("02:30"), 150.0)
        self.assertEqual(parse_timestamp("01:10:05"), 4205.0)
        self.assertEqual(parse_timestamp("invalid", default=0.0), 0.0)

    def test_viral_moments_scores_always_above_or_equal_85(self):
        """Verifies all scouted moments strictly have scores >= 85."""
        words = []
        for t in range(0, 600, 4):
            words.append({"start": float(t), "end": float(t + 2.0), "text": "Exciting play!"})
        db = np.zeros(600)
        db[250:280] = 3.0  # Middle spike

        mock_llm_return = [
            {"start": "04:10", "end": "04:45", "score": 75, "hook": "MID CLUTCH", "title": "Middle Moment", "category": "clutch"},
            {"start": "01:00", "end": "01:30", "score": 82, "hook": "EARLY PLAY", "title": "Early Moment", "category": "hype"}
        ]
        with patch("clipiest.ai.brain.ask_llm", return_value=mock_llm_return):
            moments = find_viral_moments_ai(
                words=words,
                db=db,
                duration=600.0,
                title="Stream Test",
                max_clips=2
            )
            for m in moments:
                self.assertGreaterEqual(m["score"], 85, f"Moment score {m['score']} must be >= 85")

    def test_viral_moments_guarantees_middle_timestamps(self):
        """Verifies that for videos > 180s, middle timestamps (30%-70% of duration) are included."""
        duration = 1000.0
        words = []
        for t in range(0, int(duration), 5):
            words.append({"start": float(t), "end": float(t + 3.0), "text": "Talking about the game"})
        db = np.zeros(int(duration))

        # LLM returns start and end moments, but middle guarantee ensures a middle moment is included
        mock_moments = [
            {"start": 10.0, "end": 45.0, "score": 95, "hook": "START HOOK", "title": "Start Clip", "category": "funny"},
            {"start": 920.0, "end": 960.0, "score": 93, "hook": "END HOOK", "title": "End Clip", "category": "shock"}
        ]
        with patch("clipiest.ai.brain.ask_llm", return_value=mock_moments):
            moments = find_viral_moments_ai(
                words=words,
                db=db,
                duration=duration,
                title="Full Long Stream",
                max_clips=2
            )
            starts = [m["start"] for m in moments]
            has_middle = any(0.25 * duration <= s <= 0.75 * duration for s in starts)
            self.assertTrue(has_middle, f"Must have at least one middle timestamp. Starts: {starts}")

    def test_fallback_by_loudness_spaces_across_timeline_and_scores_above_85(self):
        """Verifies heuristic fallback also spaces across early, middle, and late, and scores >= 85."""
        duration = 800.0
        picks = fallback_by_loudness(np.zeros(int(duration)), words=[], count=4, min_len=20, max_len=45, duration=duration)
        self.assertEqual(len(picks), 4)
        for p in picks:
            self.assertGreaterEqual(p["score"], 85)
        starts = [p["start"] for p in picks]
        has_middle = any(0.25 * duration <= s <= 0.75 * duration for s in starts)
        self.assertTrue(has_middle, f"Picks must cover middle of timeline: {starts}")

if __name__ == "__main__":
    unittest.main()
