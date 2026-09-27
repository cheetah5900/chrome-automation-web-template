import os
import shutil
import tempfile
import unittest

from app.video_counter import (
    count_videos_in_folder,
    get_video_counter_summary,
    get_video_counter_report,
    natural_sort_key
)


class TestVideoCounter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        # Structure:
        # test_dir/
        #   1/ (5 videos)
        #     01.mp4, 02.mp4, 03.mp4, 04.mp4, 05.mp4, notes.txt, temp.tmp, .DS_Store
        #   2/ (3 videos)
        #     1.mp4, 2.mov, 3.mkv
        #   3/ (7 videos nested in videos/)
        #     videos/ (01.mp4 ... 07.mp4)
        #   4/ (0 videos)
        #     image.png

        self.f1 = os.path.join(self.test_dir, "1")
        self.f2 = os.path.join(self.test_dir, "2")
        self.f3 = os.path.join(self.test_dir, "3")
        self.f4 = os.path.join(self.test_dir, "4")

        os.makedirs(self.f1, exist_ok=True)
        os.makedirs(self.f2, exist_ok=True)
        os.makedirs(os.path.join(self.f3, "videos"), exist_ok=True)
        os.makedirs(self.f4, exist_ok=True)

        for i in range(1, 6):
            open(os.path.join(self.f1, f"{i:02d}.mp4"), "w").close()
        open(os.path.join(self.f1, "notes.txt"), "w").close()
        open(os.path.join(self.f1, "file.tmp"), "w").close()
        open(os.path.join(self.f1, ".DS_Store"), "w").close()

        open(os.path.join(self.f2, "1.mp4"), "w").close()
        open(os.path.join(self.f2, "2.mov"), "w").close()
        open(os.path.join(self.f2, "3.mkv"), "w").close()

        for i in range(1, 8):
            open(os.path.join(self.f3, "videos", f"{i:02d}.mp4"), "w").close()

        open(os.path.join(self.f4, "image.png"), "w").close()

    def tearDown(self):
        if os.path.isdir(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_count_videos_in_folder_direct_and_filters(self):
        videos_1 = count_videos_in_folder(self.f1)
        self.assertEqual(len(videos_1), 5)
        self.assertEqual(videos_1[0], "01.mp4")
        self.assertEqual(videos_1[-1], "05.mp4")
        self.assertNotIn("notes.txt", videos_1)
        self.assertNotIn("file.tmp", videos_1)

    def test_count_videos_nested_in_subfolder(self):
        videos_3 = count_videos_in_folder(self.f3)
        self.assertEqual(len(videos_3), 7)
        self.assertTrue(all("videos/" in v for v in videos_3))

    def test_natural_sorting(self):
        raw = ["10.mp4", "2.mp4", "1.mp4", "20.mp4", "3.mp4"]
        sorted_list = sorted(raw, key=natural_sort_key)
        self.assertEqual(sorted_list, ["1.mp4", "2.mp4", "3.mp4", "10.mp4", "20.mp4"])

    def test_video_counter_summary(self):
        summary = get_video_counter_summary(self.test_dir, subfolders_str="1-2")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["total_folders"], 2)
        names = [f["name"] for f in summary["folders"]]
        self.assertEqual(names, ["1", "2"])

    def test_video_counter_report_threshold(self):
        # Target = 5 videos per folder
        # 1 has 5 (met)
        # 2 has 3 (below, missing 2)
        # 3 has 7 (met, diff +2)
        report = get_video_counter_report(self.test_dir, subfolders_str="1-3", target_count=5)
        self.assertTrue(report["ok"])
        self.assertEqual(report["total_folders"], 3)
        self.assertEqual(report["met_count"], 2)
        self.assertEqual(report["below_count"], 1)
        self.assertFalse(report["all_met"])
        self.assertEqual(report["total_videos"], 15)  # 5 + 3 + 7

        # Check below target list
        below = report["below_target_folders"]
        self.assertEqual(len(below), 1)
        self.assertEqual(below[0]["folder_name"], "2")
        self.assertEqual(below[0]["video_count"], 3)
        self.assertEqual(below[0]["missing_count"], 2)

        # Check met target list
        met = report["met_target_folders"]
        self.assertEqual(len(met), 2)
        self.assertEqual(met[0]["folder_name"], "1")
        self.assertEqual(met[0]["video_count"], 5)
        self.assertEqual(met[1]["folder_name"], "3")
        self.assertEqual(met[1]["video_count"], 7)

        # Check formatted text report
        self.assertIn("รายงานการตรวจสอบจำนวนวิดีโอ", report["text_report"])
        self.assertIn("โฟลเดอร์ 2: มี 3 วิดีโอ (ขาดอีก 2 วิดีโอ", report["text_report"])
        self.assertIn("โฟลเดอร์ 1: 5/5 ไฟล์ - ✅ ครบเกณฑ์", report["text_report"])
        self.assertIn("โฟลเดอร์ 3: 7/5 ไฟล์ - ✅ ครบเกณฑ์ (+2)", report["text_report"])

    def test_video_counter_all_met(self):
        # Target = 3 for folders 1 and 2
        report = get_video_counter_report(self.test_dir, subfolders_str="1-2", target_count=3)
        self.assertTrue(report["ok"])
        self.assertEqual(report["met_count"], 2)
        self.assertEqual(report["below_count"], 0)
        self.assertTrue(report["all_met"])
        self.assertIn("ทุกโฟลเดอร์มีจำนวนวิดีโอครบตามเกณฑ์ที่กำหนด", report["text_report"])

    def test_video_counter_invalid_folder(self):
        report = get_video_counter_report("/non/existent/path/xyz", target_count=5)
        self.assertFalse(report["ok"])
        self.assertIn("ไม่พบโฟลเดอร์หลัก", report["error"])


if __name__ == '__main__':
    unittest.main()
