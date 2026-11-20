import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import json
from fastapi.testclient import TestClient
from PIL import Image

from clipiest.server import app
from clipiest.vision.previews import preview_video_url
from clipiest.vision.facecam import detect_facecam

class TestUrlPreview(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_preview_url_empty_fails(self):
        resp = self.client.post("/api/preview/url", json={"url": ""})
        self.assertEqual(resp.status_code, 400)

    @patch("clipiest.vision.previews.yt_dlp.YoutubeDL")
    def test_preview_video_url_mocked(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "id": "mock123",
            "title": "GTA 6 Gameplay - Escaping 6 Stars",
            "uploader": "Gamer123",
            "duration": 185.0,
            "thumbnail": "https://example.com/thumb.jpg"
        }

        # Mock urllib request to return a simple 1280x720 dummy image
        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_img = Image.new("RGB", (1280, 720), color=(100, 150, 200))
            
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                import io
                buf = io.BytesIO()
                dummy_img.save(buf, format="JPEG")
                mock_resp.read.return_value = buf.getvalue()
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                data = preview_video_url("https://www.youtube.com/watch?v=mock123")
                self.assertEqual(data["id"], "yt_mock123")
                self.assertEqual(data["title"], "GTA 6 Gameplay - Escaping 6 Stars")
                self.assertEqual(data["duration"], 185.0)
                self.assertEqual(data["w"], 1280)
                self.assertEqual(data["h"], 720)
                self.assertTrue(len(data["frames"]) >= 1)

    def test_facecam_from_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            # Create 4 dummy frames
            frames = []
            for i in range(4):
                img = Image.new("RGB", (640, 360), color=(i * 30, i * 30, i * 30))
                p = tmp_p / f"frame_{i}.jpg"
                img.save(p)
                frames.append(p)

            res = detect_facecam(frames)
            self.assertIn("detected", res)
            self.assertIn("confidence", res)
            self.assertIsInstance(res["confidence"], (float, int))

if __name__ == "__main__":
    unittest.main()
