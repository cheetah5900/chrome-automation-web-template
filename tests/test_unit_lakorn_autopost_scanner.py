import os
import shutil
import tempfile
import unittest
from app.main import scan_lakorn_autopost, MetaScanRequest

class TestLakornAutoPostScanner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.final_dir = os.path.join(self.test_dir, "10 - Final")
        self.affiliate_dir = os.path.join(self.test_dir, "8 - Affiliate")
        self.caption_dir = os.path.join(self.test_dir, "9 - Caption")

        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.affiliate_dir, exist_ok=True)
        os.makedirs(self.caption_dir, exist_ok=True)

        # Create mock episode files
        # EP 1
        with open(os.path.join(self.final_dir, "21-1.mp4"), "wb") as f:
            f.write(b"video1")
        with open(os.path.join(self.caption_dir, "EP01.md"), "w", encoding="utf-8") as f:
            f.write("เรื่องราวตอนที่ 1 สุดเข้มข้น\n#ละครสั้น #ดราม่า")
        with open(os.path.join(self.affiliate_dir, "ep1 - affiliate link.md"), "w", encoding="utf-8") as f:
            f.write("https://s.shopee.co.th/affiliate_ep1")

        # EP 2
        with open(os.path.join(self.final_dir, "21-2.mp4"), "wb") as f:
            f.write(b"video2")
        with open(os.path.join(self.caption_dir, "EP02.md"), "w", encoding="utf-8") as f:
            f.write("เรื่องราวตอนที่ 2 ความลับแตก\n#ละครสั้น #ดราม่า")
        with open(os.path.join(self.affiliate_dir, "ep2 - affiliate link.md"), "w", encoding="utf-8") as f:
            f.write("https://s.shopee.co.th/affiliate_ep2")

        # EP 3
        with open(os.path.join(self.final_dir, "21-3.mp4"), "wb") as f:
            f.write(b"video3")
        with open(os.path.join(self.caption_dir, "EP03.md"), "w", encoding="utf-8") as f:
            f.write("เรื่องราวตอนที่ 3 บทสรุปความรัก\n#ละครสั้น #ดราม่า")
        with open(os.path.join(self.affiliate_dir, "ep3 - affiliate link.md"), "w", encoding="utf-8") as f:
            f.write("https://s.shopee.co.th/affiliate_ep3")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_scan_all_episodes(self):
        req = MetaScanRequest(
            main_folder=self.test_dir,
            subfolders_str="",
            start_date="2026-10-01",
            start_hour=19,
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)
        self.assertEqual(len(res["items"]), 3)

        ep1 = res["items"][0]
        self.assertEqual(ep1["subfolder_name"], "EP 1")
        self.assertEqual(ep1["video_name"], "21-1.mp4")
        self.assertTrue(ep1["has_video"])
        self.assertIn("เรื่องราวตอนที่ 1", ep1["caption"])
        # Caption must NOT contain the affiliate link!
        self.assertNotIn("https://", ep1["caption"])
        self.assertEqual(ep1["affiliate_url"], "https://s.shopee.co.th/affiliate_ep1")
        self.assertTrue(ep1["has_affiliate_url"])
        self.assertTrue(ep1["checked"])
        self.assertEqual(ep1["status"], "ready")

        ep2 = res["items"][1]
        self.assertEqual(ep2["subfolder_name"], "EP 2")
        self.assertEqual(ep2["video_name"], "21-2.mp4")
        self.assertEqual(ep2["affiliate_url"], "https://s.shopee.co.th/affiliate_ep2")

        ep3 = res["items"][2]
        self.assertEqual(ep3["subfolder_name"], "EP 3")
        self.assertEqual(ep3["video_name"], "21-3.mp4")
        self.assertEqual(ep3["affiliate_url"], "https://s.shopee.co.th/affiliate_ep3")

    def test_filter_specific_episodes(self):
        req = MetaScanRequest(
            main_folder=self.test_dir,
            subfolders_str="1, 3",
            start_date="2026-10-01",
            start_hour=19,
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        ep_names = [it["subfolder_name"] for it in res["items"]]
        self.assertEqual(ep_names, ["EP 1", "EP 3"])

    def test_filter_range_episodes(self):
        req = MetaScanRequest(
            main_folder=self.test_dir,
            subfolders_str="1-2",
            start_date="2026-10-01",
            start_hour=19,
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        ep_names = [it["subfolder_name"] for it in res["items"]]
        self.assertEqual(ep_names, ["EP 1", "EP 2"])

    def test_missing_affiliate_unchecks_by_default(self):
        # Remove affiliate file for ep 2
        os.remove(os.path.join(self.affiliate_dir, "ep2 - affiliate link.md"))
        req = MetaScanRequest(
            main_folder=self.test_dir,
            subfolders_str="",
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        ep2 = res["items"][1]
        self.assertFalse(ep2["has_affiliate_url"])
        self.assertFalse(ep2["checked"])
        self.assertEqual(ep2["status"], "missing_affiliate")
        self.assertEqual(res["missing_affiliate_count"], 1)

    def test_missing_final_folder(self):
        shutil.rmtree(self.final_dir)
        req = MetaScanRequest(
            main_folder=self.test_dir,
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertFalse(res["ok"])
        self.assertIn("10 - Final", res["message"])

if __name__ == "__main__":
    unittest.main()
