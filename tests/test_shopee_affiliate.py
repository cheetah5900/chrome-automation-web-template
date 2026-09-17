import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

class TestShopeeAffiliate(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.main.sync_ensure_chrome_debug_ready", return_value=True)
    @patch("urllib.request.urlopen")
    @patch("app.main.browser_manager.get")
    @patch("app.main._activate_chrome")
    def test_open_url_with_driver(self, mock_activate, mock_browser_get, mock_urlopen, mock_ready):
        # Mock CDP response
        mock_cdp = MagicMock()
        mock_cdp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_cdp

        mock_bot = MagicMock()
        mock_driver = MagicMock()
        mock_bot.driver = mock_driver
        mock_browser_get.return_value = mock_bot

        target_url = "https://affiliate.shopee.co.th/offer/product_offer"
        response = self.client.post("/api/shopee-affiliate/open-url", json={"url": target_url})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        mock_driver.get.assert_called_with(target_url)
        mock_activate.assert_called_once()

    @patch("app.main.sync_ensure_chrome_debug_ready", return_value=False)
    @patch("urllib.request.urlopen", side_effect=Exception("CDP closed"))
    @patch("app.main.browser_manager.get")
    def test_open_url_fallback(self, mock_browser_get, mock_urlopen, mock_ready):
        mock_browser_get.return_value = None  # No chrome attached

        target_url = "https://affiliate.shopee.co.th/offer/product_offer"
        response = self.client.post("/api/shopee-affiliate/open-url", json={"url": target_url})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get("ok"))
        self.assertIn("ไม่สามารถเปิดเบราว์เซอร์", data.get("detail", ""))

    @patch("app.main.sync_ensure_chrome_debug_ready", return_value=True)
    @patch("urllib.request.urlopen")
    @patch("app.main.browser_manager.get")
    @patch("app.main._activate_chrome")
    def test_open_url_default_when_empty(self, mock_activate, mock_browser_get, mock_urlopen, mock_ready):
        mock_bot = MagicMock()
        mock_driver = MagicMock()
        mock_bot.driver = mock_driver
        mock_browser_get.return_value = mock_bot

        response = self.client.post("/api/shopee-affiliate/open-url", json={"url": ""})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("https://affiliate.shopee.co.th/offer/product_offer", data.get("message", ""))
        mock_driver.get.assert_called_with("https://affiliate.shopee.co.th/offer/product_offer")

    def test_progress_endpoint(self):
        response = self.client.get("/api/shopee-affiliate/progress")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)

    def test_stop_endpoint(self):
        response = self.client.post("/api/shopee-affiliate/stop")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))

if __name__ == "__main__":
    unittest.main()
