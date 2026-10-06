"""
FlowKit Multi-Machine Environment Configuration Loader
Loads environment variables from .env file and provides machine-agnostic dynamic fallbacks.
Supports multi-machine environments so configs don't conflict across machines.
"""
import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Base repo directory (directory containing app/, agent/, scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent

# Load .env file from repository root if present
_env_path = REPO_ROOT / ".env"
if _env_path.is_file():
    load_dotenv(dotenv_path=_env_path, override=False)
else:
    load_dotenv(override=False)


def get_repo_dir() -> Path:
    """Returns absolute path to the repository root."""
    val = os.environ.get("REPO_DIR")
    if val:
        return Path(val).resolve()
    return REPO_ROOT


def normalize_user_path(path_str: str) -> str:
    """
    Normalizes a path containing legacy /Users/<username>/ to match the current user's home directory.
    If path is relative or doesn't start with /Users/, returns as-is.
    """
    if not path_str or not isinstance(path_str, str):
        return path_str
    if path_str.startswith("file:///Users/"):
        current_home = os.path.expanduser("~")
        sub = path_str[len("file://"):]
        match = re.match(r"^/Users/[^/]+", sub)
        if match:
            old_home = match.group(0)
            if old_home != current_home:
                sub = sub.replace(old_home, current_home, 1)
        return "file://" + sub
    elif path_str.startswith("/Users/"):
        current_home = os.path.expanduser("~")
        match = re.match(r"^/Users/[^/]+", path_str)
        if match:
            old_home = match.group(0)
            if old_home != current_home:
                return path_str.replace(old_home, current_home, 1)
    return path_str


def get_channel_dir() -> str:
    """Returns absolute path to the Lakorn Google Drive Knowledge Vault channel directory."""
    val = os.environ.get("LAKORN_CHANNEL_DIR")
    if val:
        return normalize_user_path(val)
    home = os.path.expanduser("~")
    return os.path.join(
        home,
        "Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย"
    )


def get_capcut_drafts_dir() -> str:
    """Returns absolute path to CapCut macOS Drafts root directory."""
    val = os.environ.get("CAPCUT_DRAFTS_ROOT")
    if val:
        return normalize_user_path(val)
    home = os.path.expanduser("~")
    return os.path.join(home, "Movies/CapCut/User Data/Projects/com.lveditor.draft")


def get_whisper_model_path() -> str:
    """Returns path to Whisper model binary."""
    val = os.environ.get("WHISPER_MODEL_PATH")
    if val:
        return normalize_user_path(val)
    home = os.path.expanduser("~")
    return os.path.join(home, ".cache/whisper/ggml-base.bin")


def get_shopee_project_dir() -> str:
    """Returns path to Shopee Drama project directory."""
    val = os.environ.get("SHOPEE_PROJECT_DIR")
    if val:
        return normalize_user_path(val)
    home = os.path.expanduser("~")
    return os.path.join(
        home,
        "Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/9 - ป้ายยาที่ตาซ้าย/0 - รอสร้างวิดีโอ/V1 - ดราม่าขายของ"
    )


def get_api_port() -> int:
    return int(os.environ.get("API_PORT", 6969))


def get_ws_port() -> int:
    return int(os.environ.get("WS_PORT", 9225))


def get_status_port() -> int:
    return int(os.environ.get("STATUS_PORT", 8181))


def get_flow_agent_port() -> int:
    return int(os.environ.get("FLOW_AGENT_PORT", 8100))
