# Project Overview & Current Status

This project is a web-based automation controller for managing Google Chrome profiles, launching remote debugging sessions, and running automated workflows (including image/video generation and lakorn media import).

## Key Features
1. **Profile Launching**: Launches Chrome with a specified remote debugging port (default: `9222`) and user data directory. Supports setting up to 3 startup URLs.
2. **Lakorn Import Automation**: Functional scripts to automate lakorn import workflows.
3. **AI Image/Video Generation Automation**:
   - Automates prompt submission in Gemini/ChatGPT/Google Flow.
   - Flow Kit Extension Bridge (WebSocket `ws://127.0.0.1:9225` + HTTP callback `http://127.0.0.1:6969`) for direct API interaction with Google Flow.
   - Supports both **Standard Image-to-Video Mode** and **Prompt-Only (Text-to-Video) Mode** with unified 3-card UI layout.
   - Direct Google Flow project creation via `+ New Project` button and `/api/batch-uploader/create-project` tRPC bridge.
4. **Dynamic Tooltips & Status Polling**:
   - Pure CSS absolute-positioned glassmorphism tooltips added to all functional buttons.
   - Real-time Extension connection status polling (`Connected` / `Disconnected`).

## Project Architecture
- **`app/main.py`**: FastAPI backend exposing endpoints for configuration (`/api/config`), profile launcher (`/api/profiles/launch`), and selenium automation tasks.
- **`app/browser.py`**: Handles Chrome profile processes and subprocess management.
- **`agent/main.py`**: FastAPI + WebSocket agent server entry point managing Flow Kit extension connections on `ws://127.0.0.1:9225`.
- **`agent/services/flow_client.py`**: High-level client communicating with Google Flow API via Chrome Extension bridge.
- **`agent/api/batch_uploader.py`**: Batch uploader endpoints for scanning prompts, creating projects, and submitting generation tasks.
- **`extension/background.js`**: Chrome Extension background service worker intercepting Bearer tokens (`flowKey`) and proxying API calls through browser context.
- **`web/index.html`**: Main UI dashboard layout with modern dark glassmorphism theme.
- **`web/app.js`**: Dynamic frontend script managing API updates, project dropdowns, and batch operations.

## Current Runtime Status
- **Backend Server**: Running locally on `http://127.0.0.1:6969`.
- **WebSocket Extension Port**: Running on `ws://127.0.0.1:9225`.
- **Chrome Automation Port**: Configured to `9222` (Chrome) and `9223` (Brave).
- **Active Git Branch**: `feat/google-flow-agent-integration`.
- **Latest Fixes & Features**:
  - **Unified 3-Card Flow Kit Layout**: Unified standard image-to-video mode and prompt-only mode to share an identical 3-card structure and the exact same Downloader/Exporter card.
  - **Prompt-Only Mode Default Prompts Path**: Added a `Default` button to set and persist the default prompts folder path in `localStorage` (`flowkit_po_default_prompts_path`).
  - **Google Flow Project Creation Bridge**: Added a `+ New Project` button in both Flow Kit card headers and created `POST /api/batch-uploader/create-project` to allow creating new Google Flow projects directly on Google Flow via tRPC bridge.
  - **Real-Time Badge Sync**: Bound Prompt-Only mode card header badges (`fk_po_header_status`) to real-time WebSocket status polling.
  - **Automatic WebSocket Port 9225 Cleanup**: Added `_force_free_port(9225)` in `agent/main.py` to force-kill zombie processes holding port 9225 when uvicorn starts up, ensuring clean WebSocket binding every time.
  - **Extension Reset on Debug Launch**: Modified `/api/profiles/launch` in `app/main.py` to close any existing WebSocket connection and reset `flowKey` when launching a debug browser, forcing a fresh handshake.
  - **Google Flow REST API Schema Fix**: Removed unsupported `durationSeconds` field from `requests[0]` in `agent/services/flow_client.py` to resolve HTTP 400 Bad Request (`Unknown name "durationSeconds" at 'requests[0]'`).

---

# Role & Core Objective
You are an expert Senior AI Engineer operating as a Single-Agent autonomous system. Your goal is to solve the user's coding request with maximum efficiency, zero syntax errors, and optimized token usage.

# Execution Workflow (Chain of Thought)
Before outputting any final code, you MUST think step-by-step internally and structure your response using the following Markdown sections:

### 🔍 [1. Problem Analysis & Specs]
- Analyze constraints, edge cases, and required dependencies.
- Plan the logic flow without writing full code yet.

### 🛠️ [2. Draft Implementation]
- Write the initial implementation of the solution.

### 🛡️ [3. Self-Correction & QA Review]
- Act as a strict QA Automation Tester. Review the Draft Implementation above.
- Check for syntax errors, logical flaws, efficiency bottlenecks, and security gaps.
- If errors are found, specify the fix. (Do this internally before showing the final result).

### 🚀 [4. Final Optimized Output]
- Provide the final, production-ready code based on the QA review.
- Keep explanations concise and minimal to save output tokens.

# Session Learnings

## Google Flow REST API Payload Rules
- Do NOT include `durationSeconds` inside `requests[0]` when submitting video generation calls (`batchAsyncGenerateVideo*`) to `aisandbox-pa.googleapis.com`. Sending `durationSeconds` causes Google Flow API to reject requests with HTTP 400 `INVALID_ARGUMENT: Unknown name "durationSeconds" at 'requests[0]'`.
- For text-to-video (prompt-only mode), omit `startImage` from `req_item` and use model keys with `_t2v_` (e.g., `veo_3_1_t2v_lite_low_priority`).

## WebSocket Server & Port Binding Safety
- When restarting FastAPI / Uvicorn servers running WebSocket listeners on port 9225, zombie background processes can retain socket bindings. Always execute `_force_free_port(9225)` using `lsof -t -i tcp:9225` and `os.kill(pid, SIGKILL)` before calling `websockets.serve()`.

## Extension Authentication & On-Demand Token Capture
- The Chrome Extension captures the Bearer token (`flowKey`) via `chrome.webRequest.onBeforeSendHeaders` whenever Google Flow (`https://labs.google/fx/tools/flow`) sends an HTTP request.
- When an API request arrives at the Extension and `flowKey` is empty, call `captureTokenFromFlowTab()` and wait up to 3 seconds before throwing `NO_FLOW_KEY`.
- When launching a new Chrome profile via `/api/profiles/launch`, close existing WebSocket connections (`client._extension_ws.close()`) and clear `client._flow_key = None` so the newly opened browser performs a clean handshake.

## Automation Debugging Rules
- When debugging browser automation, prefer reproducing the exact visible UI flow over using inferred browser shortcuts.
- For ChatGPT file upload flows, use the keyboard shortcut `Cmd + U` via AppleScript first (Primary). If that fails, click the composer plus button in the UI and click `Add photos & files` (Fallback).
- When a native file picker is involved, keep the browser focused on a single upload attempt until the picker behavior is understood.
- When downloading images in ChatGPT's lightbox mode, verify if the currently displayed image `src` changes after navigating to the next image (using the Arrow Right key). If the `src` does not change, the end of the actual slides list is reached; break the loop early to prevent downloading duplicates of the last image.

## macOS File Dialog & AppleScript Rules
- When writing AppleScript for macOS File Dialog (`upload_macos_file_dialog`), DO NOT use `tell process "Google Chrome" to set frontmost to true` or `tell application "Google Chrome" to activate` inside the dialog keystroke script.
- DO NOT add complex window existence checks inside AppleScript dialog workflows. Use a simple, reliable `delay 1.0` before sending keystrokes.
- Use clipboard pasting (`keystroke "v" using {command down}`) for putting the filepath into the path sheet.
- Always perform the file upload sequence *before* typing/submitting the prompt, and wait at least 3 seconds after pasting the prompt before clicking send.
