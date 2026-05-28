from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx
import shutil
import subprocess
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
DEFAULTS_FILE = RUNTIME_DIR / "defaults.json"
PROFILES_FILE = RUNTIME_DIR / "profiles.json"
SETTINGS_FILE = RUNTIME_DIR / "settings.json"

RUNTIME_DIR.mkdir(exist_ok=True)


def _ensure_json(path: Path, default_obj: dict):
    if not path.exists():
        path.write_text(json.dumps(default_obj, indent=2))


_ensure_json(DEFAULTS_FILE, {"selected_profile": "", "theme": "sunset-glass"})
_ensure_json(PROFILES_FILE, {"selected_profile": "", "profiles": []})
_ensure_json(SETTINGS_FILE, {"openai_api_key": "", "gemini_api_key": "", "openrouter_api_key": ""})

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
    name: str
    debug_port: int = 9222
    startup_urls: list[str] = []


class SelectProfilePayload(BaseModel):
    name: str


class LaunchProfilePayload(BaseModel):
    name: str


class PromptDispatchPayload(BaseModel):
    prompt: str
    targets: list[str]


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
    startup_urls = _normalize_urls(payload.startup_urls)
    existing = next((p for p in data["profiles"] if p.get("name") == name), None)
    profile_obj = {
        "name": name,
        "path": str(profile_dir),
        "debug_port": int(payload.debug_port),
        "startup_urls": startup_urls,
    }
    if existing:
        existing.update(profile_obj)
    else:
        data["profiles"].append(profile_obj)

    if not data.get("selected_profile"):
        data["selected_profile"] = name

    _write_json(PROFILES_FILE, data)
    _write_json(DEFAULTS_FILE, {"selected_profile": data["selected_profile"], "theme": "sunset-glass"})
    return {"ok": True, "profile": profile_obj}


@app.post("/api/profiles/update")
def update_profile(payload: UpdateProfilePayload):
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if p.get("name") == payload.name), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile["debug_port"] = int(payload.debug_port)
    profile["startup_urls"] = _normalize_urls(payload.startup_urls)
    _write_json(PROFILES_FILE, data)
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
def launch_profile(payload: LaunchProfilePayload):
    profile = _find_profile(payload.name)

    profile_path = profile["path"]
    debug_port = int(profile.get("debug_port", 9222))
    startup_urls = _normalize_urls(profile.get("startup_urls", []))

    base_args = [f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile_path}"]
    chrome_cmds = [
        ["google-chrome", *base_args, *startup_urls],
        ["google-chrome-stable", *base_args, *startup_urls],
        ["chromium-browser", *base_args, *startup_urls],
        ["chromium", *base_args, *startup_urls],
    ]

    launched = False
    for cmd in chrome_cmds:
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd)
            launched = True
            break

    if not launched:
        raise HTTPException(
            status_code=400,
            detail="Chrome/Chromium not found. ติดตั้งเบราว์เซอร์ก่อน หรือรันเองด้วย --remote-debugging-port",
        )

    return {
        "ok": True,
        "message": "Chrome launched",
        "debug_port": debug_port,
        "profile_path": profile_path,
        "startup_urls": startup_urls,
    }


@app.post("/api/prompt/dispatch")
def dispatch_prompt(payload: PromptDispatchPayload):
    prompt = payload.prompt.strip()
    targets = [t.lower().strip() for t in payload.targets if t and t.strip()]
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if not targets:
        raise HTTPException(status_code=400, detail="targets is required")

    q = quote_plus(prompt)
    target_map = {
        "chatgpt": f"https://chatgpt.com/?q={q}",
        "gemini": f"https://gemini.google.com/app#autoPrompt={q}",
        "claude": f"https://claude.ai/new",
    }

    opened = []
    skipped = []
    for t in targets:
        url = target_map.get(t)
        if url:
            opened.append({"target": t, "url": url})
        else:
            skipped.append(t)

    return {"ok": True, "opened": opened, "skipped": skipped}


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
