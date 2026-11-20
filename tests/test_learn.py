"""Tests for Clipiest Self-Learning Ridge Regression."""
import unittest
import sys
import tempfile
import shutil
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.ai.learn import (
    load_weights, compute_rank_score, record_feedback, DEFAULT_WEIGHTS
)

class TestLearn(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_weights(self):
        weights = load_weights(self.test_dir)
        self.assertEqual(weights, DEFAULT_WEIGHTS)

    def test_compute_rank_score(self):
        feats = {
            "loudness": 0.8,
            "shout": 0.7,
            "lexical": 0.9,
            "motion": 0.6,
            "llm": 0.85
        }
        score = compute_rank_score(feats, DEFAULT_WEIGHTS)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_record_feedback_update(self):
        feats = {"loudness": 0.9, "shout": 0.8, "lexical": 0.7, "motion": 0.5, "llm": 0.9}
        # Record 5 ratings
        for i in range(5):
            res = record_feedback(self.test_dir, f"clip_{i}", 5, feats)
        self.assertIsInstance(res, dict)
        self.assertIn("weights", res)
        self.assertIn("loud", res["weights"])

if __name__ == "__main__":
    unittest.main()
