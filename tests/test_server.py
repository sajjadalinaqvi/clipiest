"""Tests for Clipiest FastAPI Server Endpoints."""
import unittest
import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest.server import app

class TestServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_root_serves_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))

    def test_layouts_endpoint(self):
        res = self.client.get("/api/layouts")
        self.assertEqual(res.status_code, 200)
        layouts = res.json()
        self.assertEqual(len(layouts), 11)
        layout_ids = [l["id"] for l in layouts]
        self.assertIn("stack", layout_ids)
        self.assertIn("circle", layout_ids)
        self.assertIn("blur", layout_ids)

    def test_caption_styles_endpoint(self):
        res = self.client.get("/api/caption-styles")
        self.assertEqual(res.status_code, 200)
        styles = res.json()
        self.assertGreaterEqual(len(styles), 7)
        style_ids = [s["id"] for s in styles]
        self.assertIn("bounce", style_ids)
        self.assertIn("hype", style_ids)
        self.assertIn("mrbeast", style_ids)

    def test_telemetry_endpoint(self):
        res = self.client.get("/api/telemetry")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("cpu_percent", data)
        self.assertIn("hardware", data)
        self.assertIn("disk", data)

    def test_ai_providers_endpoint(self):
        res = self.client.get("/api/ai/providers")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("providers", data)
        self.assertIn("gemini", data["providers"])

    def test_library_endpoint(self):
        res = self.client.get("/api/library")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

if __name__ == "__main__":
    unittest.main()
