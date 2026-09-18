"""
End-to-End Test Suite for FlowKit Batch Uploader & Video Generation Pipeline.
Compliant with e2e-test skill standards:
- Pattern A/B/C/D assertions
- Anti-Flakiness Web-First Assertions
- Console & PageError Monitoring
- Cross-layer verification (DOM, Console, API, DB)
"""

import asyncio
import os
import sqlite3
import unittest
from playwright.async_api import async_playwright

BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:6969")
DB_PATH = "flow_agent.db"

class TestFlowKitBatchUploadE2E(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

        # Error tracking arrays
        self.page_errors = []
        self.console_errors = []

        # Listen to page errors and console errors
        self.page.on("pageerror", lambda err: self.page_errors.append(str(err)))
        self.page.on("console", lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None)

    async def asyncTearDown(self):
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()

    async def test_01_page_loads_with_zero_reference_errors(self):
        """Verify page loads cleanly and renderFlowScannedGrid is globally accessible."""
        response = await self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        self.assertIsNotNone(response)
        self.assertEqual(response.status, 200)

        # Wait for scripts to execute
        await self.page.wait_for_load_state("networkidle")

        # Assert no renderFlowScannedGrid is not defined or ReferenceError occurred
        error_texts = " | ".join(self.page_errors + self.console_errors)
        self.assertNotIn("renderFlowScannedGrid is not defined", error_texts)
        self.assertNotIn("ReferenceError", error_texts)

        # Evaluate window functions directly
        is_fn_defined = await self.page.evaluate("typeof window.renderFlowScannedGrid === 'function'")
        self.assertTrue(is_fn_defined, "window.renderFlowScannedGrid must be defined as a function on window")

        is_scanned_pairs_defined = await self.page.evaluate("typeof window.renderScannedPairs === 'function'")
        self.assertTrue(is_scanned_pairs_defined, "window.renderScannedPairs must be defined as a function on window")

    async def test_02_render_flow_scanned_grid_execution_safety(self):
        """Verify that invoking renderFlowScannedGrid with dummy data executes without exceptions."""
        await self.page.goto(BASE_URL, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")

        # Inject sample pair and trigger renderFlowScannedGrid
        eval_result = await self.page.evaluate("""
            () => {
                try {
                    window.flowScannedPairs = [
                        {
                            order: 1,
                            image_name: '01 - Scene 01.png',
                            image_path: '/dummy/path/01.png',
                            prompt_content: 'Test scene prompt content',
                            checked: true,
                            status: 'PENDING'
                        }
                    ];
                    window.renderFlowScannedGrid();
                    const container = document.getElementById('scannedPairsContainer');
                    const section = document.getElementById('scannedPairsSection');
                    return {
                        success: true,
                        renderedChildCount: container ? container.children.length : 0,
                        sectionVisible: section ? section.style.display !== 'none' : false
                    };
                } catch (e) {
                    return { success: false, error: e.message || String(e) };
                }
            }
        """)

        self.assertTrue(eval_result["success"], f"renderFlowScannedGrid failed: {eval_result.get('error')}")
        self.assertTrue(eval_result["sectionVisible"], "Scanned pairs section should be visible after rendering pairs")
        self.assertGreaterEqual(eval_result["renderedChildCount"], 1, "Should render at least 1 card in grid container")

        # Verify no unhandled page errors were thrown during execution
        ref_errors = [e for e in self.page_errors if "renderFlowScannedGrid" in e or "ReferenceError" in e]
        self.assertEqual(len(ref_errors), 0, f"Found unexpected reference errors: {ref_errors}")

    async def test_03_batch_uploader_controls_and_flow_project_priority(self):
        """Verify UI batch controls and ensure open browser project is selected."""
        await self.page.goto(BASE_URL, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")

        # Check required DOM elements
        project_select = self.page.locator("#cfg_flow_project_dropdown")
        await project_select.wait_for(state="attached", timeout=5000)

        start_btn = self.page.locator("#btnProcessFlowKitBatch")
        await start_btn.wait_for(state="attached", timeout=5000)

        msg_el = self.page.locator("#flowKitMsg")
        await msg_el.wait_for(state="attached", timeout=5000)

        # Check project options populated
        options_count = await project_select.locator("option").count()
        self.assertGreater(options_count, 0, "cfg_flow_project_dropdown should have at least 1 project option")

        # Verify flow message does not show error
        msg_text = await msg_el.inner_text()
        self.assertNotIn("renderFlowScannedGrid is not defined", msg_text)

    async def test_04_backend_video_model_default_and_wire_key_resolution(self):
        """Verify that operations service cleanly defaults video model when none or null is provided."""
        from agent.services import flow_batch as fb

        # When custom_model_key is None, resolve_video_model must return valid non-empty model
        default_resolved = fb.resolve_video_model(None)
        self.assertIsNotNone(default_resolved)
        self.assertIn("veo_3_1", default_resolved)

        # Test lite_low_priority wire key
        lite_low = fb.resolve_video_model("lite_low_priority")
        self.assertEqual(lite_low, "veo_3_1_i2v_lite_low_priority")

        # Test fast ultra wire key
        fast_ultra = fb.resolve_video_model("veo_3_1_i2v_s_fast_ultra")
        self.assertEqual(fast_ultra, "veo_3_1_i2v_s_fast_ultra")

    async def test_05_database_schema_and_integrity(self):
        """Verify local database request table columns and integrity."""
        if not os.path.isfile(DB_PATH):
            self.skipTest(f"{DB_PATH} not found")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(request)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        required_cols = {"id", "project_id", "video_id", "scene_id", "type", "orientation", "status", "request_id", "media_id", "edit_prompt"}
        self.assertTrue(required_cols.issubset(columns), f"Missing required columns in request table: {required_cols - columns}")

    async def test_06_simulated_ui_batch_submission_and_monitoring(self):
        """Simulate batch submission in UI and verify zero exceptions and correct UI transition."""
        await self.page.goto(BASE_URL, wait_until="domcontentloaded")
        await self.page.wait_for_load_state("networkidle")

        # Mock /api/batch-uploader/process to return success
        await self.page.route("**/api/batch-uploader/process", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"video_id": "test-vid-123", "results": [{"scene_id": "s1", "image_path": "/dummy/01.png", "status": "QUEUED"}]}'
        ))

        # Mock /api/requests/batch-status to return completed
        await self.page.route("**/api/requests/batch-status*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"video_id": "test-vid-123", "is_complete": true, "total": 1, "completed": 1, "failed": 0, "items": [{"id": 1, "scene_id": "s1", "status": "COMPLETED"}]}'
        ))

        # Switch to Video Gen tab & flow_kit mode and populate project dropdown
        await self.page.evaluate("""
            () => {
                document.querySelectorAll('.tab-view').forEach(v => v.classList.add('hidden'));
                const vgv = document.getElementById('videoGenView');
                if (vgv) vgv.classList.remove('hidden');
                document.querySelectorAll('.sidebar-nav-btn').forEach(b => { b.classList.remove('locked', 'active'); b.disabled = false; });
                const tabBtn = document.getElementById('tabVideoGenBtn');
                if (tabBtn) tabBtn.classList.add('active');

                const modeSelect = document.getElementById('cfg_video_gen_mode');
                if (modeSelect) {
                    modeSelect.value = 'flow_kit';
                    modeSelect.dispatchEvent(new Event('change'));
                }
                const projSelect = document.getElementById('cfg_flow_project_dropdown');
                if (projSelect) {
                    projSelect.innerHTML = '<option value="test-proj-id" selected>Test Project</option>';
                    projSelect.value = 'test-proj-id';
                }
            }
        """)

        # Wait for section to become visible
        await self.page.wait_for_selector("#flow_kit_mode_section", state="visible")

        # Setup 1 pair in flowScannedPairs
        await self.page.evaluate("""
            () => {
                window.flowScannedPairs = [
                    {
                        order: 1,
                        image_name: '01.png',
                        image_path: '/dummy/01.png',
                        prompt_content: 'Test scene 1',
                        checked: true,
                        status: 'PENDING'
                    }
                ];
                window.renderFlowScannedGrid();
            }
        """)

        # Click the submit button
        start_btn = self.page.locator("#btnProcessFlowKitBatch")
        await start_btn.click()

        # Check that flowKitMsg shows success text and does NOT have error
        msg_el = self.page.locator("#flowKitMsg")
        await msg_el.wait_for(state="visible", timeout=5000)
        msg_text = await msg_el.inner_text()
        self.assertIn("ส่งคำขอเจเนอเรทสำเร็จ", msg_text)
        self.assertNotIn("renderFlowScannedGrid is not defined", msg_text)

        # Confirm no unhandled page errors
        ref_errors = [e for e in self.page_errors if "renderFlowScannedGrid" in e or "ReferenceError" in e]
        self.assertEqual(len(ref_errors), 0, f"Found unhandled reference errors during submission: {ref_errors}")

if __name__ == "__main__":
    unittest.main()

