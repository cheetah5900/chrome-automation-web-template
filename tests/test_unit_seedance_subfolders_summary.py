import os
import shutil
import tempfile
import unittest

from app.seedance import (
    get_animation_prompt_files,
    get_seedance_subfolders_summary,
    scan_seedance_folders,
)


class TestSeedanceSubfoldersSummary(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_animation_prompt_files_matches_prompts_only(self):
        sub1 = os.path.join(self.test_dir, "1")
        os.makedirs(sub1, exist_ok=True)

        # Create files matching user's structure
        with open(os.path.join(sub1, "Caption.md"), "w", encoding="utf-8") as f:
            f.write("A short caption.")
        with open(os.path.join(sub1, "animation_prompt_1.md"), "w", encoding="utf-8") as f:
            f.write("Prompt 1 content")
        with open(os.path.join(sub1, "animation_prompt_2.md"), "w", encoding="utf-8") as f:
            f.write("Prompt 2 content")
        with open(os.path.join(sub1, "animation_prompt_3.md"), "w", encoding="utf-8") as f:
            f.write("Prompt 3 content")
        with open(os.path.join(sub1, ".DS_Store"), "w", encoding="utf-8") as f:
            f.write("")

        prompt_files = get_animation_prompt_files(sub1)
        self.assertEqual(len(prompt_files), 3)
        self.assertEqual(prompt_files, ["animation_prompt_1.md", "animation_prompt_2.md", "animation_prompt_3.md"])

    def test_get_seedance_subfolders_summary_filtering(self):
        # Create subfolders 1, 2, 3, 4
        for i in range(1, 5):
            sub = os.path.join(self.test_dir, str(i))
            os.makedirs(sub, exist_ok=True)
            with open(os.path.join(sub, "Caption.md"), "w", encoding="utf-8") as f:
                f.write("Caption")
            for p in range(1, i + 1):  # folder 1 has 1 prompt, 2 has 2 prompts, etc.
                with open(os.path.join(sub, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as f:
                    f.write(f"Prompt {p}")

        # Test single subfolder "1"
        res_single = get_seedance_subfolders_summary(self.test_dir, "1")
        self.assertTrue(res_single["ok"])
        self.assertEqual(res_single["total_folders"], 1)
        self.assertEqual(res_single["total_prompt_files"], 1)
        self.assertEqual(res_single["folders"][0]["name"], "1")
        self.assertEqual(res_single["folders"][0]["prompt_file_count"], 1)

        # Test range "2-3"
        res_range = get_seedance_subfolders_summary(self.test_dir, "2-3")
        self.assertTrue(res_range["ok"])
        self.assertEqual(res_range["total_folders"], 2)
        # folder 2 (2) + folder 3 (3) = 5
        self.assertEqual(res_range["total_prompt_files"], 5)

        # Test empty string (all folders 1..4)
        res_all = get_seedance_subfolders_summary(self.test_dir, "")
        self.assertTrue(res_all["ok"])
        self.assertEqual(res_all["total_folders"], 4)
        # 1 + 2 + 3 + 4 = 10
        self.assertEqual(res_all["total_prompt_files"], 10)

    def test_get_seedance_subfolders_summary_direct_folder(self):
        # User provides direct path to subfolder 1
        sub1 = os.path.join(self.test_dir, "1")
        os.makedirs(sub1, exist_ok=True)
        with open(os.path.join(sub1, "Caption.md"), "w", encoding="utf-8") as f:
            f.write("Caption")
        for p in range(1, 4):
            with open(os.path.join(sub1, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as f:
                f.write(f"Prompt {p}")

        res_direct = get_seedance_subfolders_summary(sub1, "")
        self.assertTrue(res_direct["ok"])
        self.assertEqual(res_direct["total_folders"], 1)
        self.assertEqual(res_direct["total_prompt_files"], 3)
        self.assertEqual(res_direct["folders"][0]["prompt_file_count"], 3)

    def test_scan_seedance_folders_contains_prompt_counts(self):
        sub1 = os.path.join(self.test_dir, "1")
        os.makedirs(sub1, exist_ok=True)
        with open(os.path.join(sub1, "Caption.md"), "w", encoding="utf-8") as f:
            f.write("Caption")
        for p in range(1, 4):
            with open(os.path.join(sub1, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as f:
                f.write(f"Prompt content {p}")

        scan_res = scan_seedance_folders(self.test_dir, "1")
        self.assertTrue(scan_res["ok"])
        # Should expand each prompt file into an individual item
        self.assertEqual(scan_res["total"], 3)
        self.assertEqual(scan_res["total_folders"], 1)

        items = scan_res["items"]
        self.assertEqual(len(items), 3)

        for idx, item in enumerate(items, 1):
            self.assertEqual(item["sub_index"], idx)
            self.assertEqual(item["total_prompts"], 3)
            self.assertEqual(item["prompt_file"], f"animation_prompt_{idx}.md")
            self.assertEqual(item["prompt_base_name"], f"animation_prompt_{idx}")
            self.assertEqual(item["display_name"], f"1 [{idx}/3] animation_prompt_{idx}.md")

    def test_multi_prompt_video_matching(self):
        from app.seedance import pair_seedance_items

        sub1 = os.path.join(self.test_dir, "1")
        os.makedirs(sub1, exist_ok=True)
        for p in range(1, 4):
            with open(os.path.join(sub1, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as f:
                f.write(f"Prompt content {p}")

        # Create video only for prompt #2
        with open(os.path.join(sub1, "animation_prompt_2.mp4"), "wb") as f:
            f.write(b"fake video data 2")

        scan_res = scan_seedance_folders(self.test_dir, "1")
        items = scan_res["items"]

        # Item 1 has no video
        self.assertFalse(items[0]["local_video_exists"])
        # Item 2 has video
        self.assertTrue(items[1]["local_video_exists"])
        self.assertEqual(items[1]["local_video_path"], os.path.join(sub1, "animation_prompt_2.mp4"))
        # Item 3 has no video
        self.assertFalse(items[2]["local_video_exists"])

        # Run through pair_seedance_items without web driver
        paired = pair_seedance_items(None, items)
        self.assertFalse(paired[0]["local_video_exists"])
        self.assertTrue(paired[1]["local_video_exists"])
        self.assertFalse(paired[2]["local_video_exists"])

    def test_filter_specific_files_in_leaf_folder(self):
        # User provides direct path to folder 1, and specifies '2-3'
        sub1 = os.path.join(self.test_dir, "1")
        os.makedirs(sub1, exist_ok=True)
        for p in range(1, 4):
            with open(os.path.join(sub1, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as f:
                f.write(f"Prompt content {p}")

        # Summary for '2-3'
        summary_23 = get_seedance_subfolders_summary(sub1, "2-3")
        self.assertTrue(summary_23["ok"])
        self.assertEqual(summary_23["total_prompt_files"], 2)
        self.assertEqual(summary_23["folders"][0]["prompt_files"], ["animation_prompt_2.md", "animation_prompt_3.md"])

        # Scan for '2-3'
        scan_23 = scan_seedance_folders(sub1, "2-3")
        self.assertTrue(scan_23["ok"])
        self.assertEqual(scan_23["total"], 2)
        self.assertEqual(scan_23["items"][0]["sub_index"], 2)
        self.assertEqual(scan_23["items"][0]["prompt_file"], "animation_prompt_2.md")
        self.assertEqual(scan_23["items"][1]["sub_index"], 3)
        self.assertEqual(scan_23["items"][1]["prompt_file"], "animation_prompt_3.md")

        # Scan for '_2, _3'
        scan_underscore = scan_seedance_folders(sub1, "_2, _3")
        self.assertEqual(scan_underscore["total"], 2)
        self.assertEqual(scan_underscore["items"][0]["prompt_file"], "animation_prompt_2.md")
        self.assertEqual(scan_underscore["items"][1]["prompt_file"], "animation_prompt_3.md")

    def test_filter_compound_syntax_from_parent(self):
        # Parent contains folder 1 and folder 2
        for f in [1, 2]:
            sub = os.path.join(self.test_dir, str(f))
            os.makedirs(sub, exist_ok=True)
            for p in range(1, 4):
                with open(os.path.join(sub, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as file:
                    file.write(f"Prompt {f}_{p}")

        # '1:2-3' -> folder 1, files 2 and 3
        scan_colon = scan_seedance_folders(self.test_dir, "1:2-3")
        self.assertEqual(scan_colon["total"], 2)
        self.assertEqual(scan_colon["items"][0]["subfolder_name"], "1")
        self.assertEqual(scan_colon["items"][0]["sub_index"], 2)
        self.assertEqual(scan_colon["items"][1]["sub_index"], 3)

        # '1_2-3' -> folder 1, files 2 and 3
        scan_under = scan_seedance_folders(self.test_dir, "1_2-3")
        self.assertEqual(scan_under["total"], 2)
        self.assertEqual(scan_under["items"][0]["sub_index"], 2)
        self.assertEqual(scan_under["items"][1]["sub_index"], 3)

    def test_filter_dual_parameters(self):
        # Parent contains folder 1 and folder 2, each with 3 files
        for f in [1, 2]:
            sub = os.path.join(self.test_dir, str(f))
            os.makedirs(sub, exist_ok=True)
            for p in range(1, 4):
                with open(os.path.join(sub, f"animation_prompt_{p}.md"), "w", encoding="utf-8") as file:
                    file.write(f"Prompt {f}_{p}")

        # subfolders_str="1", prompt_files_str="2-3" -> folder 1, files 2 and 3
        summary = get_seedance_subfolders_summary(self.test_dir, subfolders_str="1", prompt_files_str="2-3")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["total_folders"], 1)
        self.assertEqual(summary["total_prompt_files"], 2)
        self.assertEqual(summary["folders"][0]["prompt_files"], ["animation_prompt_2.md", "animation_prompt_3.md"])

        scan = scan_seedance_folders(self.test_dir, subfolders_str="1", prompt_files_str="2-3")
        self.assertTrue(scan["ok"])
        self.assertEqual(scan["total"], 2)
        self.assertEqual(scan["items"][0]["subfolder_name"], "1")
        self.assertEqual(scan["items"][0]["sub_index"], 2)
        self.assertEqual(scan["items"][1]["sub_index"], 3)


if __name__ == "__main__":
    unittest.main()
