#!/usr/bin/env python3
"""
FlowKit Headless Video Generator CLI
Generates video from storyboard images in Google Flow completely in the background without manual browser UI clicks.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any

DEFAULT_API_BASE = "http://127.0.0.1:6969"
DEFAULT_PROJECT_ID = "21a1632e-9926-46fa-954c-240d71d78f41"  # "ละคร"
DEFAULT_TIMEOUT = 600  # 10 minutes max per video

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def error_exit(msg: str, code: int = 1):
    print(f"\n[ERROR] {msg}", file=sys.stderr, flush=True)
    raise RuntimeError(msg)

def http_get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_post(url: str, data: dict, timeout: int = 45) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def inspect_tab_js(api_base: str, js_code: str, timeout: int = 25) -> Any:
    """Executes arbitrary JavaScript inside the active Google Flow tab via FlowKit extension."""
    encoded = urllib.parse.quote(js_code)
    url = f"{api_base}/api/flow/inspect-tab?js={encoded}"
    res = http_get(url, timeout=timeout)
    script_res = res.get("result", {}).get("res", {})
    if not script_res.get("success"):
        err = script_res.get("error") or "inspect_tab script failed"
        raise RuntimeError(f"Browser script error: {err}")
    return script_res.get("result")

def check_and_ensure_server(api_base: str, repo_dir: Optional[str] = None) -> bool:
    """Verifies that the Cockpit/FlowKit server is running. If not, attempts to start it."""
    log(f"Checking FlowKit server at {api_base}...")
    try:
        data = http_get(f"{api_base}/health", timeout=5)
        if data.get("status") == "ok":
            log("FlowKit server is online and responding.")
            return True
    except Exception:
        pass

    log("FlowKit server is not reachable. Attempting auto-start...")
    target_repo = repo_dir or "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"
    runserver_script = os.path.join(target_repo, "runserver.command")
    if os.path.isfile(runserver_script):
        subprocess.Popen([runserver_script], cwd=target_repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for i in range(12):
            time.sleep(2)
            try:
                data = http_get(f"{api_base}/health", timeout=5)
                if data.get("status") == "ok":
                    log("FlowKit server started successfully.")
                    return True
            except Exception:
                continue

    error_exit(f"Cannot connect to FlowKit server at {api_base}. Please start runserver.command.")
    return False

def verify_extension_connection(api_base: str, project_id: str = DEFAULT_PROJECT_ID):
    """Verifies that the Chrome extension is connected via WebSocket.
    If not connected, automatically opens Google Flow in Google Chrome and waits."""
    for _ in range(3):
        try:
            status = http_get(f"{api_base}/api/flow/status", timeout=5)
            if status.get("connected"):
                log("Chrome FlowKit extension is CONNECTED.")
                return True
        except Exception:
            pass
        time.sleep(1.0)

    log("FlowKit Chrome extension not detected. Opening Google Flow in Chrome...")
    flow_url = f"https://flow.google.com/u/1/project/{project_id}"
    try:
        subprocess.Popen(["open", "-a", "Google Chrome", flow_url])
    except Exception as e:
        log(f"Warning: Failed to launch Google Chrome: {e}")

    log("Waiting for FlowKit extension WebSocket connection (up to 30s)...")
    for _ in range(15):
        time.sleep(2)
        try:
            status = http_get(f"{api_base}/api/flow/status", timeout=5)
            if status.get("connected"):
                log("Chrome FlowKit extension is CONNECTED.")
                return True
        except Exception:
            pass

    error_exit("FlowKit Chrome extension is not connected! Ensure Google Chrome is running with the Flow tab open.")

def verify_account_and_project(api_base: str, project_id: str = DEFAULT_PROJECT_ID, expected_email: str = "dogmoneyplan@gmail.com"):
    """Verifies that Chrome is logged into the expected Google account and open to the correct project."""
    log("Verifying Google account and project in Google Chrome...")
    js = """(() => {
        const profileBtn = document.querySelector('a[aria-label*="Google Account"], button[aria-label*="Google Account"], a[aria-label*="บัญชี Google"], button[aria-label*="บัญชี Google"]');
        const ariaText = profileBtn ? profileBtn.getAttribute('aria-label') : '';
        return {
            url: window.location.href,
            title: document.title,
            accountAria: ariaText
        };
    })()"""
    try:
        info = inspect_tab_js(api_base, js)
        url = info.get("url", "")
        account_aria = info.get("accountAria", "")

        if expected_email and expected_email.lower() not in account_aria.lower():
            log(f"WARNING: Current Google account might not be {expected_email} (found: '{account_aria}'). Please ensure you are logged into {expected_email}.")
        else:
            log(f"Google Account verified: {expected_email}")

        if project_id not in url:
            log(f"Current page ({url}) is not project {project_id}. Navigating...")
            nav_js = f"window.location.href = 'https://flow.google.com/u/1/project/{project_id}';"
            inspect_tab_js(api_base, nav_js)
            time.sleep(4)
        else:
            log(f"Project verified: {project_id} (ละคร)")
    except Exception as e:
        log(f"Notice during account/project verification: {e}")

def load_full_prompt(raw_prompt: str) -> str:
    """Returns the full animation prompt text verbatim without stripping headers, dialogue, or negative clauses."""
    return raw_prompt.strip()

def sanitize_prompt(raw_prompt: str) -> str:
    """Returns full prompt verbatim to preserve all dialogue and cinematic instructions."""
    return load_full_prompt(raw_prompt)


def upload_storyboard_image(api_base: str, image_path: str, project_id: str) -> str:
    """Uploads storyboard image to Google Flow library and returns media_id."""
    log(f"Uploading image to Google Flow: {os.path.basename(image_path)}...")
    res = http_post(f"{api_base}/api/flow/upload-image", {
        "file_path": os.path.abspath(image_path),
        "project_id": project_id,
        "file_name": os.path.basename(image_path)
    })
    media_id = res.get("media_id") or res.get("raw", {}).get("media", {}).get("name")
    if not media_id:
        error_exit(f"Failed to upload image: {res}")
    log(f"Uploaded successfully! Media ID: {media_id}")
    return media_id

def attach_start_frame(api_base: str, file_name: str, project_id: str = None) -> bool:
    """Attaches the uploaded storyboard image into the Google Flow prompt box."""
    log(f"Attaching {file_name} into Google Flow prompt box...")

    # 1. Clear any old chips and prompt text
    clear_js = """(() => {
        const chips = Array.from(document.querySelectorAll('flow-prompt-box flow-image-ingredient-chip, flow-prompt-box .chip-container'));
        for (const chip of chips) {
            const cancelBtn = chip.querySelector('.hover-icon-overlay, mat-icon, button') || chip;
            cancelBtn.click();
        }
        const pm = document.querySelector('.ProseMirror');
        if (pm) pm.innerText = '';
        return true;
    })()"""
    inspect_tab_js(api_base, clear_js)
    time.sleep(0.5)

    # 2. Click "เพิ่มองค์ประกอบลงในช่องพรอมต์" (button.add-menu-trigger)
    open_js = """(() => {
        const trigger = document.querySelector('button.add-menu-trigger') ||
                        document.querySelector('button[aria-label*="เพิ่มองค์ประกอบ"]');
        if (!trigger) return { error: "add-menu-trigger button not found" };
        trigger.click();
        return { ok: true };
    })()"""
    res_open = inspect_tab_js(api_base, open_js)
    if res_open.get("error"):
        error_exit(f"Failed to open add element menu: {res_open.get('error')}")
    time.sleep(1.0)

    # 3. Filter to "รูปภาพ" in sidebar
    filter_js = """(() => {
        const popover = document.querySelector('flow-add-menu-popover-content');
        if (!popover) return { error: "popover not found" };
        const navItems = Array.from(popover.querySelectorAll('mat-list-item, .mat-mdc-list-item'));
        const imgNav = navItems.find(el => (el.innerText || '').includes('รูปภาพ') || (el.innerText || '').toLowerCase().includes('image'));
        if (imgNav) {
            imgNav.click();
            return { ok: true };
        }
        return { error: "รูปภาพ filter item not found" };
    })()"""
    inspect_tab_js(api_base, filter_js)
    time.sleep(0.8)

    # 3.5 Use search input box to filter directly to target filename
    search_js = f"""(() => {{
        const popover = document.querySelector('flow-add-menu-popover-content');
        if (!popover) return false;
        const searchInput = popover.querySelector('input.search-input');
        if (searchInput) {{
            searchInput.value = "{file_name}";
            searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            searchInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }}
        return false;
    }})()"""
    inspect_tab_js(api_base, search_js)
    time.sleep(0.4)

    # 4. Click matching image asset item
    click_item_js = f"""(() => {{
        const targetName = "{file_name}";
        const targetBase = "{os.path.splitext(file_name)[0]}";
        const popover = document.querySelector('flow-add-menu-popover-content');
        if (!popover) return {{ error: "popover not found" }};
        const items = Array.from(popover.querySelectorAll('button.asset-item, flow-add-menu-asset-item, .asset-item'));
        
        let target = items.find(el => {{
            const t = el.innerText || '';
            return t.includes(targetName) || t.includes(targetBase);
        }}) || items[0];

        if (target) {{
            const btn = target.querySelector('button') || target;
            btn.click();
            return {{ ok: true, text: target.innerText.replace(/\\s+/g, ' ').trim() }};
        }}
        return {{ error: `Could not find asset item for ${{targetName}}` }};
    }})()"""
    res_click = inspect_tab_js(api_base, click_item_js)
    if res_click.get("error"):
        log(f"Asset item '{file_name}' not found on first attempt, retrying search without reload...")
        try:
            time.sleep(1.0)
            inspect_tab_js(api_base, search_js)
            time.sleep(0.8)
            res_click = inspect_tab_js(api_base, click_item_js)
        except Exception as e:
            log(f"Notice during retry: {e}")

    if res_click.get("error"):
        error_exit(f"Failed to select image asset: {res_click.get('error')}")
    time.sleep(0.8)

    # 5. Click "เพิ่มไปยังพรอมต์" in detail pane if present
    add_btn_js = """(() => {
        const addBtn = document.querySelector('flow-add-menu-detail-pane button.detail-add-to-prompt-btn') ||
                       Array.from(document.querySelectorAll('.cdk-overlay-container button')).find(b => (b.innerText || '').includes('เพิ่มไปยังพรอมต์'));
        if (addBtn) {
            addBtn.click();
            return { clicked: true };
        }
        return { clicked: false };
    })()"""
    inspect_tab_js(api_base, add_btn_js)
    time.sleep(1.0)

    # 6. Close backdrop if open
    close_js = """(() => {
        const backdrop = document.querySelector('.cdk-overlay-backdrop');
        if (backdrop) backdrop.click();
        return true;
    })()"""
    inspect_tab_js(api_base, close_js)
    time.sleep(0.5)

    # 7. STRICT VERIFICATION: ensure image chip is in flow-prompt-box
    verify_js = """(() => {
        const promptBox = document.querySelector('flow-prompt-box');
        if (!promptBox) return false;
        const chip = promptBox.querySelector('img.chip-image, flow-image-ingredient-chip img');
        return !!chip;
    })()"""
    attached = inspect_tab_js(api_base, verify_js)
    if not attached:
        error_exit(f"CRITICAL: Failed to attach storyboard image {file_name} into prompt box! Verification failed.")

    log(f"Successfully attached {file_name} into prompt box (image chip verified present).")
    return True

select_storyboard_image_chip = attach_start_frame


def set_aspect_ratio(api_base: str, aspect: str = "16:9") -> bool:
    """Sets video aspect ratio to 16:9 or 9:16 in Google Flow settings overlay."""
    is_landscape = (aspect == "16:9" or "landscape" in aspect.lower())
    target_crop = "crop_16_9" if is_landscape else "crop_9_16"
    target_label = "16:9" if is_landscape else "9:16"
    
    log(f"Setting aspect ratio to {target_label}...")
    set_aspect_js = f"""(() => {{
        const settingsBtn = document.querySelector(".settings-trigger-button") ||
                            document.querySelector('button[aria-label="ทริกเกอร์การตั้งค่า"]');
        if (!settingsBtn) return {{ error: "Settings button not found" }};
        
        const currentText = settingsBtn.innerText || '';
        if (currentText.includes("{target_crop}")) {{
            return {{ alreadySet: true }};
        }}

        settingsBtn.click();
        return {{ opened: true }};
    }})()"""
    
    res = inspect_tab_js(api_base, set_aspect_js)
    if res.get("opened"):
        time.sleep(0.8)
        toggle_js = f"""(() => {{
            const overlay = document.querySelector(".cdk-overlay-container");
            const toggles = Array.from(overlay.querySelectorAll("mat-button-toggle, button, [role='radio']"));
            const target = toggles.find(t => t.innerText?.includes("{target_label}"));
            if (target) {{
                const btn = target.querySelector("button") || target;
                btn.click();
            }}
            const backdrop = document.querySelector(".cdk-overlay-backdrop");
            if (backdrop) backdrop.click();
            return true;
        }})()"""
        inspect_tab_js(api_base, toggle_js)
        time.sleep(0.5)

    log(f"Aspect ratio {target_label} configured.")
    return True

def submit_prompt_and_generate(api_base: str, prompt: str, aspect: str = "16:9") -> bool:
    """Types prompt and triggers generation using FlowKit CDP endpoint."""
    log("Typing prompt into ProseMirror and clicking generate...")
    res = http_post(f"{api_base}/api/flow/cdp-type-text", {
        "text": prompt,
        "click_submit": True,
        "output_count": 1,
        "aspect_ratio": aspect
    })
    
    result_data = res.get("result", {})
    if not result_data.get("clicked"):
        error_exit(f"Failed to submit prompt to Google Flow: {res}")
    log("Generation submitted successfully to Google Flow!")
    return True

def get_existing_video_ids(api_base: str) -> list[str]:
    """Retrieves list of existing video media IDs currently in the Google Flow DOM."""
    js = """(() => {
        const videoTiles = Array.from(document.querySelectorAll('flow-video-tile'));
        const ids = [];
        for (const vt of videoTiles) {
            const img = vt.querySelector('img.thumbnail, img');
            if (img && img.src && img.src.includes('/image/')) {
                const match = img.src.match(/\\/image\\/([0-9a-fA-F-]+)/);
                if (match) ids.push(match[1]);
            }
        }
        return ids;
    })()"""
    try:
        return inspect_tab_js(api_base, js) or []
    except Exception:
        return []

def monitor_video_rendering(api_base: str, prompt_snippet: str, timeout_seconds: int = DEFAULT_TIMEOUT, initial_ids: Optional[list[str]] = None) -> str:
    """Monitors Google Flow tiles until rendering reaches 100% and returns the generated video Media ID."""
    log("Monitoring video rendering in Google Flow...")
    start_time = time.time()
    last_pct = ""
    seen_ids = set(initial_ids or [])

    monitor_js = """(() => {
        // Check pending progress %
        const tiles = Array.from(document.querySelectorAll('.tiles-container, flow-pending-tile, [class*="tile"]'));
        let pct = null;
        let failureText = null;
        for (const t of tiles) {
            const text = t.innerText || '';
            const m = text.match(/(\\d+)%/);
            if (m) { pct = m[1] + '%'; }
            if (text.includes('ล้มเหลว') || text.includes('Failed') || text.includes('ละเมิดนโยบาย')) {
                failureText = text.replace(/\\s+/g, ' ').trim().slice(0, 150);
            }
        }

        // Check video tiles
        const videoTiles = Array.from(document.querySelectorAll('flow-video-tile'));
        const completedIds = [];
        for (const vt of videoTiles) {
            const img = vt.querySelector('img.thumbnail, img');
            if (img && img.src && img.src.includes('/image/')) {
                const match = img.src.match(/\\/image\\/([0-9a-fA-F-]+)/);
                if (match) completedIds.push(match[1]);
            }
        }

        return {
            pct,
            failureText,
            completedIds,
            isRendering: !!pct
        };
    })()"""

    while time.time() - start_time < timeout_seconds:
        status = inspect_tab_js(api_base, monitor_js)
        pct = status.get("pct")
        if pct and pct != last_pct:
            log(f"  Rendering in progress: {pct}")
            last_pct = pct

        completed_ids = status.get("completedIds") or []
        new_ids = [cid for cid in completed_ids if cid not in seen_ids]

        if new_ids and not status.get("isRendering"):
            log(f"Rendering complete! Found {len(new_ids)} video candidate(s): {new_ids}")
            return new_ids

        if not initial_ids and completed_ids and not status.get("isRendering"):
            log(f"Rendering complete! Found {len(completed_ids)} video candidate(s): {completed_ids[:2]}")
            return completed_ids[:2]

        failure_text = status.get("failureText")
        if failure_text and not status.get("isRendering") and (time.time() - start_time > 20):
            error_exit(f"Google Flow video rendering failed: {failure_text}")

        time.sleep(4)

    error_exit(f"Timed out after {timeout_seconds}s waiting for video rendering.")
    return []

def retrieve_signed_video_url(api_base: str, media_id: str) -> str:
    """Executes as29s batchexecute RPC to obtain the signed CDN video URL."""
    log(f"Retrieving signed CDN MP4 URL for media {media_id}...")
    rpc_js = """(async () => {
        const wiz = globalThis.WIZ_global_data || {};
        const at = wiz.SNlM0e;
        const sid = wiz.FdrFJe;
        const bl = wiz.cfb2h;
        const reqid = Math.floor(Math.random() * 900000) + 100000;
        const prefix = (window.location.pathname.match(/^\\/u\\/\\d+/) || [""])[0];
        const freqStr = JSON.stringify([[["as29s", JSON.stringify(["__MEDIA_ID__"]), null, "generic"]]]);
        const url = `${prefix}/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=as29s&source-path=${encodeURIComponent(window.location.pathname)}&f.sid=${encodeURIComponent(sid || "")}&bl=${encodeURIComponent(bl || "")}&_reqid=${reqid}&rt=c`;
        const resp = await fetch(url, {
            method: "POST",
            credentials: "include",
            headers: { "content-type": "application/x-www-form-urlencoded;charset=UTF-8", "x-same-domain": "1" },
            body: new URLSearchParams({ "f.req": freqStr, at })
        });
        const text = await resp.text();
        const lines = text.split("\\n");
        for (const line of lines) {
            if (!line.trim() || line.startsWith(")]}'")) continue;
            try {
                const parsed = JSON.parse(line);
                if (Array.isArray(parsed)) {
                    for (const item of parsed) {
                        if (item && item[1] === "as29s" && typeof item[2] === "string") {
                            const inner = JSON.parse(item[2]);
                            function findVideoUrl(obj) {
                                if (typeof obj === "string" && obj.startsWith("https://flow-content.google/video/")) {
                                    return obj;
                                }
                                if (Array.isArray(obj)) {
                                    for (const x of obj) {
                                        const res = findVideoUrl(x);
                                        if (res) return res;
                                    }
                                }
                                return null;
                            }
                            const found = findVideoUrl(inner);
                            if (found) return found;
                        }
                    }
                }
            } catch (e) {}
        }
        return null;
    })()""".replace("__MEDIA_ID__", media_id)

    for attempt in range(8):
        video_url = inspect_tab_js(api_base, rpc_js)
        if video_url:
            log(f"Signed CDN Video URL obtained successfully: {video_url[:80]}...")
            return video_url
        time.sleep(2)

    error_exit(f"Failed to retrieve signed CDN video URL for media ID: {media_id}")
    return ""

def download_video(video_url: str, output_path: str) -> int:
    """Downloads the MP4 video to the target filesystem path."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    log(f"Downloading MP4 to: {output_path}...")
    req = urllib.request.Request(video_url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://flow.google.com/'
    })
    with urllib.request.urlopen(req) as resp, open(output_path, 'wb') as f:
        f.write(resp.read())
    size_bytes = os.path.getsize(output_path)
    log(f"Download complete! File size: {size_bytes:,} bytes ({size_bytes / (1024*1024):.2f} MB)")
    return size_bytes

def dispatch_video_flow(
    image_path: str,
    prompt: str,
    api_base: str = DEFAULT_API_BASE,
    project_id: str = DEFAULT_PROJECT_ID,
    aspect_ratio: str = "9:16",
    wait_after_submit: float = 3.0
) -> bool:
    """Dispatches a single video prompt to Google Flow queue with storyboard image attached as start frame."""
    file_name = os.path.basename(image_path)
    clean_prompt = sanitize_prompt(prompt)

    # 1. Environment & Server checks
    check_and_ensure_server(api_base)
    verify_extension_connection(api_base, project_id=project_id)
    verify_account_and_project(api_base, project_id=project_id, expected_email="dogmoneyplan@gmail.com")

    # 2. Attach storyboard image as start frame chip
    select_storyboard_image_chip(api_base, file_name, project_id=project_id)
    time.sleep(0.5)

    # 3. Configure aspect ratio
    set_aspect_ratio(api_base, aspect=aspect_ratio)
    time.sleep(0.5)

    # 4. Submit prompt via CDP
    submit_prompt_and_generate(api_base, clean_prompt, aspect=aspect_ratio)

    # 5. Wait brief delay for Google Flow to queue the video pending tile
    if wait_after_submit > 0:
        time.sleep(wait_after_submit)

    return True

def _match_video_tiles_to_scenes(scenes: list, new_tiles: list) -> list:
    """Matches newly generated video tiles to scene items using keyword scoring + reverse submission order."""
    N = len(scenes)
    M = len(new_tiles)
    if M == 0 or N == 0:
        return []

    boilerplate_words = {
        "video", "animation", "cinematic", "motion", "render", "style", "pixar",
        "smooth", "cute", "camera", "movement", "slow", "pan", "zoom", "subtle"
    }

    scores = []
    for i, sc in enumerate(scenes):
        sc_prompt = sc.get("prompt", "")
        sc_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", sc_prompt.lower())) - boilerplate_words
        row = []
        for j, tl in enumerate(new_tiles):
            tl_footer = tl.get("footer_title", "")
            tl_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", tl_footer.lower()))
            overlap = len(sc_words.intersection(tl_words))
            expected_j = max(0, min(M - 1, N - 1 - i))
            pos_penalty = abs(j - expected_j) * 0.5
            total_score = overlap * 10 - pos_penalty
            row.append(total_score)
        scores.append(row)

    candidates = []
    for i in range(N):
        for j in range(M):
            candidates.append((scores[i][j], i, j))
    candidates.sort(reverse=True, key=lambda x: x[0])

    matched = []
    used_scenes = set()
    used_tiles = set()
    for score, i, j in candidates:
        if i not in used_scenes and j not in used_tiles:
            matched.append((scenes[i], new_tiles[j]))
            used_scenes.add(i)
            used_tiles.add(j)

    return matched

def monitor_video_batch(
    api_base: str,
    batch_scenes: list,
    timeout_seconds: int = 600,
    initial_ids: Optional[list] = None
) -> list:
    """Monitors Google Flow until all pending videos in the batch finish and returns matched results."""
    log(f"Monitoring Google Flow batch video rendering for {len(batch_scenes)} scenes...")
    start_time = time.time()
    seen_ids = set(initial_ids or [])
    last_pct = ""

    monitor_js = """(() => {
        const pending = Array.from(document.querySelectorAll('.tiles-container, flow-pending-tile, [class*="pending-tile"], [class*="pending"]'));
        let pcts = [];
        let failureText = null;
        for (const t of pending) {
            const text = t.innerText || '';
            const m = text.match(/(\\d+)%/);
            if (m) pcts.push(m[1] + '%');
            if (text.includes('ล้มเหลว') || text.includes('Failed') || text.includes('ละเมิดนโยบาย')) {
                failureText = text.replace(/\\s+/g, ' ').trim().slice(0, 150);
            }
        }

        const videoTiles = Array.from(document.querySelectorAll('flow-video-tile'));
        const tileData = [];
        for (const vt of videoTiles) {
            const img = vt.querySelector('img.thumbnail, img');
            const footer = vt.querySelector('.footer-title');
            let mid = null;
            if (img && img.src) {
                const match = img.src.match(/\\/image\\/([0-9a-fA-F-]+)/);
                if (match) mid = match[1];
            }
            if (mid) {
                tileData.push({
                    media_id: mid,
                    footer_title: footer ? footer.innerText.replace(/\\s+/g, ' ').trim() : ''
                });
            }
        }

        return {
            pendingCount: pending.length,
            pcts: pcts,
            failureText: failureText,
            tiles: tileData,
            isRendering: pending.length > 0
        };
    })()"""

    consecutive_zero_pending = 0
    poll_status = {}

    while time.time() - start_time < timeout_seconds:
        poll_status = inspect_tab_js(api_base, monitor_js) or {}
        pcts = poll_status.get("pcts") or []
        pending_count = poll_status.get("pendingCount", 0)
        failure_text = poll_status.get("failureText")
        tiles = poll_status.get("tiles") or []

        if pcts and str(pcts) != last_pct:
            log(f"  Rendering in progress: {', '.join(pcts[:5])} ({pending_count} pending)")
            last_pct = str(pcts)

        new_tiles = [t for t in tiles if t["media_id"] not in seen_ids]

        if not poll_status.get("isRendering"):
            consecutive_zero_pending += 1
            if len(new_tiles) >= len(batch_scenes) or consecutive_zero_pending >= 2:
                log(f"All {len(new_tiles)} video(s) completed rendering!")
                break
        else:
            consecutive_zero_pending = 0

        if failure_text and (time.time() - start_time > 30):
            log(f"Warning: failure text detected: {failure_text}")

        time.sleep(5)

    tiles = poll_status.get("tiles") or []
    new_tiles = [t for t in tiles if t["media_id"] not in seen_ids]

    matched = _match_video_tiles_to_scenes(batch_scenes, new_tiles)
    return matched

def generate_video_flow(
    image_path: str,
    prompt: str,
    output_path: str,
    api_base: str = DEFAULT_API_BASE,
    project_id: str = DEFAULT_PROJECT_ID,
    aspect_ratio: str = "16:9",
    skip_upload: bool = False
) -> Dict[str, Any]:
    """Complete end-to-end headless video generation pipeline."""
    log("==================================================")
    log(" FlowKit Headless Video Generation Started")
    log("==================================================")
    log(f"Source Image: {image_path}")
    log(f"Target Output: {output_path}")
    log(f"Aspect Ratio: {aspect_ratio}")
    log(f"Prompt: {prompt}")

    # 1. Environment & Server checks
    check_and_ensure_server(api_base)
    verify_extension_connection(api_base, project_id=project_id)
    verify_account_and_project(api_base, project_id=project_id, expected_email="dogmoneyplan@gmail.com")

    # 2. Upload Image (skip if pre-uploaded in batch)
    file_name = os.path.basename(image_path)
    if not skip_upload:
        upload_storyboard_image(api_base, image_path, project_id)

    # 3. Attach Start Frame (with auto-fallback if skipped upload wasn't found)
    try:
        attach_start_frame(api_base, file_name)
    except Exception as e:
        if skip_upload:
            log(f"Notice: Asset not found in library directly ({e}). Uploading fallback...")
            upload_storyboard_image(api_base, image_path, project_id)
            attach_start_frame(api_base, file_name)
        else:
            raise

    # 4. Configure Aspect Ratio
    set_aspect_ratio(api_base, aspect_ratio)

    # 5. Snapshot current video IDs before triggering new generation
    initial_ids = get_existing_video_ids(api_base)


    # 6. Submit Prompt via CDP
    submit_prompt_and_generate(api_base, prompt, aspect_ratio)

    # 7. Monitor Rendering
    media_res = monitor_video_rendering(api_base, prompt, initial_ids=initial_ids)
    if isinstance(media_res, list):
        primary_id = media_res[0] if media_res else ""
        candidate_ids = media_res
    else:
        primary_id = media_res
        candidate_ids = [media_res] if media_res else []

    if not primary_id:
        error_exit("No video media ID was produced by Google Flow.")

    # 8. Download Candidate 1 (Primary File -> main scene output and _v1 copy)
    video_url_1 = retrieve_signed_video_url(api_base, primary_id)
    file_size_1 = download_video(video_url_1, output_path)

    # Save pair copy as _v1
    base_no_ext, ext = os.path.splitext(output_path)
    v1_path = f"{base_no_ext}_v1{ext}"
    try:
        shutil.copyfile(output_path, v1_path)
        log(f"Saved Candidate 1 pair copy: {os.path.basename(v1_path)}")
    except Exception as e:
        log(f"Notice copying v1: {e}")

    # 9. Download Candidate 2 (Secondary File -> _v2 pair) if present
    v2_size = 0
    v2_path = f"{base_no_ext}_v2{ext}"
    if len(candidate_ids) > 1:
        cand2_id = candidate_ids[1]
        try:
            log(f"Downloading Candidate 2 pair -> {os.path.basename(v2_path)}...")
            video_url_2 = retrieve_signed_video_url(api_base, cand2_id)
            v2_size = download_video(video_url_2, v2_path)
            log(f"Saved Candidate 2 pair: {os.path.basename(v2_path)} ({v2_size:,} bytes)")
        except Exception as e:
            log(f"Notice on downloading Candidate 2: {e}")

    log("==================================================")
    log(" Video Generation Successfully Finished 100%!")
    log(f" Primary Timeline File (Candidate 1): {os.path.basename(output_path)}")
    if v2_size > 0:
        log(f" Alternate Pair File (Candidate 2): {os.path.basename(v2_path)}")
    log("==================================================")

    return {
        "success": True,
        "media_id": primary_id,
        "media_ids": candidate_ids,
        "video_url": video_url_1,
        "output_path": output_path,
        "file_size_bytes": file_size_1,
        "candidate_pair": True if v2_size > 0 else False
    }

def main():
    parser = argparse.ArgumentParser(description="Headless Google Flow Video Generator via FlowKit")
    parser.add_argument("--story-path", "-s", type=str, help="Root path of the Lakorn story folder (e.g. .../Channels/2 - ผักกาดการละคร - ละครไทย/21)")
    parser.add_argument("--ep", "-e", type=str, default="1", help="Episode number (e.g. 1 or EP01)")
    parser.add_argument("--scene", "-sc", type=str, default="1", help="Scene number (e.g. 1 or Scene 01)")
    parser.add_argument("--image-path", "-i", type=str, help="Direct path to storyboard image file")
    parser.add_argument("--prompt", "-p", type=str, help="Animation prompt text (if omitted, reads from Animation Prompt folder)")
    parser.add_argument("--prompt-dir", type=str, help="Directory containing animation prompt markdown files")
    parser.add_argument("--output-path", "-o", type=str, help="Direct path for the destination MP4 file")
    parser.add_argument("--aspect-ratio", "-a", type=str, default="16:9", choices=["16:9", "9:16"], help="Aspect ratio (16:9 landscape or 9:16 portrait)")
    parser.add_argument("--project-id", type=str, default=DEFAULT_PROJECT_ID, help="Google Flow project ID")
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE, help="FlowKit API base URL")

    args = parser.parse_args()

    # Normalize ep and scene numbers
    ep_num = int(re.search(r'\d+', args.ep).group(0)) if re.search(r'\d+', args.ep) else 1
    sc_num = int(re.search(r'\d+', args.scene).group(0)) if re.search(r'\d+', args.scene) else 1
    ep_str = f"EP{ep_num:02d}"
    sc_str = f"{sc_num:02d} - Scene {sc_num:02d}"

    # Determine image path
    image_path = args.image_path
    if not image_path and args.story_path:
        sb_dir = os.path.join(args.story_path, "6 - Storyboards", ep_str)
        candidates = [
            os.path.join(sb_dir, f"{ep_str} - Scene {args.scene:02d}.jpg"),
            os.path.join(sb_dir, f"{ep_str} - Scene {args.scene:02d}.png"),
            os.path.join(sb_dir, f"{ep_str} - Scene {args.scene:02d}.jpeg"),
            os.path.join(sb_dir, f"{ep_str} - {sc_str}.jpg"),
            os.path.join(sb_dir, f"{ep_str} - {sc_str}.png"),
            os.path.join(sb_dir, f"{ep_str} - {sc_str}.jpeg"),
            os.path.join(sb_dir, f"{sc_str}.jpg"),
            os.path.join(sb_dir, f"{sc_str}.png"),
            os.path.join(sb_dir, f"{sc_str}.jpeg")
        ]
        for c in candidates:
            if os.path.isfile(c):
                image_path = c
                break

    if not image_path or not os.path.isfile(image_path):
        error_exit(f"Storyboard image not found: {image_path}. Please specify valid --image-path or --story-path.")

    # Determine prompt
    prompt = args.prompt
    if not prompt:
        prompt_dir = args.prompt_dir or (os.path.join(args.story_path, "4 - Animation Prompt") if args.story_path else None)
        if prompt_dir:
            candidates = [
                os.path.join(prompt_dir, ep_str, f"{sc_str}.md"),
                os.path.join(prompt_dir, f"{sc_str}.md")
            ]
            for c in candidates:
                if os.path.isfile(c):
                    with open(c, "r", encoding="utf-8") as f:
                        prompt = sanitize_prompt(f.read())
                        log(f"Loaded prompt from file: {c}")
                        break


    if not prompt:
        error_exit("No prompt provided. Please specify --prompt or ensure prompt file exists in story folder.")

    # Determine output path
    output_path = args.output_path
    if not output_path and args.story_path:
        output_path = os.path.join(args.story_path, "7 - Videos", ep_str, f"{sc_str}.mp4")

    if not output_path:
        output_path = f"./output_{sc_str}.mp4"

    res = generate_video_flow(
        image_path=image_path,
        prompt=prompt,
        output_path=output_path,
        api_base=args.api_base,
        project_id=args.project_id,
        aspect_ratio=args.aspect_ratio
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
