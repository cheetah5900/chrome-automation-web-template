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

if __name__ == "__main__":
    unittest.main()
