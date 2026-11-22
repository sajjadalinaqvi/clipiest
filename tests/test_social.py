"""Tests for Clipiest Social Media Accounts and Direct Publishing Engine."""
import unittest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient
from clipiest.server import app, DATA_DIR, is_protected_storage_file
from clipiest.social.accounts import ACCOUNTS_FILE, DEFAULT_SETTINGS, load_accounts_data, save_accounts_data

class TestSocialMediaIntegration(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.original_content = ACCOUNTS_FILE.read_text(encoding="utf-8") if ACCOUNTS_FILE.exists() else None

    def tearDown(self):
        if self.original_content:
            ACCOUNTS_FILE.write_text(self.original_content, encoding="utf-8")
        elif ACCOUNTS_FILE.exists():
            ACCOUNTS_FILE.unlink()

    def test_get_social_accounts(self):
        res = self.client.get("/api/social/accounts")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("youtube", data)
        self.assertIn("tiktok", data)
        self.assertIn("instagram", data)
        self.assertIn("defaults", data)
        self.assertIn("auto_shorts_tag", data["youtube"])
        self.assertIn("share_to_feed", data["instagram"])

    def test_save_and_disconnect_accounts(self):
        # 1. Save YouTube credentials
        res = self.client.post("/api/social/accounts", json={
            "platform": "youtube",
            "credentials": {
                "access_token": "ya29.sample_oauth_access_token_12345",
                "default_privacy": "unlisted",
                "auto_shorts_tag": True,
                "channel_title": "Clipiest Official"
            }
        })
        self.assertEqual(res.status_code, 200)
        accounts = res.json().get("accounts", {})
        yt = accounts.get("youtube", {})
        self.assertTrue(yt.get("connected"))
        self.assertEqual(yt.get("default_privacy"), "unlisted")
        self.assertTrue(yt.get("access_token").startswith("ya29"))
        self.assertIn("••••", yt.get("access_token"))  # Must be masked

        # 2. Test Connection endpoint
        test_res = self.client.post("/api/social/test", json={"platform": "youtube"})
        self.assertEqual(test_res.status_code, 200)
        self.assertIn("success", test_res.json())

        # 3. Disconnect YouTube
        dis_res = self.client.post("/api/social/disconnect", json={"platform": "youtube"})
        self.assertEqual(dis_res.status_code, 200)
        accounts_after = dis_res.json().get("accounts", {})
        self.assertFalse(accounts_after.get("youtube", {}).get("connected"))

    def test_publish_validation_and_flow(self):
        # Missing platforms should raise 400
        res = self.client.post("/api/social/publish", json={
            "clip_id": "test_clip",
            "platforms": []
        })
        self.assertEqual(res.status_code, 400)

        # Missing clip file should raise 404
        res2 = self.client.post("/api/social/publish", json={
            "clip_id": "non_existent_clip_xyz",
            "platforms": ["youtube"]
        })
        self.assertEqual(res2.status_code, 404)

        # Create dummy video file
        dummy_clip = DATA_DIR / "test_publish_clip.mp4"
        dummy_clip.write_bytes(b"dummy video bytes for test")
        try:
            pub_res = self.client.post("/api/social/publish", json={
                "file": "test_publish_clip.mp4",
                "platforms": ["youtube", "tiktok", "instagram"],
                "title": "Epic Clutch Moment",
                "description": "Creator loses his mind after winning clutch!",
                "tags": ["shorts", "gaming", "clutch"],
                "privacy": "public"
            })
            self.assertEqual(pub_res.status_code, 200)
            data = pub_res.json()
            self.assertTrue(data.get("success"))
            results = data.get("result", {}).get("platforms", {})
            self.assertIn("youtube", results)
            self.assertIn("tiktok", results)
            self.assertIn("instagram", results)
            self.assertTrue(results["youtube"].get("success"))
            self.assertTrue(results["tiktok"].get("success"))
            self.assertTrue(results["instagram"].get("success"))
        finally:
            dummy_clip.unlink(missing_ok=True)

    def test_social_accounts_file_protection(self):
        # 1. Protected Heuristic
        self.assertTrue(is_protected_storage_file(Path("social_accounts.json")))

        # 2. Never exposed in storage listing
        ACCOUNTS_FILE.write_text("{}", encoding="utf-8")
        files_res = self.client.get("/api/storage/files")
        self.assertEqual(files_res.status_code, 200)
        names = [f["name"] for f in files_res.json().get("files", [])]
        self.assertNotIn("social_accounts.json", names)

        # 3. Blocked from deletion
        del_res = self.client.post("/api/storage/delete", json={"path": "social_accounts.json"})
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json().get("deleted"), 0)
        self.assertTrue(ACCOUNTS_FILE.exists())

if __name__ == "__main__":
    unittest.main()
