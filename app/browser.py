import threading
import json
from pathlib import Path
from browser_bot import BrowserBot

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULTS_FILE = BASE_DIR / "runtime" / "defaults.json"
PROFILES_FILE = BASE_DIR / "runtime" / "profiles.json"

class BrowserManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._bot: BrowserBot | None = None
        self._current_port: int | None = None

    def get(self, target_port: int | None = None) -> BrowserBot:
        with self._lock:
            # Resolve requested port
            port = target_port
            if port is None:
                port = 9222
                try:
                    if DEFAULTS_FILE.exists() and PROFILES_FILE.exists():
                        defaults = json.loads(DEFAULTS_FILE.read_text())
                        selected_name = defaults.get("selected_profile", "")
                        if selected_name:
                            profiles_data = json.loads(PROFILES_FILE.read_text())
                            profiles = profiles_data.get("profiles", [])
                            profile = next((p for p in profiles if p.get("name") == selected_name), None)
                            if profile:
                                port = int(profile.get("debug_port", 9222))
                except Exception as e:
                    print(f"Error loading selected profile port: {e}")

            if self._bot is not None:
                # Check if cached bot matches requested port
                if self._current_port != port:
                    print(f"BrowserManager port mismatch (cached={self._current_port}, requested={port}). Re-creating...")
                    try:
                        self._bot.close_browser()
                    except Exception:
                        pass
                    self._bot = None
                    self._current_port = None
                else:
                    try:
                        # Test session validity
                        _ = self._bot.driver.window_handles
                    except Exception:
                        print("Cached BrowserBot session is invalid. Re-creating...")
                        try:
                            self._bot.close_browser()
                        except Exception:
                            pass
                        self._bot = None
                        self._current_port = None

            if self._bot is None:
                self._bot = BrowserBot()
                ok = self._bot.start_browser(attach=True, port=port)
                if not ok:
                    from fastapi import HTTPException
                    self._bot = None
                    self._current_port = None
                    raise HTTPException(status_code=400, detail=f"ไม่สามารถเชื่อมต่อ Chrome Debug Port ({port}) ได้ กรุณาตรวจสอบว่าได้กด Launch Profile บนพอร์ต {port} แล้ว")
                self._current_port = port
            return self._bot

    def close(self) -> None:
        with self._lock:
            if self._bot is not None:
                try:
                    self._bot.close_browser()
                except Exception:
                    pass
                self._bot = None
                self._current_port = None

browser_manager = BrowserManager()

