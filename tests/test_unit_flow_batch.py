import unittest
from agent.services import flow_batch as fb
from agent.services.prompt_sanitizer import sanitize_lakorn_prompt
from agent.api.batch_uploader import natural_sort_key, summarize_prompt_for_filename

class TestFlowBatchUnit(unittest.TestCase):
    def test_resolve_video_model(self):
        # Ultra tier models
        self.assertEqual(fb.resolve_video_model("veo_3_1_i2v_s_fast_ultra"), "veo_3_1_i2v_s_fast_ultra")
        self.assertEqual(fb.resolve_video_model("fast_ultra"), "veo_3_1_i2v_s_fast_ultra")
        
        # Lite and low priority models
        self.assertEqual(fb.resolve_video_model("lite_low_priority"), "veo_3_1_i2v_lite_low_priority")
        self.assertEqual(fb.resolve_video_model("veo_3_1_i2v_lite_low_priority"), "veo_3_1_i2v_lite_low_priority")
        self.assertEqual(fb.resolve_video_model("lite"), "veo_3_1_i2v_lite")

        # Unknown models fallback to default VIDEO_MODEL
        self.assertEqual(fb.resolve_video_model(None), fb.VIDEO_MODEL)
        self.assertEqual(fb.resolve_video_model("unknown_model_xyz"), fb.VIDEO_MODEL)

    def test_resolve_video_aspect(self):
        self.assertEqual(fb.resolve_video_aspect("PORTRAIT"), 1)
        self.assertEqual(fb.resolve_video_aspect("VERTICAL"), 1)
        self.assertEqual(fb.resolve_video_aspect("VIDEO_ASPECT_RATIO_PORTRAIT"), 1)
        self.assertEqual(fb.resolve_video_aspect(1), 1)

        self.assertEqual(fb.resolve_video_aspect("LANDSCAPE"), 2)
        self.assertEqual(fb.resolve_video_aspect("HORIZONTAL"), 2)
        self.assertEqual(fb.resolve_video_aspect("VIDEO_ASPECT_RATIO_LANDSCAPE"), 2)
        self.assertEqual(fb.resolve_video_aspect(2), 2)

        with self.assertRaises(ValueError):
            fb.resolve_video_aspect(3)

    def test_find_media_id_in_text(self):
        op_id = "0005acec-d670-421c-8015-e5b5a33d2482"
        media_id = "469355ab-6158-4d96-856e-4b677ee3c90f"
        sample_entry = (
            f'[["{op_id}",null,null,["01 - Scene 01.png",[1787242794,355725000],'
            f'true,null,"{media_id}",null,[1787298880,403682000]],"21a1632e-9926-46fa-954c-240d71d78f41"]]'
        )
        extracted = fb.find_media_id_in_text(sample_entry, op_id)
        self.assertEqual(extracted, media_id)

        # Missing op_id returns None
        self.assertIsNone(fb.find_media_id_in_text(sample_entry, "non-existent-op"))

    def test_read_media_urls(self):
        media_id = "1ad2fba7-554c-42e1-a3da-286b401619f4"
        video_url = f"https://flow-content.google/video/{media_id}?Expires=1789667874"
        image_url = f"https://flow-content.google/image/{media_id}?Expires=1789667874"
        payload = [
            media_id,
            "project-123",
            "op-456",
            "CAE",
            None,
            [
                image_url,
                video_url
            ]
        ]
        urls = fb.read_media_urls(payload, media_id)
        self.assertEqual(urls.media_id, media_id)
        self.assertEqual(urls.video, video_url)
        self.assertEqual(urls.image, image_url)

    def test_sanitize_lakorn_prompt(self):
        # Trigger words should be replaced with cinematic safe prompt
        unsafe = "The mother leans over two small bassinets with the baby"
        safe = sanitize_lakorn_prompt(unsafe)
        self.assertIn("Slow cinematic motion", safe)

        # Normal prompt with header lines should be cleaned
        raw = "Episode: 1\nScene: 02\nA lone warrior stands upon the mountain ridge at sunset."
        clean = sanitize_lakorn_prompt(raw)
        self.assertEqual(clean, "A lone warrior stands upon the mountain ridge at sunset.")

    def test_natural_sort_key(self):
        items = ["Scene 10.png", "Scene 2.png", "Scene 1.png"]
        sorted_items = sorted(items, key=natural_sort_key)
        self.assertEqual(sorted_items, ["Scene 1.png", "Scene 2.png", "Scene 10.png"])

    def test_summarize_prompt_for_filename(self):
        prompt = "Dramatic cinematic shot of the glass castle on the highest peak under thunderstorm clouds with lightning"
        summary = summarize_prompt_for_filename(prompt, max_words=8)
        self.assertTrue(len(summary.split()) <= 8)
        self.assertNotIn("/", summary)
    def test_flow_client_fail_fast_on_not_found_round_8(self):
        import asyncio
        from unittest.mock import AsyncMock
        from agent.services.flow_client import FlowClient, MAX_AS29S_NOT_FOUND_ROUNDS

        client = FlowClient()
        op_id = "test-op-1234"
        media_id = "test-media-5678"
        client._operation_media[op_id] = media_id
        client._not_found_counts[op_id] = MAX_AS29S_NOT_FOUND_ROUNDS - 1  # becomes MAX_AS29S_NOT_FOUND_ROUNDS on poll

        client._batch_media_urls = AsyncMock(side_effect=Exception("as29s failed: [5]"))
        client._find_operation_media = AsyncMock(return_value=(None, None))
        client._check_flow_tab_404 = AsyncMock(return_value=None)

        res = asyncio.run(client._poll_batch_operation(op_id))
        self.assertEqual(res.get("status"), "MEDIA_GENERATION_STATUS_FAILED")
        self.assertIn("[5]", res.get("error"))

    def test_gemini_key_save_and_get(self):
        from agent.api.batch_uploader import save_gemini_api_key, get_saved_gemini_key
        original_key = get_saved_gemini_key()
        try:
            save_gemini_api_key("test_gemini_api_key_123456789")
            self.assertEqual(get_saved_gemini_key(), "test_gemini_api_key_123456789")
        finally:
            save_gemini_api_key(original_key)

    def test_fix_prompts_gemini_mocked(self):
        import asyncio
        from unittest.mock import patch, MagicMock
        from agent.api.batch_uploader import fix_prompts_with_gemini, FixPromptsRequest, FixPromptItem

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "A beautiful cinematic landscape at sunset with dramatic golden lighting and camera pan."}
                        ]
                    }
                }
            ]
        }

        req = FixPromptsRequest(
            gemini_api_key="mock_key",
            items=[
                FixPromptItem(
                    scene_id="scene-1",
                    order=1,
                    prompt="A scene with baby and forbidden words",
                    error_message="Safety policy block"
                )
            ]
        )

        from agent.api.batch_uploader import get_saved_gemini_key, save_gemini_api_key
        original_key = get_saved_gemini_key()
        try:
            with patch("httpx.AsyncClient.post", return_value=mock_resp):
                res = asyncio.run(fix_prompts_with_gemini(req))
                self.assertTrue(res["ok"])
                self.assertEqual(res["count"], 1)
                self.assertEqual(res["fixed_items"][0]["status"], "SUCCESS")
                self.assertIn("cinematic landscape", res["fixed_items"][0]["fixed_prompt"])
        finally:
            save_gemini_api_key(original_key)

    def test_create_mock_scene_image(self):
        from agent.api.batch_uploader import create_mock_scene_image
        
        # Test portrait mock image
        portrait_bytes = create_mock_scene_image("03", prompt="A knight on a mountain", error_reason="Safety Block", width=720, height=1280)
        self.assertIsInstance(portrait_bytes, bytes)
        self.assertTrue(len(portrait_bytes) > 1000)
        self.assertEqual(portrait_bytes[:2], b"\xff\xd8")  # JPEG magic bytes

        # Test landscape mock image
        landscape_bytes = create_mock_scene_image("07", prompt="Landscape scene", error_reason="", width=1280, height=720)
        self.assertIsInstance(landscape_bytes, bytes)
        self.assertTrue(len(landscape_bytes) > 1000)
        self.assertEqual(landscape_bytes[:2], b"\xff\xd8")

    def test_missing_sequence_detection(self):
        # Scenario 1: Gap in middle (1, 2, 4 -> 3 missing)
        written_numbers = {1, 2, 4}
        expected_map = {1: {}, 2: {}, 4: {}}
        all_nums = set(range(min(written_numbers), max(written_numbers) + 1))
        missing = sorted(list(all_nums - written_numbers))
        self.assertEqual(missing, [3])

        # Scenario 2: Gap at start and middle (2, 4 written, expected 1..4 -> 1, 3 missing)
        written_numbers_2 = {2, 4}
        expected_map_2 = {1: {}, 2: {}, 3: {}, 4: {}}
        candidate_mins = [min(written_numbers_2), min(expected_map_2.keys())]
        candidate_maxs = [max(written_numbers_2), max(expected_map_2.keys())]
        min_n = 1 if (1 in candidate_mins or any(k <= 1 for k in candidate_mins)) else min(candidate_mins)
        max_n = max(candidate_maxs)
        missing_2 = sorted(list(set(range(min_n, max_n + 1)) - written_numbers_2))
        self.assertEqual(missing_2, [1, 3])

        # Scenario 3: Complete sequence (1, 2, 3 -> no missing)
        written_numbers_3 = {1, 2, 3}
        all_nums_3 = set(range(1, max(written_numbers_3) + 1))
        missing_3 = sorted(list(all_nums_3 - written_numbers_3))
        self.assertEqual(missing_3, [])

    def test_gemini_rewrite_payload_preserves_structure(self):
        import asyncio
        from unittest.mock import patch, MagicMock
        from agent.worker.processor import _call_gemini_rewrite

        captured_payloads = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": (
                            "Duration: 10 seconds\n\n"
                            "0s-3s — Raw handheld POV of performer.\n\n"
                            "3s-7s — Acrobatic spin in center ring.\n\n"
                            "Camera style: vertical 9:16."
                        )
                    }]
                }
            }]
        }

        async def mock_post(url, **kwargs):
            captured_payloads.append(kwargs.get("json"))
            return mock_resp

        sample_prompt = (
            "Duration: 10 seconds\n\n"
            "0s-3s — Raw handheld phone POV with baby performer.\n\n"
            "3s-7s — Acrobatic spin in center ring with weapons.\n\n"
            "Camera style: vertical 9:16."
        )

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            rewritten = asyncio.run(_call_gemini_rewrite(sample_prompt, "Safety policy blocked: baby, weapons", "test_key"))

        self.assertIn("Duration: 10 seconds", rewritten)
        self.assertIn("0s-3s —", rewritten)
        self.assertIn("3s-7s —", rewritten)
        self.assertIn("\n\n", rewritten)
        self.assertGreater(len(captured_payloads), 0)
        system_text = captured_payloads[0]["contents"][0]["parts"][0]["text"]
        self.assertIn("100% STRUCTURAL PRESERVATION", system_text)
        self.assertIn("timestamps", system_text.lower())
        self.assertIn("line breaks", system_text.lower())

if __name__ == "__main__":
    unittest.main()

