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


@router.post("/generate-image-batch")
async def generate_image_batch(body: GenerateImageBatchRequest):
    """Generate image(s) on Google Flow via the Extension, download them locally, and store media IDs."""
    import os
    import json
    import base64
    import mimetypes
    import logging
    import httpx

    logger = logging.getLogger(__name__)
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")

    character_media_ids = []
    # If folder settings are provided, resolve reference images
    if body.reference_images and body.local_path and body.folder_name:
        images_dir = os.path.join(body.local_path, body.folder_name, "Images")
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
                            # Save to metadata JSON
                            meta = {}
                            if os.path.isfile(meta_path):
                                try:
                                    with open(meta_path, "r", encoding="utf-8") as f:
                                        meta = json.load(f)
                                except Exception:
                                    pass
                            meta[filename] = mid
                            with open(meta_path, "w", encoding="utf-8") as f:
                                json.dump(meta, f, ensure_ascii=False, indent=2)
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
    if body.local_path and body.folder_name:
        images_dir = os.path.join(body.local_path, body.folder_name, "Images")
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

    return {"success": True, "media": downloaded_media}
