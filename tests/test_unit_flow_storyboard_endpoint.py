"""
Unit tests for Flow Storyboard Central Endpoint & Runner
"""
import unittest
from agent.api.flow import GenerateStoryboardRequest, PreloadCharactersRequest, router
from scripts.flow_storyboard_runner import parse_range, soften_prompt_for_safety

class TestFlowStoryboard(unittest.TestCase):
    def test_preload_characters_request_defaults(self):
        req = PreloadCharactersRequest()
        self.assertEqual(req.project_id, "21a1632e-9926-46fa-954c-240d71d78f41")
        self.assertIsNone(req.story_path)
        self.assertIsNone(req.image_paths)

    def test_preload_characters_route_registered(self):
        route_paths = [r.path for r in router.routes]
        self.assertIn("/flow/preload-characters", route_paths)

    def test_generate_storyboard_request_defaults(self):
        req = GenerateStoryboardRequest(prompt="Test prompt")
        self.assertEqual(req.prompt, "Test prompt")
        self.assertEqual(req.aspect_ratio, "9:16")
        self.assertEqual(req.project_id, "21a1632e-9926-46fa-954c-240d71d78f41")
        self.assertIsNone(req.reference_images)
        self.assertIsNone(req.output_path)
        self.assertEqual(req.timeout, 180)

    def test_generate_storyboard_request_custom(self):
        req = GenerateStoryboardRequest(
            prompt="Stickman prompt",
            project_id="custom-project-123",
            aspect_ratio="16:9",
            reference_images=["/path/to/char.png"],
            output_path="/path/to/out.jpg",
            timeout=120
        )
        self.assertEqual(req.aspect_ratio, "16:9")
        self.assertEqual(req.project_id, "custom-project-123")
        self.assertEqual(req.reference_images, ["/path/to/char.png"])
        self.assertEqual(req.output_path, "/path/to/out.jpg")

    def test_generate_storyboard_route_registered(self):
        route_paths = [r.path for r in router.routes]
        self.assertIn("/flow/generate-storyboard", route_paths)

    def test_parse_range(self):
        self.assertEqual(parse_range("1-5"), [1, 2, 3, 4, 5])
        self.assertEqual(parse_range("1,3,7"), [1, 3, 7])
        self.assertEqual(parse_range("1-3,5,8-10"), [1, 2, 3, 5, 8, 9, 10])

    def test_soften_prompt_for_safety_round_1(self):
        raw = "Villain holding a knife in the torture dungeon with blood on hands"
        softened = soften_prompt_for_safety(raw, round_num=1)
        self.assertNotIn("knife", softened.lower())
        self.assertNotIn("torture dungeon", softened.lower())
        self.assertNotIn("blood", softened.lower())
        self.assertIn("dim shadowy chamber", softened)
        self.assertIn("gesturing with a dramatically pointed finger", softened)

    def test_soften_prompt_for_safety_round_2(self):
        raw = "Screaming in agony while tied up"
        softened = soften_prompt_for_safety(raw, round_num=2)
        self.assertNotIn("screaming in agony", softened.lower())
        self.assertNotIn("tied up", softened.lower())
        self.assertIn("Family-friendly emotional Thai melodrama", softened)

    def test_check_flow_busy_in_process_lock(self):
        import asyncio
        import json
        from agent.api.flow import _check_flow_busy, _storyboard_active_state

        _storyboard_active_state["busy"] = True
        _storyboard_active_state["project_id"] = "active-proj-999"
        try:
            resp = asyncio.run(_check_flow_busy(None, "fallback-proj-123"))
            self.assertIsNotNone(resp)
            self.assertEqual(resp.status_code, 429)
            body = json.loads(resp.body.decode("utf-8"))
            self.assertFalse(body["success"])
            self.assertEqual(body["status"], "busy")
            self.assertEqual(body["message"], "Google Flow is currently busy rendering another task")
            self.assertEqual(body["current_project"], "active-proj-999")
        finally:
            _storyboard_active_state["busy"] = False
            _storyboard_active_state["project_id"] = None

    def test_check_flow_busy_live_tab_pending(self):
        import asyncio
        import json
        from unittest.mock import MagicMock, AsyncMock, patch
        from agent.api.flow import _check_flow_busy

        mock_client = MagicMock()
        mock_client.connected = True

        with patch("agent.api.flow._eval_js_internal", new=AsyncMock(return_value={"isBusy": True, "pendingCount": 2, "currentProject": "tab-proj-888"})):
            resp = asyncio.run(_check_flow_busy(mock_client, "fallback-proj-123"))
            self.assertIsNotNone(resp)
            self.assertEqual(resp.status_code, 429)
            body = json.loads(resp.body.decode("utf-8"))
            self.assertFalse(body["success"])
            self.assertEqual(body["status"], "busy")
            self.assertEqual(body["message"], "Google Flow is currently busy rendering another task")
            self.assertEqual(body["current_project"], "tab-proj-888")

    def test_post_with_busy_retry_retries_and_succeeds(self):
        from unittest.mock import patch
        from scripts.flow_storyboard_runner import post_with_busy_retry

        # Call 1: 429 busy
        # Call 2: success
        side_effects = [
            {"success": False, "status_code": 429, "status": "busy", "message": "Google Flow is currently busy rendering another task", "current_project": "proj-1"},
            {"success": True, "image_url": "https://flow.google/img.jpg"}
        ]
        with patch("scripts.flow_storyboard_runner.http_post", side_effect=side_effects):
            with patch("time.sleep"):  # do not delay tests
                res = post_with_busy_retry("http://localhost:6969/api/flow/generate-storyboard", {"prompt": "test"}, timeout=10, max_busy_retries=5)
                self.assertTrue(res.get("success"))
                self.assertEqual(res.get("image_url"), "https://flow.google/img.jpg")

    def test_check_flow_busy_allow_same_project_queue(self):
        import asyncio
        import json
        from unittest.mock import MagicMock, AsyncMock, patch
        from agent.api.flow import _check_flow_busy

        mock_client = MagicMock()
        mock_client.connected = True

        # Case 1: Same project with 2 pending tiles (< 5) -> NOT busy for queue
        with patch("agent.api.flow._eval_js_internal", new=AsyncMock(return_value={"isBusy": True, "pendingCount": 2, "currentProject": "same-proj"})):
            resp = asyncio.run(_check_flow_busy(mock_client, "same-proj", allow_same_project_queue=True, max_queue=5))
            self.assertIsNone(resp)

        # Case 2: Same project with 5 pending tiles (>= 5) -> Busy (queue full)
        with patch("agent.api.flow._eval_js_internal", new=AsyncMock(return_value={"isBusy": True, "pendingCount": 5, "currentProject": "same-proj"})):
            resp = asyncio.run(_check_flow_busy(mock_client, "same-proj", allow_same_project_queue=True, max_queue=5))
            self.assertIsNotNone(resp)
            self.assertEqual(resp.status_code, 429)
            body = json.loads(resp.body.decode("utf-8"))
            self.assertIn("queue is full", body["message"])

        # Case 3: Different project with 1 pending tile -> Busy (cannot switch while other project renders)
        with patch("agent.api.flow._eval_js_internal", new=AsyncMock(return_value={"isBusy": True, "pendingCount": 1, "currentProject": "other-proj"})):
            resp = asyncio.run(_check_flow_busy(mock_client, "my-target-proj", allow_same_project_queue=True, max_queue=5))
            self.assertIsNotNone(resp)
            self.assertEqual(resp.status_code, 429)
            body = json.loads(resp.body.decode("utf-8"))
            self.assertEqual(body["current_project"], "other-proj")

    def test_preload_characters_returns_429_when_busy(self):
        import asyncio
        import json
        from unittest.mock import MagicMock, AsyncMock, patch
        from agent.api.flow import preload_characters, PreloadCharactersRequest

        mock_client = MagicMock()
        mock_client.connected = True

        with patch("agent.api.flow.get_flow_client", return_value=mock_client):
            with patch("agent.api.flow._eval_js_internal", new=AsyncMock(return_value={"isBusy": True, "pendingCount": 1, "currentProject": "stickman-proj"})):
                req = PreloadCharactersRequest(project_id="lakorn-proj")
                resp = asyncio.run(preload_characters(req))
                self.assertEqual(resp.status_code, 429)
                body = json.loads(resp.body.decode("utf-8"))
                self.assertFalse(body["success"])
                self.assertEqual(body["status"], "busy")

    def test_dispatch_storyboard_prompt_returns_429_when_busy(self):
        import asyncio
        import json
        from unittest.mock import MagicMock, AsyncMock, patch
        from agent.api.flow import dispatch_storyboard_prompt
        from agent.api.flow import DispatchStoryboardPromptRequest

        mock_client = MagicMock()
        mock_client.connected = True

        with patch("agent.api.flow.get_flow_client", return_value=mock_client):
            with patch("agent.api.flow._eval_js_internal", new=AsyncMock(return_value={"isBusy": True, "pendingCount": 2, "currentProject": "stickman-proj"})):
                req = DispatchStoryboardPromptRequest(prompt="Lakorn prompt", project_id="lakorn-proj")
                resp = asyncio.run(dispatch_storyboard_prompt(req))
                self.assertEqual(resp.status_code, 429)
                body = json.loads(resp.body.decode("utf-8"))
                self.assertFalse(body["success"])
                self.assertEqual(body["status"], "busy")

    def test_ensure_project_id_raises_429_when_other_project_busy(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from fastapi import HTTPException
        from agent.api.flow import _ensure_project_id

        mock_client = MagicMock()
        mock_client.connected = True

        # Current tab is on Stickman and has 1 pending tile
        mock_eval = AsyncMock(side_effect=[
            "https://flow.google.com/project/stickman-proj",  # window.location.href
            {"pendingCount": 1, "currentProject": "stickman-proj"}  # busy check
        ])
        with patch("agent.api.flow._eval_js_internal", new=mock_eval):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(_ensure_project_id(mock_client, "lakorn-proj"))
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertIn("stickman-proj", str(ctx.exception.detail))

    def test_flow_chip_selectors_coverage(self):
        from agent.api.flow import FLOW_CHIP_SELECTORS
        self.assertIn("flow-base-prompt-box flow-image-ingredient-chip", FLOW_CHIP_SELECTORS)
        self.assertIn("flow-base-prompt-box [class*='ingredient-chip']", FLOW_CHIP_SELECTORS)
        self.assertIn("flow-prompt-box flow-image-ingredient-chip", FLOW_CHIP_SELECTORS)
        self.assertIn("[class*='ingredient-chip']", FLOW_CHIP_SELECTORS)

    def test_ensure_project_id_returns_from_edit_mode(self):
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from agent.api.flow import _ensure_project_id

        mock_client = MagicMock()
        mock_client.connected = True

        # Current tab is in edit mode for same project
        eval_history = []
        async def mock_eval_fn(client, js, timeout=15):
            eval_history.append(js)
            if "pendingCount" in js:
                return {"pendingCount": 0, "currentProject": "lakorn-proj"}
            if "window.location.href" in js and "split" not in js:
                return "https://flow.google.com/u/1/project/lakorn-proj/edit/tile-uuid-123"
            if "button.back-button" in js:
                return "clicked_back"
            return "https://flow.google.com/u/1/project/lakorn-proj"

        with patch("agent.api.flow._eval_js_internal", new=AsyncMock(side_effect=mock_eval_fn)):
            asyncio.run(_ensure_project_id(mock_client, "lakorn-proj"))
            # Verified that back button / exit js was evaluated
            has_exit_js = any("button.back-button" in str(code) for code in eval_history)
            self.assertTrue(has_exit_js)

if __name__ == "__main__":
    unittest.main()


