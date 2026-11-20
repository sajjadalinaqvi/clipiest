"""Tests for Clipiest Re-Edit System."""
import unittest
import sys
import json
import tempfile
import shutil
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.rendering.reedit import CHANGE_KEYS, find_file, get_saved_words

class TestReEdit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_change_keys_validity(self):
        expected = {"layout", "top", "cam", "game", "caption_style", "caption_y", "captions", "hook", "title", "words"}
        self.assertEqual(CHANGE_KEYS, expected)

    def test_find_file(self):
        sub = self.test_dir / "my_video_1234"
        sub.mkdir()
        test_file = sub / "sample.mp4"
        test_file.write_text("dummy")
        
        found = find_file(self.test_dir, "sample.mp4")
        self.assertIsNotNone(found)
        self.assertEqual(found, test_file)

    def test_get_saved_words_from_record(self):
        record = {
            "settings": {
                "words": [
                    {"start": 0.0, "end": 0.5, "text": "Clipiest"},
                    {"start": 0.5, "end": 1.0, "text": "Engine"}
                ]
            }
        }
        words = get_saved_words(self.test_dir, "any_id", record)
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]["text"], "Clipiest")

if __name__ == "__main__":
    unittest.main()
