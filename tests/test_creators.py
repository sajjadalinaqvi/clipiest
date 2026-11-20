"""Tests for Clipiest Content Creator Workspaces module and endpoints."""
import unittest
import sys
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from clipiest import creators
from clipiest.server import app
from clipiest.config import DATA_DIR

class TestCreatorsModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_cid = "test-ninja-unit"

    def tearDown(self):
        # Clean up any test creators created
        c_root = creators.CREATORS_DIR / self.test_cid
        if c_root.exists():
            shutil.rmtree(c_root, ignore_errors=True)

    def test_create_and_get_creator(self):
        created = creators.create_creator({
            "name": "Test Ninja Unit",
            "channel": "https://youtube.com/@ninja",
            "default_layout": "stack",
            "default_caption_style": "mrbeast",
            "game": "Fortnite"
        })
        self.assertIn("id", created)
        cid = created["id"]
        
        # Verify folder structure on disk
        c_root = creators.creator_root(cid)
        self.assertTrue(c_root.exists())
        self.assertTrue((c_root / "videos").exists())
        self.assertTrue((c_root / "clips").exists())
        self.assertTrue((c_root / "creator.json").exists())
        self.assertTrue((c_root / "log.jsonl").exists())

        # Verify get_creator
        fetched = creators.get_creator(cid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Test Ninja Unit")
        self.assertEqual(fetched["default_caption_style"], "mrbeast")
        self.assertEqual(fetched["game"], "Fortnite")

        # Verify list_creators includes it
        all_c = creators.list_creators()
        self.assertIn(cid, [c["id"] for c in all_c])

        # Verify update_creator
        updated = creators.update_creator(cid, {"game": "Apex Legends", "min_len": 20})
        self.assertEqual(updated["game"], "Apex Legends")
        self.assertEqual(updated["min_len"], 20)

        # Verify logging
        creators.log_creator_event(cid, "Tested custom log event", action="test")
        logs = creators.get_creator_logs(cid)
        self.assertGreaterEqual(len(logs), 2)
        self.assertEqual(logs[0]["action"], "test")

        # Verify delete_creator
        ok = creators.delete_creator(cid)
        self.assertTrue(ok)
        self.assertFalse(c_root.exists())
        self.assertIsNone(creators.get_creator(cid))

    def test_creator_api_endpoints(self):
        # 1. POST /api/creators
        payload = {
            "name": "Test Streamer API",
            "channel": "https://twitch.tv/teststreamer",
            "default_layout": "blur",
            "default_caption_style": "hype",
            "game": "Valorant"
        }
        res = self.client.post("/api/creators", json=payload)
        self.assertEqual(res.status_code, 200)
        c_data = res.json()
        cid = c_data["id"]
        self.assertEqual(c_data["name"], "Test Streamer API")

        try:
            # 2. GET /api/creators
            res_list = self.client.get("/api/creators")
            self.assertEqual(res_list.status_code, 200)
            self.assertIn(cid, [c["id"] for c in res_list.json()])

            # 3. GET /api/creators/{cid}
            res_get = self.client.get(f"/api/creators/{cid}")
            self.assertEqual(res_get.status_code, 200)
            self.assertEqual(res_get.json()["id"], cid)

            # 4. PUT /api/creators/{cid}
            res_put = self.client.put(f"/api/creators/{cid}", json={"game": "Counter-Strike 2"})
            self.assertEqual(res_put.status_code, 200)
            self.assertEqual(res_put.json()["game"], "Counter-Strike 2")

            # 5. GET /api/creators/{cid}/clips and /videos
            res_clips = self.client.get(f"/api/creators/{cid}/clips")
            self.assertEqual(res_clips.status_code, 200)
            self.assertIsInstance(res_clips.json(), list)

            res_videos = self.client.get(f"/api/creators/{cid}/videos")
            self.assertEqual(res_videos.status_code, 200)
            self.assertIsInstance(res_videos.json(), list)

            # 6. GET /api/creators/{cid}/logs
            res_logs = self.client.get(f"/api/creators/{cid}/logs")
            self.assertEqual(res_logs.status_code, 200)
            self.assertGreaterEqual(len(res_logs.json()), 1)

            # 7. GET /api/library?creator={cid}
            res_lib = self.client.get(f"/api/library?creator={cid}")
            self.assertEqual(res_lib.status_code, 200)
            self.assertIsInstance(res_lib.json(), list)

        finally:
            # 8. DELETE /api/creators/{cid}
            res_del = self.client.delete(f"/api/creators/{cid}")
            self.assertEqual(res_del.status_code, 200)
            self.assertTrue(res_del.json().get("deleted"))

if __name__ == "__main__":
    unittest.main()
