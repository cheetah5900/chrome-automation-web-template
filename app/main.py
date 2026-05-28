from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
DEFAULTS_FILE = RUNTIME_DIR / "defaults.json"

RUNTIME_DIR.mkdir(exist_ok=True)
if not DEFAULTS_FILE.exists():
    DEFAULTS_FILE.write_text(
        json.dumps(
            {
                "chrome_profile_path": "",
                "chrome_debug_port": 9222,
                "theme": "sunset-glass",
            },
            indent=2,
        )
    )

app = FastAPI(title="Chrome Automation Template")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DefaultsPayload(BaseModel):
    chrome_profile_path: str
    chrome_debug_port: int = 9222
    theme: str = "sunset-glass"


class ProviderPayload(BaseModel):
    provider: str
    api_key: str


@app.get("/api/defaults")
def get_defaults():
    return json.loads(DEFAULTS_FILE.read_text())


@app.post("/api/defaults")
def save_defaults(payload: DefaultsPayload):
    data = payload.model_dump()
    DEFAULTS_FILE.write_text(json.dumps(data, indent=2))
    return {"ok": True, "message": "Saved runtime/defaults.json", "data": data}


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
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            r = await client.get(url)
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
