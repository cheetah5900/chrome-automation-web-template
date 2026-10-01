import os
import shutil
import tempfile
import unittest
from app.main import scan_lakorn_autopost, MetaScanRequest

class TestLakornAutoPostScanner(unittest.TestCase):
    def setUp(self):
        # Create channel root with story folder "21"
        self.channel_root = tempfile.mkdtemp()
        self.story_21_dir = os.path.join(self.channel_root, "21")
        self.final_dir = os.path.join(self.story_21_dir, "10 - Final")
        self.affiliate_dir = os.path.join(self.story_21_dir, "8 - Affiliate")
        self.caption_dir = os.path.join(self.story_21_dir, "9 - Caption")

        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.affiliate_dir, exist_ok=True)
        os.makedirs(self.caption_dir, exist_ok=True)

        # Mock episode clips
        # Clip 1
        with open(os.path.join(self.final_dir, "21-1.mp4"), "wb") as f:
            f.write(b"video1")
        with open(os.path.join(self.caption_dir, "EP01.md"), "w", encoding="utf-8") as f:
            f.write("เรื่องราวตอนที่ 1 สุดเข้มข้น\n#ละครสั้น #ดราม่า")
        with open(os.path.join(self.affiliate_dir, "ep1 - affiliate link.md"), "w", encoding="utf-8") as f:
            f.write("https://s.shopee.co.th/affiliate_ep1")

        # Clip 2
        with open(os.path.join(self.final_dir, "21-2.mp4"), "wb") as f:
            f.write(b"video2")
        with open(os.path.join(self.caption_dir, "EP02.md"), "w", encoding="utf-8") as f:
            f.write("เรื่องราวตอนที่ 2 ความลับแตก\n#ละครสั้น #ดราม่า")
        with open(os.path.join(self.affiliate_dir, "ep2 - affiliate link.md"), "w", encoding="utf-8") as f:
            f.write("https://s.shopee.co.th/affiliate_ep2")

        # Clip 3
        with open(os.path.join(self.final_dir, "21-3.mp4"), "wb") as f:
            f.write(b"video3")
        with open(os.path.join(self.caption_dir, "EP03.md"), "w", encoding="utf-8") as f:
            f.write("เรื่องราวตอนที่ 3 บทสรุปความรัก\n#ละครสั้น #ดราม่า")
        with open(os.path.join(self.affiliate_dir, "ep3 - affiliate link.md"), "w", encoding="utf-8") as f:
            f.write("https://s.shopee.co.th/affiliate_ep3")

    def tearDown(self):
        shutil.rmtree(self.channel_root, ignore_errors=True)

    def test_scan_with_channel_root_and_story_number(self):
        # User provides channel root as main_folder and types "21"
        req = MetaScanRequest(
            main_folder=self.channel_root,
            subfolders_str="21",
            start_date="2026-10-01",
            start_hour=19,
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)
        self.assertEqual(len(res["items"]), 3)

        c1 = res["items"][0]
        self.assertEqual(c1["subfolder_name"], "ตอน 21 (คลิป 1)")
        self.assertEqual(c1["video_name"], "21-1.mp4")
        self.assertTrue(c1["has_video"])
        self.assertIn("เรื่องราวตอนที่ 1", c1["caption"])
        self.assertNotIn("https://", c1["caption"])
        self.assertEqual(c1["affiliate_url"], "https://s.shopee.co.th/affiliate_ep1")
        self.assertTrue(c1["has_affiliate_url"])
        self.assertTrue(c1["checked"])
        self.assertEqual(c1["status"], "ready")

        c2 = res["items"][1]
        self.assertEqual(c2["subfolder_name"], "ตอน 21 (คลิป 2)")
        self.assertEqual(c2["video_name"], "21-2.mp4")

        c3 = res["items"][2]
        self.assertEqual(c3["subfolder_name"], "ตอน 21 (คลิป 3)")
        self.assertEqual(c3["video_name"], "21-3.mp4")

    def test_scan_direct_story_folder(self):
        # User provides direct story folder path (.../21)
        req = MetaScanRequest(
            main_folder=self.story_21_dir,
            subfolders_str="",
            start_date="2026-10-01",
            start_hour=19,
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)
        self.assertEqual(res["items"][0]["subfolder_name"], "ตอน 21 (คลิป 1)")

    def test_missing_affiliate_unchecks_by_default(self):
        os.remove(os.path.join(self.affiliate_dir, "ep2 - affiliate link.md"))
        req = MetaScanRequest(
            main_folder=self.channel_root,
            subfolders_str="21",
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        c2 = res["items"][1]
        self.assertFalse(c2["has_affiliate_url"])
        self.assertFalse(c2["checked"])
        self.assertEqual(c2["status"], "missing_affiliate")
        self.assertEqual(res["missing_affiliate_count"], 1)

    def test_nonexistent_story_number(self):
        req = MetaScanRequest(
            main_folder=self.channel_root,
            subfolders_str="99",
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertFalse(res["ok"])
        self.assertIn("99", res["message"])

    def test_scan_with_clip_part_filter(self):
        # Test range filter "1-2"
        req = MetaScanRequest(
            main_folder=self.channel_root,
            subfolders_str="21",
            video_prefix="1-2",
            folder_mode="lakorn"
        )
        res = scan_lakorn_autopost(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["items"][0]["video_name"], "21-1.mp4")
        self.assertEqual(res["items"][1]["video_name"], "21-2.mp4")

        # Test single clip filter "3"
        req_single = MetaScanRequest(
            main_folder=self.channel_root,
            subfolders_str="21",
            video_prefix="3",
            folder_mode="lakorn"
        )
        res_single = scan_lakorn_autopost(req_single)
        self.assertTrue(res_single["ok"])
        self.assertEqual(res_single["count"], 1)
        self.assertEqual(res_single["items"][0]["video_name"], "21-3.mp4")

        # Test fallback: prefix is story_name or "combined" -> should pull all
        req_fallback = MetaScanRequest(
            main_folder=self.channel_root,
            subfolders_str="21",
            video_prefix="21",
            folder_mode="lakorn"
        )
        res_fallback = scan_lakorn_autopost(req_fallback)
        self.assertTrue(res_fallback["ok"])
        self.assertEqual(res_fallback["count"], 3)

if __name__ == "__main__":
    unittest.main()
