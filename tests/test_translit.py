"""Tests for Clipiest Universal Transliteration."""
import unittest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.rendering.translit import to_roman, devanagari_to_hinglish

class TestTransliteration(unittest.TestCase):
    def test_devanagari_common_words(self):
        """Tests common Hindi words to Hinglish transliteration."""
        self.assertEqual(to_roman("नमस्ते"), "namaste")
        self.assertEqual(to_roman("भाई"), "bhai")
        self.assertEqual(to_roman("क्या"), "kya")
        self.assertEqual(to_roman("हाँ"), "haan")
        self.assertEqual(to_roman("नहीं"), "nahin")

    def test_devanagari_full_sentence(self):
        """Tests complex Devanagari sentence."""
        sentence = "यह बहुत ही शानदार खेल है"
        roman = to_roman(sentence)
        self.assertIn("yeh", roman)
        self.assertIn("bahut", roman)
        self.assertIn("khel", roman)

    def test_cyrillic_transliteration(self):
        """Tests Russian / Ukrainian Cyrillic to Latin."""
        self.assertEqual(to_roman("Привет мир"), "Privet mir")
        self.assertEqual(to_roman("Хорошо"), "Khorosho")

    def test_greek_transliteration(self):
        """Tests Greek to Latin."""
        self.assertEqual(to_roman("Καλημέρα"), "Kalimera")

    def test_english_passthrough(self):
        """Tests that pure English / Latin text remains unaltered."""
        text = "Hello world! What an incredible clutch by S8UL!"
        self.assertEqual(to_roman(text), text)

if __name__ == "__main__":
    unittest.main()
