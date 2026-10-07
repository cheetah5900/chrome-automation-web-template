import asyncio
import os
import logging
from typing import Optional, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from agent.services.flow_client import get_flow_client
from app.env_config import get_repo_dir

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/flow", tags=["flow"])

# Concurrency Lock & Active Task Tracking for Storyboard Rendering
_storyboard_lock = asyncio.Lock()
_storyboard_active_state: dict[str, Any] = {
    "busy": False,
    "project_id": None,
    "started_at": None,
    "prompt": None
}

# Server-side FIFO dispatch order tracker
# Each entry: {"prompt": str, "scene_num": int|None, "output_path": str|None}
# Cleared by the runner per batch session via /clear-dispatch-queue
_dispatch_order_queue: list[dict] = []


async def _check_flow_busy(client, target_project_id: str, allow_same_project_queue: bool = False, max_queue: int = 15) -> Optional[JSONResponse]:
    """Checks both the in-process concurrency lock and the active Chrome tab.
    If either the server is executing another generation or the Google Flow tab has pending tiles rendering,
    returns an HTTP 429 (Too Many Requests / Busy) JSONResponse.
    """
    # 1. In-process Concurrency Lock check
    if _storyboard_lock.locked() or _storyboard_active_state.get("busy"):
        curr_proj = _storyboard_active_state.get("project_id") or target_project_id or ""
        logger.warning("Storyboard Concurrency Lock active (busy with project %s). Returning HTTP 429.", curr_proj)
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "status": "busy",
                "message": "Google Flow is currently busy rendering another task",
                "current_project": curr_proj
            }
        )

    # 2. Chrome Extension Tab check (live DOM check for pending tiles)
    if client and client.connected:
        tab_busy_js = """(() => {
            const pending = Array.from(document.querySelectorAll('flow-pending-tile:not(.fading-out), [class*="pending-tile"]:not(.fading-out)'));
            const url = window.location.href || '';
            const match = url.match(/\\/project\\/([a-zA-Z0-9_-]+)/);
            const currentProject = match ? match[1] : '';
            return {
                isBusy: pending.length > 0,
                pendingCount: pending.length,
                currentProject: currentProject
            };
        })()"""
        try:
            tab_status = await _eval_js_internal(client, tab_busy_js, timeout=4) or {}
            pending_count = tab_status.get("pendingCount", 0)
            current_project = tab_status.get("currentProject", "")

            # If the active tab is on a DIFFERENT project and has pending renders
            if current_project and target_project_id and current_project != target_project_id:
                if pending_count > 0:
                    logger.warning(
                        "Google Flow tab is on project %s with %d pending render(s). Cannot switch to %s. Returning HTTP 429.",
                        current_project, pending_count, target_project_id
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "success": False,
                            "status": "busy",
                            "message": "Google Flow is currently busy rendering another task",
                            "current_project": current_project
                        }
                    )

            if allow_same_project_queue:
                if pending_count >= max_queue:
                    logger.warning("Google Flow queue full (%d pending tiles in project %s). Returning HTTP 429.",
                                   pending_count, current_project)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "success": False,
                            "status": "busy",
                            "message": f"Google Flow render queue is full ({pending_count}/{max_queue})",
                            "current_project": current_project
                        }
                    )
            else:
                if pending_count > 0:
                    curr_proj = current_project or target_project_id or ""
                    logger.warning("Google Flow tab has %d pending tile(s) rendering (project %s). Returning HTTP 429.",
                                   pending_count, curr_proj)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "success": False,
                            "status": "busy",
                            "message": "Google Flow is currently busy rendering another task",
                            "current_project": curr_proj
                        }
                    )
        except Exception as e:
            logger.debug("Non-critical error checking tab busy state: %s", e)

    return None


class GenerateImageRequest(BaseModel):
    prompt: str
    project_id: str
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_PORTRAIT"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"
    character_media_ids: Optional[list[str]] = None


class GenerateImageBatchRequest(BaseModel):
    prompt: str
    project_id: str
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_PORTRAIT"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"
    reference_images: Optional[list[str]] = None
    model_name: str = "GEM_PIX_2"
    quantity: int = 1
    local_path: Optional[str] = ""
    folder_name: Optional[str] = ""
    target_directory: Optional[str] = ""
    round_num: int = 1
    prompt_index: int = 1


class GenerateVideoRequest(BaseModel):
    start_image_media_id: Optional[str] = None
    prompt: str
    project_id: str
    scene_id: str
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT"
    end_image_media_id: Optional[str] = None
    user_paygate_tier: str = "PAYGATE_TIER_ONE"
    custom_model_key: Optional[str] = None
    image_path: Optional[str] = None


class GenerateVideoRefsRequest(BaseModel):
    reference_media_ids: list[str]
    prompt: str
    project_id: str
    scene_id: str
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"


class UpscaleVideoRequest(BaseModel):
    media_id: str
    scene_id: str
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT"
    resolution: str = "VIDEO_RESOLUTION_4K"


class UploadImageRequest(BaseModel):
    file_path: str  # absolute path to local image file
    project_id: str = ""
    file_name: str = "image.png"


class CheckStatusRequest(BaseModel):
    operations: list[dict]


class EditImageRequest(BaseModel):
    prompt: str
    source_media_id: str
    project_id: str
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_PORTRAIT"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"


@router.get("/status")
async def extension_status():
    """Check if extension is connected."""
    client = get_flow_client()
    return {
        "connected": client.connected,
        "flow_key_present": client._flow_key is not None,
    }


@router.post("/test-captcha")
async def test_captcha():
    """Test solving reCAPTCHA via extension."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("solve_captcha", {"captchaAction": "VIDEO_GENERATION"}, timeout=60)


@router.get("/ext-status")
async def get_ext_status():
    """Get status directly from extension."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("get_status", {}, timeout=10)


@router.get("/tabs")
async def list_tabs():
    """List all open tabs from extension."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("query_tabs", {}, timeout=10)


@router.get("/inspect-tab")
async def inspect_tab(url: Optional[str] = None, code: Optional[str] = None, prompt: Optional[str] = None, js: Optional[str] = None):
    """Inspect Flow tab environment."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    params = {}
    if url:
        params["url"] = url
    if code:
        params["eval"] = code
    if prompt:
        params["prompt"] = prompt
    if js:
        params["js"] = js
    return await client._send("inspect_tab", params, timeout=25)


class FlowTestUIGenerateRequest(BaseModel):
    prompt: Optional[str] = "Test prompt"
    orientation: Optional[str] = "VERTICAL"
    file_path: Optional[str] = None


class HandleFileDialogRequest(BaseModel):
    file_path: str


@router.post("/focus-browser")
async def focus_browser():
    # Background execution: do NOT activate or steal OS window focus
    return {"ok": True}


@router.post("/handle-file-dialog")
async def handle_file_dialog(body: HandleFileDialogRequest):
    import subprocess, asyncio
    escaped_path = body.file_path.replace('"', '\\"')

    # 1. Set system clipboard directly via pbcopy to handle UTF-8 / Thai / spaces reliably
    try:
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(input=body.file_path.encode('utf-8'))
    except Exception as pb_err:
        logger.warning(f"[Flow Dialog] pbcopy error: {pb_err}")

    # 2. AppleScript to send keystrokes directly to the open sheet
    # Strict rule (AGENTS.md): DO NOT tell application "Google Chrome" to activate
    # or tell process "Google Chrome" set frontmost to true here.
    # Doing so steals/resets focus from the NSOpenPanel sheet to the browser window,
    # causing Cmd+Shift+G to trigger Chrome's 'Find Previous' instead of the file sheet.
    as_script = f'''
    set the clipboard to "{escaped_path}"
    tell application "System Events"
        delay 0.8
        -- Press Cmd + Shift + G to open path sheet
        key code 5 using {{command down, shift down}}
        delay 0.8
        -- Select all existing text in sheet (Cmd + A) and delete
        key code 0 using {{command down}}
        delay 0.15
        key code 51
        delay 0.2
        -- Paste path (Cmd + V)
        key code 9 using {{command down}}
        delay 0.8
        -- Return to confirm path sheet
        key code 36
        delay 1.2
        -- Return to confirm open file dialog
        key code 36
    end tell
    '''
    await asyncio.to_thread(subprocess.run, ["osascript", "-e", as_script], check=False)
    return {"ok": True}


@router.post("/test-ui-generate")
async def test_ui_generate(body: FlowTestUIGenerateRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("flow_ui_generate", {
        "prompt": body.prompt,
        "orientation": body.orientation,
        "filePath": body.file_path,
    }, timeout=90)


class FlowDebugStepRequest(BaseModel):
    step: str  # 'step_1_upload', 'step_2_verify_upload', 'step_3_attach_chip', 'step_4_type_prompt', 'step_5_click_generate'
    file_path: Optional[str] = None
    prompt: Optional[str] = None
    orientation: Optional[str] = "VERTICAL"


@router.post("/debug-step")
async def debug_step(body: FlowDebugStepRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("flow_ui_step", {
        "step": body.step,
        "filePath": body.file_path,
        "prompt": body.prompt,
        "orientation": body.orientation,
    }, timeout=60)


class UploadFileRequest(BaseModel):
    image_base64: str
    file_name: str = "storyboard.png"
    mime_type: str = "image/png"


@router.post("/test-upload-file")
async def test_upload_file(body: UploadFileRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("flow_ui_upload_file", {
        "imageBase64": body.image_base64,
        "fileName": body.file_name,
        "mimeType": body.mime_type,
    }, timeout=45)


class CdpUploadFileRequest(BaseModel):
    file_path: str
    target: str = "ingredients"


@router.post("/cdp-upload-file")
async def cdp_upload_file(body: CdpUploadFileRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("flow_cdp_upload_file", {
        "filePath": body.file_path,
        "target": body.target,
    }, timeout=60)


class CdpTypeTextRequest(BaseModel):
    text: str
    click_submit: bool = False
    output_count: int = 1
    aspect_ratio: Optional[str] = None
    is_video: bool = False
    mode: Optional[str] = None
    duration: Optional[int] = None
    submode: Optional[str] = None


@router.post("/cdp-type-text")
async def cdp_type_text(body: CdpTypeTextRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("flow_cdp_type_text", {
        "text": body.text,
        "clickSubmit": body.click_submit,
        "outputCount": body.output_count,
        "aspectRatio": body.aspect_ratio,
        "isVideo": body.is_video,
        "mode": body.mode,
        "duration": body.duration,
        "submode": body.submode,
    }, timeout=45)


class PreloadCharactersRequest(BaseModel):
    project_id: str = "21a1632e-9926-46fa-954c-240d71d78f41"
    story_path: Optional[str] = None
    image_paths: Optional[list[str]] = None


@router.post("/preload-characters")
async def preload_characters(body: PreloadCharactersRequest):
    """Pre-uploads all characters listed in 4 - Reference Image Map.md (or image_paths)
    into the Google Flow project so that subsequent scene generations can reuse them
    without any mid-stream uploads or page reloads.
    """
    import asyncio
    import os
    import re
    import base64
    import mimetypes

    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    async def eval_js(js_code: str, timeout: int = 15):
        raw = await client._send("inspect_tab", {"js": js_code}, timeout=timeout)
        script_res = raw.get("result", {}).get("res", {}) if isinstance(raw, dict) and "result" in raw else (raw.get("res", {}) if isinstance(raw, dict) else {})
        if not script_res.get("success"):
            err = script_res.get("error") or "inspect_tab script failed"
            raise HTTPException(500, f"Browser script error: {err}")
        return script_res.get("result")

    # 0. Concurrency Lock & Tab Busy Check
    busy_response = await _check_flow_busy(client, body.project_id)
    if busy_response is not None:
        return busy_response

    # 1. Ensure tab is at the requested project_id
    if body.project_id:
        await _ensure_project_id(client, body.project_id)

    # 2. Gather image paths to check
    targets = []
    if body.story_path and os.path.isdir(body.story_path):
        ref_map_file = os.path.join(body.story_path, "4 - Reference Image Map.md")
        if os.path.isfile(ref_map_file):
            channel_root = os.path.dirname(os.path.abspath(body.story_path))
            with open(ref_map_file, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^-\s*([^:]+):\s*(.+)$", line.strip())
                    if m:
                        rel = m.group(2).strip()
                        cand1 = os.path.join(channel_root, rel)
                        cand2 = os.path.join(body.story_path, rel)
                        if os.path.isfile(cand1) and cand1 not in targets:
                            targets.append(cand1)
                        elif os.path.isfile(cand2) and cand2 not in targets:
                            targets.append(cand2)
    if body.image_paths:
        for p in body.image_paths:
            if p and os.path.isfile(p) and p not in targets:
                targets.append(p)

    if not targets:
        return {"success": True, "message": "No character images specified or found to preload", "uploaded": [], "already_exists": []}

    # 3. Check existing project assets in Google Flow
    open_menu_js = """(() => {
        const trigger = document.querySelector('button.add-menu-trigger') ||
                        document.querySelector('button[aria-label*="เพิ่มองค์ประกอบ"]');
        if (trigger) { trigger.click(); return true; }
        return false;
    })()"""
    await eval_js(open_menu_js)
    await asyncio.sleep(0.5)

    filter_img_js = """(() => {
        const popover = document.querySelector('flow-add-menu-popover-content');
        if (!popover) return false;
        const navItems = Array.from(popover.querySelectorAll('mat-list-item, .mat-mdc-list-item'));
        const imgNav = navItems.find(el => (el.innerText || '').includes('รูปภาพ') || (el.innerText || '').toLowerCase().includes('image'));
        if (imgNav) { imgNav.click(); return true; }
        return false;
    })()"""
    await eval_js(filter_img_js)
    await asyncio.sleep(0.5)

    already_exists = []
    missing_targets = []
    for p in targets:
        fname = os.path.basename(p)
        fname_no_ext = os.path.splitext(fname)[0]

        # Search for this character sheet in the add-menu search input
        search_item_js = f"""(() => {{
            const popover = document.querySelector('flow-add-menu-popover-content');
            if (!popover) return false;
            const searchInput = popover.querySelector('input.search-input');
            if (searchInput) {{
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                if (setter) {{
                    setter.call(searchInput, "{fname_no_ext}");
                }} else {{
                    searchInput.value = "{fname_no_ext}";
                }}
                searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                searchInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
            return false;
        }})()"""
        await eval_js(search_item_js)
        await asyncio.sleep(0.5)

        check_exists_js = f"""(() => {{
            const popover = document.querySelector('flow-add-menu-popover-content');
            if (!popover) return false;
            const items = Array.from(popover.querySelectorAll('button.asset-item, flow-add-menu-asset-item, .asset-item'));
            return items.some(el => {{
                const t = ((el.innerText || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
                return t.includes("{fname.lower()}") || t.includes("{fname_no_ext.lower()}");
            }});
        }})()"""
        found = await eval_js(check_exists_js)
        if found:
            already_exists.append(fname)
        else:
            missing_targets.append(p)

    # Close popover
    await eval_js("""(() => {
        const backdrop = document.querySelector('.cdk-overlay-backdrop');
        if (backdrop) backdrop.click();
    })()""")
    await asyncio.sleep(0.3)

    uploaded = []
    for p in missing_targets:
        fname = os.path.basename(p)
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = mimetypes.guess_type(p)[0] or "image/png"
            logger.info("Pre-uploading character sheet: %s", fname)
            await client.upload_image(b64, mime_type=mime, project_id=body.project_id, file_name=fname)
            uploaded.append(fname)
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error("Failed to preload character %s: %s", fname, e)

    # If any new image was uploaded, reload once to sync project asset store
    if uploaded:
        logger.info("Preloaded %d new characters. Reloading tab to sync...", len(uploaded))
        await eval_js("window.location.reload();")
        await asyncio.sleep(4.5)

    return {
        "success": True,
        "total_targets": len(targets),
        "already_exists": already_exists,
        "uploaded": uploaded,
        "reloaded": bool(uploaded)
    }


def is_valid_image_bytes(data: bytes) -> bool:
    """Verifies that bytes represent a valid non-empty image (not HTML login/error page)."""
    if not data or len(data) < 20480:
        return False
    header = data[:32]
    if header.startswith(b"<!doctype") or header.startswith(b"<html") or b"<body" in header.lower():
        return False
    if header.startswith(b"\xff\xd8\xff"):  # JPEG
        return True
    if header.startswith(b"\x89PNG\r\n\x1a\n"):  # PNG
        return True
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":  # WEBP
        return True
    return False


class GenerateStoryboardRequest(BaseModel):
    prompt: str
    project_id: str = "21a1632e-9926-46fa-954c-240d71d78f41"
    aspect_ratio: str = "9:16"
    reference_images: Optional[list[str]] = None
    output_path: Optional[str] = None
    timeout: int = 180



class DispatchStoryboardPromptRequest(BaseModel):
    prompt: str
    project_id: str = "21a1632e-9926-46fa-954c-240d71d78f41"
    aspect_ratio: str = "9:16"
    reference_images: Optional[list[str]] = None
    wait_after_submit: float = 0.5
    scene_num: Optional[int] = None
    output_path: Optional[str] = None


class ExpectedBatchScene(BaseModel):
    scene_num: int
    prompt: str
    output_path: str
    reference_images: Optional[list[str]] = None
    media_id: Optional[str] = None


class CollectStoryboardBatchRequest(BaseModel):
    scenes: list[ExpectedBatchScene]
    known_existing_urls: Optional[list[str]] = None
    known_existing_media_ids: Optional[list[str]] = None
    timeout: int = 240
    poll_interval: float = 3.0


class VideoBatchSceneInput(BaseModel):
    scene_num: int
    prompt: str
    image_path: str
    output_path: str


class RunVideoBatchRequest(BaseModel):
    scenes: list[VideoBatchSceneInput]
    aspect_ratio: str = "9:16"
    project_id: Optional[str] = "21a1632e-9926-46fa-954c-240d71d78f41"
    timeout_seconds: int = 600
    delay_between_dispatches: float = 3.0
    auto_retry_filters: bool = True


async def _eval_js_internal(client, js_code: str, timeout: int = 15):
    raw = await client._send("inspect_tab", {"js": js_code}, timeout=timeout)
    script_res = raw.get("result", {}).get("res", {}) if isinstance(raw, dict) and "result" in raw else (raw.get("res", {}) if isinstance(raw, dict) else {})
    if not script_res.get("success"):
        err = script_res.get("error") or "inspect_tab script failed"
        raise HTTPException(500, f"Browser script error: {err}")
    return script_res.get("result")


FLOW_CHIP_SELECTORS = (
    "flow-base-prompt-box flow-image-ingredient-chip, "
    "flow-base-prompt-box [class*='ingredient-chip'], "
    "flow-prompt-box flow-image-ingredient-chip, "
    "[class*='ingredient-chip'], "
    "flow-base-prompt-box flow-ingredient-chip, "
    "flow-prompt-box flow-ingredient-chip, "
    "flow-ingredient-chip"
)


async def _ensure_project_id(client, project_id: str):
    if not project_id:
        return
    import asyncio, re
    try:
        current_url = str(await _eval_js_internal(client, "window.location.href") or "")
        in_edit = "/edit/" in current_url or "/editor/" in current_url
        if project_id not in current_url or in_edit:
            # Check if active tab is busy rendering another project before switching
            busy_js = """(() => {
                const pending = Array.from(document.querySelectorAll('flow-pending-tile:not(.fading-out), [class*="pending-tile"]:not(.fading-out)'));
                const url = window.location.href || '';
                const match = url.match(/\\/project\\/([a-zA-Z0-9_-]+)/);
                return {
                    pendingCount: pending.length,
                    currentProject: match ? match[1] : ''
                };
            })()"""
            tab_status = await _eval_js_internal(client, busy_js, timeout=4) or {}
            pending_count = tab_status.get("pendingCount", 0)
            active_proj = tab_status.get("currentProject") or "active project"
            if (project_id not in current_url) and (pending_count > 0 or _storyboard_lock.locked() or _storyboard_active_state.get("busy")):
                logger.warning(
                    "Cannot switch Google Flow project to %s: project %s is currently rendering (%d pending tiles).",
                    project_id, active_proj, pending_count
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Cannot switch Google Flow project while project '{active_proj}' is rendering ({pending_count} pending tiles)"
                )

            if in_edit and project_id in current_url:
                logger.info("Google Flow tab in tile edit/detail view (%s). Returning to main project page...", current_url)
                exit_js = """(() => {
                    const backBtn = document.querySelector('button.back-button, [aria-label*="กลับ"], [aria-label*="Back"]');
                    if (backBtn) { backBtn.click(); return 'clicked_back'; }
                    const base = window.location.href.split('/edit/')[0];
                    window.location.href = base;
                    return 'navigated';
                })()"""
                await _eval_js_internal(client, exit_js)
                for _ in range(8):
                    await asyncio.sleep(0.5)
                    u = str(await _eval_js_internal(client, "window.location.href") or "")
                    if "/edit/" not in u and "/editor/" not in u:
                        break
            else:
                m = re.match(r"(https?://[^/]+(?:/u/\d+)?/(?:project/|tools/flow/project/))", current_url)
                prefix = m.group(1) if m else "https://flow.google.com/project/"
                target_url = prefix + project_id
                logger.info("Switching Google Flow project to: %s", target_url)
                await _eval_js_internal(client, f"window.location.href = '{target_url}';")
                await asyncio.sleep(5.0)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Project lock check warning: %s", e)


def flow_audit_log(action: str, status: str, details: dict = None):
    import time, json
    t_str = time.strftime("%Y-%m-%d %H:%M:%S")
    payload = details or {}
    line = f"[{t_str}] [{action}] [{status}] {json.dumps(payload, ensure_ascii=False)}\n"
    logger.info("AUDIT_LOG: %s", line.strip())
    try:
        with open("flow_action_audit.log", "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


async def _submit_flow_prompt_internal(
    client,
    prompt: str,
    project_id: str,
    aspect_ratio: str = "9:16",
    reference_images: Optional[list[str]] = None,
    wait_after_submit: float = 0.5
):
    import asyncio, os, base64, mimetypes

    flow_audit_log("SUBMIT_START", "BEGIN", {
        "project_id": project_id,
        "aspect_ratio": aspect_ratio,
        "prompt_preview": prompt[:70],
        "expected_refs": [os.path.basename(p) for p in reference_images] if reference_images else []
    })

    # 0. Ensure project lock and return to main project page if in edit mode
    await _ensure_project_id(client, project_id)

    # 0.1 Explicit safety check: ensure main project page & close any modals/dialogs
    ensure_main_page_js = """(() => {
        const url = window.location.href || '';
        const inEdit = url.includes('/edit/') || !!document.querySelector('flow-image-editor, flow-edit-image-prompt-box');
        let action = 'ok';
        if (inEdit) {
            const backBtn = document.querySelector('button.back-button, [aria-label*="กลับ"], [aria-label*="Back"]');
            if (backBtn) {
                backBtn.click();
                action = 'clicked_back';
            } else {
                const base = url.split('/edit/')[0];
                window.location.href = base;
                action = 'navigated';
            }
        }
        // Dismiss any lingering dialogs, popovers, or modal backdrops
        const closeBtn = document.querySelector('mat-dialog-container button.close-button, .cdk-overlay-pane button[aria-label*="close" i], .cdk-overlay-pane button[aria-label*="ปิด" i]');
        if (closeBtn) closeBtn.click();
        const backdrop = document.querySelector('.cdk-overlay-backdrop');
        if (backdrop && !document.querySelector('flow-add-menu-popover-content')) {
            backdrop.click();
        }
        return { action, url: window.location.href };
    })()"""
    page_check = await _eval_js_internal(client, ensure_main_page_js)
    if page_check and page_check.get("action") in ("clicked_back", "navigated"):
        logger.info("Exited tile edit mode back to main project page (%s)", page_check)
        for _ in range(8):
            await asyncio.sleep(0.5)
            ready = await _eval_js_internal(client, """(() => {
                const u = window.location.href || '';
                return !u.includes('/edit/') && !!document.querySelector('flow-base-prompt-box, flow-prompt-box');
            })()""")
            if ready:
                break

    # 1. Clear existing chips and prompt text — with post-clear verification loop
    clear_js = f"""(() => {{
        const chips = Array.from(document.querySelectorAll("{FLOW_CHIP_SELECTORS}"));
        for (const chip of chips) {{
            // Try multiple targets for the cancel/remove action
            const cancelBtn = chip.querySelector('.cancel-button, [aria-label*="remove" i], [aria-label*="delete" i], [aria-label*="ลบ" i], [aria-label*="ยกเลิก" i], .hover-icon-overlay')
                           || chip.querySelector('button')
                           || chip.querySelector('mat-icon');
            if (cancelBtn) {{
                cancelBtn.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, cancelable: true }}));
                cancelBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
                cancelBtn.click();
            }} else {{
                chip.click();
            }}
        }}
        const pm = document.querySelector('.ProseMirror');
        if (pm) pm.innerText = '';
        return document.querySelectorAll("{FLOW_CHIP_SELECTORS}").length;
    }})()"""
    await _eval_js_internal(client, clear_js)
    await asyncio.sleep(0.3)

    # Verify chips are fully cleared — retry up to 5 times
    verify_clear_js = f"(() => document.querySelectorAll(\"{FLOW_CHIP_SELECTORS}\").length)()"
    for _attempt in range(5):
        chip_count = await _eval_js_internal(client, verify_clear_js) or 0
        if chip_count == 0:
            break
        logger.debug("Chips still present (%d), re-clearing (attempt %d)...", chip_count, _attempt + 1)
        await _eval_js_internal(client, clear_js)
        await asyncio.sleep(0.4)

    # 2. Attach reference images if provided (deduplicated, order preserved)
    if reference_images:
        unique_refs = []
        seen = set()
        for p in reference_images:
            if p and os.path.isfile(p) and p not in seen:
                seen.add(p)
                unique_refs.append(p)

        for ref_img_path in unique_refs:
            filename = os.path.basename(ref_img_path)
            c_name = filename.split(" - ")[0]
            filename_no_ext = os.path.splitext(filename)[0]

            # Guard: skip if this character chip is already attached (prevents duplicates)
            already_attached_js = f"""(() => {{
                const chips = Array.from(document.querySelectorAll("{FLOW_CHIP_SELECTORS}"));
                return chips.some(chip => {{
                    const t = (chip.innerText || chip.getAttribute('aria-label') || chip.getAttribute('title') || '').toLowerCase();
                    return t.includes("{filename_no_ext.lower()}") || t.includes("{c_name.lower()}");
                }});
            }})()"""
            already_attached = await _eval_js_internal(client, already_attached_js)
            if already_attached:
                logger.info("Chip for '%s' already attached — skipping duplicate.", filename_no_ext)
                continue

            # A. Ensure previous popover and backdrop are closed cleanly
            ensure_closed_js = """(() => {
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (popover) {
                    const backdrop = document.querySelector('.cdk-overlay-backdrop');
                    if (backdrop) backdrop.click();
                    return true;
                }
                return false;
            })()"""
            await _eval_js_internal(client, ensure_closed_js)
            await asyncio.sleep(0.4)

            # B. Open the element popover menu with retry loop
            open_menu_js = """(() => {
                let popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) {
                    const trigger = document.querySelector('button.add-menu-trigger') ||
                                    Array.from(document.querySelectorAll('flow-prompt-box button, button')).find(b => {
                                        const l = ((b.getAttribute('aria-label')||'') + ' ' + (b.innerText||'')).toLowerCase();
                                        return l.includes('เพิ่มองค์ประกอบ') || l.includes('add') || l.includes('media');
                                    });
                    if (trigger) { trigger.click(); }
                }
                return !!document.querySelector('flow-add-menu-popover-content');
            })()"""
            for _ in range(4):
                is_open = await _eval_js_internal(client, open_menu_js)
                if is_open:
                    break
                await asyncio.sleep(0.4)
            await asyncio.sleep(0.4)

            # C. Switch to 'รูปภาพ' (Images) tab
            filter_img_js = """(() => {
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return false;
                const navItems = Array.from(popover.querySelectorAll('mat-list-item, .mat-mdc-list-item'));
                const imgNav = navItems.find(el => (el.innerText || '').includes('รูปภาพ') || (el.innerText || '').toLowerCase().includes('image'));
                if (imgNav) { imgNav.click(); return true; }
                return false;
            })()"""
            await _eval_js_internal(client, filter_img_js)
            await asyncio.sleep(0.4)

            # D. Search for character sheet by full name to bypass CDK virtual scroll limits
            search_item_js = f"""(() => {{
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return false;
                const searchInput = popover.querySelector('input.search-input, input[type="search"], input');
                if (searchInput) {{
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    if (setter) {{
                        setter.call(searchInput, "{filename_no_ext}");
                    }} else {{
                        searchInput.value = "{filename_no_ext}";
                    }}
                    searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    searchInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }})()"""
            await _eval_js_internal(client, search_item_js)
            await asyncio.sleep(0.6)

            # E. Check if search returned the target item
            find_item_js = f"""(() => {{
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return false;
                const items = Array.from(popover.querySelectorAll('button.asset-item'));
                return items.some(el => {{
                    const t = ((el.innerText || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '')).trim().toLowerCase();
                    return t.includes("{filename_no_ext.lower()}") || t.includes("{c_name.lower()}");
                }});
            }})()"""
            asset_exists = await _eval_js_internal(client, find_item_js)

            if not asset_exists:
                # Asset not found in project: upload it cleanly via API without reloading the page
                try:
                    with open(ref_img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    mime = mimetypes.guess_type(ref_img_path)[0] or "image/png"
                    await client.upload_image(b64, mime_type=mime, project_id=project_id, file_name=filename)
                    logger.info("Uploaded missing character sheet: %s", filename)
                except Exception as up_err:
                    logger.warning("Failed to upload character sheet %s: %s", filename, up_err)

                # Close and reopen popover to refresh asset list
                await _eval_js_internal(client, ensure_closed_js)
                await asyncio.sleep(0.5)
                await _eval_js_internal(client, open_menu_js)
                await asyncio.sleep(0.5)
                await _eval_js_internal(client, filter_img_js)
                await asyncio.sleep(0.4)
                await _eval_js_internal(client, search_item_js)
                await asyncio.sleep(0.6)

            # F. Check chips before click
            chips_before = await _eval_js_internal(client, f"(() => document.querySelectorAll('{FLOW_CHIP_SELECTORS}').length)()") or 0

            # Click the matching asset button
            click_item_js = f"""(() => {{
                let popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) {{
                    const trigger = document.querySelector('button.add-menu-trigger') ||
                                    Array.from(document.querySelectorAll('flow-prompt-box button, button')).find(b => {{
                                        const l = ((b.getAttribute('aria-label')||'') + ' ' + (b.innerText||'')).toLowerCase();
                                        return l.includes('เพิ่มองค์ประกอบ') || l.includes('add');
                                    }});
                    if (trigger) trigger.click();
                    popover = document.querySelector('flow-add-menu-popover-content');
                }}
                if (!popover) return {{ error: 'popover not found' }};
                const items = Array.from(popover.querySelectorAll('button.asset-item, flow-add-menu-asset-item, .asset-item, button'));
                let target = items.find(el => {{
                    const t = ((el.innerText || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '')).trim().toLowerCase();
                    return t.includes("{filename_no_ext.lower()}");
                }});
                if (!target) {{
                    target = items.find(el => {{
                        const t = ((el.innerText || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '')).trim().toLowerCase();
                        return t.includes("{c_name.lower()}");
                    }});
                }}
                if (target) {{
                    target.click();
                    return {{ ok: true, name: (target.innerText || '').trim() }};
                }}
                return {{ error: 'item not found', visible: items.map(el => (el.innerText || '').trim()) }};
            }})()"""
            click_res = await _eval_js_internal(client, click_item_js)
            if not click_res or not click_res.get("ok"):
                flow_audit_log("CLICK_ASSET_CARD", "FAILED", {"file": filename, "result": click_res})
                raise HTTPException(422, f"Could not find or click Character Sheet '{filename_no_ext}' in Google Flow popover!")
            flow_audit_log("CLICK_ASSET_CARD", "SUCCESS", {"file": filename, "name": click_res.get("name")})
            await asyncio.sleep(0.5)

            # G. Check if direct click added the chip, or if detail pane 'Add to prompt' button is needed
            chips_after = await _eval_js_internal(client, f"(() => document.querySelectorAll('{FLOW_CHIP_SELECTORS}').length)()") or 0
            if chips_after > chips_before:
                flow_audit_log("ADD_TO_PROMPT", "SUCCESS", {"file": filename, "method": "direct_click", "chips": chips_after})
            else:
                # Try clicking detail pane 'Add to prompt' button if opened
                add_prompt_js = """(() => {
                    const addBtn = document.querySelector('flow-add-menu-detail-pane button.detail-add-to-prompt-btn') ||
                                   Array.from(document.querySelectorAll('.cdk-overlay-container button')).find(b => (b.innerText || '').includes('เพิ่มไปยังพรอมต์') || (b.innerText || '').includes('Add to prompt'));
                    if (addBtn) {
                        addBtn.click();
                        return { clicked: true };
                    }
                    return { clicked: false };
                })()"""
                add_res = await _eval_js_internal(client, add_prompt_js)
                await asyncio.sleep(0.5)
                chips_after = await _eval_js_internal(client, f"(() => document.querySelectorAll('{FLOW_CHIP_SELECTORS}').length)()") or 0
                if chips_after > chips_before:
                    flow_audit_log("ADD_TO_PROMPT", "SUCCESS", {"file": filename, "method": "detail_pane_button", "chips": chips_after})
                else:
                    flow_audit_log("ADD_TO_PROMPT", "FAILED", {"file": filename, "chips_before": chips_before, "chips_after": chips_after, "add_res": add_res})
                    raise HTTPException(422, f"Could not attach Character Sheet '{filename_no_ext}': chip count did not increase (before: {chips_before}, after: {chips_after})!")

            # H. Ensure popover closes and wait for backdrop fade-out
            await _eval_js_internal(client, ensure_closed_js)
            await asyncio.sleep(0.4)

    # 2.5 Hard Gate: Strict Chip Count Assertion before generation
    expected_ref_count = len(unique_refs) if reference_images else 0
    final_chips = await _eval_js_internal(client, f"(() => document.querySelectorAll('{FLOW_CHIP_SELECTORS}').length)()")
    flow_audit_log("HARD_GATE_CHECK", "PASS" if final_chips == expected_ref_count else "FAIL", {
        "expected": expected_ref_count,
        "actual": final_chips,
        "reference_images": [os.path.basename(p) for p in reference_images] if reference_images else []
    })
    if final_chips != expected_ref_count:
        raise HTTPException(
            status_code=422,
            detail=f"Character Sheet Hard Gate Failed: Expected {expected_ref_count} chip(s) but found {final_chips} in prompt box! Aborting to prevent image without character sheet."
        )

    import time
    submit_start_ts = int(time.time() * 1000)

    # Submit prompt via CDP with aspect ratio
    cdp_res = await client._send("flow_cdp_type_text", {
        "text": prompt,
        "clickSubmit": True,
        "outputCount": 1,
        "aspectRatio": aspect_ratio
    }, timeout=45)

    logger.info("flow_cdp_type_text response: %s", cdp_res)
    if not cdp_res.get("clicked"):
        await _eval_js_internal(client, """(() => {
            const btn = document.querySelector('flow-prompt-box button.generate-icon-button, button.generate-icon-button, button[aria-label="เริ่มสร้าง"], button[aria-label="Start generation"]');
            if (btn && !btn.disabled && !btn.classList.contains('mat-mdc-button-disabled')) {
                const opts = { bubbles: true, cancelable: true, view: window };
                btn.dispatchEvent(new PointerEvent('pointerdown', opts));
                btn.dispatchEvent(new MouseEvent('mousedown', opts));
                btn.dispatchEvent(new PointerEvent('pointerup', opts));
                btn.dispatchEvent(new MouseEvent('mouseup', opts));
                btn.dispatchEvent(new MouseEvent('click', opts));
            }
        })()""")

    # 4. Wait for Google Flow to queue the prompt and capture intercepted media_id
    captured_media_id = None
    poll_start = time.time()
    max_wait = max(wait_after_submit, 3.5)
    while time.time() - poll_start < max_wait:
        await asyncio.sleep(0.4)
        check_js = f"""(() => {{
            const list = window.__FLOW_MEDIA_CAPTURES__ || [];
            const recent = list.filter(item => item.timestamp >= {submit_start_ts - 1000});
            if (recent.length > 0) {{
                return recent[recent.length - 1];
            }}
            return null;
        }})()"""
        cap = await _eval_js_internal(client, check_js)
        if cap and cap.get("mediaId"):
            captured_media_id = cap.get("mediaId")
            logger.info("🎯 [Network Intercept] Captured media_id: %s for prompt: %.50s...", captured_media_id, prompt)
            break

    return captured_media_id


def _match_batch_tiles_to_scenes(scenes: list, new_tiles: list) -> list:
    """Matches newly generated image tiles to scene requests using expected FIFO order.
    Removes fuzzy prompt similarity scoring to prevent false matches."""
    import re
    N = len(scenes)
    M = len(new_tiles)
    if M == 0 or N == 0:
        return []

    boilerplate_words = {
        "vertical", "horizontal", "cinematic", "render", "style", "pixar",
        "dreamworks", "smooth", "cute", "lighting", "masterpiece", "resolution",
        "thai", "melodrama", "depth", "field", "sharp", "focus", "characters"
    }

    scores = []
    for i, sc in enumerate(scenes):
        sc_prompt = sc.get("prompt", "")
        row = []
        for j, tl in enumerate(new_tiles):
            # Positional matching: Google Flow prepends newly finished tiles to the front
            expected_j = max(0, min(M - 1, N - 1 - i))
            pos_penalty = abs(j - expected_j) * 0.5
            sc_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", sc_prompt.lower())) - boilerplate_words
            tl_footer = tl.get("footer_title", "")
            tl_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", tl_footer.lower()))
            overlap = len(sc_words.intersection(tl_words))
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



@router.get("/snapshot-existing-tiles")
async def snapshot_existing_tiles():
    """Returns list of currently rendered image URLs and media IDs in Google Flow tab."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    snap_js = """(() => {
        const tiles = Array.from(document.querySelectorAll('flow-image-tile, flow-grid-tile-container, flow-tile, [class*="tile"]:has(img)'));
        const urls = [];
        const mediaIds = [];
        for (const t of tiles) {
            const img = t.querySelector('img');
            if (img && img.src) {
                urls.push(img.src);
                const mid = img.getAttribute('data-media-id');
                if (mid) mediaIds.push(mid);
                const m = img.src.match(/\\/image\\/([a-f0-9\\-]{36})/);
                if (m && !mediaIds.includes(m[1])) mediaIds.push(m[1]);
            }
        }
        return { urls: urls, media_ids: mediaIds, count: tiles.length };
    })()"""
    res = await _eval_js_internal(client, snap_js)
    return {
        "success": True,
        "urls": res.get("urls", []) if isinstance(res, dict) else [],
        "media_ids": res.get("media_ids", []) if isinstance(res, dict) else [],
        "count": res.get("count", 0) if isinstance(res, dict) else 0
    }


@router.post("/clear-dispatch-queue")
async def clear_dispatch_queue():
    """Clears the server-side dispatch order queue. Call this before each new batch session."""
    cleared = len(_dispatch_order_queue)
    _dispatch_order_queue.clear()
    logger.info("Dispatch order queue cleared (%d entries removed).", cleared)
    return {"success": True, "cleared": cleared}


@router.get("/dispatch-queue-status")
async def dispatch_queue_status():
    """Returns current state of the server-side dispatch order queue for debugging."""
    return {
        "queue_length": len(_dispatch_order_queue),
        "entries": [
            {"prompt_preview": e["prompt"][:60], "scene_num": e.get("scene_num")}
            for e in _dispatch_order_queue
        ]
    }


@router.post("/dispatch-storyboard-prompt")
async def dispatch_storyboard_prompt(body: DispatchStoryboardPromptRequest):
    """Submits a single prompt into Google Flow queue without blocking on render completion."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    # Concurrency Lock & Tab Busy Check (allow up to 15 queued tiles in same project)
    busy_response = await _check_flow_busy(client, body.project_id, allow_same_project_queue=True, max_queue=15)
    if busy_response is not None:
        return busy_response

    captured_media_id = await _submit_flow_prompt_internal(
        client=client,
        prompt=body.prompt,
        project_id=body.project_id,
        aspect_ratio=body.aspect_ratio,
        reference_images=body.reference_images,
        wait_after_submit=body.wait_after_submit
    )

    # Track dispatch order server-side with media_id for deterministic matching
    _dispatch_order_queue.append({
        "prompt": body.prompt,
        "media_id": captured_media_id,
        "scene_num": body.scene_num,
        "output_path": body.output_path,
        "reference_images": body.reference_images,
    })
    logger.info("Dispatch queue: recorded prompt #%d (scene: %s, media_id: %s, preview: %.50s...)",
                len(_dispatch_order_queue), body.scene_num, captured_media_id, body.prompt)

    return {
        "success": True,
        "dispatched": True,
        "media_id": captured_media_id,
        "dispatch_queue_len": len(_dispatch_order_queue),
        "prompt_preview": body.prompt[:80]
    }


async def _download_tile_image_internal(client, img_url: str, out_path: str) -> bool:
    """Helper to fetch image from browser context at full resolution and save locally."""
    import os, base64, io
    from PIL import Image
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        fetch_js = f"""(async () => {{
            const fullUrl = "{img_url}".replace(/=s\\d+/, '=s2048');
            const res = await fetch(fullUrl);
            if (!res.ok) return {{ ok: false, status: res.status }};
            const blob = await res.blob();
            return new Promise(resolve => {{
                const reader = new FileReader();
                reader.onloadend = () => resolve({{ ok: true, b64: reader.result.split(',')[1] }});
                reader.readAsDataURL(blob);
            }});
        }})()"""
        b_res = await _eval_js_internal(client, fetch_js) or {}
        if b_res.get("ok") and b_res.get("b64"):
            raw_bytes = base64.b64decode(b_res["b64"])
            im = Image.open(io.BytesIO(raw_bytes))
            im.convert("RGB").save(out_path, "JPEG", quality=95)
            logger.info("Saved batch image to %s (%dx%d)", out_path, im.width, im.height)
            return True
    except Exception as dl_err:
        logger.error("Download tile image error for %s: %s", out_path, dl_err)
    return False


@router.post("/collect-storyboard-batch")
async def collect_storyboard_batch(body: CollectStoryboardBatchRequest):
    """Waits for Google Flow pending queue to finish and downloads batch images.
    Matches media_id in real-time and downloads immediately upon tile completion."""
    import asyncio, time, httpx, os

    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    known_urls = set(body.known_existing_urls or [])
    known_media_ids = set(body.known_existing_media_ids or [])

    start_time = time.time()
    consecutive_zero_pending = 0
    has_seen_pending = False
    poll_status = {}

    completed_scene_nums = set()
    realtime_results = []
    used_tile_srcs = set()

    while time.time() - start_time < body.timeout:
        await asyncio.sleep(body.poll_interval)

        status_js = """(() => {
            const pending = [...document.querySelectorAll('flow-pending-tile, [class*="pending-tile"]')];
            const errorToast = document.querySelector('mat-snack-bar-container, .error-message, [class*="error-snackbar"], .cdk-overlay-container [role="alert"], [class*="toast"]');
            const errorText = errorToast ? (errorToast.innerText || '').trim() : '';
            const tiles = [...document.querySelectorAll('flow-image-tile')];
            const tileData = tiles.map(t => {
                const img = t.querySelector('img');
                const footer = t.querySelector('.footer-title');
                const promptText = (
                    t.getAttribute('data-prompt') ||
                    t.getAttribute('aria-label') ||
                    img?.getAttribute('alt') ||
                    img?.getAttribute('title') ||
                    img?.getAttribute('aria-label') ||
                    t.querySelector('[data-prompt]')?.getAttribute('data-prompt') ||
                    t.querySelector('[title]')?.getAttribute('title') ||
                    t.querySelector('[aria-label]')?.getAttribute('aria-label') ||
                    ''
                ).trim();
                const midAttr = img ? (img.getAttribute('data-media-id') || '') : '';
                const midRegex = (img?.src || '').match(/\/image\/([a-f0-9\-]{36})/)?.[1] || '';
                return {
                    src: img ? img.src : '',
                    media_id: midAttr || midRegex,
                    footer_title: footer ? (footer.innerText || '').trim() : '',
                    prompt_text: promptText
                };
            }).filter(t => t.src);

            return {
                pendingCount: pending.length,
                pendingPcts: pending.map(p => (p.innerText || '').match(/(\d+)%/)?.[1]).filter(Boolean),
                tiles: tileData,
                errorText: errorText
            };
        })()"""

        poll_status = await _eval_js_internal(client, status_js) or {}
        pending_count = poll_status.get("pendingCount", 0)
        error_text = poll_status.get("errorText") or ""
        tiles = poll_status.get("tiles") or []

        if error_text and any(w in error_text.lower() for w in ["policy", "violate", "safety", "guideline", "ละเมิด", "ไม่สามารถสร้าง", "นโยบาย"]):
            logger.warning("Safety policy error detected during batch render: %s", error_text)

        new_tiles = [
            t for t in tiles
            if (t.get("src") not in known_urls) and (not t.get("media_id") or t.get("media_id") not in known_media_ids)
        ]

        # ── Step 1: Real-time Immediate Download on Media ID Match ────────────
        for sc_obj in body.scenes:
            sc_dict = sc_obj.dict()
            sc_num = sc_dict.get("scene_num")
            if sc_num in completed_scene_nums:
                continue
            target_mid = sc_dict.get("media_id")
            if not target_mid:
                for q in _dispatch_order_queue:
                    if q.get("prompt") == sc_dict.get("prompt") and q.get("media_id"):
                        target_mid = q.get("media_id")
                        break
            if target_mid:
                for tl in new_tiles:
                    tl_src = tl.get("src") or ""
                    tl_mid = tl.get("media_id") or ""
                    if tl_src in used_tile_srcs:
                        continue
                    if target_mid == tl_mid or f"/image/{target_mid}" in tl_src:
                        out_path = sc_dict.get("output_path")
                        logger.info("🎯 [REALTIME MEDIA_ID MATCH] Scene %02d matched media_id %s -> Downloading immediately to %s", sc_num, target_mid, out_path)
                        dl_ok = False
                        if out_path:
                            dl_ok = await _download_tile_image_internal(client, tl_src, out_path)
                        realtime_results.append({
                            "scene_num": sc_num,
                            "success": dl_ok,
                            "output_path": out_path,
                            "footer_title": tl.get("footer_title"),
                            "image_url": tl_src,
                            "media_id": target_mid
                        })
                        completed_scene_nums.add(sc_num)
                        used_tile_srcs.add(tl_src)
                        break

        if len(completed_scene_nums) >= len(body.scenes):
            logger.info("⚡ All %d batch scenes matched by media_id and downloaded in real-time!", len(body.scenes))
            break

        if pending_count > 0:
            has_seen_pending = True
            consecutive_zero_pending = 0
        else:
            consecutive_zero_pending += 1
            if has_seen_pending and consecutive_zero_pending >= 2:
                logger.info("Batch rendering complete after seeing pending. Found %d new tiles.", len(new_tiles))
                break
            if time.time() - start_time >= 8 and len(new_tiles) >= len(body.scenes) and not has_seen_pending:
                logger.info("Batch rendering complete (found %d new tiles for %d expected scenes).", len(new_tiles), len(body.scenes))
                break

    tiles = poll_status.get("tiles") or []
    new_tiles = [
        t for t in tiles
        if (t.get("src") not in known_urls) and (not t.get("media_id") or t.get("media_id") not in known_media_ids)
    ]

    # Remaining fallback matching for any scenes not downloaded via real-time media_id
    scenes_by_prompt = {s.prompt: s.dict() for s in body.scenes}
    matched_pairs = []

    unmatched_scenes = [s.dict() for s in body.scenes if s.scene_num not in completed_scene_nums]
    remaining_tiles = [tl for tl in new_tiles if tl.get("src") not in used_tile_srcs]

    if unmatched_scenes and _dispatch_order_queue:
        batch_prompts = {s["prompt"] for s in unmatched_scenes}
        queue_entries = [e for e in _dispatch_order_queue if e["prompt"] in batch_prompts]
        if queue_entries and len(remaining_tiles) >= len(queue_entries):
            N = len(queue_entries)
            # In Google Flow DOM, newly generated tiles appear at index 0 (top-left).
            # To match dispatch order (first queued -> first rendered), reverse the tile slice:
            ordered_tiles = list(reversed(remaining_tiles[:N]))
            for q_entry, tile in zip(queue_entries, ordered_tiles):
                sc_dict = scenes_by_prompt.get(q_entry["prompt"])
                if sc_dict and sc_dict.get("scene_num") not in completed_scene_nums:
                    matched_pairs.append((sc_dict, tile))
                    completed_scene_nums.add(sc_dict.get("scene_num"))
                    used_tile_srcs.add(tile.get("src"))
                    logger.info("Dispatch-order match: Scene %02d -> tile %s", sc_dict.get("scene_num"), tile.get("media_id", "?"))

    # Fallback to positional scoring
    remaining_unmatched = [s for s in unmatched_scenes if s.get("scene_num") not in completed_scene_nums]
    final_tiles = [tl for tl in remaining_tiles if tl.get("src") not in used_tile_srcs]
    if remaining_unmatched and final_tiles:
        logger.warning("Falling back to keyword+positional matching for %d scene(s)", len(remaining_unmatched))
        fallback_pairs = _match_batch_tiles_to_scenes(remaining_unmatched, final_tiles)
        for sc_dict, tl in fallback_pairs:
            matched_pairs.append((sc_dict, tl))
            completed_scene_nums.add(sc_dict.get("scene_num"))
            used_tile_srcs.add(tl.get("src"))

    consumed_prompts = {sc["prompt"] for sc, _ in matched_pairs} | {s.prompt for s in body.scenes if s.scene_num in completed_scene_nums}
    _dispatch_order_queue[:] = [e for e in _dispatch_order_queue if e["prompt"] not in consumed_prompts]

    results = list(realtime_results)

    for sc, tl in matched_pairs:
        sc_num = sc.get("scene_num")
        out_path = sc.get("output_path")
        img_url = tl.get("src")
        footer_title = tl.get("footer_title")

        if out_path and img_url:
            dl_ok = await _download_tile_image_internal(client, img_url, out_path)
            results.append({
                "scene_num": sc_num,
                "success": dl_ok,
                "output_path": out_path,
                "footer_title": footer_title,
                "image_url": img_url
            })
        else:
            results.append({
                "scene_num": sc_num,
                "success": False,
                "error": "Missing out_path or img_url"
            })

    for s in body.scenes:
        if s.scene_num not in completed_scene_nums:
            results.append({
                "scene_num": s.scene_num,
                "success": False,
                "error": "No matching generated image found in batch"
            })

    results.sort(key=lambda x: x.get("scene_num", 0))
    successful_count = sum(1 for r in results if r.get("success"))

    return {
        "success": successful_count > 0,
        "collected_count": successful_count,
        "total_expected": len(body.scenes),
        "results": results
    }


@router.post("/generate-storyboard")
async def generate_storyboard(body: GenerateStoryboardRequest):
    """Centralized background storyboard image generation via Google Flow CDP automation.

    Reusable by all channels (Lakorn, Stickman, etc.).
    - Concurrency Lock: Checks if server or Chrome tab is busy rendering, returns HTTP 429 (Too Many Requests / Busy) if busy.
    - Uploads and attaches character sheet reference images as ingredient chips
    - Sets aspect ratio (9:16 or 16:9)
    - Submits prompt via CDP
    - Monitors rendering progress until 100%
    - Downloads completed image to output_path
    """
    import asyncio
    import os
    import time
    import httpx

    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    # 1. Concurrency Lock & Tab Busy Check (Non-blocking check)
    busy_response = await _check_flow_busy(client, body.project_id)
    if busy_response is not None:
        return busy_response

    if _storyboard_lock.locked():
        curr_proj = _storyboard_active_state.get("project_id") or body.project_id or ""
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "status": "busy",
                "message": "Google Flow is currently busy rendering another task",
                "current_project": curr_proj
            }
        )

    async with _storyboard_lock:
        _storyboard_active_state["busy"] = True
        _storyboard_active_state["project_id"] = body.project_id
        _storyboard_active_state["started_at"] = time.time()
        _storyboard_active_state["prompt"] = body.prompt[:100]

        try:
            # 1. Snapshot existing tiles before submitting prompt to guarantee only newly generated tiles are accepted
            snap_js = """(() => {
                const tiles = Array.from(document.querySelectorAll('flow-grid-tile-container, flow-tile, [class*="tile"]:has(img)'));
                const urls = [];
                const mediaIds = [];
                for (const t of tiles) {
                    const img = t.querySelector('img');
                    if (img && img.src) {
                        urls.push(img.src);
                        const mid = img.getAttribute('data-media-id');
                        if (mid) mediaIds.push(mid);
                    }
                }
                return { urls: urls, media_ids: mediaIds };
            })()"""
            pre_snap = await _eval_js_internal(client, snap_js) or {}
            pre_urls = set(pre_snap.get("urls", []))
            pre_media_ids = set(pre_snap.get("media_ids", []))

            # 2. Submit prompt via CDP
            await _submit_flow_prompt_internal(
                client=client,
                prompt=body.prompt,
                project_id=body.project_id,
                aspect_ratio=body.aspect_ratio,
                reference_images=body.reference_images,
                wait_after_submit=1.0
            )

            # 3. Monitor rendering until done (default 60s timeout)
            start_time = time.time()
            generated_img_url = None
            consecutive_zero_pending = 0
            has_seen_pending = False

            while time.time() - start_time < body.timeout:
                await asyncio.sleep(2.5)
                status_js = """(() => {
                    const pending = [...document.querySelectorAll('flow-pending-tile, [class*="pending-tile"]')];
                    const errorToast = document.querySelector('mat-snack-bar-container, .error-message, [class*="error-snackbar"], .cdk-overlay-container [role="alert"], [class*="toast"]');
                    const errorText = errorToast ? (errorToast.innerText || '').trim() : '';
                    const tiles = [...document.querySelectorAll('flow-image-tile')];
                    const tileData = tiles.map(t => {
                        const img = t.querySelector('img');
                        return {
                            src: img ? img.src : '',
                            media_id: img ? (img.getAttribute('data-media-id') || '') : ''
                        };
                    }).filter(t => t.src);
                    return {
                        pendingCount: pending.length,
                        pendingPcts: pending.map(p => (p.innerText || '').match(/(\\d+)%/)?.[1]).filter(Boolean),
                        tiles: tileData,
                        errorText: errorText
                    };
                })()"""
                render_status = await _eval_js_internal(client, status_js) or {}
                pending_count = render_status.get("pendingCount", 0)
                error_text = render_status.get("errorText") or ""
                tiles = render_status.get("tiles") or []

                if error_text and any(w in error_text.lower() for w in ["policy", "violate", "safety", "guideline", "ละเมิด", "ไม่สามารถสร้าง", "นโยบาย"]):
                    raise HTTPException(422, f"Safety policy block detected: {error_text}")

                # Strictly filter for NEW tiles that did not exist before this prompt submission
                new_tiles = [
                    t for t in tiles
                    if (t.get("src") not in pre_urls) and (not t.get("media_id") or t.get("media_id") not in pre_media_ids)
                ]

                if new_tiles:
                    generated_img_url = new_tiles[0].get("src")
                    break

                if pending_count > 0:
                    has_seen_pending = True
                    consecutive_zero_pending = 0
                else:
                    consecutive_zero_pending += 1
                    if has_seen_pending and consecutive_zero_pending >= 15:
                        # Pending tile vanished after being actively rendered
                        if new_tiles:
                            generated_img_url = new_tiles[0].get("src")
                            break
                        raise HTTPException(410, "Pending tile vanished without producing a new image (tab was refreshed or generation aborted). Must re-generate.")

            if not generated_img_url:
                raise HTTPException(504, f"Image generation timed out after {body.timeout}s without producing a new tile")

            # 4. Download and validate image to output_path if provided
            if body.output_path:
                os.makedirs(os.path.dirname(os.path.abspath(body.output_path)), exist_ok=True)
                fetch_js = f"""(async () => {{
                    const fullUrl = "{generated_img_url}".replace(/=s\\d+/, '=s2048');
                    const res = await fetch(fullUrl);
                    if (!res.ok) return {{ ok: false, status: res.status }};
                    const blob = await res.blob();
                    return new Promise(resolve => {{
                        const reader = new FileReader();
                        reader.onloadend = () => resolve({{ ok: true, b64: reader.result.split(',')[1] }});
                        reader.readAsDataURL(blob);
                    }});
                }})()"""
                b_res = await _eval_js_internal(client, fetch_js) or {}
                if b_res.get("ok") and b_res.get("b64"):
                    import base64, io
                    from PIL import Image
                    raw_bytes = base64.b64decode(b_res["b64"])
                    im = Image.open(io.BytesIO(raw_bytes))
                    im.convert("RGB").save(body.output_path, "JPEG", quality=95)
                    logger.info("Saved image to %s (%dx%d)", body.output_path, im.width, im.height)
                else:
                    raise HTTPException(502, f"Failed to download image via browser session: {b_res}")

            return {
                "success": True,
                "image_url": generated_img_url,
                "output_path": body.output_path,
                "aspect_ratio": body.aspect_ratio
            }
        finally:
            _storyboard_active_state["busy"] = False
            _storyboard_active_state["project_id"] = None
            _storyboard_active_state["started_at"] = None
            _storyboard_active_state["prompt"] = None


@router.post("/reload-extension")
async def reload_ext():
    """Trigger extension reload via WS."""
    import json
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    if client._extension_ws:
        import asyncio
        try:
            await asyncio.wait_for(client._extension_ws.send(json.dumps({"type": "reload_extension"})), timeout=1.5)
        except Exception:
            pass
    return {"ok": True}


@router.post("/reload-flow-tab")
async def reload_flow_tab():
    """Trigger reload of the active Google Flow tab via extension."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("reload_flow_tab", {}, timeout=10)


@router.post("/clear-key")
async def clear_flow_key():
    """Clear cached flow key in client and extension."""
    client = get_flow_client()
    client._flow_key = None
    if client.connected:
        await client._send("clear_flow_key", {}, timeout=5)
    return {"ok": True}


@router.get("/credits")
async def get_credits():
    """Get user credits from Google Flow."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.get_credits()
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return result.get("data", result)


@router.post("/generate-image")
async def generate_image(body: GenerateImageRequest):
    """Generate image directly (bypasses queue)."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.generate_images(**body.model_dump())
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    return result.get("data", result)


@router.post("/generate-video")
async def generate_video(body: GenerateVideoRequest):
    """Submit video generation (returns operations for polling)."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.generate_video(**body.model_dump(exclude_none=True))
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    return result.get("data", result)


@router.post("/generate-video-refs")
async def generate_video_refs(body: GenerateVideoRefsRequest):
    """Submit r2v video generation from reference images."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.generate_video_from_references(**body.model_dump())
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    return result.get("data", result)


@router.post("/upscale-video")
async def upscale_video(body: UpscaleVideoRequest):
    """Submit video upscale (returns operations for polling)."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.upscale_video(**body.model_dump())
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    return result.get("data", result)


@router.post("/check-status")
async def check_status(body: CheckStatusRequest):
    """Check video generation status."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.check_video_status(body.operations)
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return result.get("data", result)


@router.post("/refresh-urls/{project_id}")
async def refresh_project_urls(project_id: str):
    """Bulk refresh all media URLs for a project via per-media get_media calls."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.refresh_project_urls(project_id)
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return result


@router.get("/media/{media_id}")
async def get_media(media_id: str):
    """Get media metadata + fresh signed URL from Google Flow.

    Returns the raw response which should contain a fresh fifeUrl/servingUri.
    Use this to refresh expired GCS signed URLs.
    """
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.get_media(media_id)
    if result.get("error"):
        raise HTTPException(502, result["error"])
    status = result.get("status", 200)
    if isinstance(status, int) and status >= 400:
        raise HTTPException(status, result.get("data", "Media not found"))
    return result.get("data", result)


@router.post("/edit-image")
async def edit_image(body: EditImageRequest):
    """Edit an existing image using IMAGE_INPUT_TYPE_BASE_IMAGE (bypasses queue)."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    result = await client.edit_image(
        body.prompt, body.source_media_id, body.project_id,
        aspect_ratio=body.aspect_ratio,
        user_paygate_tier=body.user_paygate_tier,
    )
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    return result.get("data", result)


@router.post("/upload-image")
async def upload_image(body: UploadImageRequest):
    """Upload a local image file to Google Flow and get a media_id."""
    import base64, mimetypes
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    try:
        with open(body.file_path, "rb") as f:
            image_bytes = f.read()
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {body.file_path}")
    b64 = base64.b64encode(image_bytes).decode()
    mime = mimetypes.guess_type(body.file_path)[0] or "image/png"
    result = await client.upload_image(b64, mime_type=mime, project_id=body.project_id, file_name=body.file_name)
    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))
    media_id = result.get("_mediaId")
    return {"media_id": media_id, "raw": result.get("data", result)}


def resolve_storyboard_dir(lakorn_path: str, ton: str, ep: str) -> str:
    import os
    import pathlib
    import re
    from pathlib import Path
    
    if not lakorn_path or not os.path.exists(lakorn_path):
        return ""
        
    p = Path(lakorn_path)
    ton_val_clean = ton.strip().lower()
    subdirs = [d for d in p.iterdir() if d.is_dir()]
    
    ep_dir = None
    # 1. Try matching folder that starts with or is exactly the ton number
    for d in subdirs:
        name = d.name.lower()
        if name == ton_val_clean or name.startswith(ton_val_clean + " ") or name.startswith(ton_val_clean + "-"):
            ep_dir = d
            break
            
    # 2. Try loose match
    if not ep_dir:
        for d in subdirs:
            if ton_val_clean in d.name.lower():
                ep_dir = d
                break
                
    if not ep_dir:
        ep_dir = p / ton
        
    # Search for storyboard candidate folders
    storyboard_dir = None
    for candidate in ["6 - Storyboards", "6-Storyboards", "Storyboards", "storyboards", "3 - Storyboard", "3-Storyboard", "Storyboard", "storyboard"]:
        cand_path = ep_dir / candidate
        if cand_path.exists() and cand_path.is_dir():
            storyboard_dir = cand_path
            break
            
    if not storyboard_dir:
        storyboard_dir = ep_dir / "6 - Storyboards"
        
    # Resolve EP subfolder
    ep_storyboard_dir = None
    if ep:
        ep_val_clean = ep.strip().lower()
        subdirs_story = [d for d in storyboard_dir.iterdir() if d.is_dir()] if storyboard_dir.exists() else []
        try:
            ep_num = int(ep_val_clean)
            candidates = [f"ep{ep_num:02d}", f"ep{ep_num}", f"episode{ep_num}"]
        except ValueError:
            candidates = [ep_val_clean]
            
        for d in subdirs_story:
            name = d.name.lower()
            if any(c == name or name.startswith(c + " ") or name.startswith(c + "-") for c in candidates):
                ep_storyboard_dir = d
                break
                
        if not ep_storyboard_dir:
            for d in subdirs_story:
                if ep_val_clean in d.name.lower():
                    ep_storyboard_dir = d
                    break
                    
    if not ep_storyboard_dir:
        try:
            ep_num = int(ep.strip())
            ep_folder = f"EP{ep_num:02d}"
        except Exception:
            if not ep.lower().startswith("ep"):
                ep_folder = f"EP{ep}"
            else:
                ep_folder = ep.upper()
        ep_storyboard_dir = storyboard_dir / ep_folder
        
    return str(ep_storyboard_dir)


@router.post("/generate-image-batch")
async def generate_image_batch(body: GenerateImageBatchRequest):
    """Generate image(s) on Google Flow via the Extension, download them locally, and store media IDs."""
    import os
    import json
    import base64
    import mimetypes
    import logging
    import httpx
    import re

    logger = logging.getLogger(__name__)
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")

    character_media_ids = []
    # If folder settings are provided, resolve reference images
    if body.reference_images:
        images_dir = ""
        if body.target_directory:
            images_dir = body.target_directory
        elif body.local_path and body.folder_name:
            match = re.match(r"ton_(.+)_ep_(.+)", body.folder_name)
            if match:
                images_dir = resolve_storyboard_dir(body.local_path, match.group(1), match.group(2))
            if not images_dir:
                images_dir = os.path.join(body.local_path, body.folder_name, "Images")

        if images_dir:
            os.makedirs(images_dir, exist_ok=True)
            meta_path = os.path.join(images_dir, "flow_media_ids.json")

        for ref_img in body.reference_images:
            ref_path = ref_img
            if not os.path.isabs(ref_path):
                ref_path = os.path.join(images_dir, ref_img)

            if os.path.isfile(ref_path):
                filename = os.path.basename(ref_path)
                cached_id = None
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            if filename in meta:
                                cached_id = meta[filename]
                    except Exception:
                        pass

                if cached_id:
                    character_media_ids.append(cached_id)
                    logger.info("Using cached reference media ID for %s: %s", filename, cached_id)
                else:
                    try:
                        with open(ref_path, "rb") as f:
                            img_bytes = f.read()
                        b64 = base64.b64encode(img_bytes).decode()
                        mime = mimetypes.guess_type(ref_path)[0] or "image/png"
                        upload_res = await client.upload_image(
                            b64, mime_type=mime, project_id=body.project_id, file_name=filename
                        )
                        mid = upload_res.get("_mediaId")
                        if mid:
                            character_media_ids.append(mid)
                            logger.info("Uploaded reference image %s, got media ID: %s", filename, mid)
                    except Exception as e:
                        logger.error("Failed to upload reference image %s: %s", filename, e)

    # Call client generate_images
    result = await client.generate_images(
        prompt=body.prompt,
        project_id=body.project_id,
        aspect_ratio=body.aspect_ratio,
        user_paygate_tier=body.user_paygate_tier,
        character_media_ids=character_media_ids or None,
        model_name=body.model_name,
        quantity=body.quantity
    )

    if result.get("error") or (isinstance(result.get("status"), int) and result["status"] >= 400):
        raise HTTPException(result.get("status", 502), result.get("error", result.get("data")))

    data = result.get("data", result)
    media_list = data.get("media", [])
    if not media_list:
        return {"success": False, "message": "No media returned from Flow API"}

    downloaded_media = []
    images_dir = ""
    if body.target_directory:
        images_dir = body.target_directory
    elif body.local_path and body.folder_name:
        match = re.match(r"ton_(.+)_ep_(.+)", body.folder_name)
        if match:
            images_dir = resolve_storyboard_dir(body.local_path, match.group(1), match.group(2))
        if not images_dir:
            images_dir = os.path.join(body.local_path, body.folder_name, "Images")

    if images_dir:
        os.makedirs(images_dir, exist_ok=True)
        meta_path = os.path.join(images_dir, "flow_media_ids.json")

        async with httpx.AsyncClient() as http_client:
            for idx, item in enumerate(media_list):
                name = item.get("name", "")
                gen = item.get("image", {}).get("generatedImage", {})
                media_id = gen.get("mediaId", name)

                # Fetch url
                url = None
                for url_field in ("fifeUrl", "imageUri"):
                    u = gen.get(url_field, "")
                    if u:
                        url = u
                        break

                if not url:
                    continue

                # Determine filename
                if body.round_num == 1 and body.quantity == 1:
                    filename = f"{body.prompt_index:02d}.png"
                else:
                    filename = f"R{body.round_num}_{body.prompt_index:02d}_{idx + 1}.png"

                output_path = os.path.join(images_dir, filename)
                try:
                    resp = await http_client.get(url, timeout=30.0)
                    if resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        logger.info("Saved generated image: %s", output_path)

                        # Cache media ID mapping
                        meta = {}
                        if os.path.isfile(meta_path):
                            try:
                                with open(meta_path, "r", encoding="utf-8") as f:
                                    meta = json.load(f)
                            except Exception:
                                pass
                        meta[filename] = media_id
                        with open(meta_path, "w", encoding="utf-8") as f:
                            json.dump(meta, f, ensure_ascii=False, indent=2)

                        downloaded_media.append({
                            "filename": filename,
                            "media_id": media_id,
                            "url": url
                        })
                except Exception as e:
                    logger.error("Failed to download image from %s: %s", url, e)

    return {
        "success": True,
        "media": downloaded_media,
        "_mock_received_character_media_ids": result.get("_mock_received_character_media_ids")
    }


@router.get("/image-models")
async def get_flow_image_models():
    """Returns detected Google Flow image models parsed from TRPC intercepts, or defaults."""
    import os
    import json
    
    # Default fallback models
    default_models = [
        {"value": "GEM_PIX_2", "label": "nano banana pro (GEM_PIX_2)"},
        {"value": "NARWHAL", "label": "nano banana 2 (NARWHAL)"}
    ]
    
    intercept_path = str(get_repo_dir() / "web" / "flow_models_intercept.json")
    if not os.path.exists(intercept_path):
        return {"models": default_models}
        
    try:
        with open(intercept_path, "r", encoding="utf-8") as f:
            intercept_data = json.load(f)
            raw_data = intercept_data.get("data", {})
            
            # Use our recursive parser to extract any available image models
            extracted = parse_models_from_json(raw_data)
            
            if extracted:
                # Merge defaults and extracted models, ensuring unique by value
                all_models = {m["value"]: m for m in default_models}
                for m in extracted:
                    all_models[m["value"]] = m
                return {"models": list(all_models.values())}
    except Exception as e:
        logger.warning("Failed to parse flow_models_intercept.json: %s", e)
        
    return {"models": default_models}

def parse_models_from_json(data):
    models = []
    seen_keys = set()
    
    def traverse(node):
        if isinstance(node, dict):
            model_key = None
            display_name = None
            for k in ["modelId", "modelName", "modelKey", "model", "id"]:
                if k in node and isinstance(node[k], str):
                    val = node[k].strip()
                    # Filter out general keys, check if uppercase and looks like a model key
                    if val.isupper() and len(val) > 3 and not val.startswith("VIDEO_") and not val.startswith("VEO_") and not val.startswith("UPSCALE_"):
                        model_key = val
                        break
            
            if model_key:
                for k in ["displayName", "name", "label", "title"]:
                    if k in node and isinstance(node[k], str):
                        display_name = node[k].strip()
                        break
                
                # Normalize display name to match web UI if it matches known keys
                if display_name == "NANO_BANANA_PRO" or model_key == "GEM_PIX_2" and (not display_name or display_name == "GEM_PIX_2"):
                    display_name = "nano banana pro"
                elif display_name == "NANO_BANANA_2" or model_key == "NARWHAL" and (not display_name or display_name == "NARWHAL"):
                    display_name = "nano banana 2"
                elif model_key.endswith("_LITE") and not display_name:
                    display_name = "nano banana 2 lite"
                
                if model_key not in seen_keys:
                    seen_keys.add(model_key)
                    label = f"{display_name} ({model_key})" if display_name else model_key
                    models.append({"value": model_key, "label": label})
            
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
                
    traverse(data)
    return models


@router.post("/generate-video-batch")
@router.post("/run-video-batch")
async def run_video_batch_endpoint(body: RunVideoBatchRequest):
    """Universal 6969 Batch Video Generation Engine:
    Phase 1: Full-EP Bulk Dispatch (all prompts queued rapidly without stopping)
    Phase 2: Bulk Monitor & Collect (concurrent rendering wait & download)
    Phase 3: Filter Audit & Batch Sanitization (scans for failed/moderated scenes)
    Phase 4: Bulk Retry Dispatch (re-queues all sanitized scenes in a single pass)
    """
    import asyncio
    from scripts.flow_batch_runner import run_bulk_video_pipeline

    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    scenes_data = [s.model_dump() for s in body.scenes]

    result = await asyncio.to_thread(
        run_bulk_video_pipeline,
        scenes_data=scenes_data,
        api_base="http://127.0.0.1:6969",
        project_id=body.project_id or "21a1632e-9926-46fa-954c-240d71d78f41",
        aspect_ratio=body.aspect_ratio,
        delay=body.delay_between_dispatches,
        timeout=body.timeout_seconds,
        auto_retry_filters=body.auto_retry_filters
    )
    return result


class FlowSettingsRequest(BaseModel):
    mode: str = "image"
    aspect_ratio: str = "9:16"
    model: Optional[str] = None
    output_count: int = 1
    duration: Optional[int] = 6
    submode: Optional[str] = "เฟรม"
    project_id: Optional[str] = None


@router.get("/settings")
async def get_flow_settings_endpoint(project_id: Optional[str] = None):
    """Inspects and returns active settings directly from Google Flow UI."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")
    if project_id:
        await _ensure_project_id(client, project_id)

    js_code = """(() => {
        const btn = document.querySelector('button.settings-trigger-button') ||
                    document.querySelector('flow-prompt-box button.settings-trigger-button') ||
                    document.querySelector('button[aria-label*="ตั้งค่า"]') ||
                    document.querySelector('button[aria-label*="Settings trigger"]') ||
                    document.querySelector('button[aria-label*="Settings"]');
        if (!btn) return { success: false, error: "Settings trigger button not found" };

        const text = (btn.innerText || '').toLowerCase();
        const pb = document.querySelector('flow-prompt-box');
        const pbText = pb ? (pb.innerText || '').toLowerCase() : '';
        const isVideo = text.includes('video') || text.includes('วิดีโอ') || text.includes('720p') || text.includes('1080p');

        return {
            success: true,
            mode: isVideo ? "video" : "image",
            raw_text: btn.innerText.split(String.fromCharCode(10)).join(" | "),
            prompt_box_hint: pbText.slice(0, 100),
            active_video_model: window.__flow_video_model || null,
            active_image_model: window.__flow_model || null
        };
    })()"""
    try:
        res = await _eval_js_internal(client, js_code, timeout=10)
        return res
    except Exception as e:
        raise HTTPException(500, f"Failed to inspect settings: {e}")


@router.post("/settings")
@router.post("/configure-settings")
async def configure_flow_settings_endpoint(body: FlowSettingsRequest):
    """Unified Flow Settings Engine:
    Configures and locks any settings combination for Google Flow (both Image and Video).
    Supports aspect ratios (9:16, 16:9, 1:1, 4:3, 3:4), models, duration, output count, and submodes.
    """
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    if body.project_id:
        await _ensure_project_id(client, body.project_id)

    raw_mode = (body.mode or "image").strip().lower()
    if any(w in raw_mode for w in ["video", "vid", "วิดีโอ", "คลิป"]):
        target_mode = "video"
    else:
        target_mode = "image"

    raw_aspect = (body.aspect_ratio or "9:16").strip()
    if "16:9" in raw_aspect or "landscape" in raw_aspect.lower() or "แนวนอน" in raw_aspect:
        target_aspect = "16:9"
        target_crop = "crop_16_9"
    elif "1:1" in raw_aspect or "square" in raw_aspect.lower() or "สี่เหลี่ยม" in raw_aspect:
        target_aspect = "1:1"
        target_crop = "crop_square"
    elif "4:3" in raw_aspect:
        target_aspect = "4:3"
        target_crop = "crop_4_3"
    elif "3:4" in raw_aspect:
        target_aspect = "3:4"
        target_crop = "crop_3_4"
    else:
        target_aspect = "9:16"
        target_crop = "crop_9_16"

    target_count = max(1, min(4, int(body.output_count or 1)))
    target_dur = int(body.duration) if body.duration else (6 if target_mode == "video" else 0)

    raw_sub = (body.submode or "เฟรม").strip().lower()
    if any(w in raw_sub for w in ["text", "ข้อความ", "txt"]):
        target_submode = "ข้อความ"
    elif any(w in raw_sub for w in ["ingredient", "ส่วนผสม"]):
        target_submode = "ส่วนผสม"
    else:
        target_submode = "เฟรม"

    if body.model:
        target_model = body.model.strip().lower()
    else:
        target_model = "lower priority" if target_mode == "video" else "nano banana pro"

    js_code = f"""(async () => {{
        const btn = document.querySelector('button.settings-trigger-button') ||
                    document.querySelector('flow-prompt-box button.settings-trigger-button') ||
                    document.querySelector('button[aria-label*="ตั้งค่า"]') ||
                    document.querySelector('button[aria-label*="Settings trigger"]') ||
                    document.querySelector('button[aria-label*="Settings"]') ||
                    document.querySelector('button[aria-label*="ทริกเกอร์การตั้งค่า"]');
        if (!btn) return {{ success: false, error: "Settings trigger button not found" }};

        const targetMode = "{target_mode}";
        const targetAspect = "{target_aspect}";
        const targetCrop = "{target_crop}";
        const targetCount = {target_count};
        const targetDur = {target_dur};
        const targetSubmode = "{target_submode}".toLowerCase();
        const targetModel = "{target_model}".toLowerCase();

        // 1. Pre-check if already configured
        const btnText = (btn.innerText || '').toLowerCase();
        const pb = document.querySelector('flow-prompt-box');
        const pbText = pb ? (pb.innerText || '').toLowerCase() : '';

        let isModeMatch = false;
        if (targetMode === 'image') {{
            isModeMatch = !btnText.includes('วิดีโอ') && !btnText.includes('video') && !btnText.includes('720p') && !btnText.includes('1080p');
        }} else {{
            isModeMatch = btnText.includes('วิดีโอ') || btnText.includes('video') || btnText.includes('720p') || btnText.includes('1080p');
        }}

        const isAspectMatch = btnText.includes(targetAspect.toLowerCase()) || (targetCrop && btnText.includes(targetCrop.toLowerCase()));
        const countStr = 'x' + targetCount;
        const isCountMatch = btnText.includes(countStr) || btnText.includes(targetCount + ' เอาต์พุต') || btnText.includes(targetCount + ' output') || targetCount === 1;

        let isSubmodeMatch = true;
        let isDurationMatch = true;
        let isModelMatch = true;

        if (targetMode === 'video') {{
            if (targetSubmode.includes('เฟรม') || targetSubmode.includes('frame') || targetSubmode.includes('crop_free')) {{
                isSubmodeMatch = pbText.includes('เริ่ม') || pbText.includes('start') || pbText.includes('เฟรม') || pbText.includes('frames') || (pb && !!pb.querySelector('.chip-container, .start-frame, img'));
            }} else if (targetSubmode.includes('ข้อความ') || targetSubmode.includes('text')) {{
                isSubmodeMatch = !pbText.includes('เริ่ม') && !pbText.includes('start');
            }}
            if (targetDur) {{
                isDurationMatch = btnText.includes(targetDur + ' วินาที') || btnText.includes(targetDur + 's') || btnText.includes(targetDur + ' s');
            }}
            if (targetModel) {{
                isModelMatch = (window.__flow_video_model === targetModel) || btnText.includes(targetModel);
            }}
        }} else {{
            if (targetModel) {{
                isModelMatch = btnText.includes(targetModel) || (window.__flow_model === targetModel);
            }}
        }}

        if (isModeMatch && isAspectMatch && isCountMatch && isSubmodeMatch && isDurationMatch && isModelMatch) {{
            return {{
                success: true,
                alreadyConfigured: true,
                summary: btn.innerText.split(String.fromCharCode(10)).join(" | "),
                mode: targetMode,
                aspect_ratio: targetAspect,
                output_count: targetCount,
                duration: targetDur,
                submode: targetSubmode,
                model: targetModel
            }};
        }}

        // 2. Open settings overlay
        let settings = document.querySelector('flow-prompt-box-settings');
        if (!settings) {{
            btn.click();
            await new Promise(r => setTimeout(r, 400));
            settings = document.querySelector('flow-prompt-box-settings') || document.querySelector('.cdk-overlay-container') || document;
        }}

        const getButtons = () => {{
            return Array.from(settings.querySelectorAll('mat-button-toggle button, button'));
        }};

        // A. Switch Mode (Image vs Video)
        const modeButtons = getButtons();
        if (targetMode === 'image') {{
            const imgBtn = modeButtons.find(el => {{
                const t = (el.innerText || '').toLowerCase();
                return (t.includes('image') || t.includes('รูปภาพ')) && !t.includes('video') && !t.includes('วิดีโอ');
            }});
            if (imgBtn && imgBtn.getAttribute('aria-checked') !== 'true') {{
                imgBtn.click();
                await new Promise(r => setTimeout(r, 300));
            }}
        }} else {{
            const vidBtn = modeButtons.find(el => {{
                const t = (el.innerText || '').toLowerCase();
                return (t.includes('video') || t.includes('วิดีโอ')) && !t.includes('image') && !t.includes('รูปภาพ');
            }});
            if (vidBtn && vidBtn.getAttribute('aria-checked') !== 'true') {{
                vidBtn.click();
                await new Promise(r => setTimeout(r, 300));
            }}
        }}

        // B. Submode (Video only)
        if (targetMode === 'video' && targetSubmode) {{
            const subButtons = getButtons();
            const subBtn = subButtons.find(el => {{
                const t = (el.innerText || '').toLowerCase();
                if (targetSubmode.includes('เฟรม') || targetSubmode.includes('frame') || targetSubmode.includes('crop_free')) {{
                    return t.includes('เฟรม') || t.includes('frames') || t.includes('crop_free');
                }}
                if (targetSubmode.includes('ข้อความ') || targetSubmode.includes('text')) {{
                    return t.includes('ข้อความ') || t.includes('text') || t.includes('text_fields');
                }}
                if (targetSubmode.includes('ส่วนผสม') || targetSubmode.includes('ingredient')) {{
                    return t.includes('ส่วนผสม') || t.includes('ingredients') || t.includes('chrome_extension');
                }}
                return false;
            }});
            if (subBtn && subBtn.getAttribute('aria-checked') !== 'true') {{
                subBtn.click();
                await new Promise(r => setTimeout(r, 200));
            }}
        }}

        // C. Aspect Ratio
        if (targetAspect) {{
            const aspectButtons = getButtons();
            const aspectBtn = aspectButtons.find(el => {{
                const t = (el.innerText || '').toLowerCase();
                return t.includes(targetAspect.toLowerCase()) || (targetCrop && t.includes(targetCrop.toLowerCase()));
            }});
            if (aspectBtn && aspectBtn.getAttribute('aria-checked') !== 'true') {{
                aspectBtn.click();
                await new Promise(r => setTimeout(r, 200));
            }}
        }}

        // D. Duration (Video only)
        if (targetMode === 'video' && targetDur) {{
            const durButtons = getButtons();
            const durBtn = durButtons.find(el => {{
                const t = (el.innerText || '').trim();
                return (t === targetDur + 's' || t.includes(targetDur + 's') || t.includes(targetDur + ' วินาที')) && !t.includes('16');
            }});
            if (durBtn && durBtn.getAttribute('aria-checked') !== 'true') {{
                durBtn.click();
                await new Promise(r => setTimeout(r, 200));
            }}
        }}

        // E. Output Count
        if (targetCount) {{
            const countButtons = getButtons();
            const countBtn = countButtons.find(el => {{
                const t = (el.innerText || '').trim().toLowerCase();
                return t === countStr.toLowerCase() || t === String(targetCount) || t.includes(countStr.toLowerCase());
            }});
            if (countBtn && countBtn.getAttribute('aria-checked') !== 'true') {{
                countBtn.click();
                await new Promise(r => setTimeout(r, 200));
            }}
        }}

        // F. Model Selection
        if (targetModel) {{
            if (targetMode === 'image') {{
                const modelTrigger = settings.querySelector('button[aria-label*="เลือกกลุ่มผลิตภัณฑ์โมเดล"]') ||
                                     settings.querySelector('button[aria-label*="Select model family"]') ||
                                     settings.querySelector('.mat-mdc-menu-trigger');
                if (modelTrigger && (!modelTrigger.innerText || !modelTrigger.innerText.toLowerCase().includes(targetModel))) {{
                    modelTrigger.click();
                    await new Promise(r => setTimeout(r, 300));
                    const menuItems = Array.from(document.querySelectorAll('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button'));
                    const targetItem = menuItems.find(m => (m.innerText || '').toLowerCase().includes(targetModel));
                    if (targetItem) {{
                        targetItem.click();
                        await new Promise(r => setTimeout(r, 200));
                    }}
                }}
                window.__flow_model = targetModel;
            }} else if (targetMode === 'video') {{
                const modelTrigger = Array.from(settings.querySelectorAll('button')).find(b => {{
                    const t = (b.innerText || '').toLowerCase();
                    return t.indexOf('veo') !== -1 || t.indexOf('priority') !== -1 || t.indexOf('lower') !== -1 || t.indexOf('omni') !== -1;
                }});
                if (modelTrigger) {{
                    const isLower = targetModel.includes('lower');
                    if (!modelTrigger.innerText || (isLower && !modelTrigger.innerText.toLowerCase().includes('lower priority'))) {{
                        modelTrigger.click();
                        await new Promise(r => setTimeout(r, 350));
                        const menuItems = Array.from(document.querySelectorAll('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button')).filter(x => x.getAttribute('role') === 'menuitem');
                        const targetItem = isLower ?
                            (menuItems.find(m => (m.innerText || '').toLowerCase().includes('lower priority')) || menuItems[menuItems.length - 1]) :
                            menuItems.find(m => (m.innerText || '').toLowerCase().includes(targetModel));
                        if (targetItem) {{
                            targetItem.click();
                            await new Promise(r => setTimeout(r, 300));
                        }}
                    }}
                }}
                window.__flow_video_model = targetModel;
            }}
        }}

        // G. Close Overlay
        const backdrop = document.querySelector('.cdk-overlay-backdrop');
        if (backdrop) backdrop.click();
        else btn.click();
        await new Promise(r => setTimeout(r, 350));

        // H. Final Verification
        const finalBtn = document.querySelector('button.settings-trigger-button') ||
                         document.querySelector('flow-prompt-box button.settings-trigger-button') ||
                         document.querySelector('button[aria-label*="ตั้งค่า"]') ||
                         document.querySelector('button[aria-label*="Settings"]');
        const finalText = finalBtn ? finalBtn.innerText.split(String.fromCharCode(10)).join(" | ") : '';

        return {{
            success: true,
            alreadyConfigured: false,
            summary: finalText,
            mode: targetMode,
            aspect_ratio: targetAspect,
            output_count: targetCount,
            duration: targetDur,
            submode: targetSubmode,
            model: targetModel
        }};
    }})()"""

    try:
        res = await _eval_js_internal(client, js_code, timeout=25)
        if isinstance(res, dict) and res.get("success"):
            return res
        return {
            "success": False,
            "error": res.get("error") if isinstance(res, dict) else "Unknown script error",
            "details": res
        }
    except Exception as e:
        logger.error("Failed to configure Flow settings: %s", e)
        raise HTTPException(500, f"Failed to configure Flow settings: {e}")
