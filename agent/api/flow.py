"""Direct Flow API endpoints — for manual operations outside the queue."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent.services.flow_client import get_flow_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/flow", tags=["flow"])


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
    import subprocess, asyncio
    as_script = '''
    tell application "Google Chrome" to activate
    '''
    await asyncio.to_thread(subprocess.run, ["osascript", "-e", as_script], check=False)
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

    # 1. Ensure tab is at the requested project_id
    if body.project_id:
        try:
            current_url = str(await eval_js("window.location.href") or "")
            if body.project_id not in current_url:
                m = re.match(r"(https?://[^/]+(?:/u/\d+)?/(?:project/|tools/flow/project/))", current_url)
                prefix = m.group(1) if m else "https://flow.google.com/project/"
                target_url = prefix + body.project_id
                logger.info("Switching Google Flow project to: %s", target_url)
                await eval_js(f"window.location.href = '{target_url}';")
                await asyncio.sleep(5.0)
        except Exception as e:
            logger.warning("Project lock check warning: %s", e)

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

    get_existing_js = """(() => {
        const popover = document.querySelector('flow-add-menu-popover-content');
        if (!popover) return [];
        const items = Array.from(popover.querySelectorAll('button.asset-item, flow-add-menu-asset-item, .asset-item'));
        return items.map(el => (el.innerText || '').trim()).filter(Boolean);
    })()"""
    existing_names = await eval_js(get_existing_js) or []

    # Close popover
    await eval_js("""(() => {
        const backdrop = document.querySelector('.cdk-overlay-backdrop');
        if (backdrop) backdrop.click();
    })()""")
    await asyncio.sleep(0.3)

    already_exists = []
    missing_targets = []
    for p in targets:
        fname = os.path.basename(p)
        if any(fname in existing_name for existing_name in existing_names):
            already_exists.append(fname)
        else:
            missing_targets.append(p)

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
    timeout: int = 60



class DispatchStoryboardPromptRequest(BaseModel):
    prompt: str
    project_id: str = "21a1632e-9926-46fa-954c-240d71d78f41"
    aspect_ratio: str = "9:16"
    reference_images: Optional[list[str]] = None
    wait_after_submit: float = 2.0


class ExpectedBatchScene(BaseModel):
    scene_num: int
    prompt: str
    output_path: str
    reference_images: Optional[list[str]] = None


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


async def _ensure_project_id(client, project_id: str):
    if not project_id:
        return
    import asyncio, re
    try:
        current_url = str(await _eval_js_internal(client, "window.location.href") or "")
        if project_id not in current_url:
            m = re.match(r"(https?://[^/]+(?:/u/\d+)?/(?:project/|tools/flow/project/))", current_url)
            prefix = m.group(1) if m else "https://flow.google.com/project/"
            target_url = prefix + project_id
            logger.info("Switching Google Flow project to: %s", target_url)
            await _eval_js_internal(client, f"window.location.href = '{target_url}';")
            await asyncio.sleep(5.0)
    except Exception as e:
        logger.warning("Project lock check warning: %s", e)


async def _submit_flow_prompt_internal(
    client,
    prompt: str,
    project_id: str,
    aspect_ratio: str = "9:16",
    reference_images: Optional[list[str]] = None,
    wait_after_submit: float = 2.0
):
    import asyncio, os, base64, mimetypes

    # 0. Ensure project lock
    await _ensure_project_id(client, project_id)

    # 1. Clear existing chips and prompt text
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
    await _eval_js_internal(client, clear_js)
    await asyncio.sleep(0.4)

    # 2. Attach reference images if provided
    if reference_images:
        for ref_img_path in reference_images:
            if not ref_img_path or not os.path.isfile(ref_img_path):
                continue
            filename = os.path.basename(ref_img_path)
            c_name = filename.split(" - ")[0]
            filename_no_ext = os.path.splitext(filename)[0]

            open_menu_js = """(() => {
                let popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) {
                    const trigger = document.querySelector('button.add-menu-trigger') ||
                                    Array.from(document.querySelectorAll('button')).find(b => (b.getAttribute('aria-label')||'').includes('เพิ่มองค์ประกอบ'));
                    if (trigger) { trigger.click(); return true; }
                    return false;
                }
                return true;
            })()"""
            await _eval_js_internal(client, open_menu_js)
            await asyncio.sleep(0.6)

            filter_img_js = """(() => {
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return false;
                const navItems = Array.from(popover.querySelectorAll('mat-list-item, .mat-mdc-list-item'));
                const imgNav = navItems.find(el => (el.innerText || '').includes('รูปภาพ') || (el.innerText || '').toLowerCase().includes('image'));
                if (imgNav) { imgNav.click(); return true; }
                return false;
            })()"""
            await _eval_js_internal(client, filter_img_js)
            await asyncio.sleep(0.6)

            search_item_js = f"""(() => {{
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return false;
                const searchInput = popover.querySelector('input.search-input');
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
            await asyncio.sleep(0.4)

            find_item_js = f"""(() => {{
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return false;
                const items = Array.from(popover.querySelectorAll('button.asset-item, flow-add-menu-asset-item, .asset-item'));
                return items.some(el => {{
                    const t = (el.innerText || '').trim();
                    return t.includes("{filename}") || t.includes("{filename_no_ext}");
                }});
            }})()"""
            asset_exists = await _eval_js_internal(client, find_item_js)

            if not asset_exists:
                await _eval_js_internal(client, """(() => {
                    const backdrop = document.querySelector('.cdk-overlay-backdrop');
                    if (backdrop) backdrop.click();
                })()""")
                await asyncio.sleep(0.3)
                try:
                    with open(ref_img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    mime = mimetypes.guess_type(ref_img_path)[0] or "image/png"
                    await client.upload_image(b64, mime_type=mime, project_id=project_id, file_name=filename)
                    await _eval_js_internal(client, "window.location.reload();")
                    await asyncio.sleep(4.5)
                except Exception:
                    pass

                await _eval_js_internal(client, open_menu_js)
                await asyncio.sleep(0.6)
                await _eval_js_internal(client, filter_img_js)
                await asyncio.sleep(0.6)
                await _eval_js_internal(client, search_item_js)
                await asyncio.sleep(0.4)

            click_item_js = f"""(() => {{
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) return {{ error: 'popover not found' }};
                const items = Array.from(popover.querySelectorAll('button.asset-item, flow-add-menu-asset-item, .asset-item'));
                let target = items.find(el => {{
                    const t = (el.innerText || '').trim();
                    return t.includes("{filename}") || t.includes("{filename_no_ext}");
                }});
                if (!target) {{
                    target = items.find(el => {{
                        const t = (el.innerText || '').trim();
                        return t.includes("{c_name}");
                    }});
                }}
                if (!target && items.length > 0) {{
                    target = items[0];
                }}
                if (target) {{
                    const btn = target.querySelector('button') || target;
                    btn.click();
                    return {{ ok: true, name: (target.innerText || '').trim() }};
                }}
                return {{ error: 'item not found' }};
            }})()"""
            await _eval_js_internal(client, click_item_js)
            await asyncio.sleep(0.8)

            add_prompt_js = """(() => {
                const addBtn = document.querySelector('flow-add-menu-detail-pane button.detail-add-to-prompt-btn') ||
                               Array.from(document.querySelectorAll('.cdk-overlay-container button')).find(b => (b.innerText || '').includes('เพิ่มไปยังพรอมต์') || (b.innerText || '').includes('Add to prompt'));
                if (addBtn) {
                    addBtn.click();
                    return { clicked: true };
                }
                return { clicked: false };
            })()"""
            await _eval_js_internal(client, add_prompt_js)
            await asyncio.sleep(0.8)

            close_popover_js = """(() => {
                const backdrop = document.querySelector('.cdk-overlay-backdrop');
                if (backdrop) backdrop.click();
                return true;
            })()"""
            await _eval_js_internal(client, close_popover_js)
            await asyncio.sleep(0.5)

    # 3. Submit prompt via CDP with aspect ratio
    cdp_res = await client._send("flow_cdp_type_text", {
        "text": prompt,
        "clickSubmit": True,
        "outputCount": 1,
        "aspectRatio": aspect_ratio
    }, timeout=45)

    if not cdp_res.get("clicked"):
        await _eval_js_internal(client, """(() => {
            const btn = document.querySelector('.generate-icon-button') || document.querySelector('button[aria-label="เริ่มสร้าง"]');
            if (btn && !btn.classList.contains('mat-mdc-button-disabled')) btn.click();
        })()""")

    # 4. Wait for Google Flow to queue the prompt
    if wait_after_submit > 0:
        await asyncio.sleep(wait_after_submit)


def _match_batch_tiles_to_scenes(scenes: list, new_tiles: list) -> list:
    """Matches newly generated image tiles to scene requests using keyword scoring + DOM reverse-order fallback."""
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
        sc_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", sc_prompt.lower())) - boilerplate_words
        row = []
        for j, tl in enumerate(new_tiles):
            tl_footer = tl.get("footer_title", "")
            tl_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", tl_footer.lower()))
            overlap = len(sc_words.intersection(tl_words))
            # Expected DOM index for scene i: Google Flow prepends tiles, so earliest submitted scene (index 0) finishes earlier (higher index)
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


@router.get("/snapshot-existing-tiles")
async def snapshot_existing_tiles():
    """Returns list of currently rendered image URLs and media IDs in Google Flow tab."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    snap_js = """(() => {
        const tiles = Array.from(document.querySelectorAll('flow-image-tile'));
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
        return { urls: urls, media_ids: mediaIds, count: tiles.length };
    })()"""
    res = await _eval_js_internal(client, snap_js)
    return {
        "success": True,
        "urls": res.get("urls", []) if isinstance(res, dict) else [],
        "media_ids": res.get("media_ids", []) if isinstance(res, dict) else [],
        "count": res.get("count", 0) if isinstance(res, dict) else 0
    }


@router.post("/dispatch-storyboard-prompt")
async def dispatch_storyboard_prompt(body: DispatchStoryboardPromptRequest):
    """Submits a single prompt into Google Flow queue without blocking on render completion."""
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    await _submit_flow_prompt_internal(
        client=client,
        prompt=body.prompt,
        project_id=body.project_id,
        aspect_ratio=body.aspect_ratio,
        reference_images=body.reference_images,
        wait_after_submit=body.wait_after_submit
    )

    return {
        "success": True,
        "dispatched": True,
        "prompt_preview": body.prompt[:80]
    }


@router.post("/collect-storyboard-batch")
async def collect_storyboard_batch(body: CollectStoryboardBatchRequest):
    """Waits for Google Flow pending queue to finish and downloads batch images matched to scenes."""
    import asyncio, time, httpx, os

    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "FlowKit extension not connected")

    known_urls = set(body.known_existing_urls or [])
    known_media_ids = set(body.known_existing_media_ids or [])

    start_time = time.time()
    consecutive_zero_pending = 0
    poll_status = {}

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
                return {
                    src: img ? img.src : '',
                    media_id: img ? (img.getAttribute('data-media-id') || '') : '',
                    footer_title: footer ? (footer.innerText || '').trim() : '',
                    is_outfit: (t.innerText || '').includes('Outfit 1') || (t.innerText || '').includes('Outfit 2') || (t.innerText || '').includes('Outfit 3')
                };
            }).filter(t => t.src && !t.is_outfit);

            return {
                pendingCount: pending.length,
                pendingPcts: pending.map(p => (p.innerText || '').match(/(\\d+)%/)?.[1]).filter(Boolean),
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

        if pending_count == 0:
            consecutive_zero_pending += 1
            if len(new_tiles) >= len(body.scenes) or consecutive_zero_pending >= 2:
                logger.info("Batch rendering complete! Found %d new tiles for %d expected scenes.", len(new_tiles), len(body.scenes))
                break
        else:
            consecutive_zero_pending = 0

    tiles = poll_status.get("tiles") or []
    new_tiles = [
        t for t in tiles
        if (t.get("src") not in known_urls) and (not t.get("media_id") or t.get("media_id") not in known_media_ids)
    ]

    matched_pairs = _match_batch_tiles_to_scenes([s.dict() for s in body.scenes], new_tiles)

    results = []
    matched_scene_nums = set()

    async with httpx.AsyncClient(follow_redirects=True) as http_client:
        for sc, tl in matched_pairs:
            sc_num = sc.get("scene_num")
            matched_scene_nums.add(sc_num)
            out_path = sc.get("output_path")
            img_url = tl.get("src")
            footer_title = tl.get("footer_title")

            if out_path and img_url:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                try:
                    resp = await http_client.get(img_url, timeout=30.0)
                    if resp.status_code == 200 and is_valid_image_bytes(resp.content):
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        logger.info("Saved batch image for Scene %02d to %s", sc_num, out_path)
                        results.append({
                            "scene_num": sc_num,
                            "success": True,
                            "output_path": out_path,
                            "footer_title": footer_title,
                            "image_url": img_url
                        })
                    elif resp.status_code == 200 and not is_valid_image_bytes(resp.content):
                        results.append({
                            "scene_num": sc_num,
                            "success": False,
                            "error": f"Downloaded content is not a valid image ({len(resp.content)} bytes, HTML redirect or corrupt)"
                        })
                    else:
                        results.append({
                            "scene_num": sc_num,
                            "success": False,
                            "error": f"CDN returned HTTP {resp.status_code}"
                        })
                except Exception as dl_err:
                    results.append({
                        "scene_num": sc_num,
                        "success": False,
                        "error": str(dl_err)
                    })

    for s in body.scenes:
        if s.scene_num not in matched_scene_nums:
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

    # 1. Snapshot existing tiles before submitting prompt to guarantee only newly generated tiles are accepted
    snap_js = """(() => {
        const tiles = Array.from(document.querySelectorAll('flow-image-tile'));
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
                    media_id: img ? (img.getAttribute('data-media-id') || '') : '',
                    is_outfit: (t.innerText || '').includes('Outfit 1') || (t.innerText || '').includes('Outfit 2') || (t.innerText || '').includes('Outfit 3')
                };
            }).filter(t => t.src && !t.is_outfit);
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

        if pending_count == 0:
            consecutive_zero_pending += 1
            if consecutive_zero_pending >= 2:
                # Pending tile vanished (e.g. user refreshed the tab or Google Flow dropped the task)
                if new_tiles:
                    generated_img_url = new_tiles[0].get("src")
                    break
                raise HTTPException(410, "Pending tile vanished without producing a new image (tab was refreshed or generation aborted). Must re-generate.")
        else:
            consecutive_zero_pending = 0

    if not generated_img_url:
        raise HTTPException(504, f"Image generation timed out after {body.timeout}s without producing a new tile")

    # 4. Download and validate image to output_path if provided
    if body.output_path:
        os.makedirs(os.path.dirname(os.path.abspath(body.output_path)), exist_ok=True)
        async with httpx.AsyncClient(follow_redirects=True) as http_client:
            resp = await http_client.get(generated_img_url, timeout=30.0)
            if resp.status_code == 200:
                if not is_valid_image_bytes(resp.content):
                    raise HTTPException(502, f"Downloaded content from {generated_img_url} is not a valid image file ({len(resp.content)} bytes, HTML redirect or corrupt)")
                with open(body.output_path, "wb") as f:
                    f.write(resp.content)
            else:
                raise HTTPException(502, f"Failed to download image from CDN: status {resp.status_code}")

    return {
        "success": True,
        "image_url": generated_img_url,
        "output_path": body.output_path,
        "aspect_ratio": body.aspect_ratio
    }


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
    
    intercept_path = "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template/web/flow_models_intercept.json"
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
