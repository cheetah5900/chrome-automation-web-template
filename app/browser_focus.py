import subprocess
import sys


def focus_chrome_tab(url_part: str) -> None:
    """Best-effort: bring Chrome to front and activate a tab containing url_part.

    Selenium can switch window handles but may not visibly focus the tab.
    This is primarily for macOS where AppleScript can activate Chrome UI.
    """

    if not url_part:
        return
    if sys.platform != "darwin":
        return

    script = f"""
tell application "Google Chrome"
  activate
  set found to false
  repeat with w in windows
    set ti to 1
    repeat with t in tabs of w
      try
        set u to URL of t
      on error
        set u to ""
      end try
      if u contains "{url_part}" then
        set active tab index of w to ti
        set index of w to 1
        set found to true
        exit repeat
      end if
      set ti to ti + 1
    end repeat
    if found then exit repeat
  end repeat
end tell
"""

    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        # Best-effort only.
        return
