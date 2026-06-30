from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
_ensure_json(REF_IMAGE_DEFAULT_FILE, {"reference_image": "", "reference_image_2": "", "reference_image_3": "", "reference_image_4": "", "reference_image_5": "", "reference_image_6": "", "reference_image_7": "", "reference_images_dir": ""})

app = FastAPI(title="Chrome Automation Template")
last_submit_time = 0.0

import time
_original_sleep = time.sleep
_force_stop_requested = False

def check_force_stop():
    global _force_stop_requested
    if _force_stop_requested:
        raise RuntimeError("Force Stop Requested by user.")

def custom_sleep(seconds: float):
    slept = 0.0
    while slept < seconds:
        check_force_stop()
        _original_sleep(min(0.1, seconds - slept))
        slept += 0.1

time.sleep = custom_sleep

@app.middleware("http")
async def reset_force_stop_middleware(request, call_next):
    global _force_stop_requested
    path = request.url.path
    if request.method == "POST" and (path.startswith("/api/step/") or path.startswith("/api/video/") or path.startswith("/api/utils/")):
        if path != "/api/profiles/force-kill" and path != "/api/step/stop-upload-google-flow":
            _force_stop_requested = False
    
    response = await call_next(request)
    return response

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
    urls: list[str] = []


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


class ForceKillPayload(BaseModel):
    port: int


class ImportLakornPayload(BaseModel):
    lakorn_path: str
    ton_num: str
    ep_num: str
    ref_images_dir: str = ""


class ImportLakornVideoPayload(BaseModel):
    lakorn_path: str
    ton_num: str
    ep_num: str

class UploadImagesGoogleFlowPayload(BaseModel):
    folder_path: str



class VideoGenStepPayload(BaseModel):
    prompt: str
    round_idx: int
    google_flow_path: str = ""
    video_input_selector: str = ""
    video_settings_selector: str = ""
    video_submit_selector: str = ""
    video_wait_seconds: int = 60
    is_first_run: bool = True



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


def is_driver_alive(driver) -> bool:
    try:
        _ = driver.window_handles
        return True
    except Exception:
        return False


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
    import os
    if os.path.exists(file_path):
        return True
    import subprocess
    escaped_path = file_path.replace('"', '\\"')
    script = f"""
    tell application "System Events"
        exists POSIX file "{escaped_path}"
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
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if int(p.get("debug_port", 0)) == 9222), None)
    urls = profile.get("startup_urls", []) if profile else []
    while len(urls) < 3:
        urls.append("")
    return {"urls": urls[:3]}


@app.post("/api/settings")
def save_settings(payload: SaveSettingsPayload):
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if int(p.get("debug_port", 0)) == 9222), None)
    if not profile:
        raise HTTPException(status_code=400, detail="ไม่พบ Profile ที่ใช้ debug port 9222")
    
    # Clean and normalize urls
    urls = [u.strip() for u in payload.urls if u.strip()]
    profile["startup_urls"] = _normalize_urls(urls)
    _write_json(PROFILES_FILE, data)
    return {"ok": True, "message": "บันทึกเว็บไซต์เริ่มต้นเรียบร้อยแล้ว", "urls": profile["startup_urls"]}


@app.get("/api/config/reference-image/default")
def get_ref_image_default():
    return _read_json(REF_IMAGE_DEFAULT_FILE)


class RefImageDefaultPayload(BaseModel):
    reference_image: str = ""
    reference_image_2: str = ""
    reference_image_3: str = ""
    reference_image_4: str = ""
    reference_image_5: str = ""
    reference_image_6: str = ""
    reference_image_7: str = ""
    reference_images_dir: str = ""


@app.post("/api/config/reference-image/default")
def save_ref_image_default(payload: RefImageDefaultPayload):
    data = payload.model_dump()
    _write_json(REF_IMAGE_DEFAULT_FILE, data)
    return {"ok": True, "message": "Saved default reference images", "data": data}


class RefImageVerifyPayload(BaseModel):
    path: str


@app.post("/api/config/reference-image/verify")
def verify_reference_image(payload: RefImageVerifyPayload):
    path = payload.path.strip()
    if not path:
        return {"exists": False, "message": "Reference image path is empty."}
    
    import os
    if os.path.exists(path) and os.path.isfile(path):
        lower_path = path.lower()
        valid_extensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]
        if not any(lower_path.endswith(ext) for ext in valid_extensions):
            return {"exists": False, "message": f"Error: Selected file is not a valid image format: {path}"}
        return {"exists": True, "message": f"Success: Reference file exists and is a valid image at: {path}"}
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


@app.post("/api/profiles/force-kill")
def force_kill_profile(payload: ForceKillPayload):
    global _force_stop_requested
    _force_stop_requested = True
    port = payload.port
    print(f"Force Stop requested. Stopped active operations on port {port}.")
    log(f"Force Stop: บังคับให้หยุดทำงานเรียบร้อยแล้ว โดยไม่ปิดเบราว์เซอร์")
    return {"ok": True, "killed": False, "message": f"Force stop requested. Chrome browser on port {port} will not be closed."}




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

CONFIG_FILE = str(BASE_DIR / ("config_win.json" if os.name == "nt" else "config_mac.json"))


def _default_config() -> dict[str, Any]:
    if os.name == "nt":
        res = {
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
            "image_prompts": [],
            "image_prompt_statuses": [],
            "image_prompts_2": [],
            "image_prompt_statuses_2": [],
            "image_prompts_3": [],
            "image_prompt_statuses_3": [],
            "chatgpt_url": "",
            "video_input_path": "",
            "image_input_path": "",
            "video_output_path": "",
            "reference_image": "",
            "reference_image_2": "",
            "reference_image_3": "",
            "video_prefix_cover": "",
            "video_prefix_combine": "",
            "lakorn_path": "",
            "lakorn_ep": "",
            "lakorn_ton": "",
            "google_flow_path": "",
            "video_wait_seconds": 60,
            "video_input_selector": "",
            "video_settings_selector": "",
            "video_submit_selector": "",
            "video_lakorn_path": "",
            "video_lakorn_ep": "",
            "video_lakorn_ton": "",
        }
    else:
        h = os.path.expanduser("~")
        res = {
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
            "image_prompts": [],
            "image_prompt_statuses": [],
            "image_prompts_2": [],
            "image_prompt_statuses_2": [],
            "image_prompts_3": [],
            "image_prompt_statuses_3": [],
            "chatgpt_url": "",
            "video_input_path": "",
            "image_input_path": "",
            "video_output_path": "",
            "reference_image": "",
            "reference_image_2": "",
            "reference_image_3": "",
            "video_prefix_cover": "",
            "video_prefix_combine": "",
            "lakorn_path": "",
            "lakorn_ep": "",
            "lakorn_ton": "",
            "google_flow_path": "",
            "video_wait_seconds": 60,
            "video_input_selector": "",
            "video_settings_selector": "",
            "video_submit_selector": "",
            "video_lakorn_path": "",
            "video_lakorn_ep": "",
            "video_lakorn_ton": "",
        }

    # Dynamically ensure all 30 rounds of image prompts and 10 rounds of video prompts are initialized in config
    for r in range(1, 31):
        p_key = "image_prompts" if r == 1 else f"image_prompts_{r}"
        s_key = "image_prompt_statuses" if r == 1 else f"image_prompt_statuses_{r}"
        if p_key not in res:
            res[p_key] = []
        if s_key not in res:
            res[s_key] = []

        active_key = f"round_active_{r}"
        if active_key not in res:
            res[active_key] = True

        for i in range(1, 8):
            ref_key = f"reference_image_round_{r}_{i}"
            if ref_key not in res:
                res[ref_key] = ""

    for r in range(1, 11):
        vp_key = "video_prompts" if r == 1 else f"video_prompts_{r}"
        vs_key = "video_prompt_statuses" if r == 1 else f"video_prompt_statuses_{r}"
        if vp_key not in res:
            res[vp_key] = []
        if vs_key not in res:
            res[vs_key] = []

        vactive_key = f"video_round_active_{r}"
        if vactive_key not in res:
            res[vactive_key] = True
                
    # Also add default reference image 4 to 7 globally for defaults
    for i in range(4, 8):
        global_key = f"reference_image_{i}"
        if global_key not in res:
            res[global_key] = ""

    return res


def log(msg: str) -> None:
    print(msg, flush=True)
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
    custom_prompt = payload.get("prompt")
    if custom_prompt:
        try:
            import time
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            submit_only = payload.get("submit_only", False)
            prepare_only = payload.get("prepare_only", False)
            
            ref_images = []
            if not submit_only:
                for k in ["reference_image", "reference_image_2", "reference_image_3", "reference_image_4", "reference_image_5", "reference_image_6", "reference_image_7"]:
                    img = (payload.get(k) or "").strip()
                    if img:
                        ref_images.append(img)
            has_images = len(ref_images) > 0
            
            # Switch to Chrome only if uploading images is required
            if has_images:
                _activate_chrome()

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
                    
            if has_images:
                # Physically switch to the Gemini tab in macOS Chrome UI!
                _physical_switch_to_tab("gemini.google.com")
                _activate_chrome()
                time.sleep(0.5)
            else:
                # Background-safe Selenium tab switch
                bot.switch_to_tab_containing("gemini.google.com")
            
            # Strictly verify we are on the Gemini page before sending input!
            if "gemini.google.com" not in driver.current_url:
                raise RuntimeError("Failed to switch to Gemini tab. Please open it manually.")

            # Find the input box first to ensure tab is ready
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

            if not submit_only:
                ref_images = []
                for k in ["reference_image", "reference_image_2", "reference_image_3", "reference_image_4", "reference_image_5", "reference_image_6", "reference_image_7"]:
                    img = (payload.get(k) or "").strip()
                    if img:
                        ref_images.append(img)

                # Helper functions for uploading
                def click_element_with_retry(selectors, name):
                    combined_selector = ", ".join(selectors)
                    for attempt in range(3):
                        if not is_driver_alive(driver):
                            raise RuntimeError("Browser connection lost.")
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
                        except Exception:
                            if not is_driver_alive(driver):
                                raise RuntimeError("Browser connection lost.")
                            pass
                        if attempt < 2:
                            log(f"Failed to click {name}. Waiting 1.5 seconds before next attempt...")
                            time.sleep(1.5)
                    log(f"CRITICAL ERROR: Failed to click {name} after 3 attempts.")
                    return False

                def upload_macos_file_dialog(file_path):
                    if not is_driver_alive(driver):
                        raise RuntimeError("Browser connection lost.")
                    import subprocess
                    escaped_path = file_path.replace('"', '\\"')
                    script = f"""
                    set the clipboard to "{escaped_path}"
                    delay 0.5
                    tell application "System Events"
                        key code 5 using {{command down, shift down}}
                        delay 0.75
                        key code 9 using {{command down}}
                        delay 1.0
                        keystroke return
                        delay 1.5
                        keystroke return
                    end tell
                    """
                    try:
                        subprocess.run(["osascript", "-e", script], check=False)
                        return True
                    except Exception as e:
                        if not is_driver_alive(driver):
                            raise RuntimeError("Browser connection lost.")
                        log(f"AppleScript dialog input failed: {e}")
                        return False

                # Upload all reference images sequentially
                for run_idx, reference_image in enumerate(ref_images):
                    if not is_driver_alive(driver):
                        raise RuntimeError("Browser connection lost.")
                    if not reference_image:
                        continue
                    log(f"Uploading Gemini reference image {run_idx + 1}/{len(ref_images)}: {reference_image}")
                    if not _macos_file_exists(reference_image):
                        raise RuntimeError(f"Reference image file not found on macOS: {reference_image}")
                    
                    # Step 1: Click upload menu button
                    _activate_chrome()
                    time.sleep(2.0)
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
                            _activate_chrome()
                            time.sleep(0.5)
                            if upload_macos_file_dialog(reference_image):
                                log("Reference image uploaded successfully via macOS File Dialog AppleScript automation!")
                                log("Waiting 2.5 seconds for file attachment processing...")
                                time.sleep(2.5)
                            else:
                                log("Warning: AppleScript keys injection encountered an issue.")
                        else:
                            log("Warning: Failed to open system uploader modal after 3 attempts.")
                    else:
                        log("Warning: Failed to open Gemini upload menu after 3 attempts.")

                # Paste prompt, but do not click send
                try:
                    box.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", box)
                    
                driver.execute_script(
                    "if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }",
                    box
                )
                driver.execute_script("arguments[0].focus();", box)
                time.sleep(0.75)

                input_success = False
                try:
                    driver.execute_script("document.execCommand('insertText', false, arguments[0]);", custom_prompt)
                    time.sleep(0.75)
                    entered_text = driver.execute_script("""
                        return arguments[0].innerText || arguments[0].textContent || '';
                    """, box)
                    if entered_text and entered_text.strip() != "":
                        log("Prompt input populated successfully via browser insertText command.")
                        input_success = True
                except Exception as e:
                    log(f"Browser insertText command failed: {e}")

                if not input_success:
                    log("Browser insertText failed or could not be verified. Typing prompt via native send_keys...")
                    try:
                        box.send_keys(custom_prompt)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", box)
                    except Exception as fallback_err:
                        log(f"Safe send_keys typing failed: {fallback_err}")

                if prepare_only:
                    log("Prepare-only mode requested. Prompt pasted. Returning success without submitting.")
                    return {"ok": True, "status": "prepared"}

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
                    time.sleep(1.5)
                
                if send_success:
                    break
                else:
                    log("Warning: Generation did not start yet. Retrying send...")
                    
            if not send_success:
                raise RuntimeError("Failed to start generation: Send button clicked but 'onprocess' stop button did not appear within 5 seconds.")
                
            check_interval = int(_get_config_value("check_interval_seconds", 60))
            max_checks = int(_get_config_value("max_checks", 3))
            first_time_waiting = int(_get_config_value("first_time_waiting", check_interval))
            log(f"Starting status checks: first wait of {first_time_waiting}s, interval of {check_interval}s, max {max_checks} checks...")
            
            generation_completed = False
            for check_idx in range(1, max_checks + 1):
                wait_time = first_time_waiting if check_idx == 1 else check_interval
                log(f"Check {check_idx}/{max_checks}: Starting wait of {wait_time} seconds...")
                for s in range(wait_time, 0, -1):
                    if not is_driver_alive(driver):
                        raise RuntimeError("Browser connection lost (Force Stopped).")
                    if s % 10 == 0 or s <= 5:
                        log(f"Check {check_idx}/{max_checks}: {s} seconds remaining before checking...")
                    time.sleep(1)
                
                try:
                    stop_buttons = driver.find_elements(By.XPATH, stop_button_xpath)
                    visible_stop_button = False
                    for btn in stop_buttons:
                        if btn.is_displayed():
                            visible_stop_button = True
                            break
                    if not visible_stop_button:
                        log("Stop button has disappeared! Gemini generation completed successfully.")
                        generation_completed = True
                        break
                    else:
                        log("Gemini is still generating... Stop button is still visible.")
                except Exception:
                    log("Stop button no longer found. Gemini generation completed successfully.")
                    generation_completed = True
                    break
                    
            if not generation_completed:
                raise RuntimeError(f"Gemini generation timeout: Stop button did not disappear after {max_checks} checks of {check_interval}s interval.")
            
            return {"ok": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/3-chatgpt")
def step3_chatgpt(payload: dict[str, Any]) -> dict[str, Any]:
    global last_submit_time
    custom_prompt = payload.get("prompt")
    if custom_prompt:
        try:
            import time
            import random
            
            submit_only = payload.get("submit_only", False)
            ref_images = []
            if not submit_only:
                for k in ["reference_image", "reference_image_2", "reference_image_3", "reference_image_4", "reference_image_5", "reference_image_6", "reference_image_7"]:
                    img = (payload.get(k) or "").strip()
                    if img:
                        ref_images.append(img)
            has_images = len(ref_images) > 0

            if last_submit_time > 0.0:
                random_delay = random.randint(1, 5)
                log(f"จำลองการทำงานมนุษย์: สุ่มรอ {random_delay} วินาที ก่อนเริ่มอัปโหลดรูปและวาง Prompt ถัดไป...")
                time.sleep(random_delay)
            
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # Switch to Chrome window only if uploading images is required
            if has_images:
                _activate_chrome()

            bot = None
            try:
                bot = browser_manager.get()
                # Test the session validity by fetching handles
                _ = bot.driver.window_handles
            except Exception as e:
                log(f"Warning: Browser session check failed ({e}). Recreating browser session...")
                browser_manager.close()
                bot = browser_manager.get()
                
            driver = bot.driver
            
            chatgpt_chat_mode = payload.get("chatgpt_chat_mode", "new")
            chatgpt_url = payload.get("chatgpt_url")
            
            if chatgpt_chat_mode == "new" and chatgpt_url:
                log(f"Round transition: Redirecting first tab to ChatGPT project URL: {chatgpt_url}")
                try:
                    all_handles = driver.window_handles
                    if not all_handles:
                        raise RuntimeError("No browser windows/tabs open.")
                    
                    keep_handle = all_handles[0]
                    driver.switch_to.window(keep_handle)
                    driver.get(chatgpt_url)
                    log("Waiting for ChatGPT input element to be ready...")
                    input_strats = [
                        "//div[@id='prompt-textarea']",
                        "//textarea[@id='prompt-textarea']",
                        "//div[@contenteditable='true']",
                    ]
                    box_loaded = False
                    for wait_sec in range(10):
                        for s in input_strats:
                            try:
                                el = driver.find_element(By.XPATH, s)
                                if el.is_displayed():
                                    box_loaded = True
                                    break
                            except Exception:
                                pass
                        if box_loaded:
                            break
                        time.sleep(1.0)
                    log("ChatGPT project page input box is ready!")
 
                    # Close all other ChatGPT tabs to avoid clutter
                    closed_count = 0
                    for handle in all_handles[1:]:
                        try:
                            driver.switch_to.window(handle)
                            if "chatgpt.com" in driver.current_url.lower():
                                driver.close()
                                closed_count += 1
                        except Exception:
                            pass
                    driver.switch_to.window(keep_handle)
                    if closed_count > 0:
                        log(f"Closed {closed_count} old ChatGPT tab(s) to keep workspace clean.")
                except Exception as e:
                    log(f"Failed to navigate and clean tabs: {e}")
            else:
                log("Reusing currently active/open ChatGPT tab...")
                # Check if ChatGPT is open
                if not bot.switch_to_tab_containing("chatgpt.com"):
                    log("ChatGPT tab not found, opening natively in new tab...")
                    try:
                        driver.execute_script("window.open('');")
                        driver.switch_to.window(driver.window_handles[-1])
                        driver.get("https://chatgpt.com/")
                        time.sleep(3.0)
                    except Exception:
                        driver.get("https://chatgpt.com/")
                        time.sleep(3.0)
            
            if has_images:
                # Physically switch to the ChatGPT tab in macOS Chrome UI!
                _physical_switch_to_tab("chatgpt.com")
                _activate_chrome()
                time.sleep(0.5)
            else:
                # Background-safe Selenium tab switch
                bot.switch_to_tab_containing("chatgpt.com")
            
            # Strictly verify we are on the ChatGPT page before sending input!
            if "chatgpt.com" not in driver.current_url:
                raise RuntimeError("Failed to switch to ChatGPT tab. Please open it manually.")

            prepare_only = payload.get("prepare_only", False)
            submit_only = payload.get("submit_only", False)

            ref_images = []
            if not submit_only:
                for k in ["reference_image", "reference_image_2", "reference_image_3", "reference_image_4", "reference_image_5", "reference_image_6", "reference_image_7"]:
                    img = (payload.get(k) or "").strip()
                    if img:
                        ref_images.append(img)
            
            # Find the input box first to ensure tab is ready
            input_strats = [
                "//div[@id='prompt-textarea']//p",
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

            if not submit_only:
                def click_chatgpt_attach_button() -> bool:
                    for attempt in range(3):
                        if not is_driver_alive(driver):
                            raise RuntimeError("Browser connection lost.")
                        log(f"Attempt {attempt + 1}/3 to open ChatGPT add-files menu...")
                        try:
                            plus_btn = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "#composer-plus-btn, button[data-testid='composer-plus-btn']"))
                            )
                            try:
                                plus_btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", plus_btn)
                            log("Clicked ChatGPT composer plus button.")

                            add_files_item = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((
                                    By.XPATH,
                                    "//div[@role='menuitem' and .//div[normalize-space()='Add photos & files']]",
                                ))
                            )
                            try:
                                add_files_item.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", add_files_item)
                            log("Clicked ChatGPT 'Add photos & files' menu item.")
                            return True
                        except Exception:
                            if not is_driver_alive(driver):
                                raise RuntimeError("Browser connection lost.")
                            pass

                        fallback_selectors = [
                            "button[aria-label*='Attach' i]",
                            "button[aria-label*='Upload' i]",
                            "button[data-testid*='attach' i]",
                            "button[data-testid*='upload' i]",
                            "label[for*='file']",
                        ]
                        for selector in fallback_selectors:
                            try:
                                if not is_driver_alive(driver):
                                    raise RuntimeError("Browser connection lost.")
                                el = WebDriverWait(driver, 2).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                )
                                if not el.is_displayed():
                                    continue
                                try:
                                    el.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", el)
                                log(f"Clicked ChatGPT fallback attach control using selector: {selector}")
                                return True
                            except Exception:
                                continue
                        time.sleep(1.0)
                    log("Failed to locate a visible ChatGPT attach control.")
                    return False

                def upload_macos_file_dialog(file_path):
                    if not is_driver_alive(driver):
                        raise RuntimeError("Browser connection lost.")
                    import subprocess
                    escaped_path = file_path.replace('"', '\\"')
                    script = f"""
                    set the clipboard to "{escaped_path}"
                    delay 0.5
                    tell application "System Events"
                        key code 5 using {{command down, shift down}}
                        delay 0.75
                        key code 9 using {{command down}}
                        delay 1.0
                        keystroke return
                        delay 1.5
                        keystroke return
                    end tell
                    """
                    try:
                        subprocess.run(["osascript", "-e", script], check=False)
                        return True
                    except Exception as e:
                        if not is_driver_alive(driver):
                            raise RuntimeError("Browser connection lost.")
                        log(f"AppleScript dialog input failed: {e}")
                        return False

                # Upload all reference images sequentially
                for run_idx, reference_image in enumerate(ref_images):
                    if not is_driver_alive(driver):
                        raise RuntimeError("Browser connection lost.")
                    if not reference_image:
                        continue
                    log(f"Uploading ChatGPT reference image {run_idx + 1}/{len(ref_images)}: {reference_image}")
                    if not _macos_file_exists(reference_image):
                        raise RuntimeError(f"Reference image file not found on macOS: {reference_image}")
                    
                    _activate_chrome()
                    time.sleep(1.0)
                    
                    # We will try to upload using Cmd + U first (Primary).
                    # If that fails, we will try the '+' button (Fallback).
                    upload_success = False
                    
                    log("Primary: Sending Cmd + U keystroke via System Events to trigger file modal...")
                    try:
                        cmd_u_script = """
                        tell application "Google Chrome" to activate
                        delay 0.5
                        tell application "System Events"
                            key code 32 using command down
                        end tell
                        """
                        subprocess.run(["osascript", "-e", cmd_u_script], check=False)
                        log("Waiting 1.5 seconds for file modal to fully open...")
                        time.sleep(1.5)
                        
                        log("Triggering AppleScript folder path sheet to select file (Cmd + U method)...")
                        if upload_macos_file_dialog(reference_image):
                            upload_success = True
                            log("Reference image uploaded successfully via macOS File Dialog AppleScript automation!")
                    except Exception as e:
                        log(f"Primary Cmd + U upload method failed: {e}")
                        
                    if not upload_success:
                        log("Fallback: Cmd + U method did not succeed. Attempting UI click attach button...")
                        try:
                            if click_chatgpt_attach_button():
                                log("Waiting 1.5 seconds for file modal to fully open...")
                                time.sleep(1.5)
                                log("Triggering AppleScript folder path sheet to select file (UI Click method)...")
                                if upload_macos_file_dialog(reference_image):
                                    upload_success = True
                                    log("Reference image uploaded successfully via macOS File Dialog AppleScript automation!")
                        except Exception as click_err:
                            log(f"UI attach trigger fallback failed: {click_err}")
                            
                    if upload_success:
                        log("Waiting 2.5 seconds for file upload to settle...")
                        time.sleep(2.5)
                    else:
                        log("Warning: AppleScript file-dialog automation encountered an issue and could not upload file.")

                # Re-resolve the input box after files have finished uploading, as DOM updates may make the old reference stale
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
                    raise RuntimeError("Could not re-locate ChatGPT input box after file upload.")

                # Paste the prompt, but do not click send
                try:
                    box.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", box)
                    
                driver.execute_script("arguments[0].focus();", box)
                time.sleep(0.75)
                
                # Clear the box to prevent double-pasting (simulating delete event to sync React/ProseMirror state)
                driver.execute_script("""
                    var el = arguments[0];
                    el.focus();
                    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                        el.value = '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        if (typeof window.getSelection !== 'undefined' && document.createRange) {
                            var range = document.createRange();
                            range.selectNodeContents(el);
                            var sel = window.getSelection();
                            sel.removeAllRanges();
                            sel.addRange(range);
                            document.execCommand('delete', false, null);
                        } else {
                            el.innerHTML = '';
                        }
                    }
                """, box)
                time.sleep(0.75)

                if not is_driver_alive(driver):
                    raise RuntimeError("Browser connection lost (Force Stopped).")
                
                # Primary: Use document.execCommand('insertText') to insert prompt without triggering Enter key submits
                input_success = False
                try:
                    driver.execute_script("document.execCommand('insertText', false, arguments[0]);", custom_prompt)
                    time.sleep(0.75)
                    # Verify text inside the entire #prompt-textarea div instead of just the (potentially detached) box element
                    entered_text = driver.execute_script("""
                        var target = document.getElementById('prompt-textarea') || arguments[0];
                        return target.value || target.innerText || target.textContent || '';
                    """, box)
                    if entered_text and entered_text.strip() != "":
                        log("Prompt input populated successfully via browser insertText command.")
                        input_success = True
                except Exception as e:
                    log(f"Browser insertText command failed: {e}")

                # Secondary Fallback: Native send_keys, but replacing newlines with SHIFT+ENTER to prevent auto-submission!
                if not input_success:
                    log("Browser insertText failed or could not be verified. Typing prompt via background-safe native send_keys with SHIFT+ENTER for newlines...")
                    try:
                        box.click()
                        # Type character by character or chunk by chunk to handle newlines safely
                        parts = custom_prompt.split('\n')
                        for idx, part in enumerate(parts):
                            if part:
                                box.send_keys(part)
                            if idx < len(parts) - 1:
                                box.send_keys(Keys.SHIFT + Keys.ENTER)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", box)
                        log("Typed prompt successfully via safe send_keys.")
                    except Exception as fallback_err:
                        log(f"Safe send_keys typing failed: {fallback_err}")

                if prepare_only:
                    log("Prepare-only mode requested. Prompt pasted. Returning success without submitting.")
                    return {"ok": True, "status": "prepared"}

            # Click at '#composer-submit-button' to submit
            bypass_submit = False
            if not bypass_submit:
                stop_xpath = (
                    "//button[@id='composer-submit-button' and (@aria-label='Stop answering' or @data-testid='stop-button')]"
                )
                
                check_interval = int(_get_config_value("check_interval_seconds", 60))
                max_checks = int(_get_config_value("max_checks", 3))
                first_time_waiting = int(_get_config_value("first_time_waiting", check_interval))
                
                # Check if ChatGPT is currently generating (Stop button visible)
                is_generating = False
                try:
                    stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                    is_generating = any(b.is_displayed() for b in stop_btns)
                except Exception:
                    pass
                
                if is_generating:
                    import time
                    elapsed = time.time() - last_submit_time if last_submit_time > 0 else 0.0
                    remaining_wait = first_time_waiting - elapsed
                    
                    log(f"ตรวจพบว่า ChatGPT กำลังทำงานอยู่จากรอบก่อนหน้า (รันมาแล้ว {elapsed:.1f} วินาที)...")
                    
                    if remaining_wait > 0:
                        log(f"เริ่มนับถอยหลัง First Time Waiting ทุกๆ 1 วินาที (เหลืออีก {int(remaining_wait)} วินาที จาก {first_time_waiting} วินาที)...")
                        for s in range(int(remaining_wait), 0, -1):
                            if not is_driver_alive(driver):
                                raise RuntimeError("Browser connection lost (Force Stopped).")
                            log(f"First Time Waiting: เหลืออีก {s} วินาที จะเริ่มตรวจสอบปุ่ม Send")
                            time.sleep(1)
                    
                    generation_completed = False
                    # Check immediately after First Time Waiting completes
                    try:
                        stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                        visible = any(b.is_displayed() for b in stop_btns)
                        if not visible:
                            log("ตรวจพบปุ่ม Send พร้อมใช้งานแล้ว (หลังครบ First Time Waiting)")
                            generation_completed = True
                    except Exception:
                        generation_completed = True

                    if not generation_completed:
                        check_count = 1
                        for check_idx in range(1, max_checks + 1):
                            log(f"เริ่มตรวจรอบที่ {check_count} (Interval {check_interval} วินาที)...")
                            for s in range(check_interval, 0, -1):
                                if not is_driver_alive(driver):
                                    raise RuntimeError("Browser connection lost (Force Stopped).")
                                log(f"Interval Check ครั้งที่ {check_count}: เหลืออีก {s} วินาที")
                                time.sleep(1)
                            
                            check_count += 1
                            try:
                                stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                                visible = any(b.is_displayed() for b in stop_btns)
                                if not visible:
                                    log(f"ตรวจพบปุ่ม Send พร้อมใช้งานแล้ว (ในการตรวจสอบครั้งที่ {check_count-1})")
                                    generation_completed = True
                                    break
                                else:
                                    log(f"ChatGPT ยังคงเจเนอเรตอยู่ (ปุ่ม Stop ยังแสดงอยู่) ผ่านการตรวจสอบแล้ว {check_count-1} ครั้ง")
                            except Exception:
                                log("ไม่พบปุ่ม Stop แล้ว ChatGPT เจเนอเรตเสร็จสิ้น")
                                generation_completed = True
                                break
                                
                        if not generation_completed:
                            log("ข้อผิดพลาด: ตรวจสอบปุ่ม Send ครบตามจำนวน Max Checks แล้วแต่ ChatGPT ยังทำงานไม่เสร็จสิ้น")
                            raise RuntimeError("หยุดการทำงาน: ตรวจสอบปุ่ม Send ครบตามจำนวน Max Checks แล้วแต่ปุ่มยังไม่พร้อมใช้งาน")
                else:
                    log("ChatGPT ว่างอยู่ (ไม่มีการเจเนอเรตค้างไว้) ดำเนินการส่งได้ทันที...")

                # Now click submit button
                log("กำลังคลิกปุ่มส่ง prompt (#composer-submit-button)...")
                submit_success = False
                for click_attempt in range(3):
                    try:
                        submit_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "#composer-submit-button"))
                        )
                        submit_btn.click()
                        submit_success = True
                        break
                    except Exception:
                        try:
                            driver.execute_script("document.querySelector('#composer-submit-button').click();")
                            submit_success = True
                            break
                        except Exception:
                            pass
                    time.sleep(1.5)

                # Check if it transitioned to active generation
                started = False
                for sec in range(3):
                    try:
                        stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                        if any(b.is_displayed() for b in stop_btns):
                            started = True
                            break
                    except Exception:
                        pass
                    time.sleep(1.5)

                if started or submit_success:
                    log("ยืนยัน: ส่ง prompt เรียบร้อยแล้ว (ChatGPT กำลังทำการเจเนอเรตคำตอบ)!")
                else:
                    log("ไม่พบการตอบสนองของปุ่มส่ง กำลังลองส่งด้วยการเคาะปุ่ม Enter...")
                    try:
                        box.send_keys(Keys.ENTER)
                    except Exception:
                        pass
                
                # Update last submit timestamp immediately
                import time
                last_submit_time = time.time()
            else:
                log("Submit button click and generation wait bypassed for this debug session as requested.")
                raise RuntimeError("Bypassed submit for debug session. Aborting bulk prompt loop.")

            return {"ok": True, "status": "submitted"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
            
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


global_video_progress = {}

@app.get("/api/video/progress")
def get_video_progress(job_id: str):
    return global_video_progress.get(job_id, {"percent": 0, "status": "Idle"})

@app.post("/api/video/make-cover")
def make_video_cover(
    video: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
    video_path: str | None = Form(None),
    image_path: str | None = Form(None),
    output_path: str | None = Form(None),
    prefix: str | None = Form(None),
    no: str | None = Form(None),
    mode: str | None = Form(None),
    amount: str | None = Form(None),
    suffix: str | None = Form(None),
    folders_json: str | None = Form(None),
    folder_range: str | None = Form(None),
    sub_mode: str | None = Form(None),
    audio_path: str | None = Form(None),
    durations_json: str | None = Form(None),
    audio_boost: str | None = Form(None),
    video_audio_boost: str | None = Form(None),
    contrast: str | None = Form(None),
    saturation: str | None = Form(None),
    brightness: str | None = Form(None),
    gamma: str | None = Form(None),
    unsharp: str | None = Form(None),
    overwrite: str | None = Form(None),
    job_id: str | None = Form(None)
) -> dict[str, Any]:
    import subprocess
    import tempfile
    import os
    import json
    import shutil
    from datetime import datetime
    from fastapi.params import Form as FormParam

    def clean_form_val(v):
        if isinstance(v, FormParam):
            return None
        return v

    video_path = clean_form_val(video_path)
    image_path = clean_form_val(image_path)
    output_path = clean_form_val(output_path)
    prefix = clean_form_val(prefix)
    no = clean_form_val(no)
    mode = clean_form_val(mode)
    amount = clean_form_val(amount)
    suffix = clean_form_val(suffix)
    folders_json = clean_form_val(folders_json)
    folder_range = clean_form_val(folder_range)
    sub_mode = clean_form_val(sub_mode)
    audio_path = clean_form_val(audio_path)
    durations_json = clean_form_val(durations_json)
    audio_boost = clean_form_val(audio_boost)
    video_audio_boost = clean_form_val(video_audio_boost)
    contrast = clean_form_val(contrast)
    saturation = clean_form_val(saturation)
    brightness = clean_form_val(brightness)
    gamma = clean_form_val(gamma)
    unsharp = clean_form_val(unsharp)
    overwrite = clean_form_val(overwrite)
    job_id = clean_form_val(job_id)

    def update_progress(percent: int, status: str):
        if job_id:
            global_video_progress[job_id] = {"percent": percent, "status": status}
            
    update_progress(0, "Initializing...")
    
    is_combine_mode = (mode == "combine")
    mode_label = "Combine Mode" if is_combine_mode else "Cover Mode"
    log(f"Video Helper: Starting {mode_label} conversion...")

    video_exts = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"]
    combine_media_exts = video_exts + [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"]
    suffix_val = (suffix or "").strip()

    def resolve_named_media_file(directory: str, folder_name: str, allowed_exts: list[str]) -> str | None:
        if not os.path.isdir(directory):
            return None

        target = f"{folder_name}{suffix_val}".lower()
        suffix_has_extension = bool(suffix_val and os.path.splitext(suffix_val)[1])

        for file_name in os.listdir(directory):
            lower_name = file_name.lower()
            stem, ext = os.path.splitext(lower_name)
            if suffix_has_extension:
                if lower_name == target and ext in allowed_exts:
                    return file_name
            elif ext in allowed_exts and stem == target:
                return file_name
        return None

    def probe_media_streams(path: str) -> tuple[bool, bool]:
        has_video = False
        has_audio = False
        try:
            probe_cmd = [
                "/opt/homebrew/bin/ffprobe", "-v", "error", "-show_streams", "-of", "json", path
            ]
            if not os.path.exists(probe_cmd[0]):
                probe_cmd[0] = "ffprobe"
            result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            probe_data = json.loads(result.stdout or "{}")
            for stream in probe_data.get("streams", []):
                codec_type = stream.get("codec_type")
                if codec_type == "video":
                    has_video = True
                elif codec_type == "audio":
                    has_audio = True
        except Exception as e:
            log(f"Media probe warning for '{path}': {e}")
        return has_video, has_audio

    def build_folder_label(folder_names: list[str]) -> str:
        if not folder_names:
            return "combined"
        
        # Extract basename for any path (absolute or relative with slashes)
        names = []
        for name in folder_names:
            clean_name = str(name).strip()
            if os.path.isabs(clean_name) or "/" in clean_name or "\\" in clean_name:
                names.append(os.path.basename(clean_name.rstrip("/\\")))
            else:
                names.append(clean_name)

        if len(names) == 1:
            return names[0]

        nums = [int(name) for name in names if str(name).isdigit()]
        if len(nums) == len(names) and nums == list(range(nums[0], nums[-1] + 1)):
            return f"{names[0]}-{names[-1]}"
        return "_".join(names)

    src_video_path = ""
    video_filename = ""
    src_second_path = ""
    second_filename = ""
    combine_sources: list[tuple[str, str, str]] = []
    combine_label = ""
    
    if not is_combine_mode:
        if not output_path or not output_path.strip():
            raise HTTPException(status_code=400, detail="Path (output_path) is required in Cover Mode")
        if not no or not no.strip():
            raise HTTPException(status_code=400, detail="Sub folder (no) is required in Cover Mode")
        
        base_dir = output_path.strip()
        sub_no = no.strip()
        subfolder = os.path.join(base_dir, sub_no)
        if not os.path.exists(subfolder) or not os.path.isdir(subfolder):
            raise HTTPException(status_code=400, detail=f"Set {sub_no}: Subfolder '{subfolder}' does not exist")
            
        video_files = []
        for f in os.listdir(subfolder):
            f_lower = f.lower()
            if any(f_lower.endswith(ext) for ext in video_exts) and os.path.isfile(os.path.join(subfolder, f)):
                video_files.append(f)
                
        if len(video_files) == 0:
            raise HTTPException(status_code=400, detail=f"Set {sub_no}: No video file found in subfolder '{subfolder}'")
        elif len(video_files) > 1:
            raise HTTPException(status_code=400, detail=f"Set {sub_no}: Multiple video files found in subfolder '{subfolder}'. Only 1 video is allowed (Found: {len(video_files)})")
            
        resolved_video_name = video_files[0]
        src_video_path = os.path.join(subfolder, resolved_video_name)
        video_filename = resolved_video_name
        log(f"Cover Mode: Auto-pulled source video '{src_video_path}'")
        
        cover_dir = os.path.join(subfolder, "cover")
        if not os.path.exists(cover_dir) or not os.path.isdir(cover_dir):
            raise HTTPException(status_code=400, detail=f"Set {sub_no}: Cover folder '{cover_dir}' does not exist")
            
        image_files = []
        for f in os.listdir(cover_dir):
            f_lower = f.lower()
            if any(f_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]):
                image_files.append(f)
                
        if len(image_files) == 0:
            raise HTTPException(status_code=400, detail=f"Set {sub_no}: No cover image found inside '{cover_dir}' folder")
        elif len(image_files) > 1:
            raise HTTPException(status_code=400, detail=f"Set {sub_no}: Multiple cover images found inside '{cover_dir}' folder. Only 1 image is allowed (Found: {len(image_files)})")
            
        src_second_path = os.path.join(cover_dir, image_files[0])
        second_filename = image_files[0]
        log(f"Cover Mode: Auto-pulled cover image '{src_second_path}'")
    else:
        if not output_path or not output_path.strip():
            raise HTTPException(status_code=400, detail="Path (output_path) is required in Combine Mode")

        base_dir = output_path.strip()

        combine_folders: list[str] = []
        if folders_json and folders_json.strip():
            try:
                parsed_folders = json.loads(folders_json)
                if isinstance(parsed_folders, list):
                    combine_folders = [str(item).strip() for item in parsed_folders if str(item).strip()]
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid combine folder list: {e}")
        elif no and no.strip():
            combine_folders = [part.strip() for part in no.split(",") if part.strip()]

        if not combine_folders:
            raise HTTPException(status_code=400, detail="At least one sub folder is required in Combine Mode")

        combine_label = build_folder_label(combine_folders)

        durations = []
        if sub_mode == "view_channel" and durations_json:
            try:
                dur_list = json.loads(durations_json)
                durations = [float(d) for d in dur_list if str(d).strip()]
            except Exception as e:
                log(f"Combine Mode Warning: Failed to parse durations_json: {e}")
        prefix_str = prefix.strip() if prefix else ""

        for folder_name in combine_folders:
            subfolder = os.path.join(base_dir, folder_name)
                
            if not os.path.exists(subfolder) or not os.path.isdir(subfolder):
                raise HTTPException(status_code=400, detail=f"Set {folder_name}: Subfolder '{subfolder}' does not exist")

            media_files = []
            for f in os.listdir(subfolder):
                f_lower = f.lower()
                
                # Exclude output files from list of input media files
                is_output = False
                if "_combined" in f_lower:
                    is_output = True
                elif prefix_str:
                    import re
                    p_esc = re.escape(prefix_str)
                    c_esc = re.escape(combine_label)
                    pattern1 = f"^{p_esc}{c_esc}\\.mp4$"
                    pattern2 = f"^{p_esc}\\.mp4$"
                    pattern3 = f"^{p_esc}{c_esc}_\\d+\\.mp4$"
                    pattern4 = f"^{p_esc}_\\d+\\.mp4$"
                    if (re.match(pattern1, f, re.IGNORECASE) or 
                        re.match(pattern2, f, re.IGNORECASE) or 
                        re.match(pattern3, f, re.IGNORECASE) or 
                        re.match(pattern4, f, re.IGNORECASE)):
                        is_output = True
                
                if is_output:
                    continue

                if any(f_lower.endswith(ext) for ext in combine_media_exts) and os.path.isfile(os.path.join(subfolder, f)):
                    media_files.append(f)
                    
            import re
            def atoi(text): return int(text) if text.isdigit() else text
            def natural_keys(text): return [atoi(c) for c in re.split(r'(\d+)', text)]
            media_files.sort(key=natural_keys)
                    
            if len(media_files) == 0:
                raise HTTPException(status_code=400, detail=f"Set {folder_name}: No video file found in subfolder '{subfolder}'")
            
            for resolved_media_name in media_files:
                resolved_media_path = os.path.join(subfolder, resolved_media_name)
                combine_sources.append((folder_name, resolved_media_path, resolved_media_name))

        if sub_mode == "view_channel":
            total_videos = len(combine_sources)
            K = len(durations)
            if K == 0:
                raise HTTPException(status_code=400, detail="กรุณาระบุความยาววิดีโออย่างน้อย 1 ช่อง")
            if total_videos % K != 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"จำนวนวิดีโอในโฟลเดอร์ต้องหารด้วย {K} ลงตัว (พบทั้งหมด {total_videos} ไฟล์)"
                )

        src_video_path = combine_sources[0][1]
        video_filename = combine_sources[0][2]
        src_second_path = combine_sources[0][1]
        second_filename = combine_sources[0][2]
        log(f"Combine Mode: Auto-pulled {len(combine_sources)} matching files for folders '{combine_label}'")

    out_dir = ""
    if output_path and output_path.strip():
        out_path_clean = output_path.strip()
        if os.path.isdir(out_path_clean):
            out_dir = out_path_clean
        else:
            out_dir = os.path.dirname(out_path_clean)
            if not out_dir:
                out_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    else:
        out_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    prefix_str = prefix.strip() if prefix else ""

    if is_combine_mode:
        if combine_folders:
            out_dir = os.path.join(base_dir, combine_folders[0])
        else:
            out_dir = base_dir

        os.makedirs(out_dir, exist_ok=True)

        if sub_mode == "view_channel":
            K = len(durations)
            chunks = [combine_sources[i:i+K] for i in range(0, len(combine_sources), K)]
        else:
            chunks = [combine_sources]

        num_chunks = len(chunks)
        processed_outputs = []

        for chunk_idx, chunk_sources in enumerate(chunks, 1):
            if prefix_str:
                if num_chunks == 1:
                    if prefix_str.endswith("-") or prefix_str.endswith("_"):
                        video_filename = f"{prefix_str}{combine_label}.mp4"
                    else:
                        video_filename = f"{prefix_str}.mp4"
                else:
                    if prefix_str.endswith("-") or prefix_str.endswith("_"):
                        video_filename = f"{prefix_str}{combine_label}_{chunk_idx}.mp4"
                    else:
                        video_filename = f"{prefix_str}_{chunk_idx}.mp4"
            else:
                if num_chunks == 1:
                    video_filename = f"{combine_label}_combined.mp4"
                else:
                    video_filename = f"{combine_label}_combined_{chunk_idx}.mp4"
            
            final_output_path = os.path.join(out_dir, video_filename)
            log(f"Combine Mode Output Target [Chunk {chunk_idx}/{num_chunks}]: '{final_output_path}'")

            if os.path.exists(final_output_path):
                if str(overwrite).lower() == "true":
                    log(f"Chunk {chunk_idx}: Destination file already exists: '{final_output_path}'. Overwrite requested.")
                else:
                    log(f"Chunk {chunk_idx}: Destination file already exists: '{final_output_path}'. Skipping processing.")
                    processed_outputs.append(final_output_path)
                    continue

            def update_chunk_progress(percent: int, status: str):
                if job_id:
                    chunk_base = (chunk_idx - 1) / num_chunks * 100
                    scaled_percent = int(chunk_base + (percent / 100 * (100 / num_chunks)))
                    global_video_progress[job_id] = {
                        "percent": scaled_percent,
                        "status": f"[Chunk {chunk_idx}/{num_chunks}] {status}"
                    }

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    ffmpeg_bin = "/opt/homebrew/bin/ffmpeg"
                    if not os.path.exists(ffmpeg_bin):
                        ffmpeg_bin = "ffmpeg"
                        
                    list_txt = os.path.join(tmpdir, "list.txt")
                    amount_val = len(chunk_sources)

                    aligned_paths = []
                    for idx, (folder_name, v_path, resolved_media_name) in enumerate(chunk_sources, 1):
                        update_chunk_progress(int((idx - 1) / amount_val * 70), f"Processing video {idx} of {amount_val}...")
                        has_video_v, has_audio_v = probe_media_streams(v_path)
                        out_aligned = os.path.join(tmpdir, f"aligned_{idx}.mp4")
                        log(f"Combine Mode Chunk {chunk_idx} [{idx}/{amount_val}]: Aligning '{folder_name}/{resolved_media_name}' to 9:16 vertical 4K 60fps...")

                        if has_video_v and has_audio_v:
                            v_cmd = [
                                ffmpeg_bin, "-y", "-i", v_path,
                                "-filter_complex", "[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60[v];[0:a]aresample=async=1,aformat=sample_rates=48000:channel_layouts=stereo[a]",
                                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                            ]
                        elif has_video_v:
                            v_cmd = [
                                ffmpeg_bin, "-y", "-i", v_path, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                                "-filter_complex", "[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60[v]",
                                "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                            ]
                        elif has_audio_v:
                            v_cmd = [
                                ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=black:s=2160x3840:r=60", "-i", v_path,
                                "-map", "0:v", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                            ]
                        else:
                            raise RuntimeError(f"Matched file '{resolved_media_name}' has no usable audio or video stream")

                        if sub_mode == "view_channel" and len(durations) >= idx:
                            dur = durations[idx - 1]
                            v_cmd.extend(["-t", str(dur)])
                        
                        v_cmd.append(out_aligned)

                        res = subprocess.run(v_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if res.returncode != 0:
                            raise RuntimeError(f"FFmpeg failed aligning video {idx}: {res.stderr}")
                        aligned_paths.append(out_aligned)
                        
                    log(f"Combine Mode Chunk {chunk_idx}: Concatenating {amount_val} clips...")
                    update_chunk_progress(75, "Concatenating videos...")
                    with open(list_txt, "w", encoding="utf-8") as f:
                        for ap in aligned_paths:
                            f.write(f"file '{ap}'\n")

                    clean_audio_path = audio_path.strip().strip('"').strip("'") if audio_path else ""
                    
                    eq_parts = []
                    if contrast and contrast.strip(): eq_parts.append(f"contrast={contrast.strip()}")
                    if saturation and saturation.strip(): eq_parts.append(f"saturation={saturation.strip()}")
                    if brightness and brightness.strip(): eq_parts.append(f"brightness={brightness.strip()}")
                    if gamma and gamma.strip(): eq_parts.append(f"gamma={gamma.strip()}")
                    
                    video_filter_str = ""
                    if eq_parts:
                        video_filter_str = "eq=" + ":".join(eq_parts)
                    if unsharp and unsharp.strip():
                        if video_filter_str:
                            video_filter_str += f",unsharp={unsharp.strip()}"
                        else:
                            video_filter_str = f"unsharp={unsharp.strip()}"

                    if sub_mode == "view_channel" and clean_audio_path and os.path.isfile(clean_audio_path):
                        concat_out = os.path.join(tmpdir, "concat_temp.mp4")
                        concat_cmd = [
                            ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_txt,
                            "-c", "copy", concat_out
                        ]
                        res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if res.returncode != 0:
                            raise RuntimeError(f"FFmpeg failed concatenation: {res.stderr}")

                        log(f"View Channel Mode Chunk {chunk_idx}: Mixing original audio with background music... ({clean_audio_path})")
                        update_chunk_progress(90, "Mixing background music...")

                        bgm_dur = None
                        try:
                            probe_cmd = [
                                "/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe",
                                "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", clean_audio_path
                            ]
                            dur_str = subprocess.run(probe_cmd, capture_output=True, text=True).stdout.strip()
                            if dur_str:
                                bgm_dur = float(dur_str)
                        except Exception as e:
                            log(f"Warning: Could not probe background music duration: {e}")

                        volume_filter = ""
                        if audio_boost and audio_boost.strip():
                            try:
                                boost_val = float(audio_boost.strip())
                                volume_filter = f"volume={boost_val}dB,"
                            except ValueError:
                                pass
                                
                        video_volume_filter = ""
                        if video_audio_boost and video_audio_boost.strip():
                            try:
                                v_boost_val = float(video_audio_boost.strip())
                                video_volume_filter = f"volume={v_boost_val}dB"
                            except ValueError:
                                pass

                        if video_volume_filter:
                            filter_complex_str = f"[0:a:0]{video_volume_filter}[fg];[1:a:0]{volume_filter}apad[bgm];[fg][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
                        else:
                            filter_complex_str = f"[1:a:0]{volume_filter}apad[bgm];[0:a:0][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
                        
                        v_map = "0:v:0"
                        v_codec = "copy"
                        v_enc_args = []
                        
                        if video_filter_str:
                            filter_complex_str += f";[0:v:0]{video_filter_str}[vout]"
                            v_map = "[vout]"
                            v_codec = "libx264"
                            v_enc_args = ["-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p"]
                                
                        final_cmd = [
                            ffmpeg_bin, "-y", "-i", concat_out, "-i", clean_audio_path,
                            "-filter_complex", filter_complex_str,
                            "-map", v_map, "-map", "[aout]", "-c:v", v_codec
                        ] + v_enc_args + [
                            "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000"
                        ]

                        if bgm_dur is not None:
                            final_cmd.extend(["-t", str(bgm_dur)])
                        
                        final_cmd.extend([
                            "-disposition:a:0", "default", final_output_path
                        ])
                        res = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if res.returncode != 0:
                            raise RuntimeError(f"FFmpeg failed audio replacement: {res.stderr}")
                    else:
                        if video_filter_str:
                            concat_cmd = [
                                ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_txt,
                                "-vf", video_filter_str, "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
                                "-c:a", "copy", final_output_path
                            ]
                        else:
                            concat_cmd = [
                                ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_txt,
                                "-c", "copy", final_output_path
                            ]
                        res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if res.returncode != 0:
                            raise RuntimeError(f"FFmpeg failed concatenation: {res.stderr}")

                processed_outputs.append(final_output_path)
                update_chunk_progress(100, "Completed!")
            except Exception as e:
                log(f"Error processing chunk {chunk_idx}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed processing chunk {chunk_idx}: {e}")

        return {
            "ok": True,
            "output_paths": processed_outputs,
            "output_path": processed_outputs[0] if processed_outputs else ""
        }

    else:
        # Cover Mode: Video 1 + 2s Black + 3s Image
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                temp_input_video = src_video_path
                temp_input_second = src_second_path
                
                ffmpeg_bin = "/opt/homebrew/bin/ffmpeg"
                if not os.path.exists(ffmpeg_bin):
                    ffmpeg_bin = "ffmpeg"
                    
                list_txt = os.path.join(tmpdir, "list.txt")

                temp_video = os.path.join(tmpdir, "temp_video.mp4")
                temp_black = os.path.join(tmpdir, "temp_black.mp4")
                temp_second = os.path.join(tmpdir, "temp_second.mp4")
                
                has_audio = False
                try:
                    probe_cmd = [
                        "/opt/homebrew/bin/ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=codec_type", "-of", "json", temp_input_video
                    ]
                    if not os.path.exists(probe_cmd[0]):
                        probe_cmd[0] = "ffprobe"
                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    probe_data = json.loads(result.stdout)
                    has_audio = len(probe_data.get("streams", [])) > 0
                except Exception as e:
                    log(f"Video Helper Check Audio Warning: {e}")
                    has_audio = False
                    
                log(f"Video Helper: Input video 1 has audio track: {has_audio}")
                log("Video Helper [1/3]: Aligning first video to 9:16 vertical 4K 60fps...")
                if has_audio:
                    v_cmd = [
                        ffmpeg_bin, "-y", "-i", temp_input_video,
                        "-filter_complex", "[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60[v];[0:a]aresample=async=1,aformat=sample_rates=48000:channel_layouts=stereo[a]",
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_video
                    ]
                else:
                    v_cmd = [
                        ffmpeg_bin, "-y", "-i", temp_input_video, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-filter_complex", "[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60[v]",
                        "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_video
                    ]
                    
                res = subprocess.run(v_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed processing first video: {res.stderr}")
                    
                log("Video Helper [2/3]: Generating 2 seconds black screen...")
                b_cmd = [
                    ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=black:s=2160x3840:r=60:d=2",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=2",
                    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_black
                ]
                res = subprocess.run(b_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed generating black screen: {res.stderr}")
                    
                log("Video Helper [3/3]: Rendering cover image for 3 seconds...")
                i_cmd = [
                    ffmpeg_bin, "-y", "-loop", "1", "-i", temp_input_second,
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=3",
                    "-filter_complex", "[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60[v]",
                    "-map", "[v]", "-map", "1:a", "-t", "3", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_second
                ]
                res = subprocess.run(i_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed rendering image: {res.stderr}")
                    
                log("Video Helper [4/4]: Concatenating clips into final 9:16 60fps MP4 video...")
                with open(list_txt, "w", encoding="utf-8") as f:
                    f.write(f"file '{temp_video}'\n")
                    f.write(f"file '{temp_black}'\n")
                    f.write(f"file '{temp_second}'\n")
                    
                concat_cmd = [
                    ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_txt,
                    "-c", "copy", final_output_path
                ]
                res = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed concatenating video: {res.stderr}")
                
                log(f"Video Helper Success: Saved final video to '{final_output_path}'")
                update_progress(100, "Done")
                
            return {
                "ok": True,
                "output_path": final_output_path
            }
        except Exception as e:
            log(f"Video Helper Error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/utils/browse-directory")
def browse_directory() -> dict[str, Any]:
    import sys
    import subprocess
    import os
    
    if sys.platform == "darwin":
        try:
            cmd = ['osascript', '-e', 'POSIX path of (choose folder with prompt "Select Output Directory")']
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                path = res.stdout.strip()
                if path:
                    return {"ok": True, "path": path}
            return {"ok": False, "path": ""}
        except Exception as e:
            log(f"Browse Directory AppleScript Error: {e}")
            
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        directory = filedialog.askdirectory(parent=root, title="Select Output Directory")
        root.destroy()
        if directory:
            return {"ok": True, "path": os.path.normpath(directory)}
        return {"ok": False, "path": ""}
    except Exception as e:
        log(f"Browse Directory Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/utils/browse-file")
def browse_file(filter_type: str = "image") -> dict[str, Any]:
    import sys
    import subprocess
    import os
    
    is_audio = filter_type == "audio"
    
    if sys.platform == "darwin":
        try:
            if is_audio:
                exts = '{"mp3", "wav", "m4a", "aac", "flac", "ogg"}'
                prompt_msg = "Select Audio File"
            else:
                exts = '{"png", "jpg", "jpeg", "webp", "bmp"}'
                prompt_msg = "Select Reference Image"
                
            cmd = ['osascript', '-e', f'POSIX path of (choose file of type {exts} with prompt "{prompt_msg}")']
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                path = res.stdout.strip()
                if path:
                    return {"ok": True, "path": path}
            return {"ok": False, "path": ""}
        except Exception as e:
            log(f"Browse File AppleScript Error: {e}")
            
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        if is_audio:
            filetypes = [("Audio files", "*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg"), ("All files", "*.*")]
            prompt_msg = "Select Audio File"
        else:
            filetypes = [("Image files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("All files", "*.*")]
            prompt_msg = "Select Reference Image"
            
        file_path = filedialog.askopenfilename(
            parent=root,
            title=prompt_msg,
            filetypes=filetypes
        )
        root.destroy()
        if file_path:
            return {"ok": True, "path": os.path.normpath(file_path)}
        return {"ok": False, "path": ""}
    except Exception as e:
        log(f"Browse File Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/video/verify-audio")
def verify_audio(path: str):
    import os
    import subprocess
    import json
    if not path or not path.strip():
        return {"ok": False, "valid": False, "error": "ไม่ได้ระบุที่อยู่ไฟล์"}
    
    clean_path = path.strip().strip('"').strip("'")
    clean_path = os.path.expanduser(clean_path)
    
    if not os.path.exists(clean_path):
        return {"ok": False, "valid": False, "error": f"ไม่พบไฟล์ที่ระบุ (File not found): {clean_path}"}
        
    if not os.path.isfile(clean_path):
        return {"ok": False, "valid": False, "error": "ที่อยู่ที่ระบุไม่ใช่ไฟล์"}
        
    # Get codec and duration
    probe_cmd = [
        "/opt/homebrew/bin/ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,duration", "-of", "json", clean_path
    ]
    if not os.path.exists(probe_cmd[0]):
        probe_cmd[0] = "ffprobe"
        
    codec_name = "unknown"
    duration = "0"
    try:
        res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(res.stdout or "{}")
        streams = data.get("streams", [])
        if streams:
            codec_name = streams[0].get("codec_name", "unknown")
            duration = streams[0].get("duration", "0")
    except Exception as e:
        log(f"Audio verify probe error: {e}")
        
    return {
        "ok": True, 
        "valid": True,
        "codec": codec_name,
        "duration": duration,
        "max_volume": "N/A (Skipped)"
    }
@app.get("/api/utils/view-image")
def view_image(path: str) -> FileResponse:
    import os
    path = path.strip()
    if not path or not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="Invalid image path")
    
    lower_path = path.lower()
    valid_extensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]
    if not any(lower_path.endswith(ext) for ext in valid_extensions):
        raise HTTPException(status_code=400, detail="File is not a valid image format")
        
    return FileResponse(path)


@app.get("/api/utils/list-images")
def list_images(dir_path: str) -> dict[str, Any]:
    dir_path = dir_path.strip()
    if not dir_path:
        return {"images": []}
    
    import os
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    
    valid_extensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]
    images = []
    try:
        for item in sorted(os.listdir(dir_path)):
            full_path = os.path.join(dir_path, item)
            if os.path.isfile(full_path) and any(item.lower().endswith(ext) for ext in valid_extensions):
                images.append({
                    "name": item,
                    "path": full_path
                })
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def find_episode_dir(lakorn_path: str, ep_val: str):
    import re
    from pathlib import Path
    
    ep_val_clean = ep_val.strip().lower()
    if not ep_val_clean:
        return None
        
    path_obj = Path(lakorn_path)
    if not path_obj.exists() or not path_obj.is_dir():
        return None
        
    subdirs = [d for d in path_obj.iterdir() if d.is_dir()]
    
    # 1. Try exact match (case insensitive)
    for d in subdirs:
        if d.name.lower() == ep_val_clean:
            return d
            
    # 2. Try exact match with prepended "EP" if it's a number
    if ep_val_clean.isdigit():
        val_int = int(ep_val_clean)
        candidates = [
            f"ep{val_int}", 
            f"ep{val_int:02d}", 
            f"ep{val_int:03d}",
            f"{val_int:02d}", 
            f"{val_int:03d}",
            str(val_int)
        ]
        for d in subdirs:
            if d.name.lower() in candidates:
                return d

    # 3. Try finding by matching numbers exactly
    match = re.search(r"\d+", ep_val_clean)
    if match:
        target_num = int(match.group())
        for d in subdirs:
            num_matches = re.findall(r"\d+", d.name)
            for nm in num_matches:
                if int(nm) == target_num:
                    return d

    # 4. Fallback to simple substring match
    for d in subdirs:
        if ep_val_clean in d.name.lower():
            return d
            
    return None


def find_sub_ep_dir(parent_dir: Path, ep_val: str):
    import re
    ep_val_clean = ep_val.strip().lower()
    if not ep_val_clean:
        return parent_dir
        
    subdirs = [d for d in parent_dir.iterdir() if d.is_dir()]
    
    # 1. Try exact match
    for d in subdirs:
        if d.name.lower() == ep_val_clean:
            return d
            
    # 2. Try simple numeric candidates
    match = re.search(r"\d+", ep_val_clean)
    if match:
        val_int = int(match.group())
        candidates = [
            f"ep{val_int:02d}",
            f"ep{val_int}",
            f"ep{val_int:03d}",
            f"{val_int:02d}",
            f"{val_int:03d}",
            str(val_int)
        ]
        for d in subdirs:
            if d.name.lower() in candidates:
                return d
                
        # 3. Try finding directory containing target_num as distinct number
        for d in subdirs:
            num_matches = re.findall(r"\d+", d.name)
            for nm in num_matches:
                if int(nm) == val_int:
                    return d
                    
    # 4. Fallback to substring
    for d in subdirs:
        if ep_val_clean in d.name.lower():
            return d
            
    return parent_dir


@app.post("/api/utils/import-lakorn-auto")
def import_lakorn_auto(payload: ImportLakornPayload):
    import os
    import re
    from pathlib import Path

    lakorn_path = payload.lakorn_path.strip()
    ton_num = payload.ton_num
    ep_num = payload.ep_num
    ref_images_dir = payload.ref_images_dir.strip()

    if not lakorn_path or not os.path.exists(lakorn_path) or not os.path.isdir(lakorn_path):
        raise HTTPException(status_code=400, detail="ไม่พบ Drama Path ที่ระบุ")
    
    # 1. Find episode folder inside lakorn_path
    ep_dir = find_episode_dir(lakorn_path, ton_num)
    if not ep_dir:
        raise HTTPException(status_code=400, detail=f"ไม่พบโฟลเดอร์ตอนละครที่ระบุใน Drama Path (ค้นหาด้วยตอน: {ton_num})")

    # 1.5. Resolve character sheet directory (Strictly Global Path)
    resolved_ref_dir = None
    global_char_sheet = Path("/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/ผักกาดการละคร - ละครไทย/Character Sheet")
    if global_char_sheet.exists() and global_char_sheet.is_dir():
        resolved_ref_dir = global_char_sheet
    else:
        raise HTTPException(status_code=400, detail="ไม่พบโฟลเดอร์รูปภาพตัวละคร (Character Sheet) ใน Path หลักที่ตั้งค่าไว้")

    ref_images_dir = str(resolved_ref_dir)

    # 2. Find prompt directory inside episode folder
    prompt_dir = None
    for candidate in ["4 - Image Prompt", "4-Image Prompt", "Image Prompt", "image prompt"]:
        path = ep_dir / candidate
        if path.exists() and path.is_dir():
            prompt_dir = path
            break
            
    if not prompt_dir:
        # Fallback: scan subdirs for anything containing 'prompt'
        dirs = [d for d in ep_dir.iterdir() if d.is_dir()]
        for d in dirs:
            if "prompt" in d.name.lower():
                prompt_dir = d
                break
                
    if not prompt_dir:
        raise HTTPException(status_code=400, detail="ไม่พบโฟลเดอร์พรอพต์ภาพ (4 - Image Prompt)")

    # Find specific EP subfolder under prompt_dir
    ep_prompt_dir = find_sub_ep_dir(prompt_dir, ep_num)

    # List all prompt files
    prompt_files = sorted([
        f for f in ep_prompt_dir.iterdir() 
        if f.is_file() and f.suffix.lower() in (".md", ".txt")
    ], key=lambda x: x.name)

    # 3. Find character directory inside episode folder
    char_dir = None
    for candidate in ["4 - Character Each Scene", "4-Character Each Scene", "Character Each Scene", "character each scene"]:
        path = ep_dir / candidate
        if path.exists() and path.is_dir():
            char_dir = path
            break
            
    if not char_dir:
        # Fallback: scan subdirs for anything containing 'character' or 'scene'
        dirs = [d for d in ep_dir.iterdir() if d.is_dir()]
        for d in dirs:
            if "character" in d.name.lower() or "scene" in d.name.lower():
                char_dir = d
                break
                
    if not char_dir:
        raise HTTPException(status_code=400, detail="ไม่พบโฟลเดอร์พรอพต์ตัวละครรายฉาก (4 - Character Each Scene)")

    # Find specific EP subfolder under char_dir
    ep_char_dir = find_sub_ep_dir(char_dir, ep_num)

    # List all character files
    char_files = sorted([
        f for f in ep_char_dir.iterdir() 
        if f.is_file() and f.suffix.lower() in (".md", ".txt")
    ], key=lambda x: x.name)

    # 4. Scan the reference images folder to map names to actual paths
    images = []
    if ref_images_dir and os.path.exists(ref_images_dir) and os.path.isdir(ref_images_dir):
        valid_extensions = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
        for item in sorted(os.listdir(ref_images_dir)):
            full_path = os.path.join(ref_images_dir, item)
            if os.path.isfile(full_path) and item.lower().endswith(valid_extensions):
                images.append({
                    "name": item,
                    "path": full_path
                })

    # Calculate max rounds dynamically based on files found
    max_rounds = max(len(prompt_files), len(char_files))
    if max_rounds == 0:
        max_rounds = 1

    prompts_by_round = {str(r): [] for r in range(1, max_rounds + 1)}
    ref_images_by_round = {str(r): ["", "", "", "", "", "", ""] for r in range(1, max_rounds + 1)}

    # Process prompt files and insert into corresponding rounds
    for idx, p_file in enumerate(prompt_files):
        round_num = idx + 1
        try:
            content = p_file.read_text(encoding="utf-8")
            prompts_by_round[str(round_num)] = [content.strip()]
        except Exception as e:
            log(f"Error reading prompt file {p_file.name}: {e}")

    # Process character files and match reference images
    for idx, c_file in enumerate(char_files):
        round_num = idx + 1
        try:
            content = c_file.read_text(encoding="utf-8")
            lines = content.splitlines()
            imported_names = []
            for line in lines:
                cleaned = line.strip()
                if not cleaned:
                    continue
                # Clean markdown bullet points/numbers
                cleaned = re.sub(r"^[\s\-\*\+\d\.\#]+", "", cleaned).strip()
                # Handle markdown link brackets: e.g. [Character Name](...)
                bracket_match = re.search(r"\[([^\]]+)\]", cleaned)
                if bracket_match:
                    cleaned = bracket_match.group(1).strip()
                if cleaned:
                    imported_names.append(cleaned)

            # Match names with images
            matched_paths = []
            for name in imported_names:
                name_lower = name.lower()
                # 1. Exact match with extension
                matched_img = next((img for img in images if img["name"].lower() == name_lower), None)
                # 2. Match without extension
                if not matched_img:
                    matched_img = next((img for img in images if Path(img["name"]).stem.lower() == name_lower), None)
                if matched_img:
                    matched_paths.append(matched_img["path"])

            # Save up to 7 reference images for the round
            round_refs = matched_paths[:7]
            while len(round_refs) < 7:
                round_refs.append("")
            
            ref_images_by_round[str(round_num)] = round_refs
        except Exception as e:
            log(f"Error reading character file {c_file.name}: {e}")

    return {
        "ok": True,
        "prompts_by_round": prompts_by_round,
        "ref_images_by_round": ref_images_by_round,
        "ref_images_dir": ref_images_dir,
        "message": f"นำเข้าข้อมูลและจับคู่ตัวละครสำหรับตอนที่ {ep_num} เรียบร้อยแล้ว (จำนวน {len(prompt_files)} ฉาก)"
    }


@app.post("/api/utils/import-lakorn-video-auto")
def import_lakorn_video_auto(payload: ImportLakornVideoPayload):
    import os
    import re
    from pathlib import Path

    lakorn_path = payload.lakorn_path.strip()
    ton_num = payload.ton_num
    ep_num = payload.ep_num

    if not lakorn_path or not os.path.exists(lakorn_path) or not os.path.isdir(lakorn_path):
        raise HTTPException(status_code=400, detail="ไม่พบ Drama Path ที่ระบุ")
    
    # 1. Find episode folder inside lakorn_path
    ep_dir = find_episode_dir(lakorn_path, ton_num)
    if not ep_dir:
        raise HTTPException(status_code=400, detail=f"ไม่พบโฟลเดอร์ตอนละครที่ระบุใน Drama Path (ค้นหาด้วยตอน: {ton_num})")

    # 2. Find animation prompt directory inside episode folder
    prompt_dir = None
    for candidate in ["4 - Animation Prompt", "4-Animation Prompt", "Animation Prompt", "animation prompt", "4 - Video Prompt", "Video Prompt", "video prompt"]:
        path = ep_dir / candidate
        if path.exists() and path.is_dir():
            prompt_dir = path
            break
            
    if not prompt_dir:
        dirs = [d for d in ep_dir.iterdir() if d.is_dir()]
        for d in dirs:
            name_lower = d.name.lower()
            if "prompt" in name_lower and ("animation" in name_lower or "video" in name_lower):
                prompt_dir = d
                break
        if not prompt_dir:
            for d in dirs:
                if "prompt" in d.name.lower():
                    prompt_dir = d
                    break
                    
    if not prompt_dir:
        raise HTTPException(status_code=400, detail="ไม่พบโฟลเดอร์พรอพต์ภาพเคลื่อนไหว (4 - Animation Prompt)")

    # Find specific EP subfolder under prompt_dir
    ep_prompt_dir = find_sub_ep_dir(prompt_dir, ep_num)

    # List all prompt files
    prompt_files = sorted([
        f for f in ep_prompt_dir.iterdir() 
        if f.is_file() and f.suffix.lower() in (".md", ".txt")
    ], key=lambda x: x.name)

    max_rounds = max(len(prompt_files), 1)
    prompts_by_round = {str(r): [] for r in range(1, max_rounds + 1)}

    for idx, p_file in enumerate(prompt_files):
        round_num = idx + 1
        try:
            content = p_file.read_text(encoding="utf-8")
            prompts_by_round[str(round_num)] = [content.strip()]
        except Exception as e:
            log(f"Error reading video prompt file {p_file.name}: {e}")

    return {
        "ok": True,
        "prompts_by_round": prompts_by_round,
        "message": f"นำเข้าข้อมูลพรอพต์วิดีโอสำหรับตอนที่ {ep_num} เรียบร้อยแล้ว (จำนวน {len(prompt_files)} ฉาก)"
    }


_upload_images_stop_flag = False

@app.post("/api/step/stop-upload-google-flow")
def stop_upload_google_flow() -> dict[str, Any]:
    global _upload_images_stop_flag
    _upload_images_stop_flag = True
    return {"ok": True, "message": "Stop flag set"}

@app.post("/api/step/upload-google-flow-images")
def upload_google_flow_images(payload: UploadImagesGoogleFlowPayload) -> dict[str, Any]:
    global _upload_images_stop_flag
    _upload_images_stop_flag = False
    
    import os
    import subprocess
    import time
    from pathlib import Path
    
    _activate_chrome()
    
    folder_path = payload.folder_path.strip()
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail="Invalid folder path")
        
    valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    images = []
    for f in os.listdir(folder_path):
        full_path = os.path.join(folder_path, f)
        if os.path.isfile(full_path) and Path(f).suffix.lower() in valid_exts:
            images.append(full_path)
            
    import re
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
    images.sort(key=natural_sort_key)
    
    if not images:
        return {"ok": False, "message": "ไม่พบไฟล์รูปภาพในโฟลเดอร์ที่เลือก"}
        
    def upload_macos_file_dialog(file_path: str):
        escaped_path = file_path.replace('"', '\\"')
        script = f"""
        set the clipboard to "{escaped_path}"
        delay 0.5
        tell application "System Events"
            -- Press Cmd + Shift + G to open path dialog
            key code 5 using {{command down, shift down}}
            delay 0.75
            
            -- Press Cmd + V to paste
            key code 9 using {{command down}}
            delay 1.0
            
            -- Enter to confirm path
            keystroke return
            delay 1.5
            
            -- Enter to confirm file selection
            keystroke return
        end tell
        """
        try:
            subprocess.run(["osascript", "-e", script], check=False)
            return True
        except Exception as e:
            log(f"AppleScript dialog input failed: {e}")
            return False

    log(f"Found {len(images)} images to upload to Google Flow.")
    
    for idx, img_path in enumerate(images):
        if _upload_images_stop_flag:
            log("Upload forcefully stopped by user.")
            return {"ok": False, "message": f"ยกเลิกการอัพโหลดแล้ว (สำเร็จ {idx}/{len(images)} รูป)"}
            
        log(f"Uploading image {idx+1}/{len(images)}: {os.path.basename(img_path)}")
        _activate_chrome()
        time.sleep(1.0)
        
        # Press Cmd + U to open file picker (Use key code 32 for 'U' to bypass keyboard layout issues)
        cmd_u_script = """
        tell application "System Events"
            key code 32 using command down
        end tell
        """
        subprocess.run(["osascript", "-e", cmd_u_script], check=False)
        
        log("Waiting 1.5 seconds for file modal to fully open...")
        time.sleep(1.5)
        
        upload_macos_file_dialog(img_path)
        
        log("Waiting 2.5 seconds for file upload to settle...")
        time.sleep(2.5) 

    return {"ok": True, "message": f"อัพโหลด {len(images)} รูปไปยัง Google Flow เรียบร้อยแล้ว"}


@app.post("/api/step/video-gen")
def step_video_gen(payload: VideoGenStepPayload) -> dict[str, Any]:
    _activate_chrome()
    prompt = payload.prompt.strip()
    round_idx = payload.round_idx
    google_flow_path = payload.google_flow_path.strip()
    video_input_selector = payload.video_input_selector.strip()
    video_settings_selector = payload.video_settings_selector.strip()
    video_submit_selector = payload.video_submit_selector.strip()
    video_wait_seconds = payload.video_wait_seconds

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    bot = None
    try:
        bot = browser_manager.get()
        _ = bot.driver.window_handles
    except Exception as e:
        log(f"Warning: Browser session check failed ({e}). Recreating browser session...")
        browser_manager.close()
        bot = browser_manager.get()
        
    driver = bot.driver

    # 1. Switch to Google Flow tab if it exists (no redirect/get)
    switched = False
    for url_part in ["tools/flow", "labs.google", "vids.google.com"]:
        if bot.switch_to_tab_containing(url_part):
            switched = True
            break

    if not switched and google_flow_path:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(google_flow_path)
            if parsed.netloc and bot.switch_to_tab_containing(parsed.netloc):
                switched = True
        except Exception:
            pass

    if not switched:
        raise HTTPException(status_code=400, detail="ไม่พบแท็บ Google Flow ที่เปิดอยู่ กรุณาเปิดแท็บ Google Flow ค้างไว้ก่อนทำการรัน")

    # Bring Chrome window to front (Commented out to run completely in background)
    # _activate_chrome()

    # 3. Find and click prompt input field
    if not video_input_selector:
        video_input_selector = "div[contenteditable='true'] p, div[contenteditable='true'], [role='textbox'] p, textarea"

    # Wait for the card list to render the new box if it's not the first run
    if not payload.is_first_run:
        log("[รอการ์ดใหม่] รอให้ Google Flow โหลดกล่องป้อนพรอพต์ใหม่ขึ้นมาบนหน้าจอ...")
        for wait_attempt in range(12):
            try:
                boxes_check = driver.find_elements(By.CSS_SELECTOR, video_input_selector)
                if len(boxes_check) >= 2:
                    log(f"[การ์ดใหม่พร้อม] พบกล่องข้อความใหม่แล้ว (จำนวนกล่องทั้งหมด: {len(boxes_check)})")
                    break
            except Exception:
                pass
            time.sleep(1.0)

    log(f"[กำลังค้นหาช่องพรอพต์] ค้นหาช่องป้อนพรอพต์ด้วย CSS Selector: {video_input_selector} (รอบที่ {round_idx})")
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, video_input_selector))
        )
        boxes = driver.find_elements(By.CSS_SELECTOR, video_input_selector)
        if len(boxes) >= round_idx:
            box = boxes[round_idx - 1]
            log(f"[เลือกช่องพรอพต์] เลือกลำดับกล่องข้อความที่ {round_idx - 1} สำหรับรอบที่ {round_idx}")
        else:
            box = boxes[-1]
            log(f"[เลือกช่องพรอพต์] ไม่พบหมายเลขกล่องตรงรอบ ใช้กล่องสุดท้ายลำดับที่ {len(boxes) - 1}")
    except Exception as e1:
        log(f"ไม่พบช่องพรอพต์ด้วยตัวเลือกหลัก ({e1}) ลองใช้ตัวเลือกสำรอง (hashed class selector)...")
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#__next > div.sc-c7ee1759-1.jhwuTJ > div.sc-7175135e-1.dIpEew > div > div > div > div > div.sc-26b30722-3.kezgTH > div > p"))
            )
            boxes = driver.find_elements(By.CSS_SELECTOR, "#__next > div.sc-c7ee1759-1.jhwuTJ > div.sc-7175135e-1.dIpEew > div > div > div > div > div.sc-26b30722-3.kezgTH > div > p")
            if len(boxes) >= round_idx:
                box = boxes[round_idx - 1]
            else:
                box = boxes[-1]
        except Exception as e2:
            raise HTTPException(status_code=400, detail="ไม่พบช่องป้อนพรอพต์บนหน้าเว็บ Google Flow")

    # Click the input box to focus
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", box)
        time.sleep(0.5)
    except Exception:
        pass

    try:
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)
        actions.move_to_element(box).click().perform()
        log("[โฟกัสสำเร็จ] โฟกัสช่องพรอพต์ด้วย ActionChains")
    except Exception:
        try:
            box.click()
            log("[โฟกัสสำเร็จ] โฟกัสช่องพรอพต์ด้วย Standard Click")
        except Exception:
            driver.execute_script("arguments[0].click();", box)
            log("[โฟกัสสำเร็จ] โฟกัสช่องพรอพต์ด้วย JS Click")
    time.sleep(1.5)


    # 4. Type @ using ActionChains keyboard events
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log("[ป้อนข้อมูล] พิมพ์ @ ด้วยคีย์บอร์ดเสมือน")
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)
        actions.send_keys("@").perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"พิมพ์ @ ด้วย ActionChains ล้มเหลว, ใช้ box.send_keys: {e}")
        box.send_keys("@")
    time.sleep(3.0) # Wait 3.0s after typing @

    # Type round number using ActionChains keyboard events
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    text_to_type = f"{round_idx:02d}"
    log(f"[ป้อนข้อมูล] พิมพ์หมายเลขอ้างอิง (01, 02, ...) ด้วยคีย์บอร์ดเสมือน: {text_to_type}")
    try:
        actions = ActionChains(driver)
        actions.send_keys(text_to_type).perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"พิมพ์ด้วย ActionChains ล้มเหลว, ใช้ box.send_keys: {e}")
        box.send_keys(text_to_type)
    time.sleep(3.0) # Wait 3.0s for autocomplete

    # Press Enter using ActionChains keyboard events
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log("[ป้อนข้อมูล] กด Enter ด้วยคีย์บอร์ดเสมือน")
    try:
        actions = ActionChains(driver)
        actions.send_keys(Keys.ENTER).perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"กด Enter ด้วย ActionChains ล้มเหลว, ใช้ box.send_keys: {e}")
        box.send_keys(Keys.ENTER)
    
    # Wait 3.0 seconds after selecting autocomplete
    time.sleep(3.0)

    # Press Spacebar 1 time
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log("[ป้อนข้อมูล] กด Spacebar ด้วยคีย์บอร์ดเสมือน 1 ครั้ง")
    try:
        actions = ActionChains(driver)
        actions.send_keys(Keys.SPACE).perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"กด Spacebar ล้มเหลว: {e}")
    time.sleep(1.5)

    # 5. Paste the animation prompt using Selenium's native send_keys
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log(f"[ป้อนข้อมูล] พิมพ์พรอพต์ของฉากด้วย Selenium send_keys: {prompt}")
    try:
        # Split prompt by newlines and send shift+enter in between to avoid triggering early submits
        lines = prompt.split('\n')
        for idx, line in enumerate(lines):
            if idx > 0:
                actions = ActionChains(driver)
                actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
                time.sleep(0.2)
            
            # Prepend space on the first line to separate from mention chip
            text_chunk = (" " if idx == 0 else "") + line
            if text_chunk:
                box.send_keys(text_chunk)
        log("[ป้อนข้อมูลสำเร็จ] วางพรอพต์สำเร็จผ่าน Selenium send_keys")
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"พิมพ์ผ่าน Selenium send_keys ล้มเหลว: {e}")
        raise HTTPException(status_code=500, detail=f"ไม่สามารถกรอกพรอพต์ได้: {e}")
    time.sleep(3.0)

    # Press Enter to submit the prompt
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log("[ป้อนข้อมูล] กด Enter เพื่อส่ง prompt")
    try:
        actions = ActionChains(driver)
        actions.send_keys(Keys.ENTER).perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"ส่ง Enter ล้มเหลว, ใช้ box.send_keys: {e}")
        box.send_keys(Keys.ENTER)
    time.sleep(3.0)

    # 5. Click settings button to check/verify settings if specified
    if video_settings_selector:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"คลิกปุ่มตั้งค่าด้วย CSS Selector: {video_settings_selector}")
        try:
            settings_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, video_settings_selector))
            )
            try:
                settings_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", settings_btn)
            time.sleep(1.5) # Wait for settings panel to verify/load
        except Exception as e:
            if not is_driver_alive(driver):
                raise RuntimeError("Browser connection lost.")
            log(f"Warning: ไม่สามารถคลิกปุ่มตั้งค่าได้: {e}")

    # 6. Submit/Send the prompt
    if video_submit_selector:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"คลิกปุ่มส่งพรอพต์ด้วย CSS Selector: {video_submit_selector}")
        try:
            submit_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, video_submit_selector))
            )
            try:
                submit_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", submit_btn)
        except Exception as e:
            if not is_driver_alive(driver):
                raise RuntimeError("Browser connection lost.")
            raise HTTPException(status_code=400, detail=f"ไม่พบปุ่มส่งพรอพต์: {e}")
    else:
        log("ยกเลิกการกดปุ่ม Enter บังคับส่งพรอพต์เพื่อรอให้ผู้ใช้ตรวจทานข้อความ")

    log(f"วางพรอพต์เรียบร้อยแล้ว เริ่มเวลารอ {video_wait_seconds} วินาที...")
    return {"ok": True, "message": "วางพรอพต์และเริ่มต้นการรอ"}


class VideoRetryPayload(BaseModel):
    round_idx: int

@app.post("/api/step/video-retry")
def step_video_retry(payload: VideoRetryPayload):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    bot = None
    try:
        bot = browser_manager.get()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ไม่สามารถเชื่อมต่อ Browser ได้: {e}")

    driver = bot.driver

    # 1. Switch to Google Flow tab if it exists
    switched = False
    for url_part in ["tools/flow", "labs.google", "vids.google.com"]:
        if bot.switch_to_tab_containing(url_part):
            switched = True
            break

    if not switched:
        raise HTTPException(status_code=400, detail="ไม่พบแท็บ Google Flow ที่เปิดอยู่")

    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")

    round_str = f"{payload.round_idx:02d}"
    log(f"[Retry] ค้นหาปุ่มลองอีกครั้ง (Retry) สำหรับรอบที่ {payload.round_idx}")

    # Build possible XPath selectors to locate the retry button for the specific round/card
    retry_btn = None
    possible_xpaths = [
        # Strategy A: Find card containing round mention text (e.g. "@01" or "@01.png" or "round_01.png") and locate the refresh button inside it
        f"//div[contains(., '@{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
        f"//div[contains(., 'round_{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
        f"//div[contains(., '{round_str}.png')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
        # Strategy B: Fallback to general retry buttons, click the last one (latest)
        "//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]"
    ]

    for xpath in possible_xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            if elements:
                # If we matched Strategy B, take the last one
                if xpath == "//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]":
                    retry_btn = elements[-1]
                else:
                    retry_btn = elements[0]
                break
        except Exception:
            continue

    if not retry_btn:
        raise HTTPException(status_code=400, detail="ไม่พบปุ่ม 'ลองอีกครั้ง' (Retry) บนหน้าเว็บ")

    # 3. Click the retry button
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", retry_btn)
        time.sleep(0.5)
        retry_btn.click()
        log(f"[Retry สำเร็จ] คลิกปุ่มลองอีกครั้งสำหรับรอบที่ {payload.round_idx} สำเร็จ")
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", retry_btn)
            log(f"[Retry สำเร็จ] คลิกปุ่มลองอีกครั้งด้วย JS สำหรับรอบที่ {payload.round_idx} สำเร็จ")
        except Exception as click_err:
            raise HTTPException(status_code=500, detail=f"ไม่สามารถคลิกปุ่มลองอีกครั้งได้: {click_err}")

    return {"ok": True, "message": f"คลิกปุ่มลองอีกครั้งรอบที่ {payload.round_idx} เรียบร้อยแล้ว"}


class SeedancePayload(BaseModel):
    prompt: str


@app.post("/api/step/seedance")
async def step_seedance(payload: SeedancePayload):
    try:
        bot = browser_manager.get()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ไม่สามารถเชื่อมต่อ Browser ได้: {e}")

    try:
        # Check if tab exists and switch to it
        switched = bot.switch_to_tab_containing("dreamina.capcut.com")
        if not switched:
            bot.driver.execute_script("window.open('https://dreamina.capcut.com/ai-tool/generate', '_blank');")
            await asyncio.sleep(1) # wait for tab handles to update
            bot.switch_to_tab_containing("dreamina.capcut.com")
    except Exception as e:
        if not is_driver_alive(bot.driver):
            browser_manager.close()
            raise HTTPException(status_code=400, detail="Browser connection was lost.")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดขณะสลับแท็บ: {e}")

    safe_prompt = payload.prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    js_inject = f"""
    (function() {{
        const el = document.querySelector('.tiptap.ProseMirror');
        if (el) {{
            el.innerHTML = '<p>{safe_prompt}</p>';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return true;
        }}
        return false;
    }})();
    """

    try:
        success = False
        for _ in range(10):
            res = bot.driver.execute_script(js_inject)
            if res:
                success = True
                break
            await asyncio.sleep(0.5)

        if not success:
            raise HTTPException(status_code=400, detail="ไม่พบกล่องป้อนพรอพต์ในหน้าเว็บ CapCut Dreamina (กรุณาเปิดหน้าเว็บทิ้งไว้)")

        _activate_chrome()
        return {"ok": True, "message": "Injected prompt successfully."}

    except Exception as e:
        if not is_driver_alive(bot.driver):
            browser_manager.close()
            raise HTTPException(status_code=400, detail="Browser connection was lost.")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดขณะส่งพรอพต์: {e}")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "web" / "index.html")


app.mount("/web", StaticFiles(directory=BASE_DIR / "web"), name="web")
