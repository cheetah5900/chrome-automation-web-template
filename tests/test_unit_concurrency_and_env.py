import os
import unittest
from pathlib import Path
from scripts.flow_batch_runner import parse_batch_size as batch_runner_parse
from scripts.flow_storyboard_runner import parse_batch_size as storyboard_runner_parse
from app.env_config import (
    get_repo_dir,
    get_channel_dir,
    get_shopee_project_dir,
    get_capcut_drafts_dir,
    get_whisper_model_path,
    normalize_user_path,
    get_api_port,
    get_status_port,
)


class TestConcurrencyAndEnv(unittest.TestCase):
    def test_parse_batch_size_defaults(self):
        for pbs in (batch_runner_parse, storyboard_runner_parse):
            self.assertEqual(pbs(None), 3)
            self.assertEqual(pbs(""), 3)
            self.assertEqual(pbs("invalid"), 3)

    def test_parse_batch_size_numeric(self):
        for pbs in (batch_runner_parse, storyboard_runner_parse):
            self.assertEqual(pbs(1), 1)
            self.assertEqual(pbs("1"), 1)
            self.assertEqual(pbs(3), 3)
            self.assertEqual(pbs("3"), 3)
            self.assertEqual(pbs(10), 10)
            self.assertEqual(pbs("25"), 25)

    def test_parse_batch_size_unlimited_aliases(self):
        for pbs in (batch_runner_parse, storyboard_runner_parse):
            for alias in ("unlimit", "UNLIMIT", "unlimited", "all", "ALL", "inf", "-1", "0", "max"):
                self.assertEqual(pbs(alias), 999999, f"Failed for alias: {alias}")

    def test_env_config_resolves_existing_paths(self):
        repo_dir = get_repo_dir()
        self.assertTrue(os.path.isdir(repo_dir), f"Repo dir does not exist: {repo_dir}")

        channel_dir = get_channel_dir()
        self.assertTrue(os.path.isdir(channel_dir), f"Channel dir does not exist: {channel_dir}")

        capcut_dir = get_capcut_drafts_dir()
        self.assertTrue(os.path.isdir(capcut_dir), f"CapCut dir does not exist: {capcut_dir}")

        whisper_path = get_whisper_model_path()
        self.assertTrue(os.path.isfile(whisper_path), f"Whisper model path does not exist: {whisper_path}")

    def test_env_config_ports(self):
        self.assertEqual(get_api_port(), 6969)
        self.assertEqual(get_status_port(), 8181)

    def test_normalize_user_path(self):
        current_home = os.path.expanduser("~")
        legacy_path = "/Users/other_user/Projects/test"
        normalized = normalize_user_path(legacy_path)
        self.assertTrue(normalized.startswith(current_home))


if __name__ == "__main__":
    unittest.main()
