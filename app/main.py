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

RUNTIME_DIR.mkdir(exist_ok=True)


def _ensure_json(path: Path, default_obj: dict):
    if not path.exists():
        path.write_text(json.dumps(default_obj, indent=2))


_ensure_json(DEFAULTS_FILE, {"selected_profile": "", "theme": "sunset-glass"})
_ensure_json(PROFILES_FILE, {"selected_profile": "", "profiles": []})
_ensure_json(SETTINGS_FILE, {"openai_api_key": "", "gemini_api_key": "", "openrouter_api_key": ""})
_ensure_json(PROMPTS_FILE, {"prompts": [""]})

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


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "web" / "index.html")


app.mount("/web", StaticFiles(directory=BASE_DIR / "web"), name="web")
