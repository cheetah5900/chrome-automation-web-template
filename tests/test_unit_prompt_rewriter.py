import os
import shutil
import tempfile
import unittest

from app.prompt_rewriter import (
    get_prompt_rewriter_summary,
    scan_prompt_rewriter_items,
    call_ai_rewrite,
    execute_prompt_rewriter_batch,
    restore_prompt_backup,
    _rule_based_rewrite
)


class TestPromptRewriter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Create folder structure:
        # test_dir/
        #   1/
        #     animation_prompt_1.md
        #     animation_prompt_2.md
        #     animation_prompt_3.md
        #   2/
        #     animation_prompt_1.md
        #     animation_prompt_2.md
        self.folder_1 = os.path.join(self.test_dir, "1")
        self.folder_2 = os.path.join(self.test_dir, "2")
        os.makedirs(self.folder_1, exist_ok=True)
        os.makedirs(self.folder_2, exist_ok=True)

        with open(os.path.join(self.folder_1, "animation_prompt_1.md"), "w", encoding="utf-8") as f:
            f.write("0-2s: Tsunami wave roars forward. 2-4s: Civilians escape.")
        with open(os.path.join(self.folder_1, "animation_prompt_2.md"), "w", encoding="utf-8") as f:
            f.write("0-2s: Flash flood with violent debris and bleeding civilians. 2-4s: Hand rescues them.")
        with open(os.path.join(self.folder_1, "animation_prompt_3.md"), "w", encoding="utf-8") as f:
            f.write("0-2s: Fire inferno spreading. 2-4s: Safe rescue.")

        with open(os.path.join(self.folder_2, "animation_prompt_1.md"), "w", encoding="utf-8") as f:
            f.write("0-2s: Earthquake shaking. 2-4s: Escape.")
        with open(os.path.join(self.folder_2, "animation_prompt_2.md"), "w", encoding="utf-8") as f:
            f.write("0-2s: Landslide rushing. 2-4s: Rescue.")

    def tearDown(self):
        if os.path.isdir(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_summary_and_scan_filter_files_2_3(self):
        # Folder 1 with files 2-3
        summary = get_prompt_rewriter_summary(self.test_dir, subfolders_str="1", prompt_files_str="2-3")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["total_folders"], 1)
        self.assertEqual(summary["total_prompt_files"], 2)
        self.assertEqual(len(summary["folders"][0]["prompt_files"]), 2)
        self.assertIn("animation_prompt_2.md", summary["folders"][0]["prompt_files"])
        self.assertIn("animation_prompt_3.md", summary["folders"][0]["prompt_files"])

        # Scan items
        scan_res = scan_prompt_rewriter_items(self.test_dir, subfolders_str="1", prompt_files_str="2-3")
        self.assertTrue(scan_res["ok"])
        self.assertEqual(scan_res["total_items"], 2)
        scanned_files = [item["prompt_file"] for item in scan_res["items"]]
        self.assertEqual(scanned_files, ["animation_prompt_2.md", "animation_prompt_3.md"])

    def test_rule_based_safety_rewrite(self):
        violent_prompt = "0-2s: A violent collision with blood splatter and deadly corpses. 2-4s: Rescue."
        res = _rule_based_rewrite(violent_prompt, rules=["violence"])
        rewritten = res["rewritten_text"].lower()

        self.assertNotIn("blood splatter", rewritten)
        self.assertNotIn("deadly", rewritten)
        self.assertNotIn("corpses", rewritten)
        self.assertIn("rescue", rewritten)

    def test_batch_execution_backup_and_restore(self):
        scan_res = scan_prompt_rewriter_items(self.test_dir, subfolders_str="1", prompt_files_str="2")
        self.assertEqual(scan_res["total_items"], 1)
        target_item = scan_res["items"][0]
        original_content = target_item["prompt_text"]

        # Run batch rewrite
        exec_res = execute_prompt_rewriter_batch(
            items=[target_item],
            rules=["violence"],
            custom_instruction="Keep it comic and safe",
            provider="rule_based",  # Triggers rule-based fallback without external API
            make_backup=True
        )
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["success_count"], 1)

        # Verify .bak was created
        target_path = target_item["prompt_path"]
        bak_path = f"{target_path}.bak"
        self.assertTrue(os.path.isfile(bak_path))
        with open(bak_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content)

        # Verify modified file has changed
        with open(target_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        self.assertNotEqual(new_content, original_content)

        # Restore from backup
        restore_res = restore_prompt_backup(target_path)
        self.assertTrue(restore_res["ok"])
        with open(target_path, "r", encoding="utf-8") as f:
            restored_content = f.read()
        self.assertEqual(restored_content, original_content)


if __name__ == '__main__':
    unittest.main()
