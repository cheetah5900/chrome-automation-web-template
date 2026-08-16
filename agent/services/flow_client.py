"""
Flow Client — communicates with Google Flow API via Chrome extension WebSocket bridge.

Agent runs a WS server. Extension connects as client. Agent sends API requests,
extension executes them in browser context (residential IP, cookies, reCAPTCHA).
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from agent.config import (
    GOOGLE_FLOW_API, GOOGLE_API_KEY, ENDPOINTS,
    VIDEO_MODELS, UPSCALE_MODELS, IMAGE_MODELS, VIDEO_POLL_TIMEOUT,
)
from agent.services.headers import random_headers

logger = logging.getLogger(__name__)


class FlowClient:
    """Sends commands to Chrome extension via WebSocket."""

    def __init__(self):
        self._extension_ws = None  # Set by WS server when extension connects
        self._pending: dict[str, asyncio.Future] = {}
        self._flow_key: Optional[str] = None
        self.user_paygate_tier: str = "PAYGATE_TIER_TWO"
        # WS stats
        self._ws_connect_count = 0
        self._ws_disconnect_count = 0
        self._ws_connected_at: Optional[float] = None
        self._ws_last_disconnect_at: Optional[float] = None
        self._last_tier_sync_time = 0.0

    def set_extension(self, ws):
        """Called when extension connects via WS."""
        self._extension_ws = ws
        self._ws_connect_count += 1
        self._ws_connected_at = time.time()
        logger.info("Extension connected #%d (waiting for extension_ready/token_captured to sync)", self._ws_connect_count)

    def clear_extension(self):
        """Called when extension disconnects."""
        self._extension_ws = None
        self._ws_disconnect_count += 1
        self._ws_last_disconnect_at = time.time()
        # Cancel all pending futures (copy to avoid RuntimeError on concurrent modification)
        pending_copy = list(self._pending.items())
        count = len(pending_copy)
        for req_id, future in pending_copy:
            if not future.done():
                future.set_exception(ConnectionError("Extension disconnected"))
        self._pending.clear()
        logger.warning("Extension disconnected, cleared %d pending requests", count)

    def set_flow_key(self, key: str):
        self._flow_key = key

    @property
    def connected(self) -> bool:
        import os
        if os.environ.get("MOCK_FLOW_CLIENT") == "1":
            return True
        return self._extension_ws is not None

    @property
    def ws_stats(self) -> dict:
        uptime = None
        if self._ws_connected_at and self.connected:
            uptime = int(time.time() - self._ws_connected_at)
        return {
            "connected": self.connected,
            "connects": self._ws_connect_count,
            "disconnects": self._ws_disconnect_count,
            "uptime_s": uptime,
        }

    async def handle_message(self, data: dict):
        """Handle incoming message from extension."""
        if data.get("type") == "token_captured":
            self._flow_key = data.get("flowKey")
            logger.info("Flow key captured from extension")
            asyncio.create_task(self._sync_tier())
            return

        if data.get("type") == "extension_ready":
            logger.info("Extension ready, flowKey=%s", "yes" if data.get("flowKeyPresent") else "no")
            asyncio.create_task(self._sync_tier())
            return

        if data.get("type") == "media_urls_refresh":
            asyncio.create_task(self._refresh_media_urls(data.get("urls", [])))
            return

        if data.get("type") == "trpc_intercept":
            asyncio.create_task(self._save_trpc_intercept(data.get("url"), data.get("body")))
            return

        if data.get("type") == "trpc_models_intercept":
            asyncio.create_task(self._save_models_intercept(data.get("url"), data.get("body")))
            return

        if data.get("type") == "pong":
            return

        if data.get("type") == "ping":
            # Respond to keepalive
            if self._extension_ws:
                await self._extension_ws.send(json.dumps({"type": "pong"}))
            return

        # Response to a pending request
        req_id = data.get("id")
        if req_id and req_id in self._pending:
            if not self._pending[req_id].done():
                self._pending[req_id].set_result(data)
            return

    async def _sync_tier(self):
        """Detect current tier from credits API and update all active projects."""
        if getattr(self, '_sync_in_progress', False):
            return
        now = time.time()
        if now - self._last_tier_sync_time < 60.0:
            return
        self._sync_in_progress = True
        self._last_tier_sync_time = now
        try:
            result = await self.get_credits()
            data = result.get("data", result)
            tier = data.get("userPaygateTier", "PAYGATE_TIER_ONE")
            self.user_paygate_tier = tier
            logger.info("Syncing tier: %s", tier)

            from agent.db import crud
            projects = await crud.list_projects(status="ACTIVE")
            for p in projects:
                if p.get("user_paygate_tier") != tier:
                    await crud.update_project(p["id"], user_paygate_tier=tier)
                    logger.info("Updated project %s tier: %s -> %s",
                                p["id"][:12], p.get("user_paygate_tier"), tier)
        except Exception as e:
            logger.warning("Failed to sync tier: %s", e)
        finally:
            self._sync_in_progress = False

    _UUID_RE = __import__("re").compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    _SAFE_URL_RE = __import__("re").compile(r'^https://([a-zA-Z0-9-.]*\.googleapis\.com|[a-zA-Z0-9-.]*\.googleusercontent\.com|[a-zA-Z0-9-.]*\.google\.com|[a-zA-Z0-9-.]*\.google)/')

    async def _refresh_media_urls(self, urls: list[dict]):
        """Update scene/character URLs in DB from fresh TRPC-captured signed URLs.

        Each entry: {mediaId: str, mediaType: 'image'|'video', url: str}
        """
        from agent.db import crud
        from agent.services.event_bus import event_bus

        updated = 0
        for entry in urls:
            media_id = entry.get("mediaId", "")
            media_type = entry.get("mediaType", "")
            url = entry.get("url", "")
            if not media_id or not url:
                continue
            # Validate media_id is UUID and url is from trusted domains
            if not self._UUID_RE.match(media_id):
                logger.warning("Rejected invalid media_id: %s", media_id[:20])
                continue
            if not self._SAFE_URL_RE.match(url):
                logger.warning("Rejected untrusted URL domain for media %s: %s", media_id[:12], url)
                continue
            # If media_type not specified or invalid, check matching database fields directly
            if not media_type or media_type not in ("image", "video"):
                scenes = await crud.list_scenes_by_media_id(media_id)
                for scene in scenes:
                    updates = {}
                    if scene.get("vertical_image_media_id") == media_id:
                        updates["vertical_image_url"] = url
                    if scene.get("horizontal_image_media_id") == media_id:
                        updates["horizontal_image_url"] = url
                    if scene.get("vertical_video_media_id") == media_id:
                        updates["vertical_video_url"] = url
                    if scene.get("horizontal_video_media_id") == media_id:
                        updates["horizontal_video_url"] = url
                    if scene.get("vertical_upscale_media_id") == media_id:
                        updates["vertical_upscale_url"] = url
                    if scene.get("horizontal_upscale_media_id") == media_id:
                        updates["horizontal_upscale_url"] = url
                    if updates:
                        await crud.update_scene(scene["id"], **updates)
                        updated += 1

                chars = await crud.list_characters_by_media_id(media_id)
                for char in chars:
                    if char.get("media_id") == media_id:
                        await crud.update_character(char["id"], reference_image_url=url)
                        updated += 1
                continue

            # Try matching against scenes (check both orientations)
            scenes = await crud.list_scenes_by_media_id(media_id)
            for scene in scenes:
                updates = {}
                if media_type == "image":
                    # Update whichever orientation matches
                    if scene.get("vertical_image_media_id") == media_id:
                        updates["vertical_image_url"] = url
                    if scene.get("horizontal_image_media_id") == media_id:
                        updates["horizontal_image_url"] = url
                elif media_type == "video":
                    if scene.get("vertical_video_media_id") == media_id:
                        updates["vertical_video_url"] = url
                    if scene.get("horizontal_video_media_id") == media_id:
                        updates["horizontal_video_url"] = url
                    if scene.get("vertical_upscale_media_id") == media_id:
                        updates["vertical_upscale_url"] = url
                    if scene.get("horizontal_upscale_media_id") == media_id:
                        updates["horizontal_upscale_url"] = url
                if updates:
                    await crud.update_scene(scene["id"], **updates)
                    updated += 1

            # Try matching against characters
            chars = await crud.list_characters_by_media_id(media_id)
            for char in chars:
                if media_type == "image" and char.get("media_id") == media_id:
                    await crud.update_character(char["id"], reference_image_url=url)
                    updated += 1

        if updated:
            logger.info("Refreshed %d media URLs from TRPC intercept", updated)
            await event_bus.emit("urls_refreshed", {"count": updated})

    async def _save_trpc_intercept(self, url: str, body: str):
        try:
            import json as _json
            data = _json.loads(body)
            with open("/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template/web/trpc_intercept.json", "w", encoding="utf-8") as f:
                _json.dump({"url": url, "data": data}, f, indent=2)
            logger.info("Saved raw TRPC response intercept to web/trpc_intercept.json")
        except Exception as e:
            logger.warning("Failed to save TRPC intercept: %s", e)

    async def _save_models_intercept(self, url: str, body: str):
        try:
            import json as _json
            data = _json.loads(body)
            with open("/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template/web/flow_models_intercept.json", "w", encoding="utf-8") as f:
                _json.dump({"url": url, "data": data}, f, indent=2)
            logger.info("Saved raw models TRPC response intercept to web/flow_models_intercept.json")
        except Exception as e:
            logger.warning("Failed to save models TRPC intercept: %s", e)

    async def refresh_project_urls(self, project_id: str) -> dict:
        """Refresh media URLs for a project.

        Note: Google Flow's get_media API returns encoded content (base64),
        not fresh signed URLs. URL refresh requires TRPC intercept from
        the extension when the user opens the project in Chrome.
        The video reviewer falls back to get_media content directly.
        """
        logger.info("URL refresh requested for project %s — TRPC endpoint no longer available, "
                     "use extension passive intercept (open project in Chrome)", project_id[:12])
        return {"refreshed": 0, "found": 0, "note": "TRPC endpoint unavailable. "
                "Video reviewer uses get_media fallback automatically. "
                "For URL refresh, open the project in Google Flow in Chrome."}

    async def _send(self, method: str, params: dict, timeout: float = 300) -> dict:
        """Send request to extension and wait for response.

        Always returns a dict. On error, returns {"error": "<reason>"} — callers
        must check result.get("error") or use _is_ws_error() before reading data.
        Never raises; exceptions are caught and returned as error dicts.
        """
        if not self._extension_ws:
            return {"error": "Extension not connected"}

        req_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future

        try:
            await self._extension_ws.send(json.dumps({
                "id": req_id,
                "method": method,
                "params": params,
            }))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {"error": f"Timeout ({timeout}s) waiting for {method}"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            self._pending.pop(req_id, None)

    def _build_url(self, endpoint_key: str, **kwargs) -> str:
        """Build full API URL."""
        path = ENDPOINTS[endpoint_key].format(**kwargs)
        sep = "&" if "?" in path else "?"
        return f"{GOOGLE_FLOW_API}{path}{sep}key={GOOGLE_API_KEY}"

    def _client_context(self, project_id: str, user_paygate_tier: str = "PAYGATE_TIER_TWO") -> dict:
        """Build clientContext with recaptcha placeholder."""
        return {
            "projectId": str(project_id),
            "recaptchaContext": {
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
                "token": "",  # Extension injects real token
            },
            "sessionId": f";{int(time.time() * 1000)}",
            "tool": "PINHOLE",
            "userPaygateTier": user_paygate_tier,
        }

    # ─── High-level API Methods ──────────────────────────────

    async def create_project(self, project_title: str, tool_name: str = "PINHOLE") -> dict:
        """Create a project on Google Flow via tRPC endpoint.

        Returns the full response including projectId.
        """
        url = "https://labs.google/fx/api/trpc/project.createProject"
        body = {"json": {"projectTitle": project_title, "toolName": tool_name}}

        return await self._send("trpc_request", {
            "url": url,
            "method": "POST",
            "headers": {
                "content-type": "application/json",
                "accept": "*/*",
            },
            "body": body,
        }, timeout=30)

    async def generate_images(self, prompt: str, project_id: str,
                               aspect_ratio: str = "IMAGE_ASPECT_RATIO_PORTRAIT",
                               user_paygate_tier: str = "PAYGATE_TIER_TWO",
                               character_media_ids: list[str] = None,
                               model_name: str = "GEM_PIX_2",
                               quantity: int = 1) -> dict:
        """Generate image(s).

        If character_media_ids is provided, uses edit_image flow (batchGenerateImages
        with imageInputs) — same endpoint, but includes character references.
        Without characters, uses plain generate_images.

        Response structure:
            data.media[].name = mediaId (used for video gen)
        """
        import os
        if os.environ.get("MOCK_FLOW_CLIENT") == "1":
            media = []
            for i in range(quantity):
                media.append({
                    "name": "a2948942-2616-4731-a395-d1afac6a87a7",
                    "image": {
                        "generatedImage": {
                            "mediaId": "a2948942-2616-4731-a395-d1afac6a87a7",
                            "imageUri": f"http://127.0.0.1:{os.environ.get('PORT', '6969')}/health",
                            "fifeUrl": f"http://127.0.0.1:{os.environ.get('PORT', '6969')}/health"
                        }
                    }
                })
            return {
                "success": True,
                "data": {"media": media},
                "_mock_received_character_media_ids": character_media_ids
            }

        ts = int(time.time() * 1000)
        ctx = self._client_context(project_id, user_paygate_tier)

        requests = []
        for i in range(quantity):
            item_ts = ts + i
            request_item = {
                "clientContext": {**ctx, "sessionId": f";{item_ts}"},
                "seed": item_ts % 1000000,
                "structuredPrompt": {"parts": [{"text": prompt}]},
                "imageAspectRatio": aspect_ratio,
                "imageModelName": model_name,
            }
            # Add character references if provided (edit_image flow)
            if character_media_ids:
                request_item["imageInputs"] = [
                    {"name": mid, "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"}
                    for mid in character_media_ids
                ]
            requests.append(request_item)

        batch_id = f"{uuid.uuid4()}" if character_media_ids else None
        body = {
            "clientContext": ctx,
            "requests": requests,
        }
        if batch_id:
            body["mediaGenerationContext"] = {"batchId": batch_id}
            body["useNewMedia"] = True

        url = self._build_url("generate_images", project_id=project_id)
        return await self._send("api_request", {
            "url": url,
            "method": "POST",
            "headers": random_headers(),
            "body": body,
            "captchaAction": "IMAGE_GENERATION",
        })

    async def edit_image(self, prompt: str, source_media_id: str,
                          project_id: str,
                          aspect_ratio: str = "IMAGE_ASPECT_RATIO_PORTRAIT",
                          user_paygate_tier: str = "PAYGATE_TIER_ONE",
                          character_media_ids: list[str] = None) -> dict:
        """Edit an existing image using IMAGE_INPUT_TYPE_BASE_IMAGE.

        If character_media_ids is provided, appends them as IMAGE_INPUT_TYPE_REFERENCE
        after the base image. Order: [base_image, char_A, char_B, ...].
        This helps Google Flow detect characters for consistent edits.
        """
        ts = int(time.time() * 1000)
        ctx = self._client_context(project_id, user_paygate_tier)

        image_inputs = [
            {"name": source_media_id, "imageInputType": "IMAGE_INPUT_TYPE_BASE_IMAGE"}
        ]
        if character_media_ids:
            for mid in character_media_ids:
                image_inputs.append({"name": mid, "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"})

        request_item = {
            "clientContext": {**ctx, "sessionId": f";{ts}"},
            "seed": ts % 1000000,
            "structuredPrompt": {"parts": [{"text": prompt}]},
            "imageAspectRatio": aspect_ratio,
            "imageModelName": IMAGE_MODELS["NANO_BANANA_PRO"],
            "imageInputs": image_inputs,
        }

        body = {
            "clientContext": ctx,
            "mediaGenerationContext": {"batchId": f"{uuid.uuid4()}"},
            "useNewMedia": True,
            "requests": [request_item],
        }

        url = self._build_url("generate_images", project_id=project_id)
        return await self._send("api_request", {
            "url": url,
            "method": "POST",
            "headers": random_headers(),
            "body": body,
            "captchaAction": "IMAGE_GENERATION",
        })

    async def generate_video(self, start_image_media_id: Optional[str], prompt: str,
                              project_id: str, scene_id: str,
                              aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT",
                              end_image_media_id: str = None,
                              user_paygate_tier: str = "PAYGATE_TIER_TWO",
                              duration_seconds: int = None,
                              output_count: int = 1,
                              custom_model_key: str = None) -> dict:
        """Generate video from start image (i2v) or text (t2v)."""
        if custom_model_key:
            model_key = custom_model_key
        else:
            gen_type = "start_end_frame_2_video" if end_image_media_id else "frame_2_video"
            model_key = VIDEO_MODELS.get(user_paygate_tier, {}).get(gen_type, {}).get(aspect_ratio)

        if not start_image_media_id and model_key:
            model_key = model_key.replace("_i2v_", "_t2v_")

        if not model_key:
            return {"error": f"No model resolved for custom_model_key={custom_model_key} tier={user_paygate_tier}"}

        # We will make independent API calls for each candidate to guarantee multiple generations
        async def do_single_generation(index: int):
            # Generate a unique seed for each request candidate to ensure separate generations
            seed_val = (int(time.time()) + index * 1337) % 1000000
            req_item = {
                "aspectRatio": aspect_ratio,
                "seed": seed_val,
                "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                "videoModelKey": model_key,
                "metadata": {"sceneId": scene_id},
            }
            if start_image_media_id:
                req_item["startImage"] = {"mediaId": start_image_media_id}
            if end_image_media_id:
                req_item["endImage"] = {"mediaId": end_image_media_id}

            endpoint_key = "generate_video_start_end" if end_image_media_id else ("generate_video" if start_image_media_id else "generate_video_text")
            body = {
                "mediaGenerationContext": {"batchId": f"{uuid.uuid4()}"},
                "clientContext": self._client_context(project_id, user_paygate_tier),
                "requests": [req_item],
                "useV2ModelConfig": True,
            }

            url = self._build_url(endpoint_key)
            return await self._send("api_request", {
                "url": url,
                "method": "POST",
                "headers": random_headers(),
                "body": body,
                "captchaAction": "VIDEO_GENERATION",
            }, timeout=60)

        # Call in parallel
        tasks = [do_single_generation(i) for i in range(max(1, output_count))]
        responses = await asyncio.gather(*tasks)

        # Merge the responses
        merged_data = {"operations": [], "workflows": [], "media": []}
        for resp in responses:
            if "error" in resp or resp.get("status", 200) >= 400:
                # If any call fails, return the error
                return resp
            data = resp.get("data", resp)
            if isinstance(data, dict):
                merged_data["operations"].extend(data.get("operations") or [])
                merged_data["workflows"].extend(data.get("workflows") or [])
                merged_data["media"].extend(data.get("media") or [])

        # Clean up empty keys
        final_data = {}
        if merged_data["operations"]:
            final_data["operations"] = merged_data["operations"]
        if merged_data["workflows"]:
            final_data["workflows"] = merged_data["workflows"]
        if merged_data["media"]:
            final_data["media"] = merged_data["media"]

        return {"data": final_data}

    async def generate_video_from_references(self, reference_media_ids: list[str],
                                              prompt: str, project_id: str, scene_id: str,
                                              aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT",
                                              user_paygate_tier: str = "PAYGATE_TIER_TWO") -> dict:
        """Generate video from multiple reference images (r2v).

        Uses referenceImages instead of startImage — the model composes
        a video from all provided reference character images.

        Args:
            reference_media_ids: List of character media_ids (from uploadImage)
        """
        gen_type = "reference_frame_2_video"
        model_key = VIDEO_MODELS.get(user_paygate_tier, {}).get(gen_type, {}).get(aspect_ratio)

        if not model_key:
            return {"error": f"No model for tier={user_paygate_tier} type={gen_type} ratio={aspect_ratio}"}

        request = {
            "aspectRatio": aspect_ratio,
            "seed": int(time.time()) % 10000,
            "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
            "videoModelKey": model_key,
            "referenceImages": [
                {"mediaId": mid, "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"}
                for mid in reference_media_ids
            ],
            "metadata": {},
        }

        body = {
            "mediaGenerationContext": {"batchId": f"{uuid.uuid4()}"},
            "clientContext": self._client_context(project_id, user_paygate_tier),
            "requests": [request],
            "useV2ModelConfig": True,
        }

        url = self._build_url("generate_video_references")
        return await self._send("api_request", {
            "url": url,
            "method": "POST",
            "headers": random_headers(),
            "body": body,
            "captchaAction": "VIDEO_GENERATION",
        }, timeout=60)

    async def upscale_video(self, media_id: str, scene_id: str,
                             aspect_ratio: str = "VIDEO_ASPECT_RATIO_PORTRAIT",
                             resolution: str = "VIDEO_RESOLUTION_4K") -> dict:
        """Upscale a video."""
        model_key = UPSCALE_MODELS.get(resolution, "veo_3_1_upsampler_4k")

        body = {
            "clientContext": {
                "sessionId": f";{int(time.time() * 1000)}",
                "recaptchaContext": {
                    "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
                    "token": "",
                },
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "resolution": resolution,
                "seed": int(time.time()) % 100000,
                "metadata": {"sceneId": scene_id},
                "videoInput": {"mediaId": media_id},
                "videoModelKey": model_key,
            }],
        }

        url = self._build_url("upscale_video")
        return await self._send("api_request", {
            "url": url,
            "method": "POST",
            "headers": random_headers(),
            "body": body,
            "captchaAction": "VIDEO_GENERATION",
        }, timeout=60)

    async def check_video_status(self, operations: list[dict]) -> dict:
        """Check status of video generation operations."""
        body = {"operations": operations}
        url = self._build_url("check_video_status")
        return await self._send("api_request", {
            "url": url,
            "method": "POST",
            "headers": random_headers(),
            "body": body,
        }, timeout=30)  # No captcha needed

    async def get_credits(self) -> dict:
        """Get user credits and tier."""
        url = self._build_url("get_credits")
        return await self._send("api_request", {
            "url": url,
            "method": "GET",
            "headers": random_headers(),
        }, timeout=15)

    async def validate_media_id(self, media_id: str) -> bool:
        """Check if a mediaId is still valid.

        Production calls: GET /v1/media/{mediaId}?key=...&clientContext.tool=PINHOLE
        Returns True on 200, False otherwise.
        """
        result = await self.get_media(media_id)
        status = result.get("status", 500)
        return isinstance(status, int) and status == 200

    async def get_media(self, media_id: str, project_id: str = "") -> dict:
        """Fetch media metadata from Google Flow, trying direct redirect download first, then falling back."""
        clean_id = media_id.replace("media/", "") if media_id else ""
        
        # Try direct GCS download by checking database or triggering prefetch
        if clean_id:
            try:
                # Check if we already have it in DB
                gcs_url = None
                from agent.db import crud
                scenes = await crud.list_scenes_by_media_id(clean_id)
                for scene in scenes:
                    for p in ["vertical_video", "horizontal_video", "vertical_image", "horizontal_image", "vertical_upscale", "horizontal_upscale"]:
                        if scene.get(f"{p}_media_id") == clean_id:
                            val = scene.get(f"{p}_url")
                            if val and val.startswith("http"):
                                gcs_url = val
                                break
                    if gcs_url:
                        break
                        
                # If not in DB, trigger prefetch through the extension and poll
                if not gcs_url and self._extension_ws:
                    logger.info("GCS URL not in DB for %s. Triggering extension prefetch...", clean_id[:12])
                    await self._extension_ws.send(json.dumps({
                        "method": "trigger_media_prefetch",
                        "params": {"mediaId": clean_id}
                    }))
                    
                    # Poll SQLite for up to 4 seconds
                    for attempt in range(40):
                        await asyncio.sleep(0.1)
                        scenes = await crud.list_scenes_by_media_id(clean_id)
                        for scene in scenes:
                            for p in ["vertical_video", "horizontal_video", "vertical_image", "horizontal_image", "vertical_upscale", "horizontal_upscale"]:
                                if scene.get(f"{p}_media_id") == clean_id:
                                    val = scene.get(f"{p}_url")
                                    if val and val.startswith("http"):
                                        gcs_url = val
                                        break
                            if gcs_url:
                                break
                        if gcs_url:
                            logger.info("Prefetch matched GCS URL in DB on attempt %d: %s", attempt+1, gcs_url[:80])
                            break
                            
                # If we have a GCS URL, download it directly in python (it does not require cookies)
                if gcs_url and gcs_url.startswith("http"):
                    logger.info("Downloading direct GCS URL via python for media %s...", clean_id[:12])
                    import aiohttp
                    import base64
                    connector = aiohttp.TCPConnector(ssl=False)
                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with session.get(gcs_url) as resp:
                            if resp.status == 200:
                                body = await resp.read()
                                encoded = base64.b64encode(body).decode("utf-8")
                                logger.info("Direct GCS download succeeded for media %s (%d bytes)", clean_id[:12], len(body))
                                return {
                                    "video": {
                                        "encodedVideo": encoded
                                    },
                                    "image": {
                                        "encodedImage": encoded
                                    }
                                }
                            else:
                                logger.warning("Direct GCS download failed: HTTP %d", resp.status)
            except Exception as e:
                logger.warning("Failed direct GCS prefetch/download attempt for %s: %s", clean_id[:12], e)

        paths_to_try = []
        if project_id and clean_id:
            paths_to_try.append(f"/v1/projects/{project_id}/flowMedia/{clean_id}")
            paths_to_try.append(f"/v1/projects/{project_id}/media/{clean_id}")
        if clean_id:
            paths_to_try.append(f"/v1/media/{clean_id}")
        if media_id and media_id.startswith("media/"):
            paths_to_try.append(f"/v1/{media_id}")
            
        # Build combinations of query parameters to try
        queries_to_try = []
        if project_id:
            queries_to_try.append(f"key={GOOGLE_API_KEY}&clientContext.toolName=PINHOLE&clientContext.projectId={project_id}")
            queries_to_try.append(f"key={GOOGLE_API_KEY}&clientContext.tool=PINHOLE&clientContext.projectId={project_id}")
        queries_to_try.append(f"key={GOOGLE_API_KEY}&clientContext.toolName=PINHOLE")
        queries_to_try.append(f"key={GOOGLE_API_KEY}&clientContext.tool=PINHOLE")
        queries_to_try.append(f"key={GOOGLE_API_KEY}")
        
        last_err = None
        for path in paths_to_try:
            for query in queries_to_try:
                url = f"{GOOGLE_FLOW_API}{path}?{query}"
                logger.info("Trying get_media URL: %s", url)
                res = await self._send("api_request", {
                    "url": url,
                    "method": "GET",
                    "headers": random_headers(),
                }, timeout=15)
                
                if res and isinstance(res, dict) and not res.get("error"):
                    status = res.get("status", 200)
                    if isinstance(status, int) and status < 400:
                        logger.info("Successfully fetched get_media using URL: %s", url)
                        return res
                    else:
                        last_err = res.get("data", res)
                else:
                    last_err = res.get("error") if res else "Empty response"
                    
        return {"error": f"All get_media attempts failed. Last error: {last_err}"}

    async def upload_image(self, image_base64: str, mime_type: str = "image/jpeg",
                            project_id: str = "", file_name: str = "image.jpg") -> dict:
        """Upload an image for use as start/end frame.

        Uses /v1/flow/uploadImage endpoint.
        Response: {media: {name: "uuid", ...}, workflow: {...}}
        We store media.name as the mediaId for video generation.
        """
        import os
        if os.environ.get("MOCK_FLOW_CLIENT") == "1":
            return {
                "success": True,
                "_mediaId": "a2948942-2616-4731-a395-d1afac6a87a7",
                "data": {
                    "media": {
                        "name": "a2948942-2616-4731-a395-d1afac6a87a7"
                    }
                }
            }
        body = {
            "clientContext": {
                "projectId": project_id,
                "tool": "PINHOLE",
            },
            "fileName": file_name,
            "imageBytes": image_base64,
            "isHidden": False,
            "isUserUploaded": True,
            "mimeType": mime_type,
        }

        url = self._build_url("upload_image")
        result = await self._send("api_request", {
            "url": url,
            "method": "POST",
            "headers": random_headers(),
            "body": body,
        }, timeout=60)

        # Extract media.name for convenience (used as mediaId in video gen)
        if not _is_ws_error(result):
            data = result.get("data", {})
            if isinstance(data, dict):
                media = data.get("media", {})
                if isinstance(media, dict) and media.get("name"):
                    result["_mediaId"] = media["name"]

        return result


def _is_ws_error(result: dict) -> bool:
    return bool(result.get("error")) or (isinstance(result.get("status"), int) and result["status"] >= 400)


# Singleton
_client: Optional[FlowClient] = None


def get_flow_client() -> FlowClient:
    global _client
    if _client is None:
        _client = FlowClient()
    return _client
