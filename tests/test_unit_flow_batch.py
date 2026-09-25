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
        from agent.api.batch_uploader import fix_prompts_with_gemini, FixPromptsRequest, FixPromptItem

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
            req = FixPromptsRequest(
                gemini_api_key="test_key",
                items=[FixPromptItem(scene_num="01", prompt=sample_prompt, error_message="Safety policy blocked: baby, weapons")]
            )
            res = asyncio.run(fix_prompts_with_gemini(req))
            rewritten = res["fixed_items"][0]["fixed_prompt"]

        self.assertIn("Duration: 10 seconds", rewritten)
        self.assertIn("0s-3s —", rewritten)
        self.assertIn("3s-7s —", rewritten)
        self.assertIn("\n\n", rewritten)
        self.assertGreater(len(captured_payloads), 0)
        system_text = captured_payloads[0]["contents"][0]["parts"][0]["text"]
        self.assertIn("100% STRUCTURAL PRESERVATION", system_text)
        self.assertIn("timestamps", system_text.lower())
        self.assertIn("line breaks", system_text.lower())

    def test_find_media_id_in_listing_comprehensive(self):
        sample_payload = [
            [
                "11111111-2222-3333-4444-555555555555",
                None,
                None,
                ["Close up shot of a cute golden retriever puppy running on grass", [1710000000, 0], True, None, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "client-uuid-1", [1710000050, 0]],
                "99999999-9999-9999-9999-999999999999"
            ],
            [
                "55555555-6666-7777-8888-999999999999",
                None,
                None,
                ["A futuristic sports car driving at night through neon city", [1710000100, 0], True, None, "11111111-ffff-0000-1111-222222222222", "client-uuid-2", [1710000150, 0]],
                "99999999-9999-9999-9999-999999999999"
            ]
        ]

        # 1. Match by prompt
        m1 = fb.find_media_id_in_listing(sample_payload, target_id="ui_t2v_abc123", prompt="golden retriever puppy running")
        self.assertEqual(m1, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        # 2. Match by exact op_id
        m2 = fb.find_media_id_in_listing(sample_payload, target_id="55555555-6666-7777-8888-999999999999")
        self.assertEqual(m2, "11111111-ffff-0000-1111-222222222222")

        # 3. Exclude completed IDs
        m3 = fb.find_media_id_in_listing(sample_payload, target_id="ui_t2v_xyz", exclude_ids={"11111111-ffff-0000-1111-222222222222"})
        self.assertEqual(m3, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        # 4. Thai prompt substring match
        sample_thai = [
            [
                "22222222-3333-4444-5555-666666666666",
                None,
                None,
                ["ฉากละครสัตว์กลางคืน มีเสือกระโดดลอดบ่วงไฟ แสงไฟสว่างวาบ", [1710000200, 0], True, None, "33333333-4444-5555-6666-777777777777", "client-uuid-3", [1710000250, 0]],
                "99999999-9999-9999-9999-999999999999"
            ]
        ]
        m_thai = fb.find_media_id_in_listing(sample_thai, prompt="ฉากละครสัตว์กลางคืน มีเสือกระโดดลอดบ่วงไฟ")
        self.assertEqual(m_thai, "33333333-4444-5555-6666-777777777777")

    def test_check_flow_tab_for_video_and_poll_batch(self):
        import asyncio
        from unittest.mock import AsyncMock
        from agent.services.flow_client import FlowClient

        client = FlowClient()
        dummy_ws = object()
        client.set_extension(dummy_ws)
        op_id = "ui_t2v_mock123"
        prompt = "Aerial drone shot over lush tropical jungle"
        client._remember_operation(op_id, "mock-proj", prompt=prompt)

        # Mock inspect_tab returning active pending tile (still rendering)
        client._send = AsyncMock(return_value={
            "result": {
                "result": {
                    "results": [],
                    "pendingTexts": ["Aerial drone shot over lush tropical jungle 45%"]
                }
            }
        })
        mid, vurl = asyncio.run(client._check_flow_tab_for_video(op_id))
        self.assertIsNone(mid)
        self.assertIsNone(vurl)

        # Mock inspect_tab returning completed video element
        expected_vurl = "https://flow-content.google/video/44444444-5555-6666-7777-888888888888?Expires=123"
        client._send = AsyncMock(return_value={
            "result": {
                "result": {
                    "results": [{
                        "src": expected_vurl,
                        "mediaId": "44444444-5555-6666-7777-888888888888",
                        "text": "Aerial drone shot over lush tropical jungle"
                    }],
                    "pendingTexts": []
                }
            }
        })
        mid, vurl = asyncio.run(client._check_flow_tab_for_video(op_id))
        self.assertEqual(mid, "44444444-5555-6666-7777-888888888888")
        self.assertEqual(vurl, expected_vurl)

        # Poll batch operation should immediately succeed via DOM inspection
        poll_res = asyncio.run(client._poll_batch_operation(op_id))
        self.assertEqual(poll_res.get("status"), "MEDIA_GENERATION_STATUS_SUCCESSFUL")
        self.assertEqual(poll_res.get("operation", {}).get("metadata", {}).get("video", {}).get("fifeUrl"), expected_vurl)
        self.assertEqual(client._operation_video_urls.get(op_id), expected_vurl)

    def test_video_request_output_count_support(self):
        from agent.services.flow_batch import video_request, text_video_request, resolve_video_model
        import json

        # Check resolve_video_model resolves wire names
        self.assertEqual(resolve_video_model("lite_low_priority"), "veo_3_1_i2v_lite_low_priority")
        self.assertEqual(resolve_video_model("t2v_lite_low_priority"), "veo_3_1_t2v_lite_low_priority")
        self.assertEqual(resolve_video_model("abra_t2v_4s"), "abra_t2v_4s")

        # Check video_request with output_count = 2
        raw_env = video_request("Cinematic test", "proj-123", "media-456", output_count=2)
        parsed = json.loads(raw_env)
        # inner payload is parsed[0][0][1] as JSON string
        inner = json.loads(parsed[0][0][1])
        requests = inner[0]
        self.assertEqual(len(requests), 2, "video_request should replicate 2 items when output_count=2")
        self.assertEqual(inner[2][1], 2, "video_request outer count should match output_count")

        # Check text_video_request with output_count = 2
        raw_t2v = text_video_request("Prompt only test", "proj-123", output_count=2)
        parsed_t2v = json.loads(raw_t2v)
        inner_t2v = json.loads(parsed_t2v[0][0][1])
        self.assertEqual(len(inner_t2v[0]), 2, "text_video_request should replicate 2 items when output_count=2")
        self.assertEqual(inner_t2v[2][1], 2)

    def test_worker_controller_background_tasks_and_cancel(self):
        import asyncio
        from agent.worker.processor import WorkerController

        controller = WorkerController()
        self.assertEqual(len(controller._background_tasks), 0)

        async def dummy_bg():
            await asyncio.sleep(10)

        loop = asyncio.new_event_loop()
        task = loop.create_task(dummy_bg())
        controller.register_background_task("req-123", task)
        self.assertIn("req-123", controller._background_tasks)

        # Cancel all active tasks should cleanly cancel background tasks
        loop.run_until_complete(controller.cancel_all_active_tasks())
        self.assertTrue(task.cancelled())
        self.assertEqual(len(controller._background_tasks), 0)
        loop.close()

    def test_compute_prompt_match_score(self):
        from agent.services.flow_batch import compute_prompt_match_score

        # 1. Thai prompt matching without spaces
        p_thai = "ฉากในห้องนอนพระเอกกำลังคุยกับนางเอกด้วยอารมณ์ตึงเครียด"
        t_thai = "@01.png ฉากในห้องนอนพระเอกกำลังคุยกับนางเอก..."
        score_thai = compute_prompt_match_score(p_thai, t_thai)
        self.assertGreaterEqual(score_thai, 4.0, "Thai prompt with mention should match accurately")

        # 2. English prompt matching
        p_en = "Cinematic aerial shot of an ancient temple at sunset"
        t_en = "@02.png Ancient temple at sunset with dramatic cinematic lighting"
        score_en = compute_prompt_match_score(p_en, t_en)
        self.assertGreaterEqual(score_en, 4.0, "English prompt should match word tokens and mentions")

        # 3. Unrelated prompts should have zero score
        p_other = "A futuristic spaceship flying through hyperdrive"
        self.assertEqual(compute_prompt_match_score(p_thai, p_other), 0.0)

    def test_find_media_id_in_listing_exact_match_without_detail6(self):
        # Google Flow often has null detail[6] while rendering or completed
        sample_payload = [
            [
                "op-exact-12345",
                None,
                None,
                ["Title of the video", [1710000000, 0], False, None, "11112222-3333-4444-5555-666677778888", "uuid-1", None],
                "proj-999"
            ]
        ]
        # Should resolve mid directly when op_id matches target_id
        mid = fb.find_media_id_in_listing(sample_payload, target_id="op-exact-12345")
        self.assertEqual(mid, "11112222-3333-4444-5555-666677778888")

    def test_poll_batch_operation_instant_as29s_from_dom_mid(self):
        import asyncio
        from unittest.mock import AsyncMock
        from agent.services.flow_client import FlowClient
        from agent.services.flow_batch import MediaUrls

        client = FlowClient()
        dummy_ws = object()
        client.set_extension(dummy_ws)
        op_id = "op-test-dom-as29s"
        client._remember_operation(op_id, "mock-proj", prompt="Lush forest drone view")

        # Mock DOM returning mediaId (e.g. from outerHTML or data attribute), but video element not yet mounted
        client._check_flow_tab_for_video = AsyncMock(return_value=("dom-media-id-999", None))
        # Mock _batch_media_urls immediately returning ready video URL
        expected_vurl = "https://flow-content.google/video/dom-media-id-999?Expires=999"
        client._batch_media_urls = AsyncMock(return_value=MediaUrls(
            media_id="dom-media-id-999",
            video=expected_vurl,
            image="https://flow-content.google/image/dom-media-id-999"
        ))

        res = asyncio.run(client._poll_batch_operation(op_id))
        self.assertEqual(res.get("status"), "MEDIA_GENERATION_STATUS_SUCCESSFUL")
        self.assertEqual(res.get("operation", {}).get("metadata", {}).get("video", {}).get("fifeUrl"), expected_vurl)
        self.assertEqual(client._operation_video_urls.get(op_id), expected_vurl)

    def test_flow_client_generate_video_sequential_multi_output(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from agent.services.flow_client import FlowClient

        client = FlowClient()
        dummy_ws = object()
        client.set_extension(dummy_ws)

        # Mock _batch_payload to return dummy RPC responses
        call_count = 0
        def fake_read_submit(payload):
            nonlocal call_count
            call_count += 1
            return {
                "media_id": f"media-uuid-{call_count}",
                "workflow_id": f"workflow-uuid-{call_count}",
                "status": "PENDING"
            }

        client._batch_payload = AsyncMock(return_value=["mock-payload"])

        with patch("agent.services.flow_batch.read_text_video_submit", side_effect=fake_read_submit), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = asyncio.run(client.generate_video(
                prompt="Sunset over ocean waves",
                project_id="11112222-3333-4444-5555-666677778888",
                output_count=2
            ))

        self.assertEqual(res.get("status"), 200)
        ops = res.get("data", {}).get("operations", [])
        self.assertEqual(len(ops), 2, "Should return 2 operations for output_count=2")
        self.assertEqual(client._batch_payload.call_count, 2, "Should submit 2 separate times to Google Flow")
        mock_sleep.assert_called_once_with(2.0)
        self.assertIn("workflow-uuid-1", client._operation_media)
        self.assertIn("workflow-uuid-2", client._operation_media)

if __name__ == "__main__":
    unittest.main()

