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

    def test_config_endpoints(self):
        # 1. GET /api/config
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        cfg = res.json()
        self.assertIn("whisper_models", cfg)
        self.assertIn("providers", cfg)
        self.assertIn("lmstudio", cfg["providers"])

        # 2. POST /api/config
        update_payload = {
            "ai": {
                "provider": "lmstudio",
                "base_url": "http://127.0.0.1:1234/v1",
                "api_key": "",
                "model": "meta-llama-3.1-8b-instruct"
            },
            "whisper": {
                "model": "small"
            }
        }
        res_post = self.client.post("/api/config", json=update_payload)
        self.assertEqual(res_post.status_code, 200)
        resp_data = res_post.json()
        self.assertTrue(resp_data.get("success"))
        self.assertEqual(resp_data["config"]["ai"]["provider"], "lmstudio")
        self.assertEqual(resp_data["config"]["whisper"]["model"], "small")

    def test_llm_test_endpoint(self):
        res = self.client.post("/api/llm/test", json={
            "provider": "lmstudio",
            "base_url": "http://127.0.0.1:99999/invalid",
            "api_key": "",
            "model": "fake-model"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data.get("ok"))
        self.assertIn("error", data)

    def test_llm_models_endpoint(self):
        res = self.client.get("/api/llm/models?provider=ollama&base_url=http://127.0.0.1:99999")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["provider"], "ollama")
        self.assertIsInstance(data["models"], list)

    def test_hook_styles_endpoint(self):
        res = self.client.get("/api/hook-styles")
        self.assertEqual(res.status_code, 200)
        styles = res.json()
        self.assertGreaterEqual(len(styles), 6)
        ids = [s["id"] for s in styles]
        self.assertIn("banner", ids)
        self.assertIn("punch", ids)
        self.assertIn("neon", ids)
        self.assertIn("fire", ids)
        self.assertIn("comic", ids)
        self.assertIn("minimal", ids)

    def test_storage_endpoints(self):
        from clipiest.config import DATA_DIR
        test_file = DATA_DIR / "test_dummy.txt"
        test_file.write_text("dummy test content", encoding="utf-8")

        # 1. GET /api/storage/files
        res = self.client.get("/api/storage/files")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("files", data)
        self.assertIn("total", data)
        file_names = [f["name"] for f in data["files"]]
        self.assertIn("test_dummy.txt", file_names)

        # 2. POST /api/storage/delete
        del_res = self.client.post("/api/storage/delete", json={"path": "test_dummy.txt"})
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json().get("success"))
        self.assertFalse(test_file.exists())

        # 3. POST /api/storage/clean-tmp
        clean_res = self.client.post("/api/storage/clean-tmp")
        self.assertEqual(clean_res.status_code, 200)
        self.assertTrue(clean_res.json().get("success"))

    def test_preview_frame_fallback(self):
        res = self.client.get("/api/preview/frame?sec=5.0")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "image/jpeg")

if __name__ == "__main__":
    unittest.main()
