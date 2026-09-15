"""Direct Flow API endpoints — for manual operations outside the queue."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent.services.flow_client import get_flow_client

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
    start_image_media_id: str
    prompt: str
    project_id: str
    scene_id: str
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT"
    end_image_media_id: Optional[str] = None
    user_paygate_tier: str = "PAYGATE_TIER_ONE"


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


@router.post("/cdp-type-text")
async def cdp_type_text(body: CdpTypeTextRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")
    return await client._send("flow_cdp_type_text", {
        "text": body.text,
        "clickSubmit": body.click_submit,
    }, timeout=30)


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
