from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx
import subprocess
import socket
from urllib.parse import quote_plus
import websockets
import asyncio

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
DEFAULTS_FILE = RUNTIME_DIR / "defaults.json"
PROFILES_FILE = RUNTIME_DIR / "profiles.json"
SETTINGS_FILE = RUNTIME_DIR / "settings.json"
PROMPTS_FILE = RUNTIME_DIR / "prompts.json"
REF_IMAGE_DEFAULT_FILE = RUNTIME_DIR / "ref_image_default.json"

RUNTIME_DIR.mkdir(exist_ok=True)


def _ensure_json(path: Path, default_obj: dict):
    if not path.exists():
        path.write_text(json.dumps(default_obj, indent=2))


_ensure_json(DEFAULTS_FILE, {"selected_profile": "", "theme": "sunset-glass"})
_ensure_json(PROFILES_FILE, {"selected_profile": "", "profiles": []})
_ensure_json(SETTINGS_FILE, {"openai_api_key": "", "gemini_api_key": "", "openrouter_api_key": ""})
_ensure_json(PROMPTS_FILE, {"prompts": [""]})
_ensure_json(REF_IMAGE_DEFAULT_FILE, {"reference_image": ""})

app = FastAPI(title="Chrome Automation Template")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProviderPayload(BaseModel):
    provider: str
    api_key: str


class SaveSettingsPayload(BaseModel):
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""


class CreateProfilePayload(BaseModel):
    name: str
    debug_port: int = 9222
    startup_urls: list[str] = []


class UpdateProfilePayload(BaseModel):
    old_name: str
    new_name: str
    debug_port: int = 9222
    startup_urls: list[str] = []


class SelectProfilePayload(BaseModel):
    name: str


class DeleteProfilePayload(BaseModel):
    name: str


class LaunchProfilePayload(BaseModel):
    name: str


class PromptDispatchPayload(BaseModel):
    prompt: str = ""
    targets: list[str]


class PromptConfigPayload(BaseModel):
    prompts: list[str]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def _profiles_data() -> dict:
    data = _read_json(PROFILES_FILE)
    data.setdefault("selected_profile", "")
    data.setdefault("profiles", [])
    return data


def _profile_base_dir() -> Path:
    return RUNTIME_DIR / "chrome-profiles"


def _normalize_urls(urls: list[str]) -> list[str]:
    out = []
    for url in urls:
        u = (url or "").strip()
        if not u:
            continue
        if not u.startswith(("http://", "https://")):
            u = "https://" + u
        out.append(u)
    return out


def _find_profile(name: str) -> dict:
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if p.get("name") == name), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _is_local_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.6):
            return True
    except Exception:
        return False


def _activate_chrome():
    script = """
    tell application "Google Chrome"
        activate
        repeat with w in windows
            if minimized of w is true then
                set minimized of w to false
            end if
        end repeat
    end tell
    """
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        try:
            subprocess.run(["open", "-a", "Google Chrome"], check=False)
        except Exception:
            pass


def _physical_switch_to_tab(url_part):
    import subprocess
    script = f"""
    tell application "Google Chrome"
        repeat with w in windows
            set tabIndex to 1
            repeat with t in tabs of w
                if URL of t contains "{url_part}" then
                    set active tab index of w to tabIndex
                    set index of w to 1
                    activate
                    return true
                end if
                set tabIndex to tabIndex + 1
            end repeat
        end repeat
        return false
    end tell
    """
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
        return "true" in res.stdout.lower()
    except Exception:
        return False


def _macos_file_exists(file_path):
    import subprocess
    escaped_path = file_path.replace('"', '\\"')
    script = f"""
    tell application "System Events"
        exists file "{escaped_path}"
    end tell
    """
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
        return "true" in res.stdout.lower()
    except Exception:
        return False


@app.get("/api/defaults")
def get_defaults():
    return _read_json(DEFAULTS_FILE)


@app.get("/api/settings")
def get_settings():
    return _read_json(SETTINGS_FILE)


@app.post("/api/settings")
def save_settings(payload: SaveSettingsPayload):
    data = payload.model_dump()
    _write_json(SETTINGS_FILE, data)
    return {"ok": True, "message": "Saved runtime/settings.json", "data": data}


@app.get("/api/config/reference-image/default")
def get_ref_image_default():
    return _read_json(REF_IMAGE_DEFAULT_FILE)


class RefImageDefaultPayload(BaseModel):
    reference_image: str


@app.post("/api/config/reference-image/default")
def save_ref_image_default(payload: RefImageDefaultPayload):
    data = payload.model_dump()
    _write_json(REF_IMAGE_DEFAULT_FILE, data)
    return {"ok": True, "message": "Saved default reference image", "data": data}


class RefImageVerifyPayload(BaseModel):
    path: str


@app.post("/api/config/reference-image/verify")
def verify_reference_image(payload: RefImageVerifyPayload):
    path = payload.path.strip()
    if not path:
        return {"exists": False, "message": "Reference image path is empty."}
    
    import os
    if os.path.exists(path) and os.path.isfile(path):
        return {"exists": True, "message": f"Success: Reference file exists at: {path}"}
    else:
        return {"exists": False, "message": f"Error: Reference file does not exist at: {path}"}


@app.get("/api/profiles")
def list_profiles():
    return _profiles_data()


@app.get("/api/profiles/status")
def get_profile_status(port: int = 9222):
    return {"online": _is_local_port_open(port)}


@app.post("/api/profiles/create")
def create_profile(payload: CreateProfilePayload):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required")

    base = _profile_base_dir()
    base.mkdir(parents=True, exist_ok=True)
    profile_dir = base / name
    profile_dir.mkdir(parents=True, exist_ok=True)

    data = _profiles_data()
    
    # Check duplication of name
    if any(p.get("name").lower() == name.lower() for p in data["profiles"]):
        raise HTTPException(status_code=400, detail=f"Profile name '{name}' already exists.")

    # Check duplication of port
    port = int(payload.debug_port)
    if any(int(p.get("debug_port", 0)) == port for p in data["profiles"]):
        raise HTTPException(status_code=400, detail=f"Port {port} is already used by another profile.")

    startup_urls = _normalize_urls(payload.startup_urls)
    profile_obj = {
        "name": name,
        "path": str(profile_dir),
        "debug_port": port,
        "startup_urls": startup_urls,
    }
    data["profiles"].append(profile_obj)

    if not data.get("selected_profile"):
        data["selected_profile"] = name

    _write_json(PROFILES_FILE, data)
    _write_json(DEFAULTS_FILE, {"selected_profile": data["selected_profile"], "theme": "sunset-glass"})
    return {"ok": True, "profile": profile_obj}


@app.post("/api/profiles/delete")
def delete_profile(payload: DeleteProfilePayload):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required")
        
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if p.get("name").lower() == name.lower()), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    # Prevent deleting if it is the only profile left
    if len(data["profiles"]) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only profile. Please add another profile first.")
        
    # Update selected profile if we are deleting the active one
    if data.get("selected_profile") == name:
        # Select another profile
        remaining = [p for p in data["profiles"] if p.get("name").lower() != name.lower()]
        data["selected_profile"] = remaining[0]["name"] if remaining else ""
    
    data["profiles"] = [p for p in data["profiles"] if p.get("name").lower() != name.lower()]
    _write_json(PROFILES_FILE, data)
    
    # Clean up local profile directory under runtime/chrome-profiles (but NEVER touch the default everyday path!)
    profile_path_str = profile.get("path", "")
    if "chrome-profiles" in profile_path_str:
        profile_path = Path(profile_path_str)
        if profile_path.exists():
            import shutil
            try:
                shutil.rmtree(profile_path)
            except Exception:
                pass
                
    defaults = json.loads(DEFAULTS_FILE.read_text())
    if defaults.get("selected_profile") == name:
        defaults["selected_profile"] = data["selected_profile"]
        _write_json(DEFAULTS_FILE, defaults)
        
    return {"ok": True, "message": f"Profile '{name}' deleted successfully.", "next_profile": data["selected_profile"]}


@app.post("/api/profiles/update")
def update_profile(payload: UpdateProfilePayload):
    old_name = payload.old_name.strip()
    new_name = payload.new_name.strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name are required")

    data = _profiles_data()
    profile = next((p for p in data["profiles"] if p.get("name") == old_name), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Check duplication of name
    if old_name.lower() != new_name.lower():
        if any(p.get("name").lower() == new_name.lower() for p in data["profiles"]):
            raise HTTPException(status_code=400, detail=f"Profile name '{new_name}' already exists.")

    # Check duplication of port
    port = int(payload.debug_port)
    for p in data["profiles"]:
        if p.get("name") != old_name and int(p.get("debug_port", 0)) == port:
            raise HTTPException(status_code=400, detail=f"Port {port} is already used by another profile.")

    # Perform filesystem rename of the directory
    old_dir = Path(profile["path"])
    new_dir = old_dir.parent / new_name

    try:
        if old_dir.exists() and old_dir != new_dir:
            old_dir.rename(new_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename directory: {e}")

    # Update profile fields
    profile["name"] = new_name
    profile["path"] = str(new_dir)
    profile["debug_port"] = port
    profile["startup_urls"] = _normalize_urls(payload.startup_urls)

    if data.get("selected_profile") == old_name:
        data["selected_profile"] = new_name

    _write_json(PROFILES_FILE, data)

    defaults = _read_json(DEFAULTS_FILE)
    if defaults.get("selected_profile") == old_name:
        defaults["selected_profile"] = new_name
        _write_json(DEFAULTS_FILE, defaults)

    return {"ok": True, "profile": profile}


@app.post("/api/profiles/select")
def select_profile(payload: SelectProfilePayload):
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if p.get("name") == payload.name), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    data["selected_profile"] = payload.name
    _write_json(PROFILES_FILE, data)
    _write_json(DEFAULTS_FILE, {"selected_profile": payload.name, "theme": "sunset-glass"})
    return {"ok": True, "selected_profile": payload.name}


@app.post("/api/profiles/launch")
async def launch_profile(payload: LaunchProfilePayload):
    profile = _find_profile(payload.name)

    profile_path = profile["path"]
    debug_port = int(profile.get("debug_port", 9222))
    startup_urls = _normalize_urls(profile.get("startup_urls", []))

    if _is_local_port_open(debug_port):
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"http://127.0.0.1:{debug_port}/json")
                if r.status_code == 200:
                    urls_to_open = startup_urls if startup_urls else ["https://google.com"]
                    for url in urls_to_open:
                        await client.get(f"http://127.0.0.1:{debug_port}/json/new?{url}")
                    _activate_chrome()
                    return {
                        "ok": True,
                        "already_running": True,
                        "restored": True,
                        "message": f"Chrome ที่ port {debug_port} เปิดอยู่แล้ว (ทำการเปิดแท็บใหม่บนหน้าจอ)",
                        "debug_port": debug_port,
                        "profile_path": profile_path,
                        "startup_urls": startup_urls,
                    }
        except Exception:
            pass

    chrome_binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # Launch without --user-data-dir if it is the Everyday Chrome profile, to load untouched daily sessions directly
    if profile_path == "/Users/litarcopperkaikem/Library/Application Support/Google/Chrome":
        cmd = [
            chrome_binary,
            f"--remote-debugging-port={debug_port}",
            *startup_urls,
        ]
    else:
        cmd = [
            chrome_binary,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile_path}",
            *startup_urls,
        ]

    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail="ไม่พบ Google Chrome ที่ /Applications/Google Chrome.app (macOS)",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"เปิด Chrome ไม่สำเร็จ: {e}")

    return {
        "ok": True,
        "already_running": False,
        "message": f"เปิด Google Chrome ด้วย debug port {debug_port} แล้ว",
        "debug_port": debug_port,
        "profile_path": profile_path,
        "startup_urls": startup_urls,
    }


@app.post("/api/profiles/close")
def close_profile():
    try:
        browser_manager.close()
        return {"ok": True, "message": "Browser profile disconnected successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed closing browser: {e}")



async def _automate_tab(debug_port: int, target: str, prompt: str):
    target_map = {
        "chatgpt": "https://chatgpt.com/",
        "gemini": "https://gemini.google.com/app",
        "claude": "https://claude.ai/",
    }
    target_url = target_map.get(target)
    if not target_url:
        return

    safe_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

    js_chatgpt = f"""
    (function() {{
        const el = document.querySelector('#prompt-textarea > p');
        if (el) {{
            el.textContent = "{safe_prompt}";
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            setTimeout(() => {{
                const sendBtn = document.querySelector('button[data-testid="send-button"]') || 
                                document.querySelector('button[aria-label="Send prompt"]');
                if (sendBtn) {{
                    sendBtn.click();
                }} else {{
                    const enterEvent = new KeyboardEvent('keydown', {{
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true
                    }});
                    el.dispatchEvent(enterEvent);
                }}
            }}, 150);
            return true;
        }}
        return false;
    }})();
    """

    js_gemini = f"""
    (function() {{
        const exactSelector = `#app-root > main > side-navigation-v2 > bard-sidenav-container > bard-sidenav-content > div > div > div > chat-window > div > input-container > fieldset > input-area-v2 > div > div > div.ng-tns-c1080643930-4.single-line-format.ng-star-inserted > div > div > div > rich-textarea > div.ql-editor.ql-blank.textarea.new-input-ui > p`;
        const fallbackSelector = `rich-textarea p, div.ql-editor p`;
        let el = document.querySelector(exactSelector);
        if (!el) {{
            el = document.querySelector(fallbackSelector);
        }}
        if (el) {{
            el.textContent = "{safe_prompt}";
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            setTimeout(() => {{
                const sendBtn = document.querySelector('button[aria-label="Send message"]') || 
                                document.querySelector('.send-button-container button') ||
                                document.querySelector('button.send-button');
                if (sendBtn) {{
                    sendBtn.click();
                }} else {{
                    const enterEvent = new KeyboardEvent('keydown', {{
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true
                    }});
                    el.dispatchEvent(enterEvent);
                }}
            }}, 150);
            return true;
        }}
        return false;
    }})();
    """

    js_claude = f"""
    (function() {{
        const firstSelector = `#main-content > div.flex.h-full.flex-col > div > main > div.top-5.z-10.mx-auto.w-full.max-w-2xl > div:nth-child(2) > div:nth-child(1) > div > fieldset > div.relative > div.\\!box-content.flex.flex-col.bg-bg-000.mx-2.md\\:mx-0.items-stretch.transition-all.duration-200.relative.z-10.rounded-\\[20px\\].cursor-text.relative.z-\\[1\\].border.border-transparent.md\\:w-full.shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/3\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-300\\)\\/0\\.15\\)\\].hover\\:shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/3\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-200\\)\\/0\\.3\\)\\].focus-within\\:shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/7\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-200\\)\\/0\\.3\\)\\].hover\\:focus-within\\:shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/7\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-200\\)\\/0\\.3\\)\\] > div.flex.flex-col.m-3\\.5.gap-3 > div.relative.font-large > div.w-full.overflow-y-auto.break-words.transition-opacity.duration-200.font-large.max-h-96.min-h-\\[3rem\\].pl-\\[6px\\].pt-\\[6px\\].\\[\\&_\\.is-editor-empty\\]\\:before\\:\\!content-\\[\\'\\'\\]`;
        const followUpSelector = `#main-content > div > div.h-full.flex.flex-col.overflow-hidden.md\\:pt-\\[var\\(--df-header-h\\,0px\\)\\].print\\:h-auto.print\\:overflow-visible > div > div > div > div.sticky.bottom-0.mx-auto.w-full.pt-6.print\\:hidden.z-\\[5\\] > div:nth-child(2) > fieldset > div.relative > div.\\!box-content.flex.flex-col.bg-bg-000.mx-2.md\\:mx-0.items-stretch.transition-all.duration-200.relative.z-10.rounded-\\[20px\\].cursor-text.relative.z-\\[1\\].border.border-transparent.md\\:w-full.shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/3\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-300\\)\\/0\\.15\\)\\].hover\\:shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/3\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-200\\)\\/0\\.3\\)\\].focus-within\\:shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/7\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-200\\)\\/0\\.3\\)\\].hover\\:focus-within\\:shadow-\\[0_0\\.25rem_1\\.25rem_hsl\\(var\\(--always-black\\)\\/7\\.5\\%\\)\\,0_0_0_0\\.5px_hsla\\(var\\(--border-200\\)\\/0\\.3\\)\\] > div.flex.flex-col.m-3\\.5.gap-3 > div.relative.font-large > div > div > p`;
        
        let el = null;
        try {{
            el = document.querySelector(firstSelector) || document.querySelector(followUpSelector);
        }} catch(err) {{
            // Ignore syntax errors in long custom selectors
        }}
        
        if (!el) {{
            el = document.querySelector('div.ProseMirror p') || 
                 document.querySelector('div.ProseMirror') ||
                 document.querySelector('[contenteditable="true"] p') ||
                 document.querySelector('[contenteditable="true"]');
        }}
        
        if (el) {{
            el.innerHTML = "<p>{safe_prompt}</p>";
            if (el.tagName === 'P') {{
                el.textContent = "{safe_prompt}";
            }}
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            setTimeout(() => {{
                const sendBtn = document.querySelector('button[aria-label="Send Message"]') || 
                                document.querySelector('button[aria-label="Send message"]') ||
                                document.querySelector('button.bg-text-000') ||
                                document.querySelector('button[disabled="false"]');
                if (sendBtn) {{
                    sendBtn.click();
                }} else {{
                    const enterEvent = new KeyboardEvent('keydown', {{
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true
                    }});
                    el.dispatchEvent(enterEvent);
                }}
            }}, 150);
            return true;
        }}
        return false;
    }})();
    """

    js_code = js_chatgpt if target == "chatgpt" else (js_gemini if target == "gemini" else js_claude)

    # Poll until success or timeout (15 seconds)
    for _ in range(30):
        await asyncio.sleep(0.5)
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"http://127.0.0.1:{debug_port}/json")
                if r.status_code == 200:
                    tabs = r.json()
                    ws_url = None
                    for tab in tabs:
                        tab_url = tab.get("url", "")
                        if target == "gemini" and ("gemini.google.com/app" in tab_url or "gemini.google.com" in tab_url):
                            ws_url = tab.get("webSocketDebuggerUrl")
                            break
                        elif target == "chatgpt" and ("chatgpt.com" in tab_url):
                            ws_url = tab.get("webSocketDebuggerUrl")
                            break
                        elif target == "claude" and ("claude.ai" in tab_url):
                            ws_url = tab.get("webSocketDebuggerUrl")
                            break
                    
                    if ws_url:
                        async with websockets.connect(ws_url) as websocket:
                            payload = {
                                "id": 1,
                                "method": "Runtime.evaluate",
                                "params": {
                                    "expression": js_code,
                                    "returnByValue": True
                                }
                            }
                            await websocket.send(json.dumps(payload))
                            res_raw = await websocket.recv()
                            res = json.loads(res_raw)
                            result = res.get("result", {}).get("result", {})
                            if result.get("value") is True:
                                break
        except Exception:
            pass


@app.post("/api/prompt/dispatch")
async def dispatch_prompt(payload: PromptDispatchPayload):
    targets = [t.lower().strip() for t in payload.targets if t and t.strip()]
    if not targets:
        raise HTTPException(status_code=400, detail="targets is required")

    defaults = _read_json(DEFAULTS_FILE)
    selected_profile_name = defaults.get("selected_profile", "")
    debug_port = 9222
    profile_path = ""
    if selected_profile_name:
        try:
            profile = _find_profile(selected_profile_name)
            debug_port = int(profile.get("debug_port", 9222))
            profile_path = profile.get("path", "")
        except Exception:
            pass

    target_map = {
        "chatgpt": "https://chatgpt.com/",
        "gemini": "https://gemini.google.com/app",
        "claude": "https://claude.ai/",
    }

    opened = []
    skipped = []
    already_open_targets = []
    fallback_urls = []

    port_open = _is_local_port_open(debug_port)

    if port_open:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"http://127.0.0.1:{debug_port}/json")
                if r.status_code == 200:
                    tabs = r.json()
                    
                    for t in targets:
                        target_url = target_map.get(t)
                        if not target_url:
                            skipped.append(t)
                            continue
                        
                        existing_tab = None
                        for tab in tabs:
                            tab_url = tab.get("url", "")
                            if t == "gemini" and ("gemini.google.com/app" in tab_url or "gemini.google.com" in tab_url):
                                existing_tab = tab
                                break
                            elif t == "chatgpt" and ("chatgpt.com" in tab_url):
                                existing_tab = tab
                                break
                            elif t == "claude" and ("claude.ai" in tab_url):
                                existing_tab = tab
                                break
                        
                        if existing_tab:
                            tab_id = existing_tab.get("id")
                            if tab_id:
                                await client.get(f"http://127.0.0.1:{debug_port}/json/activate/{tab_id}")
                            already_open_targets.append(t)
                        else:
                            # Open tab by calling Chrome binary with user data dir to bypass CDP URL encoding issues
                            chrome_binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                            cmd = [
                                chrome_binary,
                                f"--user-data-dir={profile_path}",
                                target_url
                            ]
                            subprocess.Popen(cmd)
                            opened.append({"target": t, "url": target_url, "via": "chrome_ipc"})
                    
                    if opened or already_open_targets:
                        _activate_chrome()
                else:
                    port_open = False
        except Exception:
            port_open = False

    if port_open and payload.prompt.strip():
        for t in targets:
            if t in ["chatgpt", "gemini", "claude"]:
                asyncio.create_task(_automate_tab(debug_port, t, payload.prompt.strip()))

    if not port_open:
        for t in targets:
            target_url = target_map.get(t)
            if target_url:
                fallback_urls.append({"target": t, "url": target_url, "via": "fallback"})
            else:
                skipped.append(t)

    return {
        "ok": True,
        "opened": opened,
        "already_open": already_open_targets,
        "fallback": fallback_urls,
        "skipped": skipped
    }


@app.get("/api/prompts")
def get_prompts():
    data = _read_json(PROMPTS_FILE)
    prompts = data.get("prompts") if isinstance(data, dict) else []
    if not isinstance(prompts, list):
        prompts = []
    return {"prompts": [str(p) for p in prompts]}


@app.post("/api/prompts")
def save_prompts(payload: PromptConfigPayload):
    cleaned = [str(p) for p in payload.prompts]
    _write_json(PROMPTS_FILE, {"prompts": cleaned})
    return {"ok": True, "count": len(cleaned)}


@app.post("/api/test-provider")
async def test_provider(payload: ProviderPayload):
    provider = payload.provider.lower().strip()
    key = payload.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key is required")

    async with httpx.AsyncClient(timeout=25) as client:
        if provider == "openai":
            headers = {"Authorization": f"Bearer {key}"}
            r = await client.get("https://api.openai.com/v1/models", headers=headers)
            return {"ok": r.status_code == 200, "status_code": r.status_code, "provider": "openai"}

        if provider == "gemini":
            r = await client.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key})
            return {"ok": r.status_code == 200, "status_code": r.status_code, "provider": "gemini"}

        if provider == "openrouter":
            headers = {
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://localhost",
                "X-Title": "chrome-automation-template",
            }
            r = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            return {"ok": r.status_code == 200, "status_code": r.status_code, "provider": "openrouter"}

    raise HTTPException(status_code=400, detail="Provider must be one of: openai, gemini, openrouter")


# --- DDCM Browser Helper Integration ---

from typing import Any
from fastapi.responses import StreamingResponse
import os

from app.logging_bus import LogBus, heartbeat_every, sse_format
from app.browser import browser_manager
from app.workflow import (
    step10_create_preview_sheet,
    step11_canva_export_all_bot,
    step11_canva_export_bot,
    step15_etsy_listing_bot,
    step12_unzip_downloads,
    step13_download_to_local,
    step14_local_to_remote,
    step14_local_to_remote_no_elements,
    step2_create_folders,
    step3_gemini_gen_full_bot,
    step4_download_images_bot,
    step4_chatgpt_download_images_bot,
    step6_classify_resolution,
    step8_downloads_images_to_local,
    step9_elements_to_local,
)

log_bus = LogBus()

CONFIG_FILE = "config_win.json" if os.name == "nt" else "config_mac.json"


def _default_config() -> dict[str, Any]:
    if os.name == "nt":
        return {
            "folder_name": "",
            "element_name": "Songkran",
            "element_path": r"C:\Files\Project\local DDCM\Elements",
            "local_path": r"C:\Files\Project\local DDCM",
            "remote_path": r"G:\My Drive\Projects\DDCM\Cliparts DDCM",
            "watermark_path": r"C:\Files\Project\local DDCM\Watermark.png",
            "first_preview_watermark_path": "",
            "single_count": "12",
            "companion_count": "12",
            "elements_count": "5",
            "png_pages": "1-4",
            "jpg_pages": "6-9",
            "pdf_pages": "10",
            "primary_color": "Red",
            "secondary_color": "Gray",
            "focus_browser_tabs": False,
            "canva_design_url_part": "",
        }

    h = os.path.expanduser("~")
    return {
        "folder_name": "",
        "element_name": "Songkran",
        "element_path": os.path.join(h, "Documents/DDCM/Elements"),
        "local_path": os.path.join(h, "Documents/DDCM"),
        "remote_path": "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Projects/DDCM/Cliparts DDCM",
        "watermark_path": os.path.join(h, "Documents/DDCM/Watermark.png"),
        "first_preview_watermark_path": "",
        "single_count": "12",
        "companion_count": "12",
        "elements_count": "5",
        "png_pages": "1-4",
        "jpg_pages": "6-9",
        "pdf_pages": "10",
        "primary_color": "Red",
        "secondary_color": "Gray",
        "focus_browser_tabs": False,
        "canva_design_url_part": "",
    }


def log(msg: str) -> None:
    log_bus.publish(msg)


def _should_focus_tabs() -> bool:
    try:
        import json

        if not os.path.exists(CONFIG_FILE):
            return False
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return bool(data.get("focus_browser_tabs"))
    except Exception:
        return False


def _get_config_value(key: str, default: Any = None) -> Any:
    try:
        import json

        if not os.path.exists(CONFIG_FILE):
            return default
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data.get(key, default)
    except Exception:
        return default


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    defaults = _default_config()
    if not os.path.exists(CONFIG_FILE):
        return defaults
    try:
        import json

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            return {**defaults, **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed reading config: {e}")


@app.post("/api/config")
def set_config(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        import json

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed writing config: {e}")


@app.post("/api/config/set-default")
def set_default(payload: dict[str, Any]) -> dict[str, Any]:
    key = str(payload.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    value = payload.get("value")
    try:
        import json

        data: dict[str, Any] = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        data[key] = value
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed writing config: {e}")


@app.get("/logs")
def logs() -> StreamingResponse:
    sid, q = log_bus.subscribe()

    def gen():
        try:
            yield sse_format("connected", event="status")
            heartbeats = heartbeat_every(15.0)
            while True:
                try:
                    msg = q.get(timeout=0.25)
                    yield sse_format(msg, event="log")
                except Exception:
                    if next(heartbeats):
                        yield sse_format("hb", event="ping")
        finally:
            log_bus.unsubscribe(sid)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/step/1")
def step1(payload: dict[str, Any]) -> dict[str, Any]:
    log("Step 1: Config is handled in the UI. Ready.")
    return {"ok": True}


@app.post("/api/step/2")
def step2(payload: dict[str, Any]) -> dict[str, Any]:
    folder_name = str(payload.get("folder_name") or "").strip()
    local_path = str(payload.get("local_path") or "").strip()
    remote_path = str(payload.get("remote_path") or "").strip()
    if not all([folder_name, local_path, remote_path]):
        raise HTTPException(status_code=400, detail="folder_name/local_path/remote_path required")
    try:
        step2_create_folders(folder_name, local_path, remote_path, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/3")
def step3(payload: dict[str, Any]) -> dict[str, Any]:
    _activate_chrome()
    custom_prompt = payload.get("prompt")
    if custom_prompt:
        try:
            import time
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            bot = browser_manager.get()
            driver = bot.driver
            
            # Check if Gemini is open, if not open a new tab natively via webdriver protocol (immune to popup blockers)
            if not bot.switch_to_tab_containing("gemini.google.com"):
                log("Gemini tab not found, opening natively in new tab...")
                try:
                    driver.switch_to.new_window('tab')
                    driver.get("https://gemini.google.com/app")
                    time.sleep(3.0)
                except Exception:
                    driver.get("https://gemini.google.com/app")
                    time.sleep(3.0)
                    
            # Physically switch to the Gemini tab in macOS Chrome UI!
            _physical_switch_to_tab("gemini.google.com")
            _activate_chrome()
            time.sleep(0.5)
            
            # Strictly verify we are on the Gemini page before sending input!
            if "gemini.google.com" not in driver.current_url:
                raise RuntimeError("Failed to switch to Gemini tab. Please open it manually.")
            
            input_strats = [
                "//div[contains(@class, 'ql-editor') and @contenteditable='true']",
                "//rich-textarea//div[@contenteditable='true']",
                "//div[@contenteditable='true' and @role='textbox']",
            ]
            box = None
            for s in input_strats:
                try:
                    tmp = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, s)))
                    if tmp.is_displayed():
                        box = tmp
                        break
                except Exception:
                    continue
            if not box:
                raise RuntimeError("Could not find Gemini input box. Please make sure you are logged into Gemini.")
            
            try:
                box.click()
            except Exception:
                driver.execute_script("arguments[0].click();", box)
                
            driver.execute_script(
                "if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }",
                box
            )
            box.send_keys(custom_prompt)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", box)
            
            # Check if reference image is provided
            reference_image = payload.get("reference_image", "").strip()
            import os
            if not reference_image:
                log("Gemini prompt placed successfully! Skipping file attachment (Reference path is empty).")
                return {"ok": True}
                
            # If reference image is specified, verify file existence via AppleScript. If not there, stop and raise error.
            if not _macos_file_exists(reference_image):
                raise RuntimeError(f"Reference image file not found on macOS: {reference_image}")
                
            # Helper local function to click with 3 retries and 5s interval
            def click_element_with_retry(selectors, name):
                combined_selector = ", ".join(selectors)
                for attempt in range(3):
                    log(f"Attempt {attempt + 1}/3 to locate and click {name}...")
                    try:
                        el = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, combined_selector)))
                        if el.is_displayed():
                            try:
                                el.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", el)
                            log(f"Successfully clicked {name}!")
                            return True
                    except Exception as e:
                        pass
                    
                    if attempt < 2:
                        log(f"Failed to click {name}. Waiting 1.5 seconds before next attempt...")
                        time.sleep(1.5)
                
                log(f"CRITICAL ERROR: Failed to click {name} after 3 attempts.")
                return False

            def upload_macos_file_dialog(file_path):
                import subprocess
                escaped_path = file_path.replace('"', '\\"')
                script = f"""
                set the clipboard to "{escaped_path}"
                delay 0.5
                tell application "System Events"
                    keystroke "g" using {{command down, shift down}}
                    delay 1.0
                    keystroke "v" using {{command down}}
                    delay 1.0
                    keystroke return
                    delay 1.0
                    keystroke return
                end tell
                """
                try:
                    subprocess.run(["osascript", "-e", script], check=False)
                    return True
                except Exception as e:
                    log(f"AppleScript dialog input failed: {e}")
                    return False

            # Step 1: Click upload menu button
            time.sleep(1.0)
            sel1_exact = "#app-root > main > side-navigation-v2 > bard-sidenav-container > bard-sidenav-content > div > div > div > chat-window > div > input-container > fieldset > input-area-v2 > div > div > div.leading-actions-wrapper.ng-tns-c5435433-4.has-model-picker.ng-star-inserted > simplified-input-menu > div > span > gem-icon-button > button"
            sel1_fallbacks = [
                sel1_exact,
                "simplified-input-menu button",
                "input-area-v2 .leading-actions-wrapper button",
                "button[aria-label='Upload file']",
                "button[aria-label='Attach files']"
            ]
            
            if click_element_with_retry(sel1_fallbacks, "Gemini upload menu button"):
                log("Opened Gemini upload menu. Proceeding to uploader...")
                time.sleep(1.2)
                
                # Step 2: Click the image/file uploader button to open system file modal
                sel2_exact_0 = "#cdk-overlay-0 > mat-card > mat-action-list > div:nth-child(1) > uploader > div > mat-action-list > images-files-uploader > button"
                sel2_exact_3 = "#cdk-overlay-3 > mat-card > mat-action-list > div:nth-child(1) > uploader > div > mat-action-list > images-files-uploader > button"
                sel2_fallbacks = [
                    "images-files-uploader button",
                    "mat-action-list images-files-uploader button",
                    "[id^='cdk-overlay-'] mat-card images-files-uploader button",
                    sel2_exact_0,
                    sel2_exact_3,
                    "uploader button"
                ]
                
                uploader_clicked = False
                try:
                    uploader_clicked = click_element_with_retry(sel2_fallbacks, "Gemini uploader button")
                except Exception as click_err:
                    log(f"Warning: Exception encountered locating uploader button: {click_err}")
                
                if uploader_clicked:
                    log("File open dialog triggered! Activating AppleScript folder path sheet...")
                    # Focus Chrome
                    _activate_chrome()
                    time.sleep(0.5)
                    # Trigger AppleScript keys injection
                    if upload_macos_file_dialog(reference_image):
                        log("Reference image uploaded successfully via macOS File Dialog AppleScript automation!")
                        
                        log("Waiting 5 seconds for file attachment processing...")
                        time.sleep(5.0)
                        
                        active_selector = "#app-root > main > side-navigation-v2 > bard-sidenav-container > bard-sidenav-content > div > div > div > chat-window > div > input-container > fieldset > input-area-v2 > div > div > div.trailing-actions-wrapper.ng-tns-c5435433-4.with-model-picker > div.input-buttons-wrapper-bottom.ng-tns-c5435433-4.persistent-mic > div.mat-mdc-tooltip-trigger.send-button-container.ng-tns-c5435433-4.inner.lm-enabled.persistent-mic.ng-star-inserted.visible"
                        
                        log("Waiting for the Send button to become active...")
                        stop_button_xpath = (
                            "//button[@aria-label='หยุดคำตอบ'] | "
                            "//button[contains(@aria-label, 'Stop')] | "
                            "//button[.//mat-icon[@fonticon='stop' or @data-mat-icon-name='stop' or contains(@class, 'stop')]]"
                        )
                        
                        send_success = False
                        
                        for click_attempt in range(3):
                            try:
                                send_btn = WebDriverWait(driver, 10).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, active_selector))
                                )
                                log(f"Send button found! Click attempt {click_attempt + 1}/3...")
                                try:
                                    send_btn.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", send_btn)
                                log("Send button clicked, verifying start of generation...")
                            except Exception as click_err:
                                log(f"Send button click failed or not clickable: {click_err}. Trying Enter key on input box...")
                                try:
                                    box.send_keys(Keys.ENTER)
                                except Exception:
                                    pass
                            
                            # Verify if it went to 'onprocess' state (Stop button visible) within 5 seconds
                            for sec in range(5):
                                try:
                                    stop_buttons = driver.find_elements(By.XPATH, stop_button_xpath)
                                    visible_stop_button = False
                                    for btn in stop_buttons:
                                        if btn.is_displayed():
                                            visible_stop_button = True
                                            break
                                    if visible_stop_button:
                                        log("Confirmed: Generation is onprocess!")
                                        send_success = True
                                        break
                                except Exception:
                                    pass
                                time.sleep(1.0)
                            
                            if send_success:
                                break
                            else:
                                log("Warning: Generation did not start yet. Retrying send...")
                                
                        if not send_success:
                            raise RuntimeError("Failed to start generation: Send button clicked but 'onprocess' stop button did not appear within 5 seconds.")
                            
                        # Wait until generation is completed (Stop button disappears)
                        import random
                        delay_seconds = random.uniform(60.0, 135.0)
                        log(f"Waiting {delay_seconds:.1f} seconds (random 1.00 - 2.15 mins) before starting status checks...")
                        time.sleep(delay_seconds)
                        log("Checking if Stop button has disappeared...")
                        start_time = time.time()
                        generation_timeout = 180.0  # 3 minutes maximum wait
                        
                        while time.time() - start_time < generation_timeout:
                            try:
                                stop_buttons = driver.find_elements(By.XPATH, stop_button_xpath)
                                visible_stop_button = False
                                for btn in stop_buttons:
                                    if btn.is_displayed():
                                        visible_stop_button = True
                                        break
                                if not visible_stop_button:
                                    log("Stop button has disappeared! Generation completed.")
                                    break
                            except Exception:
                                log("Stop button no longer found. Generation completed.")
                                break
                            time.sleep(1.5)
                    else:
                        log("Warning: AppleScript keys injection encountered an issue.")
                else:
                    log("Warning: Failed to open system uploader modal after 3 attempts.")
            else:
                log("Warning: Failed to open Gemini upload menu after 3 attempts.")
                
            return {"ok": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/3-chatgpt")
def step3_chatgpt(payload: dict[str, Any]) -> dict[str, Any]:
    _activate_chrome()
    custom_prompt = payload.get("prompt")
    if custom_prompt:
        try:
            import time
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            bot = browser_manager.get()
            driver = bot.driver
            
            # Check if ChatGPT is open
            if not bot.switch_to_tab_containing("chatgpt.com"):
                log("ChatGPT tab not found, opening natively in new tab...")
                try:
                    driver.switch_to.new_window('tab')
                    driver.get("https://chatgpt.com/")
                    time.sleep(3.0)
                except Exception:
                    driver.get("https://chatgpt.com/")
                    time.sleep(3.0)
            
            # Physically switch to the ChatGPT tab in macOS Chrome UI!
            _physical_switch_to_tab("chatgpt.com")
            _activate_chrome()
            time.sleep(0.5)
            
            # Strictly verify we are on the ChatGPT page before sending input!
            if "chatgpt.com" not in driver.current_url:
                raise RuntimeError("Failed to switch to ChatGPT tab. Please open it manually.")
            
            input_strats = [
                "//div[@id='prompt-textarea']",
                "//textarea[@id='prompt-textarea']",
                "//div[@contenteditable='true']",
            ]
            box = None
            for s in input_strats:
                try:
                    tmp = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, s)))
                    if tmp.is_displayed():
                        box = tmp
                        break
                except Exception:
                    continue
            if not box:
                raise RuntimeError("Could not find ChatGPT input box. Please make sure the tab is fully loaded.")
            
            try:
                box.click()
            except Exception:
                driver.execute_script("arguments[0].click();", box)
                
            driver.execute_script(
                "if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }",
                box,
            )
            driver.execute_script("arguments[0].focus();", box)
            box.send_keys(custom_prompt)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", box)
            
            # ChatGPT File Upload & Submission automation
            reference_image = payload.get("reference_image", "").strip()
            import os
            if not reference_image:
                log("ChatGPT prompt placed successfully! Skipping file attachment (Reference path is empty).")
                log("Submitting prompt to ChatGPT...")
                try:
                    submit_btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "#composer-submit-button"))
                    )
                    submit_btn.click()
                except Exception:
                    driver.execute_script("document.querySelector('#composer-submit-button').click();")
                
                log("Waiting for ChatGPT to start generating (onprocess)...")
                stop_xpath = (
                    "//button[@id='composer-submit-button' and (@aria-label='Stop answering' or @data-testid='stop-button')]"
                )
                log("Waiting 1.30 minutes (90 seconds) before starting status checks...")
                time.sleep(90.0)
                
                start_time = time.time()
                while time.time() - start_time < 90.0:
                    try:
                        stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                        visible = any(b.is_displayed() for b in stop_btns)
                        if not visible:
                            log("ChatGPT generation completed successfully!")
                            break
                    except Exception:
                        log("ChatGPT generation completed successfully!")
                        break
                    time.sleep(1.5)
                return {"ok": True}

            if not _macos_file_exists(reference_image):
                raise RuntimeError(f"Reference image file not found on macOS: {reference_image}")

            # 3. press Cmd + U directly to open file modal
            log("Sending Cmd + U keystroke via System Events directly to trigger file modal...")
            _activate_chrome()
            time.sleep(1.0)
            
            import subprocess
            cmd_u_script = """
            tell application "System Events"
                key code 32 using command down
            end tell
            """
            try:
                subprocess.run(["osascript", "-e", cmd_u_script], check=False)
            except Exception as e:
                log(f"Keystroke Cmd + U failed: {e}")
                
            log("Waiting 1.0 second for file modal to fully open...")
            time.sleep(1.0)
            
            # 5. use the same flow to select a file like the Gemini one
            def upload_macos_file_dialog(file_path):
                escaped_path = file_path.replace('"', '\\"')
                script = f"""
                set the clipboard to "{escaped_path}"
                tell application "System Events"
                    keystroke "g" using {{command down, shift down}}
                    delay 1.0
                    keystroke "v" using {{command down}}
                    delay 1.0
                    keystroke return
                    delay 1.0
                    keystroke return
                end tell
                """
                try:
                    subprocess.run(["osascript", "-e", script], check=False)
                    return True
                except Exception as e:
                    log(f"AppleScript dialog input failed: {e}")
                    return False

            log("Triggering AppleScript folder path sheet to select file...")
            if upload_macos_file_dialog(reference_image):
                log("Reference image uploaded successfully via macOS File Dialog AppleScript automation!")
            else:
                log("Warning: AppleScript keys injection encountered an issue.")
                
            log("Waiting 5 seconds for file upload to settle...")
            time.sleep(5.0)
            
            # 6. Click at '#composer-submit-button' to submit
            log("Locating and clicking ChatGPT submit button (#composer-submit-button)...")
            submit_success = False
            for click_attempt in range(3):
                try:
                    submit_btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "#composer-submit-button"))
                    )
                    submit_btn.click()
                except Exception:
                    try:
                        driver.execute_script("document.querySelector('#composer-submit-button').click();")
                    except Exception:
                        pass
                
                stop_xpath = (
                    "//button[@id='composer-submit-button' and (@aria-label='Stop answering' or @data-testid='stop-button')]"
                )
                
                # Check for onprocess state for 5 seconds
                for sec in range(5):
                    try:
                        stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                        visible = any(b.is_displayed() for b in stop_btns)
                        if visible:
                            log("Confirmed: ChatGPT generation is onprocess!")
                            submit_success = True
                            break
                    except Exception:
                        pass
                    time.sleep(1.0)
                
                if submit_success:
                    break
                else:
                    log("Warning: ChatGPT generation did not start yet. Retrying submit...")
                    
            if not submit_success:
                log("Warning: Submit button click did not transition to onprocess state. Forcing ENTER key...")
                try:
                    box.send_keys(Keys.ENTER)
                except Exception:
                    pass
            
            # 7. Wait until generation is completed (Stop button disappears)
            import random
            delay_seconds = random.uniform(60.0, 135.0)
            log(f"Waiting {delay_seconds:.1f} seconds (random 1.00 - 2.15 mins) before starting status checks...")
            time.sleep(delay_seconds)
            log("Checking if Stop button has disappeared...")
            start_time = time.time()
            generation_timeout = 90.0
            
            while time.time() - start_time < generation_timeout:
                try:
                    stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                    visible = any(b.is_displayed() for b in stop_btns)
                    if not visible:
                        log("ChatGPT generation completed successfully!")
                        break
                except Exception:
                    log("ChatGPT generation completed successfully!")
                    break
                time.sleep(1.5)
                
            return {"ok": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
            
    mode = str(payload.get("mode") or "single").strip().lower()
    single_count = payload.get("single_count")
    companion_count = payload.get("companion_count")
    elements_count = payload.get("elements_count")
    try:
        bot = browser_manager.get()
        step3_gemini_gen_full_bot(
            bot,
            mode,
            int(single_count) if single_count is not None else None,
            int(companion_count) if companion_count is not None else None,
            int(elements_count) if elements_count is not None else None,
            log,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/4")
def step4(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        bot = browser_manager.get()
        step4_download_images_bot(bot, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/4-chatgpt")
def step4_chatgpt(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        bot = browser_manager.get()
        step4_chatgpt_download_images_bot(bot, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/5")
def step5(payload: dict[str, Any]) -> dict[str, Any]:
    log("Step 5: Manual step (external app).")
    return {"ok": True}


@app.post("/api/step/6")
def step6(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        step6_classify_resolution(log)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/7")
def step7(payload: dict[str, Any]) -> dict[str, Any]:
    log("Step 7: Manual step (external app).")
    return {"ok": True}


@app.post("/api/step/8")
def step8(payload: dict[str, Any]) -> dict[str, Any]:
    folder_name = str(payload.get("folder_name") or "").strip()
    local_path = str(payload.get("local_path") or "").strip()
    if not folder_name or not local_path:
        raise HTTPException(status_code=400, detail="folder_name and local_path are required")
    try:
        step8_downloads_images_to_local(folder_name, local_path, log)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/9")
def step9(payload: dict[str, Any]) -> dict[str, Any]:
    element_name = str(payload.get("element_name") or "").strip()
    element_path = str(payload.get("element_path") or "").strip()
    if not element_name or not element_path:
        raise HTTPException(status_code=400, detail="element_name/element_path required")
    try:
        step9_elements_to_local(element_name, element_path, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/10")
def step10(payload: dict[str, Any]) -> dict[str, Any]:
    folder_name = str(payload.get("folder_name") or "").strip()
    local_path = str(payload.get("local_path") or "").strip()
    watermark_path = str(payload.get("watermark_path") or "").strip() or None
    first_preview_watermark_path = str(payload.get("first_preview_watermark_path") or "").strip() or None
    element_name = str(payload.get("element_name") or "").strip()
    element_path = str(payload.get("element_path") or "").strip()
    if not folder_name or not local_path:
        raise HTTPException(status_code=400, detail="folder_name/local_path required")
    try:
        step10_create_preview_sheet(
            folder_name,
            local_path,
            watermark_path,
            first_preview_watermark_path,
            element_name,
            element_path,
            log,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/11")
def step11(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "all").strip().lower()
    png_pages = str(payload.get("png_pages") or "").strip() or None
    jpg_pages = str(payload.get("jpg_pages") or "").strip() or None
    pdf_pages = str(payload.get("pdf_pages") or "").strip() or None
    try:
        focus_tab = bool(payload.get("focus_tab")) if payload.get("focus_tab") is not None else _should_focus_tabs()
        canva_url_part = (
            str(payload.get("canva_url_part") or "").strip()
            or str(_get_config_value("canva_design_url_part", "") or "").strip()
            or "canva.com/design/"
        )
        bot = browser_manager.get()
        if mode == "png":
            step11_canva_export_bot(bot, "png", png_pages, log, focus_tab=focus_tab, canva_url_part=canva_url_part)
        elif mode == "jpg":
            step11_canva_export_bot(bot, "jpg", jpg_pages, log, focus_tab=focus_tab, canva_url_part=canva_url_part)
        elif mode == "pdf":
            step11_canva_export_bot(bot, "pdf", pdf_pages, log, focus_tab=focus_tab, canva_url_part=canva_url_part)
        else:
            step11_canva_export_all_bot(
                bot,
                png_pages,
                jpg_pages,
                pdf_pages,
                log,
                focus_tab=focus_tab,
                canva_url_part=canva_url_part,
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/12")
def step12(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        step12_unzip_downloads(log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/13")
def step13(payload: dict[str, Any]) -> dict[str, Any]:
    folder_name = str(payload.get("folder_name") or "").strip()
    local_path = str(payload.get("local_path") or "").strip()
    if not all([folder_name, local_path]):
        raise HTTPException(status_code=400, detail="folder_name/local_path required")
    try:
        step13_download_to_local(folder_name, local_path, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/14")
def step14(payload: dict[str, Any]) -> dict[str, Any]:
    folder_name = str(payload.get("folder_name") or "").strip()
    local_path = str(payload.get("local_path") or "").strip()
    remote_path = str(payload.get("remote_path") or "").strip()
    element_name = str(payload.get("element_name") or "").strip()
    element_path = str(payload.get("element_path") or "").strip()
    if not all([folder_name, local_path, remote_path, element_name, element_path]):
        raise HTTPException(status_code=400, detail="folder_name/local_path/remote_path/element_name/element_path required")
    try:
        step14_local_to_remote(folder_name, local_path, remote_path, element_name, element_path, log)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/14-no-elements")
def step14_no_elements(payload: dict[str, Any]) -> dict[str, Any]:
    folder_name = str(payload.get("folder_name") or "").strip()
    local_path = str(payload.get("local_path") or "").strip()
    remote_path = str(payload.get("remote_path") or "").strip()
    if not all([folder_name, local_path, remote_path]):
        raise HTTPException(status_code=400, detail="folder_name/local_path/remote_path required")
    try:
        step14_local_to_remote_no_elements(folder_name, local_path, remote_path, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/15")
def step15(payload: dict[str, Any]) -> dict[str, Any]:
    primary_color = str(payload.get("primary_color") or "").strip()
    secondary_color = str(payload.get("secondary_color") or "").strip()
    if not primary_color or not secondary_color:
        raise HTTPException(status_code=400, detail="primary_color/secondary_color required")
    try:
        bot = browser_manager.get()
        step15_etsy_listing_bot(bot, primary_color, secondary_color, log)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "web" / "index.html")


app.mount("/web", StaticFiles(directory=BASE_DIR / "web"), name="web")
