"""Tests for YouTube cookies management, ANSI escape stripping, and age-restricted video preview fallbacks."""
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from clipiest.server import app, clean_error_message
from clipiest.config import COOKIES_FILE, get_cookies_file
from clipiest.vision.previews import extract_youtube_id, preview_video_url

client = TestClient(app)

class TestCookiesAndAgeGate(unittest.TestCase):
    def setUp(self):
        # Backup existing cookies.txt if any
        self.cookie_backup = None
        if COOKIES_FILE.exists():
            self.cookie_backup = COOKIES_FILE.read_bytes()
            COOKIES_FILE.unlink()

    def tearDown(self):
        # Restore cookies.txt if it was backed up
        if self.cookie_backup is not None:
            COOKIES_FILE.write_bytes(self.cookie_backup)
        elif COOKIES_FILE.exists():
            COOKIES_FILE.unlink()

    def test_extract_youtube_id(self):
        self.assertEqual(extract_youtube_id("https://www.youtube.com/watch?v=aPpZMvPcgAQ"), "aPpZMvPcgAQ")
        self.assertEqual(extract_youtube_id("https://youtu.be/aPpZMvPcgAQ"), "aPpZMvPcgAQ")
        self.assertEqual(extract_youtube_id("https://www.youtube.com/shorts/aPpZMvPcgAQ"), "aPpZMvPcgAQ")
        self.assertEqual(extract_youtube_id("aPpZMvPcgAQ"), "aPpZMvPcgAQ")
        self.assertIsNone(extract_youtube_id("https://twitch.tv/videos/12345"))

    def test_clean_error_message(self):
        ansi_err = Exception("\x1b[0;31mERROR:\x1b[0m [youtube] Some error occurred")
        cleaned = clean_error_message(ansi_err)
        self.assertNotIn("\x1b", cleaned)
        self.assertIn("[youtube] Some error occurred", cleaned)

        age_err = Exception("ERROR: [youtube] aPpZMvPcgAQ: Sign in to confirm your age. This video may be inappropriate for some users. Use --cookies-from-browser or --cookies for the authentication.")
        cleaned_age = clean_error_message(age_err)
        self.assertIn("age-restricted", cleaned_age.lower())
        self.assertIn("cookies.txt", cleaned_age)

    def test_cookies_lifecycle_api(self):
        # 1. Status without cookies
        resp = client.get("/api/cookies/status")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["configured"])

        # 2. Upload invalid extension
        bad_upload = client.post(
            "/api/cookies/upload",
            files={"file": ("cookies.json", b'{"key": "value"}', "application/json")}
        )
        self.assertEqual(bad_upload.status_code, 400)

        # 3. Upload valid cookies.txt
        cookie_content = b"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tLOGIN_INFO\taaa\n"
        good_upload = client.post(
            "/api/cookies/upload",
            files={"file": ("cookies.txt", cookie_content, "text/plain")}
        )
        self.assertEqual(good_upload.status_code, 200)
        self.assertTrue(good_upload.json()["success"])

        # 4. Status with cookies
        resp2 = client.get("/api/cookies/status")
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()["configured"])
        self.assertEqual(resp2.json()["size_bytes"], len(cookie_content))

        # 5. Delete cookies
        del_resp = client.delete("/api/cookies")
        self.assertEqual(del_resp.status_code, 200)

        # 6. Verify deleted
        resp3 = client.get("/api/cookies/status")
        self.assertEqual(resp3.status_code, 200)
        self.assertFalse(resp3.json()["configured"])

    @patch("clipiest.vision.previews.yt_dlp.YoutubeDL")
    def test_preview_video_url_age_restricted_fallback(self, mock_ydl_cls):
        # Simulate yt-dlp throwing YouTube age-gate error
        mock_instance = MagicMock()
        mock_instance.extract_info.side_effect = Exception(
            "ERROR: [youtube] aPpZMvPcgAQ: Sign in to confirm your age. This video may be inappropriate for some users. Use --cookies-from-browser or --cookies for the authentication."
        )
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance

        # Mock oembed & thumbnail fetching
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"title": "GTA 6 Official Gameplay", "author_name": "RockstarGames"}'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            data = preview_video_url("https://www.youtube.com/watch?v=aPpZMvPcgAQ")
            self.assertEqual(data["id"], "yt_aPpZMvPcgAQ")
            self.assertTrue(data.get("age_restricted"))
            self.assertIn("notice", data)
            self.assertEqual(data["title"], "GTA 6 Official Gameplay")

    @patch("clipiest.server.get_ytdl")
    def test_scout_moments_age_restricted_fallback(self, mock_get_ytdl):
        # Simulate yt-dlp throwing age-restricted error on scout
        mock_instance = MagicMock()
        mock_instance.extract_info.side_effect = Exception(
            "ERROR: [youtube] aPpZMvPcgAQ: Sign in to confirm your age. This video may be inappropriate for some users. Use --cookies-from-browser or --cookies for the authentication."
        )
        mock_get_ytdl.return_value.__enter__.return_value = mock_instance

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"title": "GTA 6 Official Gameplay", "author_name": "RockstarGames"}'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            resp = client.post("/api/moments/scout", json={
                "url": "https://www.youtube.com/watch?v=aPpZMvPcgAQ",
                "count": 3,
                "min_len": 30,
                "max_len": 60
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("success"))
            self.assertGreaterEqual(len(data.get("moments", [])), 1)

if __name__ == "__main__":
    unittest.main()
