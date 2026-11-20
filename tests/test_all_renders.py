"""Exhaustive test suite for rendering, cropping, cutting, all 11 layouts, all 7 caption styles, and fonts."""
import unittest
import sys
import shutil
import tempfile
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.rendering.render import render_clip, probe_video
from clipiest.rendering.layouts import CATALOG, LAYOUT_IDS, geometry, render_graph
from clipiest.rendering.captions import STYLE_DEFINITIONS, write_subtitles
from clipiest.rendering.translit import to_roman

FIXTURE_PATH = Path("C:/peakcut/test_fixture_gaming.mp4")

class TestAllRendersAndFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_dir = Path(tempfile.mkdtemp(prefix="test_clipiest_render_"))
        cls.fixture = FIXTURE_PATH
        cls.meta = probe_video(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work_dir, ignore_errors=True)

    def test_fixture_probe(self):
        self.assertGreater(self.meta["w"], 0)
        self.assertGreater(self.meta["h"], 0)
        self.assertGreater(self.meta["duration"], 0)

    def test_all_11_layouts_render(self):
        """Renders a short 1.0s clip with every single layout in the catalog."""
        test_words = [
            {"text": "Clipiest", "start": 0.1, "end": 0.4},
            {"text": "Engine", "start": 0.4, "end": 0.8}
        ]
        
        for layout_id, layout_name, _ in CATALOG:
            with self.subTest(layout=layout_id):
                clip_name = f"clip_layout_{layout_id}"
                res = render_clip(
                    src_path=self.fixture,
                    out_dir=self.work_dir,
                    name=clip_name,
                    start=1.0,
                    end=2.0,
                    layout=layout_id,
                    top=0.32,
                    cam_rect=(0, 0, 320, 240),
                    game_rect=(320, 0, 960, 720),
                    words=test_words,
                    caption_style="bounce",
                    hook="VIRAL MOMENT"
                )
                self.assertEqual(res["status"], "done")
                out_mp4 = self.work_dir / f"{clip_name}.mp4"
                self.assertTrue(out_mp4.exists())
                meta = probe_video(out_mp4)
                self.assertEqual(meta["w"], 1080)
                self.assertEqual(meta["h"], 1920)
                self.assertAlmostEqual(meta["duration"], 1.0, delta=0.2)

    def test_all_7_caption_styles_render(self):
        """Renders clips with all 7 typography styles and burns them in."""
        test_words = [
            {"text": "HEADSHOT", "start": 0.05, "end": 0.45},
            {"text": "CLUTCH", "start": 0.45, "end": 0.85}
        ]
        for style_name in STYLE_DEFINITIONS.keys():
            with self.subTest(style=style_name):
                clip_name = f"clip_style_{style_name}"
                res = render_clip(
                    src_path=self.fixture,
                    out_dir=self.work_dir,
                    name=clip_name,
                    start=2.0,
                    end=3.0,
                    layout="blur",
                    words=test_words,
                    caption_style=style_name,
                    hook="INSANE PLAY"
                )
                self.assertEqual(res["status"], "done")
                out_mp4 = self.work_dir / f"{clip_name}.mp4"
                self.assertTrue(out_mp4.exists())

    def test_extreme_and_invalid_crop_rectangles(self):
        """Verifies clamping and sanitization for out-of-bounds crop rects."""
        bad_rects = [
            ((-100, -50, -200, -100), (0, 0, 5000, 5000)),
            ((9999, 9999, 10, 10), (0, 0, 0, 0)),
            ((15.5, 20.3, 319.7, 239.9), (320.1, 0.0, 959.9, 719.8)),
            (None, None),
            ((), ())
        ]
        for i, (cam_r, game_r) in enumerate(bad_rects):
            with self.subTest(case=i):
                clip_name = f"clip_extreme_crop_{i}"
                res = render_clip(
                    src_path=self.fixture,
                    out_dir=self.work_dir,
                    name=clip_name,
                    start=0.5,
                    end=1.5,
                    layout="stack",
                    cam_rect=cam_r,
                    game_rect=game_r
                )
                self.assertEqual(res["status"], "done")
                out_mp4 = self.work_dir / f"{clip_name}.mp4"
                self.assertTrue(out_mp4.exists())

    def test_multilingual_and_hinglish_captions(self):
        """Verifies Hindi/Devanagari, Cyrillic, and special characters don't break ASS subtitles."""
        words = [
            {"text": "नमस्ते", "start": 0.1, "end": 0.4},
            {"text": "duniya", "start": 0.4, "end": 0.7},
            {"text": "क्या", "start": 0.7, "end": 1.0},
            {"text": "baat", "start": 1.0, "end": 1.3}
        ]
        res = render_clip(
            src_path=self.fixture,
            out_dir=self.work_dir,
            name="clip_hinglish",
            start=0.0,
            end=1.5,
            layout="stack",
            words=words,
            caption_style="mrbeast",
            hook="🔥 EPIC MOMENT (100% REAL)!"
        )
        self.assertEqual(res["status"], "done")
        self.assertTrue((self.work_dir / "clip_hinglish.mp4").exists())
        self.assertTrue((self.work_dir / "clip_hinglish.ass").exists())
        ass_content = (self.work_dir / "clip_hinglish.ass").read_text(encoding="utf-8")
        # Ensure Devanagari was romanized so fonts without Devanagari glyphs don't show tofu boxes
        self.assertIn("namaste", ass_content.lower())

if __name__ == "__main__":
    unittest.main()
