#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app/shopeesave_watcher.py - Watcher Manager Service for FastAPI Backend.
Controls the watch_shopeesave.py daemon lifecycle and log streaming.
"""

import os
import sys
import time
import signal
import subprocess
from typing import Any

PID_FILE = os.path.expanduser("~/.shopeesave_watcher.pid")
LOG_FILE = os.path.expanduser("~/.shopeesave_watcher.log")
DEFAULT_PROJECT_V1_DIR = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/9 - ป้ายยาที่ตาซ้าย/0 - รอสร้างวิดีโอ/V1 - ดราม่าขายของ"
DEFAULT_DOWNLOADS_DIR = os.path.expanduser("~/Downloads")


def _is_pid_alive(pid: int) -> bool:
    """Checks if a PID is alive and running watch_shopeesave."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    # Verify command line to make sure PID was not recycled
    try:
        res = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
        cmd = res.stdout.strip()
        if "watch_shopeesave" in cmd:
            return True
    except Exception:
        pass
    return True


def is_watcher_running() -> tuple[bool, int | None]:
    """Returns (running, pid). Cleans up stale PID file if process is dead."""
    if not os.path.exists(PID_FILE):
        return False, None

    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content or not content.isdigit():
                return False, None
            pid = int(content)
    except Exception:
        return False, None

    if _is_pid_alive(pid):
        return True, pid

    # Clean up stale PID file
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    return False, None


def start_watcher(project_dir: str | None = None, downloads_dir: str | None = None) -> dict[str, Any]:
    """Starts the watch_shopeesave.py background worker daemon."""
    running, pid = is_watcher_running()
    if running:
        return {
            "ok": True,
            "already_running": True,
            "pid": pid,
            "message": f"Watcher is already running (PID: {pid})"
        }

    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script_path = os.path.join(repo_dir, "watch_shopeesave.py")
    if not os.path.exists(script_path):
        return {"ok": False, "detail": f"Script not found: {script_path}"}

    python_bin = sys.executable

    proj_dir = (project_dir or "").strip() or DEFAULT_PROJECT_V1_DIR
    dl_dir = (downloads_dir or "").strip() or DEFAULT_DOWNLOADS_DIR

    cmd = [
        python_bin,
        script_path,
        "--project-dir", proj_dir,
        "--downloads-dir", dl_dir
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Allow time to write PID
        for _ in range(10):
            time.sleep(0.1)
            is_run, written_pid = is_watcher_running()
            if is_run:
                return {
                    "ok": True,
                    "pid": written_pid,
                    "project_dir": proj_dir,
                    "downloads_dir": dl_dir,
                    "message": f"ShopeeSave Watcher started successfully (PID: {written_pid})"
                }

        return {
            "ok": True,
            "pid": proc.pid,
            "project_dir": proj_dir,
            "downloads_dir": dl_dir,
            "message": f"ShopeeSave Watcher started (PID: {proc.pid})"
        }
    except Exception as e:
        return {"ok": False, "detail": f"Failed to start watcher: {e}"}


def stop_watcher() -> dict[str, Any]:
    """Stops the watch_shopeesave.py background worker daemon."""
    running, pid = is_watcher_running()
    if not running or not pid:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        return {"ok": True, "already_stopped": True, "message": "Watcher is not running"}

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        return {"ok": False, "detail": f"Failed to send SIGTERM to PID {pid}: {e}"}

    # Wait for process to exit
    for _ in range(15):
        time.sleep(0.1)
        if not _is_pid_alive(pid):
            break
    else:
        # Force kill if still running
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    return {"ok": True, "message": f"ShopeeSave Watcher stopped (PID: {pid})"}


def get_watcher_status() -> dict[str, Any]:
    """Returns current status and configuration of the watcher."""
    running, pid = is_watcher_running()
    logs_res = get_watcher_logs(max_lines=30)
    return {
        "ok": True,
        "running": running,
        "pid": pid,
        "default_project_dir": DEFAULT_PROJECT_V1_DIR,
        "default_downloads_dir": DEFAULT_DOWNLOADS_DIR,
        "log_file": LOG_FILE,
        "pid_file": PID_FILE,
        "last_logs": logs_res.get("logs", [])
    }


def get_watcher_logs(max_lines: int = 50) -> dict[str, Any]:
    """Reads the last N lines from the watcher log file."""
    if not os.path.exists(LOG_FILE):
        return {"ok": True, "logs": []}

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            tail_lines = [l.rstrip("\r\n") for l in lines[-max_lines:]]
            return {"ok": True, "logs": tail_lines}
    except Exception as e:
        return {"ok": False, "detail": f"Failed to read logs: {e}", "logs": []}


def clear_watcher_logs() -> dict[str, Any]:
    """Clears the watcher log file."""
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return {"ok": True, "message": "Log file cleared"}
    except Exception as e:
        return {"ok": False, "detail": f"Failed to clear log file: {e}"}
