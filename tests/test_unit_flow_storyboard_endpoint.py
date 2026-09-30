"""
Unit tests for Flow Storyboard Central Endpoint & Runner
"""
import unittest
from agent.api.flow import GenerateStoryboardRequest, router
from scripts.flow_storyboard_runner import parse_range

class TestFlowStoryboard(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()
