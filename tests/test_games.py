"""Tests for Clipiest Game Detection and Viral Hashtags."""
import unittest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.ai.games import detect_game

class TestGameDetection(unittest.TestCase):
    def test_gta_detection(self):
        game, tags = detect_game("GTA 5 Thug Life Moments #shorts", "Techno Gamerz")
        self.assertEqual(game, "Grand Theft Auto V")
        self.assertIn("GTA5", tags)
        self.assertIn("GTAOnline", tags)

    def test_bgmi_detection(self):
        game, tags = detect_game("Mortal 1v4 clutch in BGMI tournament", "Mortal")
        self.assertEqual(game, "BGMI")
        self.assertIn("BGMI", tags)
        self.assertIn("BattlegroundsMobileIndia", tags)

    def test_valorant_detection(self):
        game, tags = detect_game("Radiant Ace with Jett on Ascent", "TenZ")
        self.assertEqual(game, "Valorant")
        self.assertIn("Valorant", tags)

    def test_minecraft_detection(self):
        game, tags = detect_game("100 Days Hardcore Survival Minecraft", "Mythpat")
        self.assertEqual(game, "Minecraft")
        self.assertIn("Minecraft", tags)

    def test_generic_title(self):
        game, tags = detect_game("Funny IRL moments in Mumbai vlog", "Flying Beast")
        self.assertIsNone(game)
        self.assertIn("ViralShorts", tags)

if __name__ == "__main__":
    unittest.main()
