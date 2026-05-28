from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx
import os
import shutil
import subprocess
import time

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


class SelectProfilePayload(BaseModel):
    name: str


class LaunchProfilePayload(BaseModel):
    name: str


class GeminiRunPayload(BaseModel):
    prompts: list[str]
    download_images: bool = False


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
    existing = next((p for p in data["profiles"] if p.get("name") == name), None)
    if existing:
        existing["debug_port"] = payload.debug_port
        existing["path"] = str(profile_dir)
    else:
        data["profiles"].append({"name": name, "path": str(profile_dir), "debug_port": payload.debug_port})

    if not data.get("selected_profile"):
        data["selected_profile"] = name

    _write_json(PROFILES_FILE, data)
    _write_json(DEFAULTS_FILE, {"selected_profile": data["selected_profile"], "theme": "sunset-glass"})
    return {"ok": True, "profile": {"name": name, "path": str(profile_dir), "debug_port": payload.debug_port}}


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
    data = _profiles_data()
    profile = next((p for p in data["profiles"] if p.get("name") == payload.name), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile_path = profile["path"]
    debug_port = int(profile.get("debug_port", 9222))

    chrome_cmds = [
        ["google-chrome", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile_path}"],
        ["google-chrome-stable", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile_path}"],
        ["chromium-browser", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile_path}"],
        ["chromium", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile_path}"],
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
            detail="Chrome executable not found. Install Chrome/Chromium or launch manually with --remote-debugging-port.",
        )

    return {
        "ok": True,
        "message": "Chrome launched",
        "debug_port": debug_port,
        "profile_path": profile_path,
        "manual_command": f"google-chrome --remote-debugging-port={debug_port} --user-data-dir='{profile_path}'",
    }


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
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            r = await client.get(url, params={"key": key})
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


@app.post("/api/gemini/run")
def run_gemini(payload: GeminiRunPayload):
    data = _profiles_data()
    selected = data.get("selected_profile")
    profile = next((p for p in data["profiles"] if p.get("name") == selected), None)
    if not profile:
        raise HTTPException(status_code=400, detail="No selected profile")

    prompts = [p.strip() for p in payload.prompts if p and p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="prompts is empty")

    # Gemini logic adapted from ddcm-browser-helper-ai workflow.py step3/step4.
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{int(profile.get('debug_port', 9222))}")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed connecting Chrome debugger: {e}")

    try:
        # Switch/create Gemini tab
        found = False
        for h in driver.window_handles:
            driver.switch_to.window(h)
            if "gemini.google.com" in driver.current_url:
                found = True
                break
        if not found:
            driver.switch_to.new_window("tab")
            driver.get("https://gemini.google.com/app")
            time.sleep(2)

        input_strats = [
            "//div[contains(@class, 'ql-editor') and @contenteditable='true']",
            "//rich-textarea//div[@contenteditable='true']",
            "//div[@contenteditable='true' and @role='textbox']",
        ]

        sent = 0
        for prompt in prompts:
            box = None
            for xp in input_strats:
                try:
                    tmp = WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.XPATH, xp)))
                    if tmp.is_displayed():
                        box = tmp
                        break
                except Exception:
                    continue
            if not box:
                raise RuntimeError("Gemini input box not found")

            try:
                box.click()
            except Exception:
                driver.execute_script("arguments[0].click();", box)

            driver.execute_script(
                "if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }",
                box,
            )
            box.send_keys(prompt)
            box.send_keys(Keys.ENTER)
            time.sleep(3)

            stop_xp = "//mat-icon[contains(@data-mat-icon-name, 'stop') or @fonticon='stop']"
            elapsed = 0
            while elapsed < 120:
                try:
                    driver.find_element(By.XPATH, stop_xp)
                    time.sleep(2)
                    elapsed += 2
                except Exception:
                    break
            time.sleep(2)
            sent += 1

        downloaded = 0
        if payload.download_images:
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            def get_buttons():
                return driver.find_elements(By.CSS_SELECTOR, "download-generated-image-button > button")

            btns = get_buttons()
            if not btns:
                driver.execute_script("window.scrollTo(0, 1000);")
                time.sleep(2)
                btns = get_buttons()

            for i in range(len(btns)):
                curr = get_buttons()
                if i >= len(curr):
                    break
                btn = curr[i]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                time.sleep(0.4)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(1.2)
                downloaded += 1

        return {
            "ok": True,
            "selected_profile": selected,
            "sent_prompts": sent,
            "download_attempts": downloaded,
            "message": "Gemini automation complete",
        }
    finally:
        # Keep Chrome open, only detach Selenium.
        try:
            driver.quit()
        except Exception:
            pass


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "web" / "index.html")


app.mount("/web", StaticFiles(directory=BASE_DIR / "web"), name="web")
