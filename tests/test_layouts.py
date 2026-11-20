"""Tests for Clipiest 11 Layouts and Geometry Calculations."""
import unittest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.rendering.layouts import (
    CATALOG, LAYOUT_IDS, geometry, text_positions, render_graph
)

class TestLayouts(unittest.TestCase):
    def test_catalog_completeness(self):
        """Verifies all 11 layouts exist in the catalog."""
        self.assertEqual(len(CATALOG), 11)
        self.assertEqual(len(LAYOUT_IDS), 11)
        expected = {"stack", "bottom", "blur", "fill", "game", "pip_tl", "pip_tr", "pip_bl", "pip_br", "circle", "side"}
        self.assertEqual(LAYOUT_IDS, expected)

    def test_geometry_bounds(self):
        """Ensures all layout layers stay within 1080x1920 boundaries."""
        sample_tops = [0.20, 0.32, 0.40, 0.50]
        for top in sample_tops:
            for lid in LAYOUT_IDS:
                geom = geometry(lid, top)
                self.assertIn("mode", geom)
                if geom["mode"] == "blur":
                    continue
                self.assertIn("layers", geom)
                for layer in geom["layers"]:
                    x, y, w, h = layer["x"], layer["y"], layer["w"], layer["h"]
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, 1080, f"Layer exceeds width in layout {lid}")
                    self.assertLessEqual(y + h, 1920, f"Layer exceeds height in layout {lid}")
                    self.assertIn(layer["source"], ("cam", "game", "full"))

    def test_text_positions(self):
        """Ensures safe caption positions are within platform safe guidelines."""
        for lid in LAYOUT_IDS:
            pos = text_positions(lid, 0.32)
            self.assertIn("caption_y", pos)
            self.assertIn("hook_y", pos)
            self.assertGreaterEqual(pos["caption_y"], 500)
            self.assertLessEqual(pos["caption_y"], 1750)
            self.assertGreaterEqual(pos["hook_y"], 60)
            self.assertLessEqual(pos["hook_y"], 1000)

    def test_render_graph_generation(self):
        """Verifies filtergraph strings are generated without syntax errors."""
        rects = [(0, 0, 480, 270), (0, 0, 1920, 1080)]
        for lid in LAYOUT_IDS:
            graph = render_graph(lid, rects, 0.32)
            self.assertIsInstance(graph, str)
            self.assertIn("[base]", graph)
            if lid == "circle":
                self.assertIn("geq=r=", graph)

if __name__ == "__main__":
    unittest.main()
