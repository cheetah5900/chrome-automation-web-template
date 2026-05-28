# Chrome Automation Web Template

A beautiful starter web app to prepare Chrome profiles for automation.

## Features

- Set **Chrome profile folder path**
- Fixed default **remote debugging port = 9222** (editable)
- **Set as default** button saves into `runtime/defaults.json` (tracked in repo)
- Test API connectivity for:
  - OpenAI
  - Gemini
  - OpenRouter
- Glassmorphism UI with gradient theme

## Project Structure

- `app/main.py` — FastAPI backend + API endpoints
- `web/index.html` — UI
- `web/styles.css` — styling
- `web/app.js` — frontend logic
- `runtime/defaults.json` — default path/port JSON included in repo

## Run locally

```bash
cd chrome-automation-template
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open: `http://localhost:8080`

## API Endpoints

- `GET /api/defaults` — read defaults JSON
- `POST /api/defaults` — save defaults JSON
- `POST /api/test-provider` — test provider key

### test-provider payload

```json
{
  "provider": "openai | gemini | openrouter",
  "api_key": "..."
}
```

## Chrome launch example for automation

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/path/to/your/profile-folder"
```

On Windows:

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\path\to\profile"
```

## Notes

- API keys are only sent to test endpoint and are **not persisted** to git-tracked files.
- `runtime/defaults.json` is versioned so template users always get a default config file.
