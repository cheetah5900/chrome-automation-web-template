# Project Overview & Current Status

This project is a web-based automation controller for managing Google Chrome profiles, launching remote debugging sessions, and running automated workflows (including image/video generation and lakorn media import).

## Key Features
1. **Profile Launching**: Launches Chrome with a specified remote debugging port (default: `9222`) and user data directory. Supports setting up to 3 startup URLs.
2. **Lakorn Import Automation**: Functional scripts to automate lakorn import workflows.
3. **AI Image/Video Generation Automation**:
   - Automates prompt submission in Gemini/ChatGPT/Google Flow.
   - Refined typing sequence for Google Flow video generation: types `@round.png`, selects the mention autocomplete option, enters a `Space`, and uses macOS AppleScript clipboard pasting to enter prompt text without losing editor focus or triggering highlight-all conflicts.
   - Generous typing and mention autocomplete delays (doubled sleeps) to guarantee stable UI loading.
4. **Dynamic Tooltips**:
   - Pure CSS absolute-positioned glassmorphism tooltips added to all 9 functional buttons.
   - Explanations are written in Thai, providing a step-by-step breakdown of delays, key presses, and actions.
   - Tooltip text updates in real-time via JS event listeners whenever UI parameters (active combine sets, intervals, URLs, ports) are changed.

## Project Architecture
- **`app/main.py`**: FastAPI backend exposing endpoints for configuration (`/api/config`), profile launcher (`/api/profiles/launch`), and selenium automation tasks (`/api/step/video-gen`).
- **`app/browser.py`**: Handles Chrome profile processes and subprocess management.
- **`web/index.html`**: Main UI dashboard layout.
- **`web/styles.css`**: Styling dashboard with a modern dark glassmorphism theme and tooltip hover states.
- **`web/app.js`**: Dynamic frontend script that manages API updates, UI events, and builds dynamic tooltip explanations.
- **`config_mac.json`**: Persistence file for active configurations, prompts, and run-statuses.

## Current Runtime Status
- **Backend Server**: Running locally on `http://127.0.0.1:6969`.
- **Chrome Automation Port**: Configured to `9222`.
- **Active Git Branch**: `feat/video-helper-batch-process`.
- **Latest Fixes & Features**:
  - **Force Stop Safety**: Implemented `is_driver_alive` session validation inside all selenium click/upload functions. If Chrome is force-killed, the backend immediately raises an exception and aborts execution, completely preventing AppleScript keystrokes from leaking into other active desktop windows.
  - **Google Flow Optimization**: Modified the video generation workflow to skip settings configuration (ratio, speed, model selection) after the first round has successfully completed, significantly speeding up subsequent rounds.
  - **Close Browser Button**: Added a dedicated button to the Profile Manager UI to close Chrome profiles cleanly.
  - **Delay Optimizations**: Doubled keyboard typing delays for stable autocompletion, and randomized the human simulation delay interval.

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

## Automation Debugging Rules
- When debugging browser automation, prefer reproducing the exact visible UI flow over using inferred browser shortcuts.
- For ChatGPT file upload flows, use the composer plus button first, then click `Add photos & files`, then interact with the native macOS picker.
- Do not rely on `Cmd+U` as a file upload trigger in Chrome debugging flows; treat browser-level shortcuts as potentially conflicting with Chrome features.
- When a native file picker is involved, keep the browser focused on a single upload attempt until the picker behavior is understood.

## Code Path Verification Rules
- When a fix is reported as applied, re-read the exact target code path to confirm the change landed in the intended flow.
- If similar logic exists in multiple places (for example Gemini and ChatGPT flows), verify which branch is actually running before claiming a fix.
- If a temporary debug limiter is needed, place it in the exact active flow being tested, not in a parallel implementation.

## macOS File Dialog & AppleScript Rules
- When writing AppleScript for macOS File Dialog (`upload_macos_file_dialog`), DO NOT use `tell process "Google Chrome" to set frontmost to true` or `tell application "Google Chrome" to activate` inside the dialog keystroke script. This causes Chrome to steal/reset window focus, closing or defocusing the active sheet and causing `Cmd + Shift + G` to fail.
- DO NOT add complex window existence checks (like `exists windows of process "Google Chrome"`) inside the AppleScript dialog workflow. These queries require Accessibility (Assistive device) permissions in macOS, which standard Terminal/Python processes do not have, causing the script to bypass the keystrokes or crash. Use a simple, reliable `delay 1.0` before sending keystrokes instead.
- Use clipboard pasting (`keystroke "v" using {command down}`) for putting the filepath into the path sheet, as it is 10x faster and layout-independent compared to character-by-character typing.
- Always perform the file upload sequence *before* typing/submitting the prompt, and wait at least 3 seconds after pasting the prompt before clicking send.

## Force Stop Handling & Session Validation
- Webdriver commands and AppleScript dialog automation must always verify driver session validity (`is_driver_alive`) before starting or retrying, to prevent sending system key-events to the wrong application if Chrome is closed.
- If the browser session is closed, raise a runtime error immediately to break backend automation loops, letting the frontend know it should stop processing further rounds.

## Google Flow JS & React State Limitations
- DO NOT use JavaScript DOM manipulation (such as modifying `textContent`, `innerHTML`, or appending text nodes) to input text into the Google Flow (React/ProseMirror) prompt editor. Bypassing the React state and ProseMirror models causes the Virtual DOM to get out of sync, breaking the editor's submission state and causing empty or corrupted submissions.
- Always use native Selenium `send_keys` commands to input prompt text into Google Flow, as it simulates native OS-level keyboard events and correctly updates the React and ProseMirror state models.
- When entering multiline prompts via Selenium `send_keys` in Google Flow, DO NOT send raw newlines (`\n`) in one go, as this triggers the browser's default `Enter` event and submits the form prematurely. Instead, split the text by `\n` and use Selenium's `ActionChains` to perform a `Shift + Enter` sequence between lines before typing the next line.

