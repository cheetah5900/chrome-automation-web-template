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

    def get(self) -> BrowserBot:
        with self._lock:
            if self._bot is None:
                # Find current selected profile's debug port dynamically
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

                self._bot = BrowserBot()
                ok = self._bot.start_browser(attach=True, port=port)
                if not ok:
                    raise RuntimeError(f"Failed to attach to Chrome on port {port}")
            return self._bot

    def close(self) -> None:
        with self._lock:
            if self._bot is not None:
                try:
                    self._bot.close_browser()
                except Exception:
                    pass
                self._bot = None

browser_manager = BrowserManager()

