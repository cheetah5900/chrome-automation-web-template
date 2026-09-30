import unittest
from unittest.mock import MagicMock
from app.meta_autopost import wait_for_schedule_option_ready

class TestMetaAutopostScheduleReady(unittest.TestCase):
    def test_date_input_already_ready(self):
        mock_driver = MagicMock()
        mock_driver.execute_script.return_value = {
            "status": "date_input_ready",
            "message": "ช่องใส่วันที่และเวลาพร้อมใช้งานแล้ว"
        }
        res = wait_for_schedule_option_ready(mock_driver, timeout=2.0)
        self.assertTrue(res)

    def test_wait_until_upload_finishes_then_ready(self):
        mock_driver = MagicMock()
        # Call 1 & 2: disabled with upload progress
        # Call 3: ready
        mock_driver.execute_script.side_effect = [
            {"status": "disabled", "uploadText": "ความคืบหน้า 30%", "text": "Schedule for later"},
            {"status": "disabled", "uploadText": "ความคืบหน้า 70%", "text": "Schedule for later"},
            {"status": "ready", "uploadText": "", "text": "Schedule for later"},
            True, # click script return
            MagicMock(offsetParent=True) # date input check via fast_poll
        ]

        res = wait_for_schedule_option_ready(mock_driver, timeout=5.0)
        self.assertTrue(res)

    def test_timeout_raises_runtime_error(self):
        mock_driver = MagicMock()
        mock_driver.execute_script.return_value = {
            "status": "disabled",
            "uploadText": "กำลังอัปโหลดวิดีโอ... (50%)",
            "text": "Schedule for later"
        }

        with self.assertRaises(RuntimeError) as ctx:
            wait_for_schedule_option_ready(mock_driver, timeout=0.2)
        self.assertIn("Schedule for later", str(ctx.exception))
        self.assertIn("ยังไม่พร้อมใช้งาน", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
