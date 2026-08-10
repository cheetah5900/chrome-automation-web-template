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

def correct_legacy_paths(data):
    import os
    import re
    if isinstance(data, dict):
        return {k: correct_legacy_paths(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [correct_legacy_paths(item) for item in data]
    elif isinstance(data, str):
        if data.startswith("/Users/"):
            current_home = os.path.expanduser("~")
            match = re.match(r"^/Users/[^/]+", data)
            if match:
                old_home = match.group(0)
                if old_home != current_home:
                    data = data.replace(old_home, current_home, 1)
        if "//" in data:
            data = data.replace("//", "/")
        if "MythicForge84 - วิว/วิว/Soundtrack" in data:
            data = data.replace("MythicForge84 - วิว/วิว/Soundtrack", "[เลิกใช้] 0 - MythicForge84 - วิว /วิว - out/Soundtrack")
        return data
    else:
        return data

RUNTIME_DIR.mkdir(exist_ok=True)


def _ensure_json(path: Path, default_obj: dict):
    if not path.exists():
        path.write_text(json.dumps(default_obj, indent=2))


_ensure_json(DEFAULTS_FILE, {"selected_profile": "", "theme": "sunset-glass"})
_ensure_json(PROFILES_FILE, {"selected_profile": "", "profiles": []})

def _normalize_profiles_paths():
    if not PROFILES_FILE.exists():
        return
    try:
        data = json.loads(PROFILES_FILE.read_text())
        changed = False
        profiles = data.get("profiles", [])
        for p in profiles:
            path_str = p.get("path", "")
            if "chrome-profiles" in path_str:
                parts = Path(path_str).parts
                if "chrome-profiles" in parts:
                    idx = parts.index("chrome-profiles")
                    if idx + 1 < len(parts):
                        profile_name = parts[idx + 1]
                        new_path = RUNTIME_DIR / "chrome-profiles" / profile_name
                        if path_str != str(new_path):
                            p["path"] = str(new_path)
                            changed = True
        if changed:
            PROFILES_FILE.write_text(json.dumps(data, indent=2))
            print("Normalized profiles.json paths to match current project directory.")
    except Exception as e:
        print(f"Error normalizing profile paths: {e}")

_normalize_profiles_paths()

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

# ─── Flow Kit (GFA) Integration ──────────────────────────────
try:
    from agent.api.characters import router as characters_router
    from agent.api.projects import router as projects_router
    from agent.api.videos import router as videos_router
    from agent.api.scenes import router as scenes_router
    from agent.api.requests import router as requests_router
    from agent.api.flow import router as flow_router
    from agent.api.reviews import router as reviews_router
    from agent.api.tts import router as tts_router
    from agent.api.materials import router as materials_router
    from agent.api.music import router as music_router
    from agent.api.models import router as models_router
    from agent.api.active_project import router as active_project_router
    from agent.api.batch_uploader import router as batch_uploader_router
    from agent.main import ext_callback, dashboard_ws, health as flow_health

    app.include_router(projects_router, prefix="/api")
    app.include_router(scenes_router, prefix="/api")
    app.include_router(videos_router, prefix="/api")
    app.include_router(characters_router, prefix="/api")
    app.include_router(requests_router, prefix="/api")
    app.include_router(flow_router, prefix="/api")
    app.include_router(reviews_router, prefix="/api")
    app.include_router(tts_router, prefix="/api")
    app.include_router(materials_router, prefix="/api")
    app.include_router(music_router, prefix="/api")
    app.include_router(models_router)
    app.include_router(active_project_router)
    app.include_router(batch_uploader_router, prefix="/api")

    # Native callback and WS handlers for extension/dashboard
    app.post("/api/ext/callback")(ext_callback)
    app.websocket("/ws/dashboard")(dashboard_ws)
    app.get("/health")(flow_health)
    
    print("Flow Kit routers registered successfully.")
except ImportError as e:
    print(f"Skipping Flow Kit routers/callbacks import: {e}")

# Flow Kit startup background tasks
_flow_kit_ws_task = None
_flow_kit_worker_task = None

@app.on_event("startup")
async def startup_flow_kit():
    global _flow_kit_ws_task, _flow_kit_worker_task
    try:
        from agent.db.schema import init_db
        from agent.materials import register_material, _BUILTIN_IDS
        from agent.db.crud import list_materials as db_list_materials
        from agent.sdk import init_sdk
        from agent.services.flow_client import get_flow_client
        from agent.worker.processor import get_worker_controller
        from agent.main import run_ws_server
        
        # 1. Init Flow Kit database
        await init_db()

        # Clear stale pending/processing tasks on startup so they do not execute unwantedly
        try:
            from agent.db.schema import get_db, _db_lock
            db = await get_db()
            async with _db_lock:
                await db.execute("UPDATE request SET status='FAILED', error_message='Stale task aborted on server start' WHERE status IN ('PENDING', 'PROCESSING')")
                await db.commit()
                print("Aborted stale pending/processing requests on startup")
        except Exception as stale_err:
            print(f"Failed to clear stale requests on startup: {stale_err}")
        
        # 2. Load custom materials
        try:
            custom_materials = await db_list_materials()
            for m in custom_materials:
                if m["id"] not in _BUILTIN_IDS:
                    register_material(m)
        except Exception as e:
            print(f"Failed to load custom materials: {e}")
            
        # 3. Init SDK
        init_sdk(get_flow_client())
        
        # 4. Start WebSocket Server and worker processor
        controller = get_worker_controller()
        
        # Load worker cooldown settings from config on startup
        try:
            delay_min = float(_get_config_value("flowkit_worker_delay_min", 10.0))
            delay_max = float(_get_config_value("flowkit_worker_delay_max", 20.0))
            controller.update_cooldown(delay_min, delay_max)
            print(f"Flow Kit worker API delay range configured: {delay_min}s - {delay_max}s")
        except Exception as cooldown_err:
            print(f"Failed to apply worker cooldown range config: {cooldown_err}")
            
        _flow_kit_ws_task = asyncio.create_task(run_ws_server())
        _flow_kit_worker_task = asyncio.create_task(controller.start())
        print("Flow Kit background services (WebSocket + Worker) started successfully!")
    except Exception as e:
        print(f"Failed to start Flow Kit background services: {e}")



class ProviderPayload(BaseModel):
    provider: str
    api_key: str


class SaveSettingsPayload(BaseModel):
    urls: list[str] = []


class CreateProfilePayload(BaseModel):
    name: str
    debug_port: int = 9222
    startup_urls: list[str] = []
    browser_type: str = "chrome"


class UpdateProfilePayload(BaseModel):
    old_name: str
    new_name: str
    debug_port: int = 9222
    startup_urls: list[str] = []
    browser_type: str = "chrome"


class SelectProfilePayload(BaseModel):
    name: str


class DeleteProfilePayload(BaseModel):
    name: str


class LaunchProfilePayload(BaseModel):
    name: str


class ForceKillPayload(BaseModel):
    port: int

class CloseProfilePayload(BaseModel):
    port: int = 9222



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
    google_flow_email: str = "dogdadcatmom@gmail.com"
    google_flow_project_name: str = "7-1"
    auto_retry_mode: bool = False
    video_gen_mode: str = "selenium"
    video_model: str = ""
    output_count: int = 1
    upscale_resolution: str = "NONE"




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

def _kill_port_processes(port: int):
    try:
        res = subprocess.run(["lsof", "-t", "-i", f"tcp:{port}"], capture_output=True, text=True)
        pids = res.stdout.strip().split("\n")
        for pid in pids:
            if pid.strip().isdigit():
                subprocess.run(["kill", "-9", pid.strip()], check=False)
                print(f"Killed process {pid} on port {port}")
    except Exception as e:
        print(f"Error killing processes on port {port}: {e}")



def _get_selected_profile_browser_type() -> str:
    try:
        if DEFAULTS_FILE.exists() and PROFILES_FILE.exists():
            defaults = _read_json(DEFAULTS_FILE)
            selected_name = defaults.get("selected_profile", "")
            if selected_name:
                profiles_data = _read_json(PROFILES_FILE)
                profiles = profiles_data.get("profiles", [])
                profile = next((p for p in profiles if p.get("name") == selected_name), None)
                if profile:
                    return profile.get("browser_type", "chrome")
    except Exception:
        pass
    return "chrome"


def _get_active_browser_binary(browser_type: str = None) -> str:
    import os
    if browser_type is None:
        browser_type = _get_selected_profile_browser_type()
        
    canary_binary = "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
    chrome_binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    brave_binary = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    edge_binary = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    
    if browser_type == "canary":
        return canary_binary
    elif browser_type == "brave":
        return brave_binary
    elif browser_type == "edge":
        return edge_binary
    elif browser_type == "chrome":
        return chrome_binary
        
    # Auto-detect fallback if profile browser type is default/missing
    if os.path.exists(canary_binary):
        return canary_binary
    elif os.path.exists(chrome_binary):
        return chrome_binary
    elif os.path.exists(brave_binary):
        return brave_binary
    elif os.path.exists(edge_binary):
        return edge_binary
    return chrome_binary


def _get_active_browser_app_name(browser_type: str = None) -> str:
    import os
    if browser_type is None:
        browser_type = _get_selected_profile_browser_type()
        
    if browser_type == "canary":
        return "Google Chrome Canary"
    elif browser_type == "brave":
        return "Brave Browser"
    elif browser_type == "edge":
        return "Microsoft Edge"
    elif browser_type == "chrome":
        return "Google Chrome"
        
    # Auto-detect fallback
    canary_binary = "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
    chrome_binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    brave_binary = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    edge_binary = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    
    if os.path.exists(canary_binary):
        return "Google Chrome Canary"
    elif os.path.exists(chrome_binary):
        return "Google Chrome"
    elif os.path.exists(brave_binary):
        return "Brave Browser"
    elif os.path.exists(edge_binary):
        return "Microsoft Edge"
    return "Google Chrome"


def _activate_chrome():
    app_name = _get_active_browser_app_name()
    script = f"""
    tell application "{app_name}"
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
            subprocess.run(["open", "-a", app_name], check=False)
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
    app_name = _get_active_browser_app_name()
    script = f"""
    tell application "{app_name}"
        repeat with w in windows
            set tabIndex to 1
            repeat with t in tabs of w
                if URL of t contains "{url_part}" then
                    set active tab index of w to tabIndex
                    set index of w to 1
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
    return correct_legacy_paths(_read_json(REF_IMAGE_DEFAULT_FILE))


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
        "browser_type": payload.browser_type,
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
    profile["browser_type"] = payload.browser_type

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
    # Reset extension connection state so newly launched Chrome profile gets a fresh WebSocket handshake
    try:
        from agent.services.flow_client import get_flow_client
        client = get_flow_client()
        if client._extension_ws:
            try:
                await client._extension_ws.close()
            except Exception:
                pass
        client.clear_extension()
        client._flow_key = None
    except Exception as e:
        logger.warning("Failed to reset extension state on launch: %s", e)

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

    chrome_binary = _get_active_browser_binary(profile.get("browser_type", "chrome"))
    # Launch without --user-data-dir if it is the Everyday Chrome profile, to load untouched daily sessions directly
    from pathlib import Path
    everyday_profile = str(Path.home() / "Library/Application Support/Google/Chrome")
    ext_dir = str(Path(__file__).resolve().parent.parent / "extension")
    if profile_path == "/Users/litar/Library/Application Support/Google/Chrome" or profile_path == everyday_profile:
        cmd = [
            chrome_binary,
            f"--remote-debugging-port={debug_port}",
            f"--load-extension={ext_dir}",
            *startup_urls,
        ]
    else:
        cmd = [
            chrome_binary,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile_path}",
            f"--load-extension={ext_dir}",
            *startup_urls,
        ]

    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"ไม่พบตัวติดตั้งเบราว์เซอร์เป้าหมายที่ {chrome_binary}",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"เปิดเบราว์เซอร์ไม่สำเร็จ: {e}")

    return {
        "ok": True,
        "already_running": False,
        "message": f"เปิด Google Chrome ด้วย debug port {debug_port} แล้ว",
        "debug_port": debug_port,
        "profile_path": profile_path,
        "startup_urls": startup_urls,
    }


@app.post("/api/profiles/close")
def close_profile(payload: CloseProfilePayload = None):
    try:
        port = payload.port if payload else None
        if port is None:
            port = 9222
            try:
                if DEFAULTS_FILE.exists() and PROFILES_FILE.exists():
                    defaults = _read_json(DEFAULTS_FILE)
                    selected_name = defaults.get("selected_profile", "")
                    if selected_name:
                        profiles_data = _read_json(PROFILES_FILE)
                        profiles = profiles_data.get("profiles", [])
                        profile = next((p for p in profiles if p.get("name") == selected_name), None)
                        if profile:
                            port = int(profile.get("debug_port", 9222))
            except Exception:
                pass

        try:
            browser_manager.close()
        except Exception:
            pass

        _kill_port_processes(port)
        return {"ok": True, "message": f"Browser profile on port {port} closed successfully."}
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
                            chrome_binary = _get_active_browser_binary()
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
            "google_flow_email": "dogdadcatmom@gmail.com",
            "google_flow_project_name": "7-1",
            "video_wait_seconds": 60,
            "video_input_selector": "",
            "video_settings_selector": "",
            "video_submit_selector": "",
            "video_lakorn_path": "",
            "video_lakorn_ep": "",
            "video_lakorn_ton": "",
            "video_presets": {
                "ตึกสวย": {
                    "use_bgm": True,
                    "target_folder": "/Users/litar/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/MythicForge84 - วิว/ตึกสวย_40 วีดีโอ/",
                    "audio_path": "/Users/litar/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/MythicForge84 - วิว/วิว/Soundtrack/soundtrack_for_view.mp3",
                    "audio_boost": "",
                    "video_audio_boost": "-10",
                    "contrast": "1.10",
                    "saturation": "1.75",
                    "brightness": "0.02",
                    "gamma": "1.02",
                    "unsharp": "5:5:0.7:3:3:0.3",
                    "durations": [3.56, 5.2, 5.6, 4.8, 4.88]
                }
            },
            "flowkit_worker_delay_min": 10.0,
            "flowkit_worker_delay_max": 20.0,
            "flow_video_presets": {},
            "flow_po_presets": {}
        }
    else:
        h = os.path.expanduser("~")
        res = {
            "folder_name": "",
            "element_name": "Songkran",
            "element_path": os.path.join(h, "Documents/DDCM/Elements"),
            "local_path": os.path.join(h, "Documents/DDCM"),
            "remote_path": "/Users/litar/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Projects/DDCM/Cliparts DDCM",
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
            "google_flow_email": "dogdadcatmom@gmail.com",
            "google_flow_project_name": "7-1",
            "video_wait_seconds": 60,
            "video_input_selector": "",
            "video_settings_selector": "",
            "video_submit_selector": "",
            "video_lakorn_path": "",
            "video_lakorn_ep": "",
            "video_lakorn_ton": "",
            "video_presets": {
                "ตึกสวย": {
                    "use_bgm": True,
                    "target_folder": "/Users/litar/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/MythicForge84 - วิว/ตึกสวย_40 วีดีโอ/",
                    "audio_path": "/Users/litar/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/MythicForge84 - วิว/วิว/Soundtrack/soundtrack_for_view.mp3",
                    "audio_boost": "",
                    "video_audio_boost": "-10",
                    "contrast": "1.10",
                    "saturation": "1.75",
                    "brightness": "0.02",
                    "gamma": "1.02",
                    "unsharp": "5:5:0.7:3:3:0.3",
                    "durations": [3.56, 5.2, 5.6, 4.8, 4.88]
                }
            },
            "flowkit_worker_delay_min": 10.0,
            "flowkit_worker_delay_max": 20.0,
            "flow_video_presets": {},
            "flow_po_presets": {}
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
    try:
        import os
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "automation.log"), "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


def check_unusual_activity_and_clear(driver, target_email: str = "dogdadcatmom@gmail.com", target_project_name: str = "7-1") -> None:
    from selenium.webdriver.common.by import By
    # Target only elements inside the virtuoso-item-list container where the video/image generation cards live
    unusual_activity_xpath = "//*[@data-testid='virtuoso-item-list']//*[contains(text(), 'เราพบกิจกรรมที่ผิดปกติ') or contains(text(), 'unusual activity') or contains(., 'เราพบกิจกรรมที่ผิดปกติ') or contains(., 'unusual activity')]"
    try:
        elements = driver.find_elements(By.XPATH, unusual_activity_xpath)
        visible_elements = []
        for el in elements:
            try:
                if el.is_displayed():
                    tag = el.tag_name.lower()
                    text = el.text.strip()
                    if tag in ["html", "body", "script", "style", "noscript"] or not text:
                        continue
                    visible_elements.append(el)
                    log(f"[ตรวจพบกิจกรรมผิดปกติ] พบธาตุข้อความแจ้งเตือนจริงในรายการสร้างวิดีโอ: Tag='{tag}', Text='{text[:100]}'")
            except Exception:
                pass

        if visible_elements:
            log("[ตรวจพบกิจกรรมผิดปกติ] ตรวจพบข้อความแจ้งเตือนกิจกรรมผิดปกติที่มองเห็นได้จริงในรายการสร้างวิดีโอ! เริ่มต้นกระบวนการล้างข้อมูล Cache และ Cookies สำหรับ Google Flow...")

            # 1. Clear cookies for the current domain only (labs.google / vids.google.com)
            try:
                driver.delete_all_cookies()
                log("[ระบบกู้คืน] ล้าง Cookies สำหรับขอบเขตโดเมน Google Flow ในปัจจุบันสำเร็จ")
            except Exception as e:
                log(f"[ระบบกู้คืน] Warning: ไม่สามารถล้าง Cookies สำหรับโดเมนปัจจุบันได้: {e}")

            # 2. Clear LocalStorage and SessionStorage for the Google Flow domain specifically
            try:
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")
                log("[ระบบกู้คืน] ล้าง LocalStorage และ SessionStorage ของ Google Flow ในโดเมนปัจจุบันสำเร็จ")
            except Exception as e:
                log(f"[ระบบกู้คืน] Warning: ไม่สามารถล้าง LocalStorage/SessionStorage ได้: {e}")

            # 3. Clear browser cache via CDP
            try:
                driver.execute_cdp_cmd("Network.clearBrowserCache", {})
                log("[ระบบกู้คืน] ล้าง Cache ทั้งหมดในเบราว์เซอร์ผ่าน CDP (Network.clearBrowserCache) สำเร็จ")
            except Exception as e:
                log(f"[ระบบกู้คืน] Warning: ไม่สามารถล้าง Cache ทั้งหมดผ่าน CDP ได้: {e}")
                
            # Refresh to clean slate
            try:
                driver.refresh()
                log("[ระบบกู้คืน] สั่งรีเฟรชหน้าเว็บเรียบร้อย")
                time.sleep(3.0)
                handle_google_flow_login_if_needed(driver, target_email)
                time.sleep(2.0)
                open_google_flow_project_if_needed(driver, target_project_name)
            except Exception as login_err:
                log(f"[ระบบกู้คืนเตือน] ล็อกอินหรือเปิดโปรเจกต์ใหม่อัตโนมัติหลังกู้คืนล้มเหลว: {login_err}")
                
            raise HTTPException(
                status_code=400,
                detail=f"ตรวจพบกิจกรรมที่ผิดปกติของบัญชี Google! ระบบได้ทำการเคลียร์คุ้กกี้และล้างแคชเรียบร้อย และได้ดำเนินการล็อกอินเข้าสู่ระบบบัญชี {target_email} และเปิดโปรเจกต์ '{target_project_name}' ให้โดยอัตโนมัติแล้ว กรุณากดเริ่มรันบอทอีกครั้งเพื่อทำงานต่อ"
            )
    except HTTPException:
        raise
    except Exception as e:
        log(f"Warning: การตรวจสอบระบบเตือนกิจกรรมผิดปกติขัดข้อง: {e}")


def handle_google_flow_login_if_needed(driver, target_email: str) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    if not is_driver_alive(driver):
        return

    # 1. Check if the "Create with Google Flow" button is visible
    create_btn_xpath = "//button[.//span[text()='Create with Google Flow'] or contains(., 'Create with Google Flow') or contains(text(), 'Create with Google Flow')]"
    try:
        create_btns = driver.find_elements(By.XPATH, create_btn_xpath)
        visible_create_btns = [b for b in create_btns if b.is_displayed()]
        if visible_create_btns:
            log("[ล็อกอินอัตโนมัติ] พบปุ่ม 'Create with Google Flow' กำลังคลิกปุ่มเพื่อล็อกอิน...")
            try:
                visible_create_btns[0].click()
            except Exception:
                driver.execute_script("arguments[0].click();", visible_create_btns[0])
            time.sleep(4.0) # Wait for accounts chooser page to load
    except Exception as e:
        log(f"[ล็อกอินอัตโนมัติ] ไม่พบปุ่ม Create with Google Flow หรือคลิกมีปัญหา: {e}")

    if not is_driver_alive(driver):
        return

    # 2. Check if we are on accounts.google.com page (wait/poll for up to 10 seconds for redirect, skip if already on Flow page)
    current_url = driver.current_url.lower()
    is_google_accounts = "accounts.google.com" in current_url or "accounts.google" in current_url or "signin" in current_url
    
    if not is_google_accounts:
        is_flow_page = any(x in current_url for x in ["labs.google", "vids.google.com", "vids.google", "tools/flow"])
        if not is_flow_page:
            for check_url_attempt in range(10):
                if not is_driver_alive(driver):
                    return
                current_url = driver.current_url.lower()
                if "accounts.google.com" in current_url or "accounts.google" in current_url or "signin" in current_url:
                    is_google_accounts = True
                    break
                time.sleep(1.0)

    if is_google_accounts:
        log(f"[ล็อกอินอัตโนมัติ] อยู่ในหน้าบัญชี Google กำลังค้นหาอีเมลเป้าหมาย: {target_email} (รอโหลดไม่เกิน 15 วินาที)...")
        
        email_selectors = [
            f"//*[@data-email='{target_email}']",
            f"//div[contains(@class, 'yAlK0b') and (text()='{target_email}' or contains(., '{target_email}'))]",
            f"//div[@data-identifier='{target_email}']",
            f"//div[@data-email='{target_email}']",
            f"//div[contains(@class, 'VV3oRb') and contains(., '{target_email}')]",
            f"//*[not(self::script or self::style) and text()='{target_email}']",
            f"//*[not(self::script or self::style) and contains(., '{target_email}')]"
        ]
        
        selected_item = None
        for attempt in range(15):
            if not is_driver_alive(driver):
                return
            for selector in email_selectors:
                try:
                    items = driver.find_elements(By.XPATH, selector)
                    visible_items = [item for item in items if item.is_displayed()]
                    if visible_items:
                        selected_item = visible_items[0]
                        log(f"[ล็อกอินอัตโนมัติ] ตรวจพบตัวเลือกอีเมลด้วย XPath: {selector}")
                        break
                except Exception:
                    pass
            if selected_item:
                break
            time.sleep(1.0)
                
        if selected_item:
            # Click target strategy
            click_target = selected_item
            try:
                ancestor = selected_item.find_element(By.XPATH, "./ancestor::div[@role='button' or @role='link'] | ./ancestor::button | ./ancestor::a | ./ancestor::li")
                if ancestor:
                    click_target = ancestor
                    log(f"[ล็อกอินอัตโนมัติ] พบบัญชีในตัวหุ้มปุ่ม: Tag='{ancestor.tag_name}'")
            except Exception:
                pass
                
            try:
                click_target.click()
                log(f"[ล็อกอินอัตโนมัติ] คลิกเลือกบัญชี {target_email} เรียบร้อยแล้ว")
                time.sleep(6.0) # Wait for authentication redirect
            except Exception as e:
                log(f"[ล็อกอินอัตโนมัติ] คลิกปกติล้มเหลว ลองด้วย JS: {e}")
                try:
                    driver.execute_script("arguments[0].click();", click_target)
                    time.sleep(6.0)
                except Exception as js_e:
                    log(f"[ล็อกอินอัตโนมัติ] JS Click ล้มเหลว: {js_e}")
                    try:
                        driver.execute_script("arguments[0].click();", selected_item)
                        time.sleep(6.0)
                    except Exception:
                        pass
        else:
            log(f"[ล็อกอินอัตโนมัติเตือน] ไม่พบบัญชีอีเมล {target_email} ในหน้าตัวเลือกบัญชี Google")


def open_google_flow_project_if_needed(driver, project_name: str) -> None:
    from selenium.webdriver.common.by import By
    import time
    
    if not is_driver_alive(driver):
        return

    # Check if we are already inside a project editor page
    current_url = driver.current_url.lower()
    if "/project/" in current_url:
        log("[โครงการ] ตรวจพบว่าอยู่ในหน้าโครงการเรียบร้อยแล้ว (มี '/project/' ใน URL) ไม่ต้องเปิดโครงการใหม่")
        return

    log(f"[โครงการ] เริ่มค้นหาและเปิดโครงการชื่อ: '{project_name}'...")
    
    # 1. Look for the virtuoso-item-list container (wait/poll for up to 15 seconds)
    list_selectors = [
        "//*[@data-testid='virtuoso-item-list']",
        "//*[@id='__next']/div[2]/div/div/div/div[2]/div/div/div[2]",
        "//div[contains(@class, 'virtuoso-item-list')]"
    ]
    
    list_el = None
    for attempt in range(15):
        if not is_driver_alive(driver):
            return
        for selector in list_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                visible_elements = [el for el in elements if el.is_displayed()]
                if visible_elements:
                    list_el = visible_elements[0]
                    break
            except Exception:
                pass
        if list_el:
            break
        time.sleep(1.0)
            
    if not list_el:
        log("[โครงการเตือน] ไม่พบตู้คอนเทนเนอร์รายการโครงการ (virtuoso-item-list) บอทอาจจะยังไม่อยู่ในหน้ารายการหลัก")
        return

    # 2. Find the project span/element containing the project name text (e.g. "7-1") (wait/poll for up to 10 seconds)
    project_selectors = [
        f".//span[contains(@class, 'kJLHvy') and (text()='{project_name}' or contains(., '{project_name}'))]",
        f".//*[not(self::script or self::style) and text()='{project_name}']",
        f".//*[not(self::script or self::style) and contains(., '{project_name}')]"
    ]
    
    target_el = None
    for attempt in range(10):
        if not is_driver_alive(driver):
            return
        for selector in project_selectors:
            try:
                elements = list_el.find_elements(By.XPATH, selector)
                visible_elements = [el for el in elements if el.is_displayed()]
                if visible_elements:
                    target_el = visible_elements[0]
                    log(f"[โครงการ] ตรวจพบตัวเลือกชื่อโครงการด้วย XPath: {selector}")
                    break
            except Exception:
                pass
        if target_el:
            break
        time.sleep(1.0)

    if target_el:
        log(f"[โครงการ] พบเป้าหมายโครงการชื่อ '{project_name}' ดึงลิงก์โครงการเพื่อเปลี่ยนเส้นทางโดยตรง...")
        
        href = None
        try:
            # Let's search inside the project's main wrapper card.
            parent_card = target_el.find_element(By.XPATH, "./ancestor::div[contains(@class, 'jJBbql') or contains(@class, 'sc-42dc016-0') or .//a]")
            a_el = parent_card.find_element(By.TAG_NAME, "a")
            href = a_el.get_attribute("href")
        except Exception as e:
            log(f"[โครงการเตือน] ไม่สามารถหาแท็ก a จากตัวหุ้มการ์ดหลักได้: {e}")
            try:
                # Fallback: search for any anchor with href relative to target_el's ancestor
                a_el = target_el.find_element(By.XPATH, "./ancestor::div[contains(@class, 'kRvDFG')]/preceding-sibling::a")
                href = a_el.get_attribute("href")
            except Exception:
                try:
                    a_el = target_el.find_element(By.XPATH, "./ancestor::div[1]//a[contains(@href, '/project/')]")
                    href = a_el.get_attribute("href")
                except Exception:
                    pass

        if href:
            log(f"[โครงการ] ตรวจพบ URL โครงการสำเร็จ: '{href}' กำลังดำเนินการเปิดโดยตรง (driver.get)...")
            try:
                driver.get(href)
                time.sleep(6.0) # Wait for project editor page to load
                return
            except Exception as get_err:
                log(f"[โครงการเตือน] มีข้อผิดพลาดในขณะเปิดลิงก์โครงการโดยตรง: {get_err}")

        # Fallback to click if href extraction fails
        log("[โครงการ] ตรวจไม่พบ URL ของโครงการ พยายามเปิดโดยคลิกอิลิเมนต์ตัวเลือกแทน...")
        try:
            parent_card = target_el.find_element(By.XPATH, "./ancestor::a | ./ancestor::div[contains(@role, 'button')]")
            parent_card.click()
            log(f"[โครงการ] คลิกเปิดโครงการ '{project_name}' ผ่านแรปเปอร์สำเร็จ")
        except Exception:
            try:
                target_el.click()
                log(f"[โครงการ] คลิกเปิดโครงการ '{project_name}' ตรงตัวสำเร็จ")
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", target_el)
                    log(f"[โครงการ] คลิกเปิดโครงการ '{project_name}' ด้วย JS สำเร็จ")
                except Exception as click_err:
                    log(f"[โครงการเตือน] คลิกเปิดโครงการล้มเหลว: {click_err}")
                    
        time.sleep(6.0) # Wait for project editor page to load
    else:
        log(f"[โครงการเตือน] ไม่พบชื่อโครงการ '{project_name}' ที่กำลังแสดงผลอยู่ภายในรายการโครงการ")


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
        return correct_legacy_paths(defaults)
    try:
        import json

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            return correct_legacy_paths({**defaults, **data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed reading config: {e}")
@app.get("/api/utils/serve-image")
def serve_image(path: str):
    import os
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    path = path.strip()
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.post("/api/config")
def set_config(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        import json

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            
        # Update active worker cooldown range if present in payload
        if "flowkit_worker_delay_min" in payload and "flowkit_worker_delay_max" in payload:
            try:
                from agent.worker.processor import get_worker_controller
                controller = get_worker_controller()
                delay_min = float(payload["flowkit_worker_delay_min"])
                delay_max = float(payload["flowkit_worker_delay_max"])
                controller.update_cooldown(delay_min, delay_max)
                log(f"[Worker Config] Updated cooldown range: {delay_min}s - {delay_max}s")
            except Exception as cooldown_err:
                log(f"[Worker Config] Failed to update active worker delay: {cooldown_err}")
                
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed writing config: {e}")


FONT_MAP = {
    "arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "georgia": "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "verdana": "/System/Library/Fonts/Supplemental/Verdana.ttf",
    "times new roman": "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "courier new": "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "impact": "/System/Library/Fonts/Supplemental/Impact.ttf",
    "ayuthaya": "/System/Library/Fonts/Supplemental/Ayuthaya.ttf",
    "thonburi": "/System/Library/Fonts/ThonburiUI.ttc",
}

def get_font_path(font_name: str) -> str | None:
    if not font_name:
        return None
    f_lower = font_name.lower().strip()
    path = FONT_MAP.get(f_lower)
    if path and os.path.exists(path):
        return path
    
    # Try directly in Supplemental
    alt_path = f"/System/Library/Fonts/Supplemental/{font_name}.ttf"
    if os.path.exists(alt_path):
        return alt_path
        
    alt_path_tc = f"/System/Library/Fonts/Supplemental/{font_name}.ttc"
    if os.path.exists(alt_path_tc):
        return alt_path_tc

    # Try in /System/Library/Fonts/
    alt_path_sys = f"/System/Library/Fonts/{font_name}.ttc"
    if os.path.exists(alt_path_sys):
        return alt_path_sys
        
    alt_path_sys_ttf = f"/System/Library/Fonts/{font_name}.ttf"
    if os.path.exists(alt_path_sys_ttf):
        return alt_path_sys_ttf

    # Fallbacks
    for name in ["Arial.ttf", "Helvetica.ttc", "ThonburiUI.ttc", "Times New Roman.ttf"]:
        for prefix in ["/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/", "/Library/Fonts/"]:
            check_p = os.path.join(prefix, name)
            if os.path.exists(check_p):
                return check_p
                
    return None

def create_text_watermark_image(
    text: str,
    font_name: str,
    font_size: int,
    position: str,
    opacity: float,
    color_hex: str,
    video_w: int,
    video_h: int,
    output_png_path: str,
    watermark_border_width: int = 0
):
    from PIL import Image, ImageDraw, ImageFont
    
    # Create transparent image
    img = Image.new("RGBA", (video_w, video_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font_path = get_font_path(font_name)
    try:
        if font_path:
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
        
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        text_w, text_h = draw.textsize(text, font=font)
        
    margin_x = int(video_w * 0.05)
    margin_y = int(video_h * 0.03)
    
    pos_lower = position.lower().strip()
    if pos_lower == "top-left":
        x = margin_x
        y = margin_y
    elif pos_lower == "top-right":
        x = video_w - text_w - margin_x
        y = margin_y
    elif pos_lower == "bottom-left":
        x = margin_x
        y = video_h - text_h - margin_y
    elif pos_lower == "bottom-right":
        x = video_w - text_w - margin_x
        y = video_h - text_h - margin_y
    elif pos_lower == "bottom-center":
        x = (video_w - text_w) // 2
        y = video_h - text_h - int(video_h * 0.10)  # 10% from bottom (subtitle height)
    elif pos_lower == "center":
        x = (video_w - text_w) // 2
        y = (video_h - text_h) // 2
    else:
        x = video_w - text_w - margin_x
        y = video_h - text_h - margin_y
        
    c_hex = color_hex.strip().lstrip("#")
    if len(c_hex) == 6:
        r = int(c_hex[0:2], 16)
        g = int(c_hex[2:4], 16)
        b = int(c_hex[4:6], 16)
    else:
        r, g, b = 255, 255, 255
        
    alpha = int(opacity * 255)
    outline_alpha = int(opacity * 180)
    
    # Draw text with outline if border_width > 0
    if watermark_border_width > 0:
        draw.text(
            (x, y), text, font=font, fill=(r, g, b, alpha),
            stroke_width=watermark_border_width, stroke_fill=(0, 0, 0, outline_alpha)
        )
    else:
        # Draw main text
        draw.text((x, y), text, font=font, fill=(r, g, b, alpha))
    img.save(output_png_path, "PNG")


@app.post("/api/config/set-defaults")
def set_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    updates = payload.get("updates")
    if not updates or not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="updates dict required")
    try:
        import json
        data: dict[str, Any] = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        for key, value in updates.items():
            data[key] = value
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            
        # Update active worker cooldown range if relevant key is saved
        if key in ("flowkit_worker_delay_min", "flowkit_worker_delay_max"):
            try:
                from agent.worker.processor import get_worker_controller
                controller = get_worker_controller()
                delay_min = float(data.get("flowkit_worker_delay_min", 10.0))
                delay_max = float(data.get("flowkit_worker_delay_max", 20.0))
                controller.update_cooldown(delay_min, delay_max)
                log(f"[Worker Config] Updated cooldown range after set-default: {delay_min}s - {delay_max}s")
            except Exception as cooldown_err:
                log(f"[Worker Config] Failed to update active worker delay on default save: {cooldown_err}")
                
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
            
            # Always activate debug browser and delay 1.5 seconds before starting the round
            _activate_chrome()
            time.sleep(1.5)

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
                            log(f"Failed to click {name}. Waiting 0.75 seconds before next attempt...")
                            time.sleep(0.75)
                    log(f"CRITICAL ERROR: Failed to click {name} after 3 attempts.")
                    return False

                def upload_macos_file_dialog(file_path):
                    if not is_driver_alive(driver):
                        raise RuntimeError("Browser connection lost.")
                    import subprocess
                    escaped_path = file_path.replace('"', '\\"')
                    app_name = _get_active_browser_app_name()
                    script = f"""
                    set the clipboard to "{escaped_path}"
                    tell application "System Events"
                        key code 5 using {{command down, shift down}}
                        delay 0.75
                        key code 9 using {{command down}}
                        delay 0.75
                        keystroke return
                        delay 1.25
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
                        time.sleep(0.6)
                        
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

                # Wait 0.5 seconds after image attachment before starting paste
                if has_images:
                    time.sleep(0.5)

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
                time.sleep(0.25)

                input_success = False
                try:
                    driver.execute_script("document.execCommand('insertText', false, arguments[0]);", custom_prompt)
                    time.sleep(0.25)
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
            
            # Always activate debug browser and delay 1.5 seconds before starting the round
            _activate_chrome()
            time.sleep(1.5)

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

            # 1. Switch to ChatGPT tab if it exists, or open it
            if not bot.switch_to_tab_containing("chatgpt.com"):
                log("ChatGPT tab not found, opening natively...")
                driver.get("https://chatgpt.com/")
                time.sleep(3.0)
            
            # 2. Setup constants
            stop_xpath = (
                "//button[@id='composer-submit-button' and (@aria-label='Stop answering' or @data-testid='stop-button')]"
            )
            check_interval = int(_get_config_value("check_interval_seconds", 60))
            max_checks = int(_get_config_value("max_checks", 3))
            first_time_waiting = int(_get_config_value("first_time_waiting", check_interval))

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
                "//div[@id='prompt-textarea']",
                "//textarea[@id='prompt-textarea']",
                "//div[@contenteditable='true']",
                "//div[@id='prompt-textarea']//p",
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
                    app_name = _get_active_browser_app_name()
                    script = f"""
                    set the clipboard to "{escaped_path}"
                    tell application "System Events"
                        key code 5 using {{command down, shift down}}
                        delay 0.75
                        key code 9 using {{command down}}
                        delay 0.75
                        keystroke return
                        delay 1.25
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
                    
                    # We will try to upload using Cmd + U first (Primary).
                    # If that fails, we will try the '+' button (Fallback).
                    upload_success = False
                    
                    log("Primary: Sending Cmd + U keystroke to trigger file modal...")
                    try:
                        app_name = _get_active_browser_app_name()
                        cmd_u_script = """
                        tell application "System Events"
                            key code 32 using command down
                        end tell
                        """
                        subprocess.run(["osascript", "-e", cmd_u_script], check=False)
                        log("Waiting 0.75 seconds for file modal to fully open...")
                        time.sleep(0.75)
                        
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
                                log("Waiting 0.75 seconds for file modal to fully open...")
                                time.sleep(0.75)
                                log("Triggering AppleScript folder path sheet to select file (UI Click method)...")
                                if upload_macos_file_dialog(reference_image):
                                    upload_success = True
                                    log("Reference image uploaded successfully via macOS File Dialog AppleScript automation!")
                        except Exception as click_err:
                            log(f"UI attach trigger fallback failed: {click_err}")
                            
                    if upload_success:
                        log("Waiting 1.25 seconds for file upload to settle...")
                        time.sleep(1.25)
                    else:
                        log("Warning: AppleScript file-dialog automation encountered an issue and could not upload file.")

                    # Check for duplicate file upload pop-up
                    try:
                        dup_xpath = "//*[contains(text(), \"already uploaded this file\") or contains(text(), \"uploaded this file\")]"
                        dup_elems = driver.find_elements(By.XPATH, dup_xpath)
                        if any(e.is_displayed() for e in dup_elems):
                            log("🚨 ตรวจพบป๊อปอัปแจ้งเตือนอัปโหลดไฟล์ซ้ำ (You've already uploaded this file.)")
                            raise RuntimeError("Duplicate file upload detected: You've already uploaded this file.")
                    except Exception as e:
                        if "Duplicate file" in str(e):
                            raise e

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

                # Wait 0.5 seconds after image attachment before starting paste
                if has_images:
                    time.sleep(0.5)

                # Paste the prompt, but do not click send
                try:
                    box.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", box)
                    
                driver.execute_script("arguments[0].focus();", box)
                time.sleep(0.25)
                
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
                time.sleep(0.25)

                if not is_driver_alive(driver):
                    raise RuntimeError("Browser connection lost (Force Stopped).")
                
                # Primary: Use document.execCommand('insertText') to insert prompt without triggering Enter key submits
                input_success = False
                try:
                    # Re-locate box dynamically to ensure it is fresh
                    try:
                        box = driver.find_element(By.XPATH, "//div[@id='prompt-textarea'] | //textarea[@id='prompt-textarea'] | //div[@contenteditable='true']")
                    except Exception:
                        pass
                    driver.execute_script("arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);", box, custom_prompt)
                    time.sleep(0.75)
                    # Verify text inside the entire #prompt-textarea div without passing box to prevent StaleElementReferenceException
                    entered_text = driver.execute_script("""
                        var target = document.getElementById('prompt-textarea');
                        if (!target) return '';
                        return target.value || target.innerText || target.textContent || '';
                    """)
                    if entered_text and entered_text.strip() != "":
                        log("Prompt input populated successfully via browser insertText command.")
                        input_success = True
                except Exception as e:
                    log(f"Browser insertText command failed: {e}")

                # Secondary Fallback: Native send_keys, but replacing newlines with SHIFT+ENTER to prevent auto-submission!
                if not input_success:
                    log("Browser insertText failed or could not be verified. Typing prompt via background-safe native send_keys with SHIFT+ENTER for newlines...")
                    try:
                        # Re-locate box dynamically to ensure it is fresh
                        try:
                            box = driver.find_element(By.XPATH, "//div[@id='prompt-textarea'] | //textarea[@id='prompt-textarea'] | //div[@contenteditable='true']")
                        except Exception:
                            pass
                        box.click()
                        # Type character by character or chunk by chunk to handle newlines safely
                        parts = custom_prompt.split('\n')
                        for idx, part in enumerate(parts):
                            if part:
                                box.send_keys(part)
                            if idx < len(parts) - 1:
                                box.send_keys(Keys.SHIFT + Keys.ENTER)
                        # Re-locate box one more time before dispatching event
                        try:
                            box = driver.find_element(By.XPATH, "//div[@id='prompt-textarea'] | //textarea[@id='prompt-textarea'] | //div[@contenteditable='true']")
                        except Exception:
                            pass
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
                # ─── Wait for previous generation to finish before clicking submit ───
                is_generating = False
                try:
                    stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                    is_generating = any(b.is_displayed() for b in stop_btns)
                    if not is_generating:
                        dots = driver.find_elements(By.CSS_SELECTOR, "[data-testid='image-gen-loading-state-dots']")
                        if any(d.is_displayed() for d in dots):
                            log("ตรวจพบสถานะกำลังสร้างรูปภาพ (image-gen-loading-state-dots)")
                            is_generating = True
                except Exception:
                    pass
                    
                if is_generating:
                    elapsed = time.time() - last_submit_time if last_submit_time > 0 else 0.0
                    remaining_wait = first_time_waiting - elapsed
                    log(f"ตรวจพบว่า ChatGPT กำลังทำงานอยู่จากรอบก่อนหน้า (รันมาแล้ว {elapsed:.1f} วินาที)... รอให้เจเนอเรตเสร็จสิ้นก่อนส่ง Prompt ถัดไป...")
                    
                    if remaining_wait > 0:
                        log(f"เริ่มนับถอยหลัง First Time Waiting ทุกๆ 1 วินาที (เหลืออีก {int(remaining_wait)} วินาที จาก {first_time_waiting} วินาที)...")
                        for s in range(int(remaining_wait), 0, -1):
                            if not is_driver_alive(driver):
                                raise RuntimeError("Browser connection lost (Force Stopped).")
                            log(f"First Time Waiting: เหลืออีก {s} วินาที จะเริ่มตรวจสอบปุ่ม Send")
                            time.sleep(1)
                    
                    generation_completed = False
                    try:
                        stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                        visible = any(b.is_displayed() for b in stop_btns)
                        dots_visible = False
                        dots = driver.find_elements(By.CSS_SELECTOR, "[data-testid='image-gen-loading-state-dots']")
                        if any(d.is_displayed() for d in dots):
                            dots_visible = True
                        if not visible and not dots_visible:
                            log("ตรวจพบว่าปุ่ม Send ว่างและไม่มี Loading dots แล้ว กำลังรอตรวจซ้ำอีก 3 วินาทีเพื่อความแน่ใจ...")
                            time.sleep(3.0)
                            stop_btns_re = driver.find_elements(By.XPATH, stop_xpath)
                            visible_re = any(b.is_displayed() for b in stop_btns_re)
                            dots_re = driver.find_elements(By.CSS_SELECTOR, "[data-testid='image-gen-loading-state-dots']")
                            dots_visible_re = any(d.is_displayed() for d in dots_re)
                            if not visible_re and not dots_visible_re:
                                log("ตรวจพบปุ่ม Send พร้อมใช้งานและรูปสร้างเสร็จแล้ว (หลังครบ First Time Waiting)")
                                generation_completed = True
                            else:
                                log(f"ตรวจพบการสลับสถานะชั่วคราว ChatGPT ยังคงทำงานอยู่ (ปุ่ม Stop: {visible_re}, กำลังสร้างรูปภาพ: {dots_visible_re})")
                        else:
                            log(f"ChatGPT ยังคงทำงานอยู่ (ปุ่ม Stop: {visible}, กำลังสร้างรูปภาพ: {dots_visible})")
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
                                dots_visible = False
                                dots = driver.find_elements(By.CSS_SELECTOR, "[data-testid='image-gen-loading-state-dots']")
                                if any(d.is_displayed() for d in dots):
                                    dots_visible = True
                                if not visible and not dots_visible:
                                    log("ตรวจพบว่าปุ่ม Send ว่างและไม่มี Loading dots แล้ว กำลังรอตรวจซ้ำอีก 3 วินาทีเพื่อความแน่ใจ...")
                                    time.sleep(3.0)
                                    stop_btns_re = driver.find_elements(By.XPATH, stop_xpath)
                                    visible_re = any(b.is_displayed() for b in stop_btns_re)
                                    dots_re = driver.find_elements(By.CSS_SELECTOR, "[data-testid='image-gen-loading-state-dots']")
                                    dots_visible_re = any(d.is_displayed() for d in dots_re)
                                    if not visible_re and not dots_visible_re:
                                        log(f"ตรวจพบปุ่ม Send พร้อมใช้งานและรูปสร้างเสร็จแล้ว (ในการตรวจสอบครั้งที่ {check_count-1})")
                                        generation_completed = True
                                        break
                                    else:
                                        log(f"ตรวจพบการสลับสถานะชั่วคราว ChatGPT ยังคงทำงานอยู่ (ปุ่ม Stop: {visible_re}, กำลังสร้างรูปภาพ: {dots_visible_re})")
                                else:
                                    log(f"ChatGPT ยังคงเจเนอเรตอยู่ (ปุ่ม Stop: {visible}, กำลังสร้างรูปภาพ: {dots_visible}) ผ่านการตรวจสอบแล้ว {check_count-1} ครั้ง")
                            except Exception:
                                log("ไม่พบปุ่ม Stop แล้ว ChatGPT เจเนอเรตเสร็จสิ้น")
                                generation_completed = True
                                break
                        if not generation_completed:
                            log("ข้อผิดพลาด: ตรวจสอบปุ่ม Send ครบตามจำนวน Max Checks แล้วแต่ ChatGPT ยังทำงานไม่เสร็จสิ้น")
                            raise RuntimeError("หยุดการทำงาน: ตรวจสอบปุ่ม Send ครบตามจำนวน Max Checks แล้วแต่ปุ่มยังไม่พร้อมใช้งาน")
                else:
                    log("ChatGPT ว่างอยู่ (ไม่มีการเจเนอเรตค้างไว้) ดำเนินการกดส่งพรอพต์ได้ทันที...")

                # Now click submit button
                log("กำลังคลิกปุ่มส่ง prompt (#composer-submit-button)...")
                submit_success = False
                try:
                    submit_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "#composer-submit-button"))
                    )
                    submit_btn.click()
                    submit_success = True
                except Exception:
                    try:
                        driver.execute_script("document.querySelector('#composer-submit-button').click();")
                        submit_success = True
                    except Exception:
                        pass

                if not submit_success:
                    log("ไม่พบการตอบสนองของปุ่มส่ง กำลังลองส่งด้วยการเคาะปุ่ม Enter...")
                    try:
                        box.send_keys(Keys.ENTER)
                    except Exception:
                        pass
                
                # Update last submit timestamp immediately
                import time
                last_submit_time = time.time()
                
                # ─── Wait for the new generation to start (Stop button / loading dots appear) ───
                log("กำลังตรวจสอบว่า ChatGPT เริ่มทำงานและเริ่มสร้างภาพหรือยัง...")
                generation_started = False
                for check_start in range(16): # 16 attempts, 0.25s each = 4 seconds
                    try:
                        stop_btns = driver.find_elements(By.XPATH, stop_xpath)
                        visible = any(b.is_displayed() for b in stop_btns)
                        dots = driver.find_elements(By.CSS_SELECTOR, "[data-testid='image-gen-loading-state-dots']")
                        dots_visible = any(d.is_displayed() for d in dots)
                        if visible or dots_visible:
                            log("ตรวจพบว่า ChatGPT เริ่มสร้างภาพแล้ว (ปุ่ม Stop / Loading dots ปรากฏขึ้นแล้ว)")
                            generation_started = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.25)
                if not generation_started:
                    log("คำเตือน: ไม่พบปุ่ม Stop หรือ Loading dots ขึ้นมาใน 4 วินาที ดำเนินการต่อ...")
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
        start_num = payload.get("start_num", 1)
        bot = browser_manager.get()
        step4_chatgpt_download_images_bot(bot, log, start_num=start_num)
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
    transitions_json: str | None = Form(None),
    fade_durations_json: str | None = Form(None),
    audio_boost: str | None = Form(None),
    video_audio_boost: str | None = Form(None),
    contrast: str | None = Form(None),
    saturation: str | None = Form(None),
    brightness: str | None = Form(None),
    gamma: str | None = Form(None),
    unsharp: str | None = Form(None),
    video_speed: str | None = Form(None),
    overwrite: str | None = Form(None),
    job_id: str | None = Form(None),
    watermark_text: str | None = Form(None),
    watermark_font: str | None = Form(None),
    watermark_position: str | None = Form(None),
    watermark_opacity: str | None = Form(None),
    watermark_font_size: str | None = Form(None),
    watermark_color: str | None = Form(None),
    watermark_border_width: str | None = Form(None)
) -> dict[str, Any]:
    try:
        video_path = correct_legacy_paths(video_path)
        image_path = correct_legacy_paths(image_path)
        output_path = correct_legacy_paths(output_path)
        audio_path = correct_legacy_paths(audio_path)
        
        return _make_video_cover_impl(
            video=video, image=image, video_path=video_path, image_path=image_path,
            output_path=output_path, prefix=prefix, no=no, mode=mode, amount=amount,
            suffix=suffix, folders_json=folders_json, folder_range=folder_range,
            sub_mode=sub_mode, audio_path=audio_path, durations_json=durations_json,
            transitions_json=transitions_json, fade_durations_json=fade_durations_json,
            audio_boost=audio_boost, video_audio_boost=video_audio_boost,
            contrast=contrast, saturation=saturation, brightness=brightness,
            gamma=gamma, unsharp=unsharp, video_speed=video_speed,
            overwrite=overwrite, job_id=job_id,
            watermark_text=watermark_text, watermark_font=watermark_font,
            watermark_position=watermark_position, watermark_opacity=watermark_opacity,
            watermark_font_size=watermark_font_size, watermark_color=watermark_color,
            watermark_border_width=watermark_border_width
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"Video Helper Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _make_video_cover_impl(
    video: UploadFile | None = None,
    image: UploadFile | None = None,
    video_path: str | None = None,
    image_path: str | None = None,
    output_path: str | None = None,
    prefix: str | None = None,
    no: str | None = None,
    mode: str | None = None,
    amount: str | None = None,
    suffix: str | None = None,
    folders_json: str | None = None,
    folder_range: str | None = None,
    sub_mode: str | None = None,
    audio_path: str | None = None,
    durations_json: str | None = None,
    transitions_json: str | None = None,
    fade_durations_json: str | None = None,
    audio_boost: str | None = None,
    video_audio_boost: str | None = None,
    contrast: str | None = None,
    saturation: str | None = None,
    brightness: str | None = None,
    gamma: str | None = None,
    unsharp: str | None = None,
    video_speed: str | None = None,
    overwrite: str | None = None,
    job_id: str | None = None,
    watermark_text: str | None = None,
    watermark_font: str | None = None,
    watermark_position: str | None = None,
    watermark_opacity: str | None = None,
    watermark_font_size: str | None = None,
    watermark_color: str | None = None,
    watermark_border_width: str | None = None
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
    transitions_json = clean_form_val(transitions_json)
    fade_durations_json = clean_form_val(fade_durations_json)
    audio_boost = clean_form_val(audio_boost)
    video_audio_boost = clean_form_val(video_audio_boost)
    contrast = clean_form_val(contrast)
    saturation = clean_form_val(saturation)
    brightness = clean_form_val(brightness)
    gamma = clean_form_val(gamma)
    unsharp = clean_form_val(unsharp)
    video_speed = clean_form_val(video_speed)
    overwrite = clean_form_val(overwrite)
    job_id = clean_form_val(job_id)
    watermark_text = clean_form_val(watermark_text)
    watermark_font = clean_form_val(watermark_font)
    watermark_position = clean_form_val(watermark_position)
    watermark_opacity = clean_form_val(watermark_opacity)
    watermark_font_size = clean_form_val(watermark_font_size)
    watermark_color = clean_form_val(watermark_color)
    watermark_border_width = clean_form_val(watermark_border_width)

    speed_factor = 1.0
    if video_speed and video_speed.strip():
        try:
            speed_factor = float(video_speed.strip())
        except ValueError:
            log(f"Warning: Invalid video_speed '{video_speed}', defaulting to 1.0")

    video_speed_filter = ""
    audio_speed_filter = ""
    if speed_factor != 1.0:
        video_speed_filter = f",setpts={1.0 / speed_factor}*PTS"
        
        # Build atempo filter chain
        filters = []
        temp_speed = speed_factor
        while temp_speed > 2.0:
            filters.append("atempo=2.0")
            temp_speed /= 2.0
        while temp_speed < 0.5:
            filters.append("atempo=0.5")
            temp_speed /= 0.5
        if temp_speed != 1.0:
            filters.append(f"atempo={temp_speed}")
        audio_speed_filter = "," + ",".join(filters)

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
                        
                    # Generate text watermark if present
                    watermark_temp_png = None
                    if watermark_text and watermark_text.strip():
                        try:
                            wm_font_size = int(watermark_font_size) if watermark_font_size else 72
                        except ValueError:
                            wm_font_size = 72
                        try:
                            wm_opacity = float(watermark_opacity) if watermark_opacity else 0.5
                        except ValueError:
                            wm_opacity = 0.5
                        try:
                            wm_border = int(watermark_border_width) if watermark_border_width else 0
                        except ValueError:
                            wm_border = 0
                        wm_font = watermark_font or "arial"
                        wm_pos = watermark_position or "bottom-right"
                        wm_color = watermark_color or "#ffffff"
                        
                        watermark_temp_png = os.path.join(tmpdir, "watermark_temp.png")
                        create_text_watermark_image(
                            text=watermark_text.strip(),
                            font_name=wm_font,
                            font_size=wm_font_size,
                            position=wm_pos,
                            opacity=wm_opacity,
                            color_hex=wm_color,
                            video_w=2160,
                            video_h=3840,
                            output_png_path=watermark_temp_png,
                            watermark_border_width=wm_border
                        )
                        log(f"Generated text watermark temp PNG (border={wm_border}): '{watermark_temp_png}'")

                    list_txt = os.path.join(tmpdir, "list.txt")
                    amount_val = len(chunk_sources)

                    aligned_paths = []
                    for idx, (folder_name, v_path, resolved_media_name) in enumerate(chunk_sources, 1):
                        update_chunk_progress(int((idx - 1) / amount_val * 70), f"Processing video {idx} of {amount_val}...")
                        has_video_v, has_audio_v = probe_media_streams(v_path)
                        out_aligned = os.path.join(tmpdir, f"aligned_{idx}.mp4")
                        log(f"Combine Mode Chunk {chunk_idx} [{idx}/{amount_val}]: Aligning '{folder_name}/{resolved_media_name}' to 9:16 vertical 4K 60fps...")

                        if has_video_v and has_audio_v:
                            if watermark_temp_png:
                                v_cmd = [
                                    ffmpeg_bin, "-y", "-i", v_path, "-i", watermark_temp_png,
                                    "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[scaled];[scaled][1:v]overlay=0:0[v];[0:a]aresample=async=1{audio_speed_filter},aformat=sample_rates=48000:channel_layouts=stereo[a]",
                                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                ]
                            else:
                                v_cmd = [
                                    ffmpeg_bin, "-y", "-i", v_path,
                                    "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[v];[0:a]aresample=async=1{audio_speed_filter},aformat=sample_rates=48000:channel_layouts=stereo[a]",
                                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                ]
                        elif has_video_v:
                            if watermark_temp_png:
                                v_cmd = [
                                    ffmpeg_bin, "-y", "-i", v_path, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-i", watermark_temp_png,
                                    "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[scaled];[scaled][2:v]overlay=0:0[v]",
                                    "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                ]
                            else:
                                v_cmd = [
                                    ffmpeg_bin, "-y", "-i", v_path, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                                    "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[v]",
                                    "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                ]
                        elif has_audio_v:
                            if watermark_temp_png:
                                if speed_factor != 1.0:
                                    v_cmd = [
                                        ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=black:s=2160x3840:r=60", "-i", v_path, "-i", watermark_temp_png,
                                        "-filter_complex", f"[0:v][2:v]overlay=0:0[v];[1:a]aresample=async=1{audio_speed_filter},aformat=sample_rates=48000:channel_layouts=stereo[a]",
                                        "-map", "[v]", "-map", "[a]", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                    ]
                                else:
                                    v_cmd = [
                                        ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=black:s=2160x3840:r=60", "-i", v_path, "-i", watermark_temp_png,
                                        "-filter_complex", "[0:v][2:v]overlay=0:0[v]",
                                        "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                    ]
                            else:
                                if speed_factor != 1.0:
                                    v_cmd = [
                                        ffmpeg_bin, "-y", "-f", "lavfi", "-i", "color=c=black:s=2160x3840:r=60", "-i", v_path,
                                        "-filter_complex", f"[1:a]aresample=async=1{audio_speed_filter},aformat=sample_rates=48000:channel_layouts=stereo[a]",
                                        "-map", "0:v", "-map", "[a]", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac"
                                    ]
                                else:
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

                    # Parse transitions and fade durations if provided
                    transitions = []
                    if transitions_json:
                        try:
                            transitions = json.loads(transitions_json)
                        except Exception as e:
                            log(f"Warning: Failed to parse transitions_json: {e}")
                    
                    fade_durations = []
                    if fade_durations_json:
                        try:
                            fade_durations = [float(fd) for fd in json.loads(fade_durations_json)]
                        except Exception as e:
                            log(f"Warning: Failed to parse fade_durations_json: {e}")

                    has_fade_transitions = any(t == "fade" for t in transitions)
                    clean_audio_path = audio_path.strip().strip('"').strip("'") if audio_path else ""

                    if has_fade_transitions and len(aligned_paths) >= 2:
                        log(f"View Channel Mode Chunk {chunk_idx}: Crossfade transitions detected. Concatenating {amount_val} clips using filter_complex...")
                        update_chunk_progress(75, "Applying transitions and mixing...")
                        
                        final_cmd = [ffmpeg_bin, "-y"]
                        for ap in aligned_paths:
                            final_cmd.extend(["-i", ap])
                        
                        has_bgm = sub_mode == "view_channel" and clean_audio_path and os.path.isfile(clean_audio_path)
                        if has_bgm:
                            final_cmd.extend(["-i", clean_audio_path])
                            
                        filter_parts = []
                        v_cur = "[0:v]"
                        a_cur = "[0:a]"
                        t_cur = durations[0] if (sub_mode == "view_channel" and len(durations) >= 1) else 5.0
                        
                        P = len(aligned_paths)
                        for idx in range(1, P):
                            next_v = f"[{idx}:v]"
                            next_a = f"[{idx}:a]"
                            next_dur = durations[idx] if (sub_mode == "view_channel" and len(durations) >= idx + 1) else 5.0
                            
                            trans = transitions[idx] if idx < len(transitions) else "cut"
                            fade_dur = fade_durations[idx] if idx < len(fade_durations) else 0.0
                            
                            if trans == "fade" and fade_dur > 0.0:
                                prev_dur = durations[idx - 1] if (sub_mode == "view_channel" and len(durations) >= idx) else 5.0
                                fade_dur = min(fade_dur, next_dur, prev_dur)
                                offset = t_cur - fade_dur
                                v_next = f"[v_trans_{idx}]"
                                a_next = f"[a_trans_{idx}]"
                                filter_parts.append(f"{v_cur}{next_v}xfade=transition=fade:duration={fade_dur}:offset={offset}{v_next}")
                                filter_parts.append(f"{a_cur}{next_a}acrossfade=d={fade_dur}{a_next}")
                                v_cur = v_next
                                a_cur = a_next
                                t_cur = t_cur + next_dur - fade_dur
                            else:
                                v_next = f"[v_concat_{idx}]"
                                a_next = f"[a_concat_{idx}]"
                                filter_parts.append(f"{v_cur}{next_v}concat=n=2:v=1:a=0{v_next}")
                                filter_parts.append(f"{a_cur}{next_a}concat=n=2:v=0:a=1{a_next}")
                                v_cur = v_next
                                a_cur = a_next
                                t_cur = t_cur + next_dur
                                
                        if video_filter_str:
                            filter_parts.append(f"{v_cur}{video_filter_str}[vout]")
                            v_map = "[vout]"
                        else:
                            v_map = v_cur
                            
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
                                
                        if has_bgm:
                            BGM_idx = P
                            if video_volume_filter:
                                filter_parts.append(f"{a_cur}{video_volume_filter}[fg]")
                            else:
                                filter_parts.append(f"{a_cur}anull[fg]")
                            filter_parts.append(f"[{BGM_idx}:a]{volume_filter}apad[bgm]")
                            filter_parts.append(f"[fg][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
                            a_map = "[aout]"
                        else:
                            if video_volume_filter:
                                filter_parts.append(f"{a_cur}{video_volume_filter}[aout]")
                                a_map = "[aout]"
                            else:
                                a_map = a_cur
                                
                        filter_complex_str = ";".join(filter_parts)
                        final_cmd.extend(["-filter_complex", filter_complex_str])
                        final_cmd.extend(["-map", v_map, "-map", a_map])
                        
                        final_cmd.extend([
                            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60",
                            "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000"
                        ])
                        
                        if has_bgm:
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
                            if bgm_dur is not None:
                                final_cmd.extend(["-t", str(bgm_dur)])
                                
                        final_cmd.extend([
                            "-disposition:a:0", "default", final_output_path
                        ])
                        
                        log(f"Executing Crossfade FFmpeg complex: {' '.join(final_cmd)}")
                        res = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if res.returncode != 0:
                            raise RuntimeError(f"FFmpeg crossfade concatenation failed: {res.stderr}")
                    else:
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
                    
                # Generate text watermark if present
                watermark_temp_png = None
                if watermark_text and watermark_text.strip():
                    try:
                        wm_font_size = int(watermark_font_size) if watermark_font_size else 72
                    except ValueError:
                        wm_font_size = 72
                    try:
                        wm_opacity = float(watermark_opacity) if watermark_opacity else 0.5
                    except ValueError:
                        wm_opacity = 0.5
                    try:
                        wm_border = int(watermark_border_width) if watermark_border_width else 0
                    except ValueError:
                        wm_border = 0
                    wm_font = watermark_font or "arial"
                    wm_pos = watermark_position or "bottom-right"
                    wm_color = watermark_color or "#ffffff"
                    
                    watermark_temp_png = os.path.join(tmpdir, "watermark_temp.png")
                    create_text_watermark_image(
                        text=watermark_text.strip(),
                        font_name=wm_font,
                        font_size=wm_font_size,
                        position=wm_pos,
                        opacity=wm_opacity,
                        color_hex=wm_color,
                        video_w=2160,
                        video_h=3840,
                        output_png_path=watermark_temp_png,
                        watermark_border_width=wm_border
                    )
                    log(f"Generated text watermark temp PNG (border={wm_border}): '{watermark_temp_png}'")

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
                    if watermark_temp_png:
                        v_cmd = [
                            ffmpeg_bin, "-y", "-i", temp_input_video, "-i", watermark_temp_png,
                            "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[scaled];[scaled][1:v]overlay=0:0[v];[0:a]aresample=async=1{audio_speed_filter},aformat=sample_rates=48000:channel_layouts=stereo[a]",
                            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_video
                        ]
                    else:
                        v_cmd = [
                            ffmpeg_bin, "-y", "-i", temp_input_video,
                            "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[v];[0:a]aresample=async=1{audio_speed_filter},aformat=sample_rates=48000:channel_layouts=stereo[a]",
                            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_video
                        ]
                else:
                    if watermark_temp_png:
                        v_cmd = [
                            ffmpeg_bin, "-y", "-i", temp_input_video, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-i", watermark_temp_png,
                            "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[scaled];[scaled][2:v]overlay=0:0[v]",
                            "-map", "[v]", "-map", "1:a", "-shortest", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "60", "-c:a", "aac", temp_video
                        ]
                    else:
                        v_cmd = [
                            ffmpeg_bin, "-y", "-i", temp_input_video, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-filter_complex", f"[0:v]scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60{video_speed_filter}[v]",
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
    import json
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    
    # Load media ID mapping if present
    meta_path = os.path.join(dir_path, "flow_media_ids.json")
    meta = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass

    valid_extensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]
    images = []
    try:
        for item in sorted(os.listdir(dir_path)):
            full_path = os.path.join(dir_path, item)
            if os.path.isfile(full_path) and any(item.lower().endswith(ext) for ext in valid_extensions):
                images.append({
                    "name": item,
                    "path": full_path,
                    "media_id": meta.get(item)
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

    # 1.5. Resolve character sheet directory relative to lakorn_path
    resolved_ref_dir = None
    lakorn_path_obj = Path(lakorn_path)
    
    # Try finding Character Sheet folder directly inside lakorn_path
    for candidate in ["Character Sheet", "2 - Character Sheet", "2-Character Sheet", "character_sheet"]:
        path = lakorn_path_obj / candidate
        if path.exists() and path.is_dir():
            resolved_ref_dir = path
            break
            
    # Fallback to legacy hardcoded paths if not found relative to lakorn_path
    if not resolved_ref_dir:
        global_char_sheet = Path("/Users/litar/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/ผักกาดการละคร - ละครไทย/Character Sheet")
        if global_char_sheet.exists() and global_char_sheet.is_dir():
            resolved_ref_dir = global_char_sheet
        else:
            fallback_char_sheet = Path.home() / "Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/ผักกาดการละคร - ละครไทย/Character Sheet"
            if fallback_char_sheet.exists() and fallback_char_sheet.is_dir():
                resolved_ref_dir = fallback_char_sheet
            else:
                new_fallback_char_sheet = Path.home() / "Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย/Character Sheet"
                if new_fallback_char_sheet.exists() and new_fallback_char_sheet.is_dir():
                    resolved_ref_dir = new_fallback_char_sheet
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"ไม่พบโฟลเดอร์รูปภาพตัวละคร (Character Sheet) ใน Path ละคร: '{lakorn_path}'"
                    )

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
        app_name = _get_active_browser_app_name()
        script = f"""
        set the clipboard to "{escaped_path}"
        tell application "System Events"
            -- Press Cmd + Shift + G to open path dialog
            key code 5 using {{command down, shift down}}
            delay 0.75
            
            -- Press Cmd + V to paste
            key code 9 using {{command down}}
            delay 0.75
            
            -- Enter to confirm path
            keystroke return
            delay 1.25
            
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
async def step_video_gen(payload: VideoGenStepPayload) -> dict[str, Any]:
    # _activate_chrome()
    prompt = payload.prompt.strip()
    round_idx = payload.round_idx
    
    # ─── Flow Kit Mode Handler ──────────────────────────────────
    if payload.video_gen_mode == "flow_kit":
        try:
            from agent.db import crud
            from agent.services.flow_client import get_flow_client
            
            # 1. Verify extension is connected
            client = get_flow_client()
            if not client.connected:
                raise HTTPException(
                    status_code=503,
                    detail="Flow Kit Extension is not connected! Please open Chrome and make sure the extension connects to the WebSocket server on port 9222."
                )
                
            # 2. Get or create project in Flow Kit DB
            project_name = payload.google_flow_project_name or "default_project"
            projects = await crud.list_projects()
            target_project = None
            for p in projects:
                if p.get("name") == project_name:
                    target_project = p
                    break
            
            if not target_project:
                target_project = await crud.create_project(
                    name=project_name,
                    description="Auto-created via Cockpit integration",
                    material="realistic"
                )
            project_id = target_project["id"]
            
            # 3. Get or create video in project
            videos = await crud.list_videos(project_id)
            target_video = None
            for v in videos:
                if v.get("title") == "Default Video":
                    target_video = v
                    break
            if not target_video:
                target_video = await crud.create_video(
                    project_id=project_id,
                    title="Default Video",
                    description="Auto-created video container",
                    orientation="VERTICAL"
                )
            video_id = target_video["id"]
            
            # 4. Get or create scene for this round
            scenes = await crud.list_scenes(video_id)
            target_scene = None
            display_order = round_idx
            for s in scenes:
                if s.get("display_order") == display_order:
                    target_scene = s
                    break
            
            if not target_scene:
                target_scene = await crud.create_scene(
                    video_id=video_id,
                    display_order=display_order,
                    prompt=prompt
                )
            else:
                # Update prompt if changed
                if target_scene.get("prompt") != prompt:
                    await crud.update_scene(target_scene["id"], prompt=prompt)
                    target_scene = await crud.get_scene(target_scene["id"])
            
            scene_id = target_scene["id"]
            
            # 4.5. Check for matching local storyboard image to upload if it exists
            # We first need to check if there is an image already completed or uploaded.
            # If not, let's look for local storyboard files under the episode folder.
            orientation = target_video.get("orientation") or "VERTICAL"
            image_media_id = target_scene.get("vertical_image_media_id") if orientation == "VERTICAL" else target_scene.get("horizontal_image_media_id")
            
            if not image_media_id:
                try:
                    import json
                    from pathlib import Path
                    
                    config_data = {}
                    if os.path.exists(CONFIG_FILE):
                        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                            config_data = json.load(f) or {}
                    
                    lakorn_path = config_data.get("video_lakorn_path", "").strip()
                    ton_num = config_data.get("video_lakorn_ton", "").strip()
                    ep_num = config_data.get("video_lakorn_ep", "").strip()
                    
                    if lakorn_path and ton_num:
                        ep_dir = find_episode_dir(lakorn_path, ton_num)
                        if ep_dir:
                            # Search for storyboard directory
                            storyboard_dir = None
                            for candidate in ["6 - Storyboards", "6-Storyboards", "Storyboards", "storyboards", "3 - Storyboard", "3-Storyboard", "Storyboard", "storyboard", "3 - Animation Image", "Animation Image", "animation image", "3 - Story Board", "Story Board", "story board"]:
                                cand_path = ep_dir / candidate
                                if cand_path.exists() and cand_path.is_dir():
                                    storyboard_dir = cand_path
                                    break
                            
                            # Fallback if no matching candidate
                            if not storyboard_dir:
                                for d in ep_dir.iterdir():
                                    if d.is_dir() and ("storyboard" in d.name.lower() or "story board" in d.name.lower() or "image" in d.name.lower()):
                                        storyboard_dir = d
                                        break
                            
                            if storyboard_dir:
                                # Find specific EP subfolder under storyboard_dir (e.g. ep_num subfolder)
                                ep_storyboard_dir = find_sub_ep_dir(storyboard_dir, ep_num) if ep_num else storyboard_dir
                                if not ep_storyboard_dir:
                                    ep_storyboard_dir = storyboard_dir
                                
                                # Search for file starting with round_idx
                                matched_img_path = None
                                valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
                                for f in ep_storyboard_dir.iterdir():
                                    if f.is_file() and f.suffix.lower() in valid_exts:
                                        # Match names like: "01.png", "1.png", "01_pose.jpg", "1-pose.png", "round_01.png", "round_1.png"
                                        name_no_ext = f.stem.lower()
                                        candidates = [
                                            f"{round_idx:02d}",
                                            f"{round_idx}",
                                            f"round_{round_idx:02d}",
                                            f"round_{round_idx}",
                                            f"round {round_idx:02d}",
                                            f"round {round_idx}"
                                        ]
                                        
                                        # Check exact prefix matches
                                        is_match = False
                                        for cand in candidates:
                                            if name_no_ext == cand:
                                                is_match = True
                                                break
                                            if name_no_ext.startswith(cand) and name_no_ext[len(cand)] in ('_', '-', ' ', '.'):
                                                is_match = True
                                                break
                                        
                                        if is_match:
                                            matched_img_path = f
                                            break
                                
                                if matched_img_path:
                                    log(f"[Flow Kit Storyboard] Found matching local storyboard image: {matched_img_path.name}. Uploading to Google Flow...")
                                    import base64
                                    import mimetypes
                                    
                                    with open(matched_img_path, "rb") as img_f:
                                        img_bytes = img_f.read()
                                    
                                    b64 = base64.b64encode(img_bytes).decode()
                                    mime = mimetypes.guess_type(str(matched_img_path))[0] or "image/png"
                                    file_name = matched_img_path.name
                                    
                                    upload_res = await client.upload_image(
                                        b64, mime_type=mime, project_id=project_id, file_name=file_name
                                    )
                                    
                                    if upload_res.get("error") or (isinstance(upload_res.get("status"), int) and upload_res["status"] >= 400):
                                        log(f"[Flow Kit Storyboard] Failed to upload storyboard image: {upload_res.get('error')}")
                                    else:
                                        uploaded_media_id = upload_res.get("_mediaId")
                                        if uploaded_media_id:
                                            # Update database
                                            if orientation == "VERTICAL":
                                                await crud.update_scene(
                                                    scene_id, 
                                                    vertical_image_media_id=uploaded_media_id,
                                                    vertical_image_status="COMPLETED",
                                                    vertical_image_url=upload_res.get("url")
                                                )
                                            else:
                                                await crud.update_scene(
                                                    scene_id, 
                                                    horizontal_image_media_id=uploaded_media_id,
                                                    horizontal_image_status="COMPLETED",
                                                    horizontal_image_url=upload_res.get("url")
                                                )
                                            # Re-fetch scene to update target_scene variable so step 5 uses it
                                            target_scene = await crud.get_scene(scene_id)
                                            log(f"[Flow Kit Storyboard] Uploaded and synced storyboard image Media ID: {uploaded_media_id}")
                                        else:
                                            log(f"[Flow Kit Storyboard] No media_id returned from upload: {upload_res}")
                except Exception as sb_err:
                    log(f"[Flow Kit Storyboard Warning] Failed to scan/upload storyboard: {sb_err}")
            
            # 5. Submit request to queue
            orientation = target_video.get("orientation") or "VERTICAL"
            image_media_id = target_scene.get("vertical_image_media_id") if orientation == "VERTICAL" else target_scene.get("horizontal_image_media_id")
            
            if not image_media_id:
                req_type = "GENERATE_IMAGE"
                log(f"[Flow Kit Queue] Scene {round_idx} doesn't have image media ID. Submitting GENERATE_IMAGE request...")
            else:
                req_type = "GENERATE_VIDEO"
                log(f"[Flow Kit Queue] Scene {round_idx} has image media ID ({image_media_id}). Submitting GENERATE_VIDEO request...")
                
            existing_reqs = await crud.list_requests(scene_id=scene_id)
            active_req = [r for r in existing_reqs if r.get("type") == req_type and r.get("status") in ("PENDING", "PROCESSING")]
            
            # Resolve parameters for video generation
            edit_prompt_json = None
            if req_type == "GENERATE_VIDEO":
                import json as _json
                vmodel = payload.video_model or "veo_3_1_i2v_s_fast"
                params_dict = {
                    "video_model": vmodel,
                    "duration_seconds": 5,
                    "output_count": payload.output_count
                }
                edit_prompt_json = _json.dumps(params_dict)

            if not active_req:
                new_req = await crud.create_request(
                    project_id=project_id,
                    video_id=video_id,
                    scene_id=scene_id,
                    req_type=req_type,
                    orientation=orientation,
                    edit_prompt=edit_prompt_json
                )
                log(f"[Flow Kit Queue] Submitted request: {new_req['id']}")
                
                # Check if we should also queue UPSCALE_VIDEO
                if req_type == "GENERATE_VIDEO" and payload.upscale_resolution and payload.upscale_resolution != "NONE":
                    upscale_active = [r for r in existing_reqs if r.get("type") == "UPSCALE_VIDEO" and r.get("status") in ("PENDING", "PROCESSING")]
                    if not upscale_active:
                        upscale_params = {
                            "resolution": payload.upscale_resolution
                        }
                        await crud.create_request(
                            project_id=project_id,
                            video_id=video_id,
                            scene_id=scene_id,
                            req_type="UPSCALE_VIDEO",
                            orientation=orientation,
                            edit_prompt=_json.dumps(upscale_params)
                        )
                        log(f"[Flow Kit Queue] Submitted UPSCALE_VIDEO request for resolution: {payload.upscale_resolution}")
                
                return {"ok": True, "message": f"ส่งคำขอไปยังคิว Flow Kit สำเร็จ (ประเภท: {req_type})", "status": "PENDING"}
            else:
                log(f"[Flow Kit Queue] Request already active: {active_req[0]['id']}")
                
                # Double-check if we should queue UPSCALE_VIDEO even if GENERATE_VIDEO is already active/pending
                if req_type == "GENERATE_VIDEO" and payload.upscale_resolution and payload.upscale_resolution != "NONE":
                    upscale_active = [r for r in existing_reqs if r.get("type") == "UPSCALE_VIDEO" and r.get("status") in ("PENDING", "PROCESSING")]
                    if not upscale_active:
                        upscale_params = {
                            "resolution": payload.upscale_resolution
                        }
                        await crud.create_request(
                            project_id=project_id,
                            video_id=video_id,
                            scene_id=scene_id,
                            req_type="UPSCALE_VIDEO",
                            orientation=orientation,
                            edit_prompt=_json.dumps(upscale_params)
                        )
                        log(f"[Flow Kit Queue] Submitted UPSCALE_VIDEO request for resolution: {payload.upscale_resolution}")
                        
                return {"ok": True, "message": f"คำขอนี้กำลังทำงานอยู่แล้วในคิว Flow Kit (ประเภท: {req_type})", "status": active_req[0]['status']}

        except Exception as flow_err:
            log(f"[Flow Kit Error] {flow_err}")
            raise HTTPException(status_code=500, detail=f"Flow Kit Error: {flow_err}")
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



    if not switched:
        opened_urls = []
        try:
            current_handle = driver.current_window_handle
            for handle in driver.window_handles:
                try:
                    driver.switch_to.window(handle)
                    opened_urls.append(driver.current_url)
                except Exception:
                    pass
            try:
                driver.switch_to.window(current_handle)
            except Exception:
                pass
        except Exception:
            pass
        
        urls_str = ", ".join(opened_urls) if opened_urls else "ไม่พบแท็บใดๆ"
        log(f"[ไม่พบแท็บ Flow] สแกนเจอแท็บอื่นๆ ในเบราว์เซอร์: {urls_str}")
        raise HTTPException(
            status_code=400, 
            detail=f"ไม่พบแท็บ Google Flow ที่เปิดอยู่ (แท็บที่สแกนเจอในเบราว์เซอร์อัตโนมัติ: {urls_str}) กรุณาตรวจสอบว่าได้เปิดหน้า Google Flow ในเบราว์เซอร์ที่เปิดขึ้นมานี้"
        )

    # Bring Chrome window to front (Commented out to run completely in background)
    # _activate_chrome()

    # 2. Check for unusual activity and clear cache/cookies if found (Disabled by user request)
    # check_unusual_activity_and_clear(driver, payload.google_flow_email, payload.google_flow_project_name)

    # 2.5 Ensure logged in if on landing page or accounts chooser page
    handle_google_flow_login_if_needed(driver, payload.google_flow_email)

    # 2.7 Ensure target project is opened
    open_google_flow_project_if_needed(driver, payload.google_flow_project_name)

    # 2.75 If auto_retry_mode is enabled, check before anything if any previous round needs retry
    if payload.auto_retry_mode and round_idx > 1:
        log("[Auto Retry Pre-Submit] สแกนหาปุ่ม 'ลองอีกครั้ง' (Retry) สำหรับรอบก่อนหน้านี้...")
        for prev_r in range(1, round_idx):
            round_str = f"{prev_r:02d}"
            possible_xpaths = [
                f"//div[contains(., '@{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
                f"//div[contains(., 'round_{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
                f"//div[contains(., '{round_str}.png')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
            ]
            retry_btn = None
            for xpath in possible_xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                    if elements:
                        retry_btn = elements[0]
                        break
                except Exception:
                    continue
            
            if retry_btn:
                log(f"[Auto Retry] พบปุ่ม 'ลองอีกครั้ง' สำหรับรอบที่ {prev_r} กำลังทำการคลิก...")
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", retry_btn)
                    time.sleep(0.5)
                    retry_btn.click()
                    log(f"[Auto Retry สำเร็จ] คลิกปุ่มลองอีกครั้งสำหรับรอบที่ {prev_r} สำเร็จ")
                    time.sleep(1.0)
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", retry_btn)
                        log(f"[Auto Retry สำเร็จ] คลิกปุ่มลองอีกครั้งด้วย JS สำหรับรอบที่ {prev_r} สำเร็จ")
                        time.sleep(1.0)
                    except Exception as click_err:
                        log(f"[Auto Retry Warning] ไม่สามารถคลิกปุ่มลองอีกครั้งสำหรับรอบที่ {prev_r} ได้: {click_err}")

    # 2.8 Check if auto_retry_mode is enabled and try to find/click the retry button
    if payload.auto_retry_mode:
        log(f"[Auto Retry Check] ตรวจสอบว่ามีปุ่ม 'ลองอีกครั้ง' (Retry) สำหรับรอบที่ {round_idx} หรือไม่...")
        round_str = f"{round_idx:02d}"
        possible_xpaths = [
            f"//div[contains(., '@{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
            f"//div[contains(., 'round_{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
            f"//div[contains(., '{round_str}.png')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
        ]
        retry_btn = None
        for xpath in possible_xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                if elements:
                    retry_btn = elements[0]
                    break
            except Exception:
                continue
        
        if retry_btn:
            log(f"[Auto Retry] พบปุ่ม 'ลองอีกครั้ง' สำหรับรอบที่ {round_idx} จะทำการคลิกแทนการส่งพรอพต์ใหม่")
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", retry_btn)
                time.sleep(0.5)
                retry_btn.click()
                log(f"[Auto Retry สำเร็จ] คลิกปุ่มลองอีกครั้งสำหรับรอบที่ {round_idx} เรียบร้อยแล้ว")
                return {"ok": True, "message": f"คลิกปุ่มลองอีกครั้งรอบที่ {round_idx} เรียบร้อยแล้ว (Auto Retry)"}
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", retry_btn)
                    log(f"[Auto Retry สำเร็จ] คลิกปุ่มลองอีกครั้งด้วย JS สำหรับรอบที่ {round_idx} เรียบร้อยแล้ว")
                    return {"ok": True, "message": f"คลิกปุ่มลองอีกครั้งรอบที่ {round_idx} เรียบร้อยแล้ว (Auto Retry)"}
                except Exception as click_err:
                    log(f"[Auto Retry Warning] ไม่สามารถคลิกปุ่มลองอีกครั้งได้: {click_err}. จะดำเนินการป้อนพรอพต์ตามปกติ")
        else:
            log(f"[Auto Retry] ไม่พบปุ่ม 'ลองอีกครั้ง' สำหรับรอบที่ {round_idx} ดำเนินการป้อนพรอพต์ตามปกติ")

    # 3. Find and click prompt input field
    if not video_input_selector:
        video_input_selector = "div[contenteditable='true']"

    # Wait for the card list to render the new box if it's not the first run
    if not payload.is_first_run:
        log("[รอการ์ดใหม่] รอให้ Google Flow โหลดกล่องป้อนพรอพต์ใหม่ขึ้นมาบนหน้าจอ...")
        for wait_attempt in range(12):
            try:
                boxes_check = driver.find_elements(By.CSS_SELECTOR, video_input_selector)
                if len(boxes_check) >= round_idx:
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
    time.sleep(1.0)

    # 3.5 Check and configure Model (Veo 3.1 - Lite) and Settings (Only on the first run of the batch)
    if payload.is_first_run:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")

        # 1. Click settings button to open the panel
        trigger_xpath = "//button[@aria-haspopup='menu' and (contains(@class, 'ldbhld') or contains(@class, 'sc-93abd9dc-1'))]"
        log("[แผงตั้งค่า] คลิกเปิดแผงตั้งค่าตัวเลือก...")
        try:
            trigger_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, trigger_xpath))
            )
            try:
                trigger_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", trigger_btn)
            log("[แผงตั้งค่า] คลิกเปิดแผงตั้งค่าสำเร็จ")
        except Exception as open_err:
            log(f"[แผงตั้งค่าล้มเหลว] ไม่สามารถคลิกเปิดแผงตั้งค่าได้: {open_err}")
            raise HTTPException(
                status_code=400,
                detail=f"เปิดแผงตั้งค่าวิดีโอล้มเหลว: {open_err}"
            )
            
        time.sleep(1.0) # Wait for panel to load

        # 1.2 Click the "Video" tab if it is not selected
        video_tab_xpath = "//button[@role='tab' and (contains(., 'Video') or contains(@id, 'VIDEO') or contains(@aria-controls, 'VIDEO'))]"
        log("[แผงตั้งค่า] คลิกเลือกแท็บหลัก Video...")
        try:
            video_tab = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, video_tab_xpath))
            )
            state = video_tab.get_attribute("data-state")
            if state != "active":
                try:
                    video_tab.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", video_tab)
                log("[แผงตั้งค่า] คลิกเลือกแท็บหลัก Video สำเร็จ")
                time.sleep(1.0) # Wait for tab switch
            else:
                log("[แผงตั้งค่า] แท็บหลักเป็น Video อยู่แล้ว")
        except Exception as tab_err:
            log(f"[แผงตั้งค่าเตือน] ไม่สามารถคลิกเลือกแท็บหลัก Video ได้: {tab_err}")

        # 1.5 Click the "Frames" tab inside the settings panel
        frames_tab_xpath = "//button[@role='tab' and (contains(., 'Frames') or contains(@id, 'VIDEO_FRAMES') or contains(@aria-controls, 'VIDEO_FRAMES'))]"
        log("[แผงตั้งค่า] คลิกเลือกแท็บ Frames...")
        try:
            frames_tab = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, frames_tab_xpath))
            )
            try:
                frames_tab.click()
            except Exception:
                driver.execute_script("arguments[0].click();", frames_tab)
            log("[แผงตั้งค่า] คลิกเลือกแท็บ Frames สำเร็จ")
        except Exception as tab_err:
            log(f"[แผงตั้งค่าเตือน] ไม่สามารถคลิกเลือกแท็บ Frames ได้: {tab_err}")
        time.sleep(0.8)

        # 1.7 Click the "9:16" (Portrait) ratio tab inside the settings panel
        ratio_916_xpath = "//button[@role='tab' and (contains(., '9:16') or contains(@id, 'PORTRAIT') or contains(@aria-controls, 'PORTRAIT'))]"
        log("[แผงตั้งค่า] คลิกเลือกอัตราส่วน 9:16...")
        try:
            ratio_tab = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, ratio_916_xpath))
            )
            state = ratio_tab.get_attribute("data-state")
            if state != "active":
                try:
                    ratio_tab.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", ratio_tab)
                log("[แผงตั้งค่า] คลิกเลือกอัตราส่วน 9:16 สำเร็จ")
                time.sleep(1.0) # Wait for animation
            else:
                log("[แผงตั้งค่า] อัตราส่วนเป็น 9:16 อยู่แล้ว")
        except Exception as ratio_err:
            log(f"[แผงตั้งค่าเตือน] ไม่สามารถคลิกเลือกอัตราส่วน 9:16 ได้: {ratio_err}")
        time.sleep(0.8)

        # 2. Locate the model selection dropdown button inside the panel
        model_dropdown_xpath = "//button[(contains(@class, 'eaVRLg') or contains(@class, 'sc-3f41cc92-1') or contains(., 'Omni') or contains(., 'Veo') or contains(., 'Flash') or contains(., 'Lite')) and (contains(., 'arrow_drop_down') or .//i[text()='arrow_drop_down'])]"
        model_option_xpath = "//button[.//span[text()='Veo 3.1 - Lite'] or contains(., 'Veo 3.1 - Lite')]"
        
        try:
            log("[แผงตั้งค่า] ค้นหาปุ่มเลือกโมเดล (Model Button)...")
            model_dropdown = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, model_dropdown_xpath))
            )
            current_model_text = model_dropdown.text.strip()
            log(f"[แผงตั้งค่า] โมเดลที่เลือกอยู่ในปัจจุบันคือ: '{current_model_text}'")
            
            if "Veo 3.1 - Lite" not in current_model_text:
                log(f"[แผงตั้งค่า] โมเดลไม่ใช่ Veo 3.1 - Lite (เป็น '{current_model_text}'), กำลังคลิกปุ่มนี้เพื่อเปลี่ยนโมเดล...")
                
                opened = False
                for click_attempt in range(3):
                    log(f"[แผงตั้งค่า] พยายามคลิกเปิดเมนูโมเดล รอบที่ {click_attempt+1}...")
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", model_dropdown)
                        time.sleep(0.3)
                        model_dropdown.click()
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", model_dropdown)
                        except Exception:
                            pass
                    
                    time.sleep(0.8) # Wait for dropdown animation
                    
                    # Check if option is visible in DOM
                    options = driver.find_elements(By.XPATH, model_option_xpath)
                    if any(opt.is_displayed() for opt in options):
                        log("[แผงตั้งค่า] ตรวจพบเมนูตัวเลือกโมเดลเปิดสำเร็จแล้ว!")
                        opened = True
                        break
                
                if not opened:
                    # Debugging: scan all buttons while settings panel is open
                    try:
                        log("=== [DEBUG] เริ่มการดึงข้อมูลปุ่มทั้งหมดในขณะที่แผงตั้งค่าเปิดอยู่ ===")
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        log(f"พบปุ่มทั้งหมด {len(buttons)} ปุ่ม")
                        for idx, btn in enumerate(buttons):
                            try:
                                btn_id = btn.get_attribute("id") or "ไม่มี ID"
                                btn_class = btn.get_attribute("class") or "ไม่มี Class"
                                btn_text = btn.text.strip().replace('\n', ' ') or "ไม่มี Text"
                                btn_html = btn.get_attribute("outerHTML")
                                log(f"ปุ่มที่ #{idx}: ID='{btn_id}', Class='{btn_class}', Text='{btn_text}' | HTML={btn_html[:350]}...")
                            except Exception:
                                pass
                        log("=== [DEBUG] สิ้นสุดการดึงข้อมูลปุ่ม ===")
                    except Exception:
                        pass
                    raise RuntimeError("ไม่สามารถเปิดเมนูตัวเลือกโมเดลได้")

                # Select Model Option: "Veo 3.1 - Lite"
                log("[แผงตั้งค่า] คลิกเลือกโมเดล Veo 3.1 - Lite จากดรอปดาวน์...")
                model_option = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, model_option_xpath))
                )
                try:
                    model_option.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", model_option)
                time.sleep(1.0)
            else:
                log("[แผงตั้งค่า] โมเดลเป็น Veo 3.1 - Lite อยู่แล้ว ข้ามการคลิกเลือกโมเดล")
                
            # 3. Press ESCAPE to close settings panel
            log("[แผงตั้งค่า] กดปุ่ม Escape เพื่อปิดหน้าต่างการตั้งค่า...")
            try:
                driver.switch_to.active_element.send_keys(Keys.ESCAPE)
            except Exception:
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(driver)
                    actions.send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
            time.sleep(1.0)

        except Exception as model_err:
            log(f"[แผงตั้งค่าล้มเหลว] ไม่สามารถเลือกโมเดลได้: {model_err}")
            import traceback
            tb = traceback.format_exc()
            log(f"Traceback:\n{tb}")
            raise HTTPException(
                status_code=400,
                detail=f"เลือกโมเดล Veo 3.1 - Lite ล้มเหลว: {model_err}"
            )

        # 4. Refocus prompt input box on the first run (because settings panel was opened and closed)
        log("[ป้อนข้อมูล] โฟกัสช่องพรอพต์อีกครั้งก่อนป้อน @")
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", box)
            time.sleep(0.3)
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
        time.sleep(0.8)

    log("[ป้อนข้อมูล] พิมพ์ @ ด้วยคีย์บอร์ดเสมือน")
    try:
        actions = ActionChains(driver)
        actions.send_keys("@").perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"พิมพ์ @ ด้วย ActionChains ล้มเหลว, ใช้ box.send_keys: {e}")
        box.send_keys("@")
    time.sleep(1.0) # Wait 1.0s after typing @

    # Type round number and extension using ActionChains keyboard events
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    text_to_type = f"{round_idx:02d}.png"
    log(f"[ป้อนข้อมูล] พิมพ์หมายเลขอ้างอิงและนามสกุล (.png) ด้วยคีย์บอร์ดเสมือน: {text_to_type}")
    try:
        actions = ActionChains(driver)
        actions.send_keys(text_to_type).perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"พิมพ์ด้วย ActionChains ล้มเหลว, ใช้ box.send_keys: {e}")
        box.send_keys(text_to_type)
    time.sleep(1.0) # Wait 1.0s for autocomplete

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
    
    # Wait 0.05 seconds after selecting autocomplete
    time.sleep(0.05)

    # Press Shift+Enter 1 time
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log("[ป้อนข้อมูล] กด Shift+Enter ด้วยคีย์บอร์ดเสมือน 1 ครั้ง")
    try:
        actions = ActionChains(driver)
        actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"กด Shift+Enter ล้มเหลว: {e}")
    time.sleep(0.05)

    # 5. Paste the animation prompt using ActionChains (simulating active caret input)
    if not is_driver_alive(driver):
        raise RuntimeError("Browser connection lost.")
    log(f"[ป้อนข้อมูล] พิมพ์พรอพต์ของฉากด้วย ActionChains: {prompt}")
    try:
        # Split prompt by newlines and send shift+enter in between to avoid triggering early submits
        lines = prompt.split('\n')
        for idx, line in enumerate(lines):
            if idx > 0:
                actions = ActionChains(driver)
                actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
                time.sleep(0.05)
            
            # Prepend space on the first line to separate from mention chip
            text_chunk = (" " if idx == 0 else "") + line
            if text_chunk:
                try:
                    actions = ActionChains(driver)
                    actions.send_keys(text_chunk).perform()
                except Exception as ac_err:
                    log(f"พิมพ์ด้วย ActionChains ล้มเหลว: {ac_err}, ลองใช้ box.send_keys")
                    box.send_keys(text_chunk)
        log("[ป้อนข้อมูลสำเร็จ] วางพรอพต์สำเร็จ")
    except Exception as e:
        if not is_driver_alive(driver):
            raise RuntimeError("Browser connection lost.")
        log(f"พิมพ์พรอพต์ล้มเหลว: {e}")
        raise HTTPException(status_code=500, detail=f"ไม่สามารถกรอกพรอพต์ได้: {e}")
    time.sleep(1.0)

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

    log(f"วางพรอพต์เรียบร้อยแล้วและส่งเรียบร้อย")
    return {"ok": True, "message": "วางพรอพต์และส่งเรียบร้อย"}


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

    # 1.5 Check for unusual activity and clear cache/cookies if found (Disabled by user request)
    target_email = "dogdadcatmom@gmail.com"
    target_project_name = "7-1"
    try:
        import json
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                target_email = cfg.get("google_flow_email", "dogdadcatmom@gmail.com")
                target_project_name = cfg.get("google_flow_project_name", "7-1")
    except Exception:
        pass

    # check_unusual_activity_and_clear(driver, target_email, target_project_name)
    handle_google_flow_login_if_needed(driver, target_email)
    open_google_flow_project_if_needed(driver, target_project_name)

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


class VideoRetryScanPayload(BaseModel):
    max_round_idx: int


@app.post("/api/step/video-retry-scan")
def step_video_retry_scan(payload: VideoRetryScanPayload) -> dict[str, Any]:
    from selenium.webdriver.common.by import By
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
        return {"ok": False, "message": "ไม่พบแท็บ Google Flow ที่เปิดอยู่", "clicked_rounds": []}

    if not is_driver_alive(driver):
        return {"ok": False, "message": "Browser session is not alive", "clicked_rounds": []}

    clicked_rounds = []
    
    # Scan from round 1 up to max_round_idx
    for r in range(1, payload.max_round_idx + 1):
        round_str = f"{r:02d}"
        possible_xpaths = [
            f"//div[contains(., '@{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
            f"//div[contains(., 'round_{round_str}')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
            f"//div[contains(., '{round_str}.png')]//button[.//span[text()='ลองอีกครั้ง' or text()='Try again'] or .//i[text()='refresh']]",
        ]
        
        retry_btn = None
        for xpath in possible_xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                if elements:
                    retry_btn = elements[0]
                    break
            except Exception:
                continue
        
        if retry_btn:
            log(f"[Scan Retry] พบปุ่ม 'ลองอีกครั้ง' สำหรับรอบที่ {r} ระหว่างรอนับถอยหลัง กำลังคลิก...")
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", retry_btn)
                time.sleep(0.3)
                retry_btn.click()
                log(f"[Scan Retry สำเร็จ] คลิกปุ่มลองอีกครั้งสำหรับรอบที่ {r} สำเร็จ")
                clicked_rounds.append(r)
                time.sleep(0.5)
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", retry_btn)
                    log(f"[Scan Retry สำเร็จ] คลิกปุ่มลองอีกครั้งด้วย JS สำหรับรอบที่ {r} สำเร็จ")
                    clicked_rounds.append(r)
                    time.sleep(0.5)
                except Exception as click_err:
                    log(f"[Scan Retry Warning] ไม่สามารถคลิกปุ่มลองอีกครั้งสำหรับรอบที่ {r} ได้: {click_err}")

    if clicked_rounds:
        return {"ok": True, "message": f"คลิกปุ่มลองอีกครั้งสำหรับรอบ {clicked_rounds} เรียบร้อยแล้ว", "clicked_rounds": clicked_rounds}
    return {"ok": True, "message": "ไม่พบรอบที่ต้องกดลองอีกครั้ง", "clicked_rounds": []}


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


class StoryboardAutofillPayload(BaseModel):
    autofill_characters: bool = True
    autofill_locations: bool = True
    autofill_props: bool = True
    autofill_scenes: bool = True
    delay_seconds: float = 1.5
    scene_range: str = ""


@app.post("/api/step/storyboard-autofill")
async def step_storyboard_autofill(payload: StoryboardAutofillPayload) -> dict[str, Any]:
    try:
        bot = browser_manager.get()
        if not bot or not bot.driver:
            raise Exception("Browser is not active. Please launch a browser profile first.")
        
        driver = bot.driver
        
        # 1. Switch to Google Flow tab if it exists
        switched = False
        for url_part in ["tools/flow", "labs.google", "vids.google.com"]:
            if bot.switch_to_tab_containing(url_part):
                switched = True
                break
                
        if not switched:
            raise Exception("Google Flow tab was not found in the browser. Please open Google Flow first.")

        # 2. Build list of button text targets to autofill based on payload
        targets = []
        if payload.autofill_characters:
            targets.append("Autofill Characters")
        if payload.autofill_locations:
            targets.append("Autofill Locations")
        if payload.autofill_props:
            targets.append("Autofill Props")
        if payload.autofill_scenes:
            targets.append("Autofill Scene")

        if not targets:
            return {"ok": True, "clicked_count": 0, "clicked_buttons": []}

        # 3. Check if buttons are in main window or inside an iframe
        target_frame = None
        
        # Check default content first
        buttons_count = driver.execute_script("""
            const targets = arguments[0];
            const buttons = Array.from(document.querySelectorAll('button'));
            return buttons.filter(btn => targets.some(t => btn.textContent.trim().includes(t))).length;
        """, targets)
        
        if buttons_count > 0:
            target_frame = "default"
        else:
            # Check iframes
            iframes = driver.find_elements("tag name", "iframe")
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    count = driver.execute_script("""
                        const targets = arguments[0];
                        const buttons = Array.from(document.querySelectorAll('button'));
                        return buttons.filter(btn => targets.some(t => btn.textContent.trim().includes(t))).length;
                    """, targets)
                    if count > 0:
                        target_frame = iframe
                        break
                except Exception:
                    pass
                finally:
                    driver.switch_to.default_content()

        # Switch to the frame if found
        if target_frame and target_frame != "default":
            driver.switch_to.frame(target_frame)
            log("Switched to iframe containing autofill buttons.")
        elif not target_frame:
            log("Warning: No matching autofill buttons found in default content or any iframes. Running script on default content.")

        try:
            # Initialize stop flag to false
            driver.execute_script("window.autofillStopRequested = false;")
            
            # 4. Execute JS in browser context with async script for delayed clicking
            delay_ms = int(payload.delay_seconds * 1000)
            
            script = """
            const callback = arguments[arguments.length - 1];
            const targets = arguments[0];
            const delayMs = arguments[1];
            const rangeStr = arguments[2];
            
            (async () => {
                try {
                    window.autofillStopRequested = false;
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const matchedButtons = [];
                    for (const btn of buttons) {
                        const txt = btn.textContent.trim();
                        if (targets.some(t => txt.includes(t))) {
                            matchedButtons.push(btn);
                        }
                    }
                    
                    // Parse range
                    let rangeStart = 1;
                    let rangeEnd = 999999;
                    let hasRange = false;
                    if (rangeStr && rangeStr.trim()) {
                        hasRange = true;
                        const parts = rangeStr.trim().split('-');
                        if (parts.length === 2) {
                            const s = parseInt(parts[0], 10);
                            const e = parseInt(parts[1], 10);
                            if (!isNaN(s)) rangeStart = s;
                            if (!isNaN(e)) rangeEnd = e;
                        } else {
                            const s = parseInt(rangeStr.trim(), 10);
                            if (!isNaN(s)) {
                                rangeStart = s;
                                rangeEnd = s;
                            }
                        }
                    }
                    
                    let clickedCount = 0;
                    let details = [];
                    let n = 0; // 1-based storyboard scene index (1, 2, 3...)
                    
                    for (const btn of matchedButtons) {
                        if (window.autofillStopRequested) {
                            details.push("[STOPPED BY USER]");
                            break;
                        }
                        
                        const txt = btn.textContent.trim();
                        const isSceneButton = txt.includes("Autofill Scene");
                        
                        if (isSceneButton) {
                            n++; // 1st storyboard scene button is n = 1
                            
                            // Apply n + 3 logic: user typed range (e.g., 5-10) is checked against (n + 3)
                            const overallIndex = n + 3; // n + 3 maps 1 -> 4, 2 -> 5, 3 -> 6...
                            
                            if (hasRange) {
                                const targetStart = rangeStart + 3; // Shift start range by +3
                                const targetEnd = rangeEnd + 3;     // Shift end range by +3
                                
                                if (overallIndex < targetStart || overallIndex > targetEnd) {
                                    continue; // Skip scenes outside n + 3 target range
                                }
                            }
                        }
                        
                        // Scroll to button to ensure visibility and prevent click interception
                        btn.scrollIntoView({ block: 'center', behavior: 'smooth' });
                        // Small delay after scrolling to let UI settle
                        await new Promise(r => setTimeout(r, 200));
                        if (window.autofillStopRequested) {
                            details.push("[STOPPED BY USER]");
                            break;
                        }
                        btn.click();
                        clickedCount++;
                        details.push(txt);
                        if (delayMs > 0) {
                            // Check stop request in chunks of 100ms during the delay
                            const startWait = Date.now();
                            while (Date.now() - startWait < delayMs) {
                                if (window.autofillStopRequested) {
                                    break;
                                }
                                await new Promise(r => setTimeout(r, 100));
                            }
                        }
                    }
                    callback({ ok: true, clicked_count: clickedCount, clicked_buttons: details });
                } catch (e) {
                    callback({ ok: false, error: e.toString() });
                }
            })();
            """
            # Set script timeout in driver to be larger than total delay
            total_timeout = max(60, int(20 * payload.delay_seconds) + 15)
            driver.set_script_timeout(total_timeout)
            
            result = driver.execute_async_script(script, targets, delay_ms, payload.scene_range)
            if not result.get("ok"):
                raise Exception(result.get("error", "Unknown script error"))
                
            log(f"[Storyboard Autofill] Clicked {result['clicked_count']} autofill buttons: {result['clicked_buttons']}")
            return {"ok": True, "clicked_count": result["clicked_count"], "clicked_buttons": result["clicked_buttons"]}
        finally:
            # Always return to default content context
            driver.switch_to.default_content()
    except Exception as e:
        log(f"[Storyboard Autofill] Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/step/storyboard-autofill/stop")
async def stop_storyboard_autofill() -> dict[str, Any]:
    try:
        bot = browser_manager.get()
        if bot and bot.driver:
            for url_part in ["tools/flow", "labs.google", "vids.google.com"]:
                if bot.switch_to_tab_containing(url_part):
                    # Set the flag on both the main window and all sub-iframes
                    script = """
                    window.autofillStopRequested = true;
                    try {
                        const iframes = document.querySelectorAll('iframe');
                        for (const iframe of iframes) {
                            try {
                                const iframeDoc = iframe.contentDocument || iframe.contentWindow;
                                if (iframeDoc) {
                                    iframeDoc.autofillStopRequested = true;
                                }
                            } catch(e) {}
                        }
                    } catch(e) {}
                    """
                    bot.driver.execute_script(script)
                    log("[Storyboard Autofill] Sent stop request to browser context.")
                    return {"ok": True, "message": "Stop request sent successfully"}
        return {"ok": False, "message": "Browser or driver not active"}
    except Exception as e:
        log(f"[Storyboard Autofill] Stop Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/")

def index():
    return FileResponse(BASE_DIR / "web" / "index.html")


app.mount("/web", StaticFiles(directory=BASE_DIR / "web"), name="web")
