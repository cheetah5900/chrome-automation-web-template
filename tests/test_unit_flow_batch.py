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
        from agent.services.flow_client import FlowClient

        client = FlowClient()
        op_id = "test-op-1234"
        media_id = "test-media-5678"
        client._operation_media[op_id] = media_id
        client._not_found_counts[op_id] = 7  # becomes 8 on poll

        client._batch_media_urls = AsyncMock(side_effect=Exception("as29s failed: [5]"))
        client._find_operation_media = AsyncMock(return_value=(None, None))
        client._check_flow_tab_404 = AsyncMock(return_value=None)

        res = asyncio.run(client._poll_batch_operation(op_id))
        self.assertEqual(res.get("status"), "MEDIA_GENERATION_STATUS_FAILED")
        self.assertIn("[5]", res.get("error"))

if __name__ == "__main__":
    unittest.main()
