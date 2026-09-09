import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: console_logs.append(f"[pageerror] {exc}"))

        await page.add_init_script("""
            localStorage.setItem('flowVideoPresets', JSON.stringify({
                'ละคร': {
                    'project_id': '21a1632e-9926-46fa-954c-240d71d78f41',
                    'video_model': 'veo_3_1_i2v_s_fast_portrait',
                    'orientation': 'VERTICAL',
                    'output_count': '1',
                    'upscale_resolution': 'NONE',
                    'lakorn_path': '/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย',
                    'lakorn_ton': '18',
                    'lakorn_ep': '1'
                }
            }));
        """)

        print("=== E2E PHASE 1: DISCOVERY & NAVIGATION ===")
        print("Step 1: Navigating to http://127.0.0.1:6969/ ...")
        await page.goto("http://127.0.0.1:6969/")
        await page.wait_for_load_state("networkidle")

        print("Step 2: Switching to Video Gen tab & Flow Kit mode...")
        await page.evaluate("""async () => {
            document.querySelectorAll('.tab-view').forEach(v => v.classList.add('hidden'));
            document.getElementById('videoGenView').classList.remove('hidden');
            document.querySelectorAll('.sidebar-nav-btn').forEach(b => { b.classList.remove('locked', 'active'); b.disabled = false; });
            document.getElementById('tabVideoGenBtn').classList.add('active');
            document.getElementById('selenium_mode_section').style.display = 'none';
            document.getElementById('flow_kit_mode_section').style.display = 'block';
            document.getElementById('flow_kit_downloader_section').style.display = 'block';
            const modeSelect = document.getElementById('cfg_video_gen_mode');
            if (modeSelect) modeSelect.value = 'flow_kit';
            if (typeof loadConfig === 'function') await loadConfig();
            if (typeof loadFlowKitProjects === 'function') await loadFlowKitProjects();
            if (typeof calculateFlowKitPaths === 'function') calculateFlowKitPaths();
        }""")
        await asyncio.sleep(2)

        print("Step 3: Selecting 'ละคร' preset...")
        await page.evaluate("""() => {
            const sel = document.getElementById('flowVideoPresetSelect');
            if (sel) sel.value = 'ละคร';
            if (typeof applyFlowVideoPreset === 'function') applyFlowVideoPreset('ละคร');
            if (typeof calculateFlowKitPaths === 'function') calculateFlowKitPaths();
        }""")
        await asyncio.sleep(1)

        proj_val = await page.locator("#cfg_flow_project_dropdown").input_value()
        model_val = await page.locator("#cfg_flow_video_model").input_value()
        sb_path = await page.locator("#lbl_resolved_storyboard_path").inner_text()
        pr_path = await page.locator("#lbl_resolved_prompt_path").inner_text()
        print(f"Project ID: {proj_val}")
        print(f"Video Model: {model_val}")
        print(f"Storyboard Path: {sb_path}")
        print(f"Prompt Path: {pr_path}")

        print("=== E2E PHASE 2: SCAN & SELECTION ===")
        print("Step 4: Clicking 'Scan & Sync Folders'...")
        async with page.expect_response(lambda res: "/api/batch-uploader/scan" in res.url, timeout=30000) as scan_resp:
            await page.evaluate("() => document.getElementById('btnScanFlowKit').click()")
        scan_response = await scan_resp.value
        print(f"Scan API Response Status: {scan_response.status}")
        await asyncio.sleep(2)

        msg = await page.locator("#flowKitMsg").inner_text()
        print(f"Scan message: {msg}")

        # Count rendered grid cells
        cells = await page.locator("#scannedPairsContainer > div > div").count()
        print(f"Rendered grid cells count: {cells}")

        print("Step 5: Selecting Scene 1 only via range filter...")
        await page.evaluate("""() => {
            const rangeInput = document.getElementById('cfg_flow_select_range');
            if (rangeInput) rangeInput.value = '1';
            document.getElementById('btnApplyFlowRange')?.click();
        }""")
        await asyncio.sleep(1)

        print("=== E2E PHASE 3: BATCH SUBMISSION EXECUTION ===")
        print("Step 6: Clicking '🚀 Start Batch Upload' for Scene 1...")
        async with page.expect_response(lambda res: "/api/batch-uploader/process" in res.url, timeout=30000) as response_info:
            await page.evaluate("() => document.getElementById('btnProcessFlowKitBatch').click()")
        
        response = await response_info.value
        status = response.status
        body_text = await response.text()
        print(f"Process API Response Status: {status}")
        req_id = None
        try:
            body_json = json.loads(body_text)
            print("Process API Response JSON:", json.dumps(body_json, indent=2, ensure_ascii=False))
            results = body_json.get("results", [])
            if results:
                req_id = results[0].get("request_id")
        except Exception:
            print("Process API Response Text:", body_text)

        batch_msg = await page.locator("#flowKitMsg").inner_text()
        print(f"UI Batch Message: {batch_msg}")

        print("=== E2E PHASE 4: MONITORING GENERATION STATUS ===")
        print(f"Monitoring request {req_id}...")
        import urllib.request
        for poll_i in range(30):
            await asyncio.sleep(3)
            # Query status from DB or API
            try:
                with urllib.request.urlopen("http://127.0.0.1:6969/api/requests?limit=5") as resp:
                    req_data = json.loads(resp.read().decode())
                    matched = next((r for r in req_data if r.get("id") == req_id), None)
                    if matched:
                        cur_status = matched.get("status")
                        err = matched.get("error_message")
                        print(f"  [Poll {poll_i+1}/30] Request {req_id[:8]} status: {cur_status} (err: {err})")
                        if cur_status in ("COMPLETED", "FAILED"):
                            break
            except Exception as pe:
                print(f"  [Poll {poll_i+1}/30] Poll err: {pe}")

        # Read video console output
        console_lines = await page.locator("#videoConsole .console-line").all_inner_texts()
        print(f"Video Console Lines ({len(console_lines)}):")
        for line in console_lines[-10:]:
            print("  >", line)

        print("\nBrowser Console Logs (Last 10):")
        for log in console_logs[-10:]:
            print("  *", log)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
