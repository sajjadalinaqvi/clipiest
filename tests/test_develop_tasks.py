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
from clipiest.storage.manager import is_protected_storage_file, cleanup_on_shutdown
import tempfile
import shutil
import asyncio

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
    # 2. Gameplay box left-to-right fit & 3 background options (default, black, white)
    # -------------------------------------------------------------
    def test_gameplay_box_left_to_right_fit(self):
        """Gameplay box (e.g. 1280x620) fits from left to right under facecam without affecting facecam size."""
        rects = [(0, 0, 480, 270), (0, 0, 1280, 620)]
        graph = render_graph("stack", rects, top=0.32, background="default")
        # Facecam size is untouched (fills its camera slot 1080x614)
        self.assertIn("crop=1080:614", graph)
        # Gameplay fits left-to-right with decrease, preserving aspect ratio
        self.assertIn("force_original_aspect_ratio=decrease", graph)
        self.assertIn("(1080-w)/2", graph)

    def test_background_options(self):
        """Verifies default (blurred video), black, and white background filter complex generation."""
        rects = [(0, 0, 480, 270), (0, 0, 1280, 620)]
        graph_default = render_graph("stack", rects, top=0.32, background="default")
        self.assertIn("boxblur=", graph_default)

        graph_black = render_graph("stack", rects, top=0.32, background="black")
        self.assertIn("color=black", graph_black)

        graph_white = render_graph("stack", rects, top=0.32, background="white")
        self.assertIn("color=white", graph_white)

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

    # -------------------------------------------------------------
    # 4. Server shutdown cleanup & storage protection
    # -------------------------------------------------------------
    def test_is_protected_storage_file(self):
        """Verifies that sensitive configurations, whisper models, and creator profiles are protected."""
        self.assertTrue(is_protected_storage_file(Path("config.json")))
        self.assertTrue(is_protected_storage_file(Path("cookies.txt")))
        self.assertTrue(is_protected_storage_file(Path("weights.json")))
        self.assertTrue(is_protected_storage_file(Path("feedback.jsonl")))
        self.assertTrue(is_protected_storage_file(Path("social_accounts.json")))
        self.assertTrue(is_protected_storage_file(Path("models/faster-whisper/model.bin")))
        self.assertTrue(is_protected_storage_file(Path(".git/config")))
        self.assertTrue(is_protected_storage_file(Path("creators/creators.json")))
        self.assertTrue(is_protected_storage_file(Path("creators/ninja/profile.json")))
        self.assertTrue(is_protected_storage_file(Path("secret.env")))
        self.assertTrue(is_protected_storage_file(Path("script.py")))

        # Disposable clipping artifacts must NOT be protected
        self.assertFalse(is_protected_storage_file(Path("exports/clip1.mp4")))
        self.assertFalse(is_protected_storage_file(Path("slices/slice_1.json")))
        self.assertFalse(is_protected_storage_file(Path("slices/slice_1_words.json")))
        self.assertFalse(is_protected_storage_file(Path("exports/clip1.ass")))
        self.assertFalse(is_protected_storage_file(Path("exports/clip1.srt")))
        self.assertFalse(is_protected_storage_file(Path("frame_0.jpg")))

    def test_cleanup_on_shutdown_purges_clipping_data_and_protects_configs(self):
        """Verifies that cleanup_on_shutdown wipes clipped videos, downloads, thumbnails, json, and ass files,
        while strictly keeping Whisper models and config files intact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_data = Path(temp_dir) / "data"
            temp_dl = Path(temp_dir) / "Downloads"
            temp_data.mkdir(parents=True)
            temp_dl.mkdir(parents=True)

            # 1. Create protected files
            (temp_data / "config.json").write_text("{}", encoding="utf-8")
            (temp_data / "cookies.txt").write_text("# Netscape HTTP Cookie File", encoding="utf-8")
            (temp_data / "weights.json").write_text("{}", encoding="utf-8")
            (temp_data / "social_accounts.json").write_text("{}", encoding="utf-8")
            (temp_data / "feedback.jsonl").write_text("", encoding="utf-8")
            models_dir = temp_data / "models" / "faster-whisper-small"
            models_dir.mkdir(parents=True)
            (models_dir / "model.bin").write_bytes(b"dummy_whisper_weights")
            creator_dir = temp_data / "creators" / "streamer1"
            creator_dir.mkdir(parents=True)
            (creator_dir / "profile.json").write_text('{"name": "Streamer"}', encoding="utf-8")
            (temp_data / "creators" / "creators.json").write_text("[]", encoding="utf-8")

            # 2. Create disposable files to be purged
            exports_dir = temp_data / "exports"
            exports_dir.mkdir(parents=True)
            (exports_dir / "clip1.mp4").write_bytes(b"video_bytes")
            (exports_dir / "clip1.ass").write_text("[Script Info]", encoding="utf-8")
            (exports_dir / "clip1.srt").write_text("1\n00:00:00 --> 00:00:02\nHi", encoding="utf-8")
            (exports_dir / "clip1.json").write_text("{}", encoding="utf-8")
            (exports_dir / "clip1.jpg").write_bytes(b"thumbnail_bytes")

            slices_dir = temp_data / "slices"
            slices_dir.mkdir(parents=True)
            (slices_dir / "slice_01.mp4").write_bytes(b"slice_bytes")
            (slices_dir / "slice_01.json").write_text("{}", encoding="utf-8")
            (slices_dir / "slice_01_words.json").write_text("[]", encoding="utf-8")
            (slices_dir / "slice_01_preview.jpg").write_bytes(b"jpg_bytes")

            tmp_dir = temp_data / "tmp" / "frames"
            tmp_dir.mkdir(parents=True)
            (tmp_dir / "frame_0.jpg").write_bytes(b"frame_bytes")
            (temp_data / "tmp" / "temp.wav").write_bytes(b"audio_bytes")

            yt_cache = temp_data / "yt_test123"
            yt_cache.mkdir(parents=True)
            (yt_cache / "frame_0.jpg").write_bytes(b"frame_bytes")
            (yt_cache / "source.json").write_text("{}", encoding="utf-8")

            creator_clips = creator_dir / "clips"
            creator_clips.mkdir(parents=True)
            (creator_clips / "c1.mp4").write_bytes(b"creator_clip")
            creator_videos = creator_dir / "videos"
            creator_videos.mkdir(parents=True)
            (creator_videos / "v1.mp4").write_bytes(b"creator_raw_video")

            # Loose files in data
            (temp_data / "loose_clip.mp4").write_bytes(b"loose_video")
            (temp_data / "loose_sub.ass").write_text("sub", encoding="utf-8")

            # Downloads folder
            (temp_dl / "downloaded_clip.mp4").write_bytes(b"downloaded_video")

            # Execute shutdown cleanup
            result = cleanup_on_shutdown(data_dir=temp_data, downloads_dir=temp_dl)
            self.assertGreater(result["deleted_files"], 0)

            # Check that disposable files are completely gone
            self.assertFalse((exports_dir / "clip1.mp4").exists())
            self.assertFalse((exports_dir / "clip1.ass").exists())
            self.assertFalse((exports_dir / "clip1.srt").exists())
            self.assertFalse((exports_dir / "clip1.json").exists())
            self.assertFalse((exports_dir / "clip1.jpg").exists())
            self.assertFalse((slices_dir / "slice_01.mp4").exists())
            self.assertFalse((slices_dir / "slice_01.json").exists())
            self.assertFalse((slices_dir / "slice_01_words.json").exists())
            self.assertFalse((slices_dir / "slice_01_preview.jpg").exists())
            self.assertFalse((temp_data / "tmp" / "temp.wav").exists())
            self.assertFalse(yt_cache.exists())
            self.assertFalse((creator_clips / "c1.mp4").exists())
            self.assertFalse((creator_videos / "v1.mp4").exists())
            self.assertFalse((temp_data / "loose_clip.mp4").exists())
            self.assertFalse((temp_data / "loose_sub.ass").exists())
            self.assertFalse((temp_dl / "downloaded_clip.mp4").exists())

            # Check that protected configs and whisper models are 100% intact
            self.assertTrue((temp_data / "config.json").exists())
            self.assertTrue((temp_data / "cookies.txt").exists())
            self.assertTrue((temp_data / "weights.json").exists())
            self.assertTrue((temp_data / "social_accounts.json").exists())
            self.assertTrue((temp_data / "feedback.jsonl").exists())
            self.assertTrue((models_dir / "model.bin").exists())
            self.assertTrue((temp_data / "creators" / "creators.json").exists())
            self.assertTrue((creator_dir / "profile.json").exists())

    def test_server_lifespan_calls_cleanup_on_shutdown(self):
        """Verifies that FastAPI lifespan triggers cleanup_on_shutdown upon exit."""
        from clipiest.server import lifespan, app
        with patch("clipiest.server.cleanup_on_shutdown") as mock_cleanup:
            async def run_cycle():
                async with lifespan(app):
                    pass
            asyncio.run(run_cycle())
            mock_cleanup.assert_called_once()

    # -------------------------------------------------------------
    # 5. Interactive 9:16 Preview: Caption Y centering & Hook (X, Y, Size)
    # -------------------------------------------------------------
    def test_hook_custom_placement_and_size_in_subtitles(self):
        """Verifies that hook x, y, and size are correctly embedded into ASS subtitle events."""
        from clipiest.rendering.captions import write_subtitles
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            write_subtitles(
                words=[{"start": 0.5, "end": 1.5, "text": "Testing", "clean": "Testing"}],
                style_key="bounce",
                out_dir=out_dir,
                name="test_hook",
                caption_y=1400,
                hook="EPIC VICTORY",
                hook_y=350,
                hook_x=420,
                hook_size=95
            )
            out_p = out_dir / "test_hook.ass"
            content = out_p.read_text(encoding="utf-8")
            self.assertIn("\\pos(420,350)", content)
            self.assertIn("\\fs95", content)
            self.assertIn("EPIC VICTORY", content)

    def test_caption_y_vertical_adjustment_centered(self):
        """Verifies that caption is always aligned to horizontal center (X=540) while Y is custom."""
        from clipiest.rendering.captions import write_subtitles
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            write_subtitles(
                words=[{"start": 0.5, "end": 1.5, "text": "Centered", "clean": "Centered"}],
                style_key="karaoke",
                out_dir=out_dir,
                name="test_cap",
                caption_y=1550,
                hook="",
            )
            out_p = out_dir / "test_cap.ass"
            content = out_p.read_text(encoding="utf-8")
            self.assertIn("\\pos(540,1550)", content)

if __name__ == "__main__":
    unittest.main()
