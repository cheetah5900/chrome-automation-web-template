"""Background worker — processes pending requests via Chrome extension.

Thin dispatcher: picks up PENDING requests, delegates to OperationService
for actual API work, handles status transitions + retry + scene updates.
"""
import asyncio
import base64
import json
import logging
import os
import re
import time

import aiohttp

from agent.db import crud
from agent.services.flow_client import get_flow_client
from agent.services.event_bus import event_bus
from agent.config import POLL_INTERVAL, MAX_RETRIES, API_COOLDOWN, MAX_CONCURRENT_REQUESTS
from agent.worker._parsing import _is_error
from agent.sdk.services.result_handler import parse_result, apply_scene_result, apply_character_result

logger = logging.getLogger(__name__)

_API_CALL_TYPES = {"GENERATE_IMAGE", "REGENERATE_IMAGE", "EDIT_IMAGE",
                   "GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS", "UPSCALE_VIDEO",
                   "GENERATE_CHARACTER_IMAGE", "REGENERATE_CHARACTER_IMAGE",
                   "EDIT_CHARACTER_IMAGE"}

_TYPE_PRIORITY = {
    "GENERATE_CHARACTER_IMAGE": 0, "REGENERATE_CHARACTER_IMAGE": 0, "EDIT_CHARACTER_IMAGE": 0,
    "GENERATE_IMAGE": 1, "REGENERATE_IMAGE": 1, "EDIT_IMAGE": 1,
    "GENERATE_VIDEO": 2, "REGENERATE_VIDEO": 2, "GENERATE_VIDEO_REFS": 2,
    "UPSCALE_VIDEO": 3,
}


import random


class APIRateLimiter:
    """Enforces max concurrent requests AND minimum gap between API calls."""
    def __init__(self, max_concurrent: int, cooldown_min: float, cooldown_max: float = None):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cooldown_min = cooldown_min
        self._cooldown_max = cooldown_max if cooldown_max is not None else cooldown_min
        self._last_call = 0.0
        self._gate = asyncio.Lock()

    def set_cooldown(self, cooldown_min: float, cooldown_max: float):
        self._cooldown_min = cooldown_min
        self._cooldown_max = cooldown_max

    async def acquire(self):
        await self._semaphore.acquire()
        async with self._gate:
            elapsed = time.monotonic() - self._last_call
            cooldown = random.uniform(self._cooldown_min, self._cooldown_max)
            if elapsed < cooldown:
                await asyncio.sleep(cooldown - elapsed)
            self._last_call = time.monotonic()

    def release(self):
        self._semaphore.release()


class WorkerController:
    """Controls the background worker loop with rate limiting and graceful shutdown."""

    def __init__(self):
        self._shutdown = asyncio.Event()
        self._active_ids: set[str] = set()
        self._active_tasks: dict[str, asyncio.Task] = {}
        # Initialize with default cooldown as both min and max
        self._rate_limiter = APIRateLimiter(MAX_CONCURRENT_REQUESTS, API_COOLDOWN, API_COOLDOWN)
        self._deferred: dict[str, float] = {}  # rid -> defer_until timestamp
        self._retry_after: dict[str, float] = {}  # rid -> retry_after timestamp

    def update_cooldown(self, cooldown_min: float, cooldown_max: float):
        """Update worker API cooldown range dynamically."""
        self._rate_limiter.set_cooldown(cooldown_min, cooldown_max)

    def get_cooldown_range(self) -> tuple[float, float]:
        """Get current worker API cooldown range."""
        return self._rate_limiter._cooldown_min, self._rate_limiter._cooldown_max

    @property
    def active_count(self) -> int:
        """Number of currently active requests."""
        return len(self._active_ids)

    async def start(self):
        """Start the worker loop."""
        await self._cleanup_stale_processing()
        await self._run_loop()

    async def cancel_all_active_tasks(self):
        """Cancel all running tasks immediately."""
        tasks = list(self._active_tasks.values())
        if tasks:
            logger.info("Worker: Cancelling %d active tasks...", len(tasks))
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active_ids.clear()
        self._active_tasks.clear()

    def request_shutdown(self):
        """Signal the worker to stop after current tasks drain."""
        self._shutdown.set()

    async def drain(self, timeout: float = 30.0):
        """Wait until all active tasks complete, with timeout."""
        deadline = time.monotonic() + timeout
        while self._active_ids and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
        if self._active_ids:
            logger.warning("Drain timeout: %d tasks still active after %.0fs", len(self._active_ids), timeout)

    async def _cleanup_stale_processing(self):
        """Reset any requests stuck in PROCESSING state from a previous run."""
        try:
            stale = await crud.list_requests(status="PROCESSING")
            for req in stale:
                await crud.update_request(req["id"], status="PENDING",
                                          error_message="reset: stale PROCESSING on startup")
                logger.warning("Stale request reset: %s type=%s", req["id"][:8], req.get("type"))
            if stale:
                logger.info("Cleaned up %d stale PROCESSING requests", len(stale))
        except Exception as e:
            logger.warning("Could not clean up stale requests: %s", e)

    async def _run_loop(self):
        client = get_flow_client()

        while not self._shutdown.is_set():
            try:
                if not client.connected:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                now = time.time()
                slots_available = MAX_CONCURRENT_REQUESTS - len(self._active_ids)
                if slots_available <= 0:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                pending = await crud.list_actionable_requests(
                    exclude_ids=self._active_ids, limit=slots_available
                )

                pending_count = len(pending)
                await event_bus.emit("worker_tick", {
                    "active": len(self._active_ids),
                    "slots": slots_available,
                    "pending": pending_count,
                })

                if pending:
                    logger.info("Worker: %d actionable, %d active, %d slots",
                                len(pending), len(self._active_ids), slots_available)

                for req in pending:
                    if slots_available <= 0:
                        break
                    rid = req["id"]

                    # Skip in-flight
                    if rid in self._active_ids:
                        continue

                    # Skip recently deferred (prereq or retry cooldown)
                    if rid in self._deferred and self._deferred[rid] > now:
                        continue
                    self._deferred.pop(rid, None)

                    # Skip if retry backoff not elapsed
                    if rid in self._retry_after and self._retry_after[rid] > now:
                        continue

                    self._active_ids.add(rid)
                    slots_available -= 1
                    task = asyncio.create_task(self._run_one(req))
                    self._active_tasks[rid] = task

                # Prune stale deferred/retry entries for requests no longer pending
                pending_ids = {r["id"] for r in pending}
                self._deferred = {k: v for k, v in self._deferred.items() if k in pending_ids}
                self._retry_after = {k: v for k, v in self._retry_after.items() if k in pending_ids}

            except Exception as e:
                logger.exception("Worker loop error: %s", e)

            await asyncio.sleep(POLL_INTERVAL)

    async def _run_one(self, req: dict):
        rid = req["id"]
        try:
            # Check DB status before rate-limiter acquisition
            db_req = await crud.get_request(rid)
            if not db_req or db_req.get("status") != "PENDING":
                logger.info("Request %s status changed to %s, skipping _run_one", rid[:8], db_req.get("status") if db_req else "None")
                return

            await self._rate_limiter.acquire()
            try:
                # Re-check DB status after rate-limiter acquisition
                db_req = await crud.get_request(rid)
                if not db_req or db_req.get("status") != "PENDING":
                    logger.info("Request %s status changed to %s during acquisition delay, skipping", rid[:8], db_req.get("status") if db_req else "None")
                    return
                await _process_one(db_req, self._deferred, self._retry_after)
            finally:
                self._rate_limiter.release()
        except asyncio.CancelledError:
            logger.info("Request task %s cancelled", rid[:8])
            try:
                db_req = await crud.get_request(rid)
                if db_req and db_req.get("status") in ("PENDING", "PROCESSING"):
                    await crud.update_request(rid, status="FAILED", error_message="Cancelled by user")
            except Exception as e:
                logger.warning("Failed to update status on CancelledError: %s", e)
            raise
        finally:
            self._active_ids.discard(rid)
            self._active_tasks.pop(rid, None)


async def _prerequisites_met(req: dict, orientation: str) -> bool:
    """Check if prerequisites are ready. Returns False to defer (stay PENDING)."""
    req_type = req.get("type", "")
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"

    # Video gen needs scene image to be ready (if image generation is pending); upscale needs video to be ready
    if req_type in ("GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS", "UPSCALE_VIDEO"):
        scene = await crud.get_scene(req.get("scene_id"))
        if not scene:
            return True  # let _dispatch handle "scene not found"
        if req_type in ("GENERATE_VIDEO", "REGENERATE_VIDEO"):
            if not scene.get(f"{prefix}_image_media_id"):
                image_reqs = await crud.list_requests(scene_id=scene["id"])
                has_pending_image = any(
                    r.get("type") in ("GENERATE_IMAGE", "EDIT_IMAGE", "REGENERATE_IMAGE")
                    and r.get("status") in ("PENDING", "PROCESSING", "CLAIMED")
                    for r in image_reqs
                )
                if has_pending_image:
                    logger.info("VIDEO prereq deferred: scene=%s waiting for image generation", req.get("scene_id","")[:12])
                    return False
        elif req_type == "GENERATE_VIDEO_REFS":
            if not scene.get(f"{prefix}_image_media_id"):
                logger.info("VIDEO_REFS prereq deferred: scene=%s no %s_image_media_id", req.get("scene_id","")[:12], prefix)
                return False
        elif req_type == "UPSCALE_VIDEO":
            if not scene.get(f"{prefix}_video_media_id"):
                logger.info("UPSCALE prereq deferred: scene=%s no %s_video_media_id", req.get("scene_id","")[:12], prefix)
                return False

    # Edit requests need source media (own image or parent's for INSERT scenes)
    if req_type in ("EDIT_IMAGE", "EDIT_CHARACTER_IMAGE"):
        if not req.get("source_media_id"):
            if req_type == "EDIT_CHARACTER_IMAGE":
                char = await crud.get_character(req.get("character_id"))
                if not char or not char.get("media_id"):
                    return False
            elif req_type == "EDIT_IMAGE":
                scene = await crud.get_scene(req.get("scene_id"))
                if not scene:
                    return True  # let _dispatch handle
                # CONTINUATION scenes always use parent's image as source
                src = None
                if scene.get("parent_scene_id"):
                    parent = await crud.get_scene(scene["parent_scene_id"])
                    src = parent.get(f"{prefix}_image_media_id") if parent else None
                if not src:
                    src = scene.get(f"{prefix}_image_media_id")
                logger.info("EDIT_IMAGE prereq: scene=%s src=%s parent=%s", req.get("scene_id","")[:12], src, scene.get("parent_scene_id","")[:12] if scene.get("parent_scene_id") else "none")
                if not src:
                    return False

    return True


async def _resolve_orientation(req: dict) -> str:
    """Resolve orientation from request, falling back to video table, then VERTICAL."""
    orient = req.get("orientation")
    if orient:
        return orient
    vid = req.get("video_id")
    if vid:
        video = await crud.get_video(vid)
        if video and video.get("orientation"):
            return video["orientation"]
    return "VERTICAL"


async def _process_one(req: dict, deferred: dict = None, retry_after: dict = None):
    rid, req_type = req["id"], req["type"]
    orientation = await _resolve_orientation(req)

    if await _is_already_completed(req, orientation):
        logger.info("Request %s skipped — already COMPLETED", rid[:8])
        # Copy existing result data from scene/character onto the request record
        skip_kwargs = {"status": "COMPLETED", "error_message": "skipped: already completed"}
        prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
        if req_type in ("GENERATE_CHARACTER_IMAGE", "REGENERATE_CHARACTER_IMAGE", "EDIT_CHARACTER_IMAGE"):
            char = await crud.get_character(req.get("character_id"))
            if char:
                skip_kwargs["media_id"] = char.get("media_id")
                skip_kwargs["output_url"] = char.get("image_url")
        else:
            scene = await crud.get_scene(req.get("scene_id"))
            if scene:
                if req_type == "GENERATE_IMAGE":
                    skip_kwargs["media_id"] = scene.get(f"{prefix}_image_media_id")
                    skip_kwargs["output_url"] = scene.get(f"{prefix}_image_url")
                elif req_type in ("GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS"):
                    skip_kwargs["media_id"] = scene.get(f"{prefix}_video_media_id")
                    skip_kwargs["output_url"] = scene.get(f"{prefix}_video_url")
                elif req_type == "UPSCALE_VIDEO":
                    skip_kwargs["media_id"] = scene.get(f"{prefix}_upscale_media_id")
                    skip_kwargs["output_url"] = scene.get(f"{prefix}_upscale_url")
        await crud.update_request(rid, **skip_kwargs)
        return

    # Check prerequisites before dispatching — don't burn retries on missing deps
    if not await _prerequisites_met(req, orientation):
        if deferred is not None:
            deferred[rid] = time.time() + 30  # defer 30s before rechecking
        return

    logger.info("Processing request %s type=%s", rid[:8], req_type)
    await crud.update_request(rid, status="PROCESSING")
    await event_bus.emit("request_update", {"id": rid, "status": "PROCESSING", "type": req_type})

    try:
        result = await _dispatch(req, orientation)
        if _is_error(result):
            await _handle_failure(rid, req, result, retry_after, deferred)
        else:
            gen_result = parse_result(result, req_type)
            await crud.update_request(rid, status="COMPLETED", media_id=gen_result.media_id, output_url=gen_result.url)
            if req_type in ("GENERATE_CHARACTER_IMAGE", "REGENERATE_CHARACTER_IMAGE", "EDIT_CHARACTER_IMAGE"):
                char_id = req.get("character_id")
                if char_id:
                    await apply_character_result(char_id, gen_result)
            else:
                await apply_scene_result(req.get("scene_id"), req_type, orientation, gen_result)
            await event_bus.emit("request_update", {"id": rid, "status": "COMPLETED"})
            logger.info("Request %s COMPLETED: media=%s", rid[:8], gen_result.media_id[:20] if gen_result.media_id else "?")
    except Exception as e:
        logger.exception("Request %s exception: %s", rid[:8], e)
        await event_bus.emit("request_update", {"id": rid, "status": "FAILED", "error": str(e)})
        await _handle_failure(rid, req, {"error": str(e)}, retry_after, deferred)


async def _dispatch(req: dict, orientation: str) -> dict:
    """Route request to the appropriate OperationService method."""
    from agent.sdk.services.operations import get_operations
    ops = get_operations()
    req_type, rid = req["type"], req["id"]
    pid = req.get("project_id", "0")

    # Scene-based operations
    if req_type in ("GENERATE_IMAGE", "REGENERATE_IMAGE", "EDIT_IMAGE",
                    "GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS", "UPSCALE_VIDEO"):
        scene = await crud.get_scene(req.get("scene_id"))
        if not scene:
            return {"error": "Scene not found"}
        scene["_project_id"] = pid

        if req_type in ("GENERATE_IMAGE", "REGENERATE_IMAGE"):
            return await ops.generate_scene_image(scene, orientation)
        if req_type == "EDIT_IMAGE":
            return await ops.edit_scene_image(scene, orientation, source_media_id=req.get("source_media_id"))
        if req_type in ("GENERATE_VIDEO", "REGENERATE_VIDEO"):
            return await ops.generate_scene_video(scene, orientation, request_id=rid)
        if req_type == "GENERATE_VIDEO_REFS":
            return await ops.generate_scene_video_refs(scene, orientation, request_id=rid)
        if req_type == "UPSCALE_VIDEO":
            return await ops.upscale_scene_video(scene, orientation, request_id=rid)

    # Character operations
    if req_type in ("GENERATE_CHARACTER_IMAGE", "REGENERATE_CHARACTER_IMAGE", "EDIT_CHARACTER_IMAGE"):
        char = await crud.get_character(req.get("character_id"))
        if not char:
            return {"error": "Character not found"}
        if req_type == "REGENERATE_CHARACTER_IMAGE":
            # Clear existing media so generate_reference_image takes the normal (not fast) path
            await crud.update_character(char["id"], media_id=None, reference_image_url=None)
            char["media_id"] = None
            char["reference_image_url"] = None
            return await ops.generate_reference_image(char, pid)
        if req_type == "EDIT_CHARACTER_IMAGE":
            src = req.get("source_media_id") or char.get("media_id")
            if not src:
                return {"error": "No source image to edit — generate a reference image first"}
            edit_prompt = char.get("image_prompt") or char.get("description", "")
            project = await crud.get_project(pid) if pid != "0" else None
            tier = project.get("user_paygate_tier", "PAYGATE_TIER_ONE") if project else "PAYGATE_TIER_ONE"
            aspect = "IMAGE_ASPECT_RATIO_LANDSCAPE" if char.get("entity_type") in ("location",) else "IMAGE_ASPECT_RATIO_PORTRAIT"
            return await ops._client.edit_image(
                prompt=edit_prompt, source_media_id=src,
                project_id=pid, aspect_ratio=aspect,
                user_paygate_tier=tier,
            )
        return await ops.generate_reference_image(char, pid)

    return {"error": f"Unknown request type: {req_type}"}


async def _reupload_media(url: str, project_id: str) -> str | None:
    """Download image from URL and re-upload to get a fresh media_id."""
    try:
        if url.startswith("file://"):
            from urllib.parse import unquote
            file_path = unquote(url[7:])
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            ext = file_path.lower().split(".")[-1]
            mime = "image/png" if ext == "png" else ("image/webp" if ext == "webp" else "image/jpeg")
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning("Re-upload: failed to download %s (status %d)", url[:60], resp.status)
                        return None
                    image_bytes = await resp.read()
                    content_type = resp.headers.get("Content-Type", "image/jpeg")

            if not content_type.startswith("image/"):
                logger.warning("Re-upload: unexpected content-type %s from %s", content_type, url[:60])
                return None
            mime = content_type.split(";")[0].strip()
        image_b64 = base64.b64encode(image_bytes).decode()

        client = get_flow_client()
        result = await client.upload_image(image_b64, mime_type=mime, project_id=project_id)
        new_mid = result.get("_mediaId")
        if new_mid:
            logger.info("Re-upload OK: fresh media_id=%s", new_mid[:20])
            return new_mid
        logger.warning("Re-upload: no media_id in response: %s", str(result)[:200])
    except Exception as e:
        logger.warning("Re-upload failed: %s", e)
    return None


async def _recover_entity_not_found(req: dict) -> bool:
    """When Google returns 'entity not found', re-upload the image to get a fresh media_id."""
    req_type = req.get("type", "")
    pid = req.get("project_id", "")
    orientation = await _resolve_orientation(req)
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"

    # Scene-based requests: re-upload scene image
    if req_type in ("GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS", "UPSCALE_VIDEO"):
        scene = await crud.get_scene(req.get("scene_id"))
        if not scene:
            return False
        url = scene.get(f"{prefix}_image_url")
        if not url:
            return False
        new_mid = await _reupload_media(url, pid)
        if new_mid:
            await crud.update_scene(scene["id"], **{f"{prefix}_image_media_id": new_mid})
            logger.info("Recovered scene %s: new %s_image_media_id=%s", scene["id"][:12], prefix, new_mid[:12])
            return True

    # Character-based requests: re-upload ref image
    if req_type in ("EDIT_CHARACTER_IMAGE",):
        char = await crud.get_character(req.get("character_id"))
        if not char:
            return False
        url = char.get("reference_image_url")
        if not url:
            return False
        new_mid = await _reupload_media(url, pid)
        if new_mid:
            await crud.update_character(char["id"], media_id=new_mid)
            logger.info("Recovered character %s: new media_id=%s", char["id"][:12], new_mid[:12])
            return True

    return False


def _apply_rule_based_safety_rewrite(prompt: str) -> str:
    """Softens sensitive and policy-violating words (e.g. baby -> kids, infant -> toddler, weapons, gore)."""
    if not prompt:
        return prompt

    substitutions = [
        # Children / Infants
        (r"\b(newborns)\b", "young children"),
        (r"\b(newborn)\b", "young child"),
        (r"\b(infants)\b", "toddlers"),
        (r"\b(infant)\b", "toddler"),
        (r"\b(babies)\b", "kids"),
        (r"\b(baby)\b", "kids"),

        # Blood / Gore
        (r"\b(bloody)\b", "crimson-hued"),
        (r"\b(blood)\b", "crimson dye"),
        (r"\b(gory|gore)\b", "dramatic flair"),
        (r"\b(wounds|wounded)\b", "markings"),
        (r"\b(wound)\b", "marking"),

        # Weapons
        (r"\b(guns|firearms|pistols|rifles)\b", "theatrical props"),
        (r"\b(gun|firearm|pistol|rifle)\b", "theatrical prop"),
        (r"\b(knives|daggers)\b", "ornate props"),
        (r"\b(knife|dagger|blade)\b", "ornate prop"),
        (r"\b(weapons)\b", "stage props"),
        (r"\b(weapon)\b", "stage prop"),

        # Violence / Killing
        (r"\b(murders|murdering|killing|slaying)\b", "dramatically confronting"),
        (r"\b(murder|kill|slay)\b", "dramatic showdown"),
        (r"\b(corpses|dead bodies)\b", "resting figures"),
        (r"\b(corpse|dead body)\b", "resting figure"),
        (r"\b(terrorist|terrorism)\b", "rival faction"),
    ]

    res = prompt
    for pattern, repl in substitutions:
        def _repl_case(m):
            txt = m.group(0)
            if txt.isupper():
                return repl.upper()
            if txt[0].isupper():
                return repl.capitalize()
            return repl
        res = re.sub(pattern, _repl_case, res, flags=re.IGNORECASE)

    return res


async def _call_gemini_rewrite(prompt: str, err_msg: str, api_key: str) -> str:
    """Call Gemini 3.6 Flash to rewrite the prompt while preserving artistic intent and style."""
    try:
        import httpx
        system_instruction = (
            "You are an expert AI video prompt director for Google Flow (Veo).\n"
            "Your job is to rewrite a video generation prompt that was BLOCKED or REJECTED by Google Flow "
            "due to safety filters, content policy, or sensitive words.\n\n"
            "RULES FOR REWRITING:\n"
            "1. Strictly replace 'baby' or 'babies' with 'kids' or 'young children', and 'infant' or 'infants' with 'toddler' or 'toddlers'.\n"
            "2. Replace any copyrighted brands, celebrities, named living people, or public figures with neutral artistic descriptions.\n"
            "3. Soften any violence, weapons, blood, conflict, or gore into theatrical drama, dynamic camera motion, lighting effects, or silhouette storytelling.\n"
            "4. PRESERVE the original cinematic camera movements (pan, zoom, tracking), lighting style, color grading, shot framing, and atmosphere.\n"
            "5. Output ONLY the rewritten prompt text. Do NOT wrap in markdown code blocks, quotes, or conversational explanations."
        )
        user_content = (
            f"Original Prompt:\n{prompt}\n\n"
            f"Rejection / Error Reason:\n{err_msg}\n\n"
            f"Please rewrite this prompt to be 100% compliant with Google Flow safety policies while maintaining the cinematic style and motion."
        )
        payload = {
            "contents": [{"parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}
        }
        models = ["gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
        async with httpx.AsyncClient(timeout=25.0) as http_client:
            for target_model in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
                try:
                    resp = await http_client.post(url, params={"key": api_key}, json=payload, headers={"Content-Type": "application/json"})
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                res_text = parts[0].get("text", "").strip()
                                res_text = re.sub(r"^```[a-z]*\s*", "", res_text)
                                res_text = re.sub(r"\s*```$", "", res_text)
                                res_text = res_text.strip(" \"'\n\r")
                                if res_text:
                                    return res_text
                except Exception:
                    continue
    except Exception as e:
        logger.warning("Error in _call_gemini_rewrite: %s", e)
    return ""


async def _rewrite_prompt_for_safety(prompt: str, error_msg: str) -> str:
    """Rewrite prompt for safety using Gemini if key is configured, plus rule-based softening."""
    if not prompt:
        return prompt
    # 1. Try Gemini API first if configured
    try:
        from agent.api.batch_uploader import get_saved_gemini_key
        key = get_saved_gemini_key()
        if key:
            ai_rewritten = await _call_gemini_rewrite(prompt, error_msg, key)
            if ai_rewritten and ai_rewritten.strip():
                return _apply_rule_based_safety_rewrite(ai_rewritten.strip())
    except Exception as e:
        logger.warning("Gemini safety rewrite failed, falling back to rule-based: %s", e)

    # 2. Rule-based softening
    return _apply_rule_based_safety_rewrite(prompt)


async def _auto_rewrite_and_save_prompt(req: dict, error_msg: str) -> str:
    """Rewrites prompt, saves it to file on disk, and updates database scene & request."""
    scene_id = req.get("scene_id")
    scene = await crud.get_scene(scene_id) if scene_id else None

    current_prompt = ""
    prompt_path = None
    image_path = None

    ep = req.get("edit_prompt")
    params = {}
    if ep:
        try:
            params = json.loads(ep)
            if isinstance(params, dict):
                prompt_path = params.get("prompt_path")
                image_path = params.get("image_path")
                current_prompt = params.get("original_prompt") or params.get("prompt_content") or ""
        except Exception:
            pass

    if not current_prompt and scene:
        current_prompt = scene.get("video_prompt") or scene.get("prompt") or ""

    # Locate prompt file if prompt_path is not given or doesn't exist
    if not prompt_path or not os.path.isfile(prompt_path):
        img = image_path or (scene.get("vertical_image_url") if scene else None)
        if img:
            if img.startswith("file://"):
                from urllib.parse import unquote
                img = unquote(img[7:])
            if os.path.exists(img):
                base, _ = os.path.splitext(img)
                for ext in (".txt", ".md"):
                    if os.path.isfile(base + ext):
                        prompt_path = base + ext
                        break
                if not prompt_path:
                    img_dir = os.path.dirname(img)
                    img_name = os.path.splitext(os.path.basename(img))[0]
                    for candidate_dir in (img_dir, os.path.join(img_dir, "..", "prompts"), os.path.join(img_dir, "prompts")):
                        if os.path.isdir(candidate_dir):
                            for ext in (".txt", ".md"):
                                cand = os.path.join(candidate_dir, img_name + ext)
                                if os.path.isfile(cand):
                                    prompt_path = cand
                                    break
                            if prompt_path:
                                break

    if prompt_path and os.path.isfile(prompt_path) and not current_prompt:
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                current_prompt = f.read().strip()
        except Exception as e:
            logger.warning("Failed to read prompt from %s: %s", prompt_path, e)

    rewritten_prompt = await _rewrite_prompt_for_safety(current_prompt or "", error_msg)

    # 1. Overwrite file on disk
    if prompt_path:
        try:
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(rewritten_prompt)
            logger.info("Saved auto-rewritten prompt to disk: %s", prompt_path)
        except Exception as e:
            logger.warning("Failed to save auto-rewritten prompt to %s: %s", prompt_path, e)
    elif image_path and os.path.exists(os.path.dirname(image_path)):
        base, _ = os.path.splitext(image_path)
        save_file = base + ".txt"
        try:
            with open(save_file, "w", encoding="utf-8") as f:
                f.write(rewritten_prompt)
            prompt_path = save_file
            params["prompt_path"] = save_file
            logger.info("Saved auto-rewritten prompt to newly created file: %s", save_file)
        except Exception as e:
            logger.warning("Failed to create new prompt file %s: %s", save_file, e)

    # 2. Update scene in database
    if scene_id:
        try:
            await crud.update_scene(scene_id, prompt=rewritten_prompt, video_prompt=rewritten_prompt)
            logger.info("Updated scene %s with auto-rewritten prompt", scene_id)
        except Exception as e:
            logger.warning("Failed to update scene %s with rewritten prompt: %s", scene_id, e)

    # 3. Update request edit_prompt JSON
    params["original_prompt"] = rewritten_prompt
    params["prompt_content"] = rewritten_prompt
    if prompt_path:
        params["prompt_path"] = prompt_path
    try:
        new_ep = json.dumps(params)
        await crud.update_request(req["id"], edit_prompt=new_ep)
        req["edit_prompt"] = new_ep
    except Exception as e:
        logger.warning("Failed to update request edit_prompt: %s", e)

    return rewritten_prompt


async def _handle_failure(rid: str, req: dict, result: dict, retry_after: dict = None, deferred: dict = None):
    error_msg = result.get("error")
    if not error_msg:
        data = result.get("data", {})
        if isinstance(data, dict):
            ef = data.get("error", "Unknown error")
            if isinstance(ef, dict):
                error_msg = ef.get("message", json.dumps(ef)[:200])
                details = ef.get("details", [])
                if details and isinstance(details, list):
                    for d in details:
                        reason = d.get("reason") if isinstance(d, dict) else None
                        if reason:
                            error_msg = f"{error_msg} [{reason}]"
                            break
            else:
                error_msg = str(ef)
        else:
            error_msg = "Unknown error"
    if isinstance(error_msg, dict):
        error_msg = json.dumps(error_msg)[:200]

    error_lower = str(error_msg).lower()

    # Quota/billing limits are strictly non-retryable
    if any(kw in error_lower for kw in ("billing", "credits", "quota", "paygate", "insufficient", "payment", "tier")):
        await crud.update_request(rid, status="FAILED", error_message=str(error_msg))
        await _mark_scene_failed(req)
        await event_bus.emit("request_update", {"id": rid, "status": "FAILED", "error": str(error_msg)})
        logger.error("Request %s FAILED permanently (quota/billing): %s", rid[:8], error_msg)
        return

    # Auto-recover expired media by re-uploading ONLY if specifically image entity missing
    if "not found" in error_lower and not any(kw in error_lower for kw in ("failed: [5]", "as29s", "media not found or cancelled")):
        recovered = await _recover_entity_not_found(req)
        if recovered:
            logger.info("Request %s: recovered expired media, retrying", rid[:8])
            await crud.update_request(rid, status="PENDING", request_id=None, media_id=None, error_message=f"recovered: {error_msg}")
            return

    # WS transient errors: retry without incrementing count
    if any(kw in error_lower for kw in ("extension reconnected", "extension disconnected", "extension not connected")):
        await crud.update_request(rid, status="PENDING", request_id=None, media_id=None, error_message=str(error_msg))
        logger.info("Request %s transient WS error, will retry (no retry increment): %s", rid[:8], error_msg)
        return

    # reCAPTCHA errors: retry up to 10 times
    if "captcha" in error_lower or "recaptcha" in error_lower:
        retry = req.get("retry_count", 0) + 1
        if retry < 10:
            if deferred is not None:
                deferred[rid] = time.time() + 5.0
            await crud.update_request(rid, status="PENDING", retry_count=retry, request_id=None, media_id=None, error_message=str(error_msg))
            logger.warning("Request %s reCAPTCHA failed (retry %d/10), will retry in 5s", rid[:8], retry)
            return
        else:
            await crud.update_request(rid, status="FAILED", error_message=str(error_msg))
            await _mark_scene_failed(req)
            logger.error("Request %s FAILED after 10 reCAPTCHA retries: %s", rid[:8], error_msg)
            return

    # 2-Tier Auto-Retry with Prompt Safety Rewriting Workflow
    # Read latest retry_count directly from DB if available
    db_req = await crud.get_request(rid)
    current_retry = (db_req.get("retry_count", 0) if db_req else req.get("retry_count", 0)) or 0

    if current_retry == 0:
        # Attempt 1 failed -> Retry 1/2
        new_retry = 1
        msg = f"🔄 กำลังลองซ้ำครั้งที่ 1/2... ({error_msg})"
        if retry_after is not None:
            retry_after[rid] = time.time() + 3.0
        await crud.update_request(rid, status="PENDING", retry_count=new_retry, request_id=None, media_id=None, error_message=msg)
        await event_bus.emit("request_update", {"id": rid, "status": "PENDING", "retry_count": new_retry, "error": msg})
        logger.warning("Request %s: retry 1/2 scheduled - %s", rid[:8], msg)
        return

    elif current_retry == 1:
        # Attempt 2 failed -> Retry 2/2
        new_retry = 2
        msg = f"🔄 กำลังลองซ้ำครั้งที่ 2/2... ({error_msg})"
        if retry_after is not None:
            retry_after[rid] = time.time() + 3.0
        await crud.update_request(rid, status="PENDING", retry_count=new_retry, request_id=None, media_id=None, error_message=msg)
        await event_bus.emit("request_update", {"id": rid, "status": "PENDING", "retry_count": new_retry, "error": msg})
        logger.warning("Request %s: retry 2/2 scheduled - %s", rid[:8], msg)
        return

    elif current_retry == 2:
        # Tried 2 times, both failed -> State clearly, rewrite prompt in file on disk & DB, then retry once more!
        new_retry = 3
        rewritten_prompt = await _auto_rewrite_and_save_prompt(req, error_msg)
        msg = "ลองครบ 2 ครั้งแล้ว แต่ล้มเหลว -> ปรับแก้ Prompt ในไฟล์เรียบร้อยแล้ว (เลี่ยงคำต้องห้าม) และกำลังลองสร้างใหม่อีกครั้ง..."
        if retry_after is not None:
            retry_after[rid] = time.time() + 3.0
        await crud.update_request(rid, status="PENDING", retry_count=new_retry, request_id=None, media_id=None, error_message=msg)
        await event_bus.emit("request_update", {"id": rid, "status": "PENDING", "retry_count": new_retry, "error": msg, "prompt": rewritten_prompt})
        logger.warning("Request %s: %s (rewritten prompt: %s)", rid[:8], msg, rewritten_prompt[:100] if rewritten_prompt else "none")
        return

    else:
        # Tried retry with rewritten prompt (attempt 3), and it still failed -> Mark failed permanently
        new_retry = current_retry + 1
        msg = f"ลองครบ 2 ครั้งแล้ว และปรับแก้ Prompt ในไฟล์แล้ว แต่ล้มเหลว: {error_msg}"
        await crud.update_request(rid, status="FAILED", retry_count=new_retry, error_message=msg)
        await _mark_scene_failed(req)
        await event_bus.emit("request_update", {"id": rid, "status": "FAILED", "retry_count": new_retry, "error": msg})
        logger.error("Request %s FAILED permanently: %s", rid[:8], msg)
        return


async def _mark_scene_failed(req: dict):
    scene_id = req.get("scene_id")
    if not scene_id:
        return
    orientation = await _resolve_orientation(req)
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    req_type = req["type"]
    updates = {}
    if req_type in ("GENERATE_IMAGE", "REGENERATE_IMAGE", "EDIT_IMAGE"):
        updates[f"{prefix}_image_status"] = "FAILED"
    elif req_type in ("GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS"):
        updates[f"{prefix}_video_status"] = "FAILED"
    elif req_type == "UPSCALE_VIDEO":
        updates[f"{prefix}_upscale_status"] = "FAILED"
    if updates:
        await crud.update_scene(scene_id, **updates)


async def _is_already_completed(req: dict, orientation: str) -> bool:
    scene_id = req.get("scene_id")
    req_type = req.get("type", "")
    if not scene_id or req_type == "GENERATE_CHARACTER_IMAGE":
        return False
    scene = await crud.get_scene(scene_id)
    if not scene:
        return False
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    if req_type in ("EDIT_IMAGE", "REGENERATE_IMAGE", "REGENERATE_VIDEO", "REGENERATE_CHARACTER_IMAGE", "EDIT_CHARACTER_IMAGE"):
        return False  # Always run — explicitly requesting new generation
    if req_type == "GENERATE_IMAGE":
        return scene.get(f"{prefix}_image_status") == "COMPLETED" and bool(scene.get(f"{prefix}_image_url"))
    if req_type in ("GENERATE_VIDEO", "GENERATE_VIDEO_REFS"):
        return scene.get(f"{prefix}_video_status") == "COMPLETED" and bool(scene.get(f"{prefix}_video_url"))
    if req_type == "UPSCALE_VIDEO":
        return scene.get(f"{prefix}_upscale_status") == "COMPLETED" and bool(scene.get(f"{prefix}_upscale_url"))
    return False


# ─── Module-level controller ──────────────────────────────────

_controller: WorkerController | None = None


def get_worker_controller() -> WorkerController:
    global _controller
    if _controller is None:
        _controller = WorkerController()
    return _controller
