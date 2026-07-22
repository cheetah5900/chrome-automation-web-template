import os
import base64
import mimetypes
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.services.flow_client import get_flow_client
from agent.db import crud
from agent.sdk.persistence.sqlite_repository import SQLiteRepository

import subprocess
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/batch-uploader", tags=["batch-uploader"])
_repo = SQLiteRepository()


@router.post("/browse-folder")
async def browse_folder():
    """Trigger native macOS folder browser dialog and return selected absolute path."""
    script = 'POSIX path of (choose folder with prompt "Select Folder")'
    try:
        def run_script():
            return subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=60
            )
        
        proc = await asyncio.to_thread(run_script)
        if proc.returncode == 0:
            path = proc.stdout.strip()
            return {"path": path}
        else:
            return {"path": None}
    except Exception as e:
        logger.warning("Folder browser failed: %s", e)
        return {"path": None, "error": str(e)}


@router.get("/flow-projects")
async def get_flow_projects():
    """List projects from Google Flow with fallback to local projects."""
    client = get_flow_client()
    if client.connected:
        try:
            import urllib.parse
            import json
            
            input_params = {
                "json": {
                    "pageSize": 20,
                    "toolName": "PINHOLE",
                    "cursor": None
                },
                "meta": {
                    "values": {
                        "cursor": ["undefined"]
                    }
                }
            }
            encoded_input = urllib.parse.quote(json.dumps(input_params))
            url = f"https://labs.google/fx/api/trpc/project.searchUserProjects?input={encoded_input}"
            
            res = await client._send("trpc_request", {
                "url": url,
                "method": "GET",
                "headers": {
                    "accept": "*/*",
                }
            }, timeout=30)
            
            logger.info("tRPC raw response: %s", res)
            
            trpc_data = res.get("data") if isinstance(res, dict) else res
            if isinstance(trpc_data, dict) and "error" not in trpc_data:
                projects_data = trpc_data.get("result", {}).get("data", {}).get("json", {}).get("result", {}).get("projects", [])
                formatted = []
                for p in projects_data:
                    title = p.get("projectInfo", {}).get("projectTitle") or p.get("projectTitle") or p.get("title") or p.get("name")
                    formatted.append({
                        "id": p.get("projectId") or p.get("id"),
                        "name": title or p.get("projectId") or p.get("id"),
                        "material": p.get("material") or p.get("projectInfo", {}).get("material") or None
                    })
                if formatted:
                    return {"projects": formatted, "source": "google-flow"}
        except Exception as e:
            logger.warning("Failed to fetch projects from Google Flow, falling back to local: %s", e)
            
    # Fallback to local DB
    rows = await crud.list_projects()
    formatted = [{"id": r["id"], "name": r["name"], "material": r.get("material", "3d_pixar")} for r in rows]
    return {"projects": formatted, "source": "local"}


class ScanRequest(BaseModel):
    images_dir: str
    prompts_dir: str


class ProcessPair(BaseModel):
    image_path: str
    prompt_content: str


class ProcessRequest(BaseModel):
    project_id: str
    video_id: Optional[str] = None
    orientation: str  # VERTICAL or HORIZONTAL
    pairs: List[ProcessPair]
    video_model: Optional[str] = None
    duration_seconds: Optional[int] = None
    output_count: Optional[int] = 1


@router.post("/scan")
async def scan_directories(body: ScanRequest):
    images_dir = body.images_dir
    prompts_dir = body.prompts_dir

    logger.info("Scanning request received: images_dir=%s, prompts_dir=%s", images_dir, prompts_dir)

    if not os.path.isdir(images_dir):
        logger.error("Images directory does not exist: %s", images_dir)
        raise HTTPException(400, f"Images directory does not exist: {images_dir}")
    if not os.path.isdir(prompts_dir):
        logger.error("Prompts directory does not exist: %s", prompts_dir)
        raise HTTPException(400, f"Prompts directory does not exist: {prompts_dir}")

    # Scan image files
    img_exts = (".png", ".jpg", ".jpeg", ".webp")
    image_files = []
    try:
        raw_images = os.listdir(images_dir)
        logger.info("Raw images directory listing (%d files): %s", len(raw_images), raw_images)
        for f in raw_images:
            if f.lower().endswith(img_exts):
                image_files.append(f)
    except Exception as e:
        logger.exception("Failed to read images directory")
        raise HTTPException(500, f"Failed to read images directory: {str(e)}")
    image_files.sort()
    logger.info("Filtered & sorted image files (%d files): %s", len(image_files), image_files)

    # Scan prompt files (supporting .txt and .md)
    prompt_exts = (".txt", ".md")
    prompt_files = []
    try:
        raw_prompts = os.listdir(prompts_dir)
        logger.info("Raw prompts directory listing (%d files): %s", len(raw_prompts), raw_prompts)
        for f in raw_prompts:
            if f.lower().endswith(prompt_exts):
                prompt_files.append(f)
    except Exception as e:
        logger.exception("Failed to read prompts directory")
        raise HTTPException(500, f"Failed to read prompts directory: {str(e)}")
    prompt_files.sort()
    logger.info("Filtered & sorted prompt files (%d files): %s", len(prompt_files), prompt_files)

    # Pair them up by name-based matching, falling back to index-based for leftovers
    pairs = []
    
    # 1. Create a dictionary of prompt files for O(1) basename lookup
    # key: lower-case basename, value: filename
    prompt_by_base = {}
    for pf in prompt_files:
        base = os.path.splitext(pf)[0].lower()
        prompt_by_base[base] = pf

    used_prompts = set()
    
    # 2. Match images with prompt files of the same basename
    matched_pairs = []
    unmatched_images = []
    
    for img_name in image_files:
        img_base = os.path.splitext(img_name)[0].lower()
        if img_base in prompt_by_base:
            pf = prompt_by_base[img_base]
            matched_pairs.append((img_name, pf))
            used_prompts.add(pf)
        else:
            unmatched_images.append(img_name)
            
    # 3. Leftover prompts (not matched by basename)
    remaining_prompts = [pf for pf in prompt_files if pf not in used_prompts]
    
    # 4. Combine them:
    # First, the matched pairs
    for img_name, pf in matched_pairs:
        prompt_content = ""
        prompt_path = os.path.join(prompts_dir, pf)
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_content = f.read().strip()
        except Exception as e:
            prompt_content = f"Error reading file: {str(e)}"
            
        pairs.append({
            "index": len(pairs) + 1,
            "image_name": img_name,
            "image_path": os.path.join(images_dir, img_name),
            "prompt_name": pf,
            "prompt_path": prompt_path,
            "prompt_content": prompt_content
        })
        
    # Then, pair any unmatched images with remaining prompts by index
    for i, img_name in enumerate(unmatched_images):
        pf = remaining_prompts[i] if i < len(remaining_prompts) else None
        prompt_content = ""
        prompt_path = None
        if pf:
            prompt_path = os.path.join(prompts_dir, pf)
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    prompt_content = f.read().strip()
            except Exception as e:
                prompt_content = f"Error reading file: {str(e)}"
                
        pairs.append({
            "index": len(pairs) + 1,
            "image_name": img_name,
            "image_path": os.path.join(images_dir, img_name),
            "prompt_name": pf,
            "prompt_path": prompt_path,
            "prompt_content": prompt_content
        })
        
    # Finally, if there are leftover prompts with no images
    if len(remaining_prompts) > len(unmatched_images):
        for pf in remaining_prompts[len(unmatched_images):]:
            prompt_content = ""
            prompt_path = os.path.join(prompts_dir, pf)
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    prompt_content = f.read().strip()
            except Exception as e:
                prompt_content = f"Error reading file: {str(e)}"
                
            pairs.append({
                "index": len(pairs) + 1,
                "image_name": None,
                "image_path": None,
                "prompt_name": pf,
                "prompt_path": prompt_path,
                "prompt_content": prompt_content
            })

    logger.info("Pairing completed. Matched count: %d, Leftover images: %d, Leftover prompts: %d, Total pairs: %d",
                len(matched_pairs), len(unmatched_images), max(0, len(remaining_prompts) - len(unmatched_images)), len(pairs))
    return {"pairs": pairs}


@router.post("/process")
async def process_batch(body: ProcessRequest):
    client = get_flow_client()
    if not client.connected:
        raise HTTPException(503, "Extension not connected")

    results = []
    
    # Verify/create video
    # Verify project exists locally to satisfy SQLite foreign keys
    local_proj = await crud.get_project(body.project_id)
    if not local_proj:
        logger.info("Project %s not found in local DB. Creating it to satisfy SQLite constraints...", body.project_id)
        await crud.create_project(
            id=body.project_id,
            name=f"Synced Project ({body.project_id[:8]})",
            story="Synced from Google Flow",
            material=None
        )

    video_id = body.video_id
    orientation = body.orientation.upper()
    if orientation not in ("VERTICAL", "HORIZONTAL"):
        raise HTTPException(400, f"Invalid orientation: {orientation}")

    if not video_id:
        from datetime import datetime
        title = f"Batch Video ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        sdk_video = await _repo.create_video(
            project_id=body.project_id,
            title=title,
            orientation=orientation
        )
        video_id = sdk_video.id
        logger.info("Auto-created video container: %s (ID: %s)", title, video_id)
    else:
        video = await _repo.get_video(video_id)
        if not video:
            raise HTTPException(404, f"Video not found: {video_id}")

    # Fetch existing scenes to see next display_order
    existing_scenes = await _repo.list_scenes(video_id)
    next_order = len(existing_scenes)

    for i, pair in enumerate(body.pairs):
        if not pair.image_path or not os.path.isfile(pair.image_path):
            results.append({
                "image_path": pair.image_path,
                "status": "FAILED",
                "error": f"Image file not found: {pair.image_path}"
            })
            continue

        try:
            # 1. Read and upload image
            with open(pair.image_path, "rb") as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode()
            mime = mimetypes.guess_type(pair.image_path)[0] or "image/png"
            file_name = os.path.basename(pair.image_path)
            
            logger.info("Uploading batch image: %s", file_name)
            upload_res = await client.upload_image(
                b64, mime_type=mime, project_id=body.project_id, file_name=file_name
            )
            
            if upload_res.get("error") or (isinstance(upload_res.get("status"), int) and upload_res["status"] >= 400):
                error_msg = upload_res.get("error", "Upload failed")
                logger.error("Upload failed for %s: %s", file_name, error_msg)
                results.append({
                    "image_path": pair.image_path,
                    "status": "FAILED",
                    "error": error_msg
                })
                continue
                
            media_id = upload_res.get("_mediaId")
            if not media_id:
                logger.error("No media_id returned for %s: %s", file_name, upload_res)
                results.append({
                    "image_path": pair.image_path,
                    "status": "FAILED",
                    "error": "No media_id returned from upload"
                })
                continue

            # 2. Create scene
            prompt_summary = pair.prompt_content[:100] if pair.prompt_content else f"Batch Scene {next_order}"
            
            # Autoprepending scene material prefix if applicable
            project_row = await crud.get_project(body.project_id)
            if project_row and project_row.get("material"):
                from agent.materials import get_material
                mat = get_material(project_row["material"])
                if mat and mat.get("scene_prefix"):
                    prefix = mat["scene_prefix"]
                    if not prompt_summary.startswith(prefix):
                        prompt_summary = f"{prefix} {prompt_summary}"

            logger.info("Creating scene for display_order %d", next_order)
            sdk_scene = await _repo.create_scene(
                video_id=video_id,
                display_order=next_order,
                prompt=prompt_summary,
                video_prompt=pair.prompt_content,
                chain_type="CONTINUATION" if next_order > 0 else "ROOT",
                source="user"
            )
            next_order += 1

            # 3. Update scene with vertical/horizontal image ID and status
            update_data = {}
            if orientation == "HORIZONTAL":
                update_data = {
                    "horizontal_image_media_id": media_id,
                    "horizontal_image_status": "COMPLETED"
                }
            else:
                update_data = {
                    "vertical_image_media_id": media_id,
                    "vertical_image_status": "COMPLETED"
                }
            await _repo.update("scene", sdk_scene.id, **update_data)

            # 4. Queue GENERATE_VIDEO request
            import json as _json
            params_dict = {
                "video_model": body.video_model,
                "duration_seconds": body.duration_seconds,
                "output_count": body.output_count
            }
            db_req_data = {
                "project_id": body.project_id,
                "video_id": video_id,
                "scene_id": sdk_scene.id,
                "req_type": "GENERATE_VIDEO",
                "orientation": orientation,
                "status": "PENDING",
                "edit_prompt": _json.dumps(params_dict)
            }
            await crud.create_request(**db_req_data)
            
            logger.info("Queued video request for scene %s", sdk_scene.id)

            results.append({
                "image_path": pair.image_path,
                "scene_id": sdk_scene.id,
                "media_id": media_id,
                "status": "QUEUED"
            })
        except Exception as e:
            logger.exception("Error processing batch pair: %s", pair.image_path)
            results.append({
                "image_path": pair.image_path,
                "status": "FAILED",
                "error": str(e)
            })

    return {"results": results, "video_id": video_id}
