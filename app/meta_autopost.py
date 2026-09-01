import os
import sys
import time
import subprocess
import argparse
from datetime import datetime
from typing import Any, Callable, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from app.browser import browser_manager

def log(msg: str) -> None:
    print(msg)
    try:
        from app.main import log_bus
        log_bus.publish(msg)
    except Exception:
        pass

def cleanup_browser_tabs(driver) -> None:
    """Closes all extraneous tabs/windows, keeping only the active single working tab."""
    try:
        handles = driver.window_handles
        if len(handles) > 1:
            main_handle = None
            for h in handles:
                try:
                    driver.switch_to.window(h)
                    if "business.facebook.com" in driver.current_url:
                        main_handle = h
                        break
                except Exception:
                    pass
            if not main_handle:
                main_handle = handles[0]
            for h in handles:
                if h != main_handle:
                    try:
                        driver.switch_to.window(h)
                        driver.close()
                    except Exception:
                        pass
            driver.switch_to.window(main_handle)
    except Exception:
        pass

def get_browser_window_pid(port: int = 9222) -> Optional[int]:
    """Finds the exact Chrome process PID with an open window on the debug port."""
    try:
        res = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, check=False)
        pids = [p.strip() for p in res.stdout.strip().split() if p.strip()]
        for pid in pids:
            check_script = f'''
            tell application "System Events"
                try
                    set p to first process whose unix id is {pid}
                    if (count of windows of p) > 0 then
                        return "FOUND"
                    end if
                end try
            end tell
            '''
            r = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True, check=False)
            if "FOUND" in r.stdout:
                return int(pid)
        return int(pids[0]) if pids else None
    except Exception:
        return None

def focus_9222_browser_tab(driver, port: int = 9222) -> None:
    """Focuses the port 9222 tab directly through CDP and native macOS NSRunningApplication by PID."""
    if driver:
        try:
            driver.switch_to.window(driver.current_window_handle)
            driver.execute_script("window.focus();")
            driver.execute_cdp_cmd('Page.bringToFront', {})
        except Exception:
            pass

    if sys.platform != "darwin":
        return

    pid = get_browser_window_pid(port)
    if pid:
        jxa_script = f'''
        ObjC.import('AppKit');
        var app = $.NSRunningApplication.runningApplicationWithProcessIdentifier({pid});
        if (app) {{
            app.activateWithOptions($.NSApplicationActivateAllWindows | $.NSApplicationActivateIgnoringOtherApps);
        }}
        '''
        try:
            subprocess.run(["osascript", "-l", "JavaScript", "-e", jxa_script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def upload_macos_file_dialog_fast(file_path: str, port: int = 9222) -> bool:
    """Sends keystrokes to the open macOS file sheet for the 9222 window."""
    if sys.platform != "darwin":
        return False
    escaped_path = file_path.replace('"', '\\"')

    # Ensure 9222 is active right before keystrokes
    focus_9222_browser_tab(None, port=port)

    script = f"""
    set the clipboard to "{escaped_path}"
    tell application "System Events"
        delay 1.0
        
        -- Press Cmd + Shift + G
        key code 5 using {{command down, shift down}}
        delay 1.0
        
        -- Press Cmd + V
        keystroke "v" using {{command down}}
        delay 1.0
        
        -- Enter to confirm path
        keystroke return
        delay 1.2
        
        -- Enter to confirm file selection
        keystroke return
    end tell
    """
    try:
        subprocess.run(["osascript", "-e", script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        log(f"[Meta Auto Post Dialog Error] {e}")
        return False

_meta_stop_requested = False

def request_meta_stop():
    global _meta_stop_requested
    _meta_stop_requested = True

def reset_meta_stop():
    global _meta_stop_requested
    _meta_stop_requested = False

def is_meta_stopped() -> bool:
    global _meta_stop_requested
    return _meta_stop_requested

def fast_poll(driver, js_expr: str, timeout: float = 30.0, poll_interval: float = 0.2, *args, **kwargs) -> Any:
    """Polls JavaScript expression until truthy or timeout."""
    start_t = time.time()
    js_args = kwargs.get("js_args", args)
    if isinstance(js_args, (list, tuple)):
        call_args = list(js_args)
    elif js_args is not None:
        call_args = [js_args]
    else:
        call_args = []

    while time.time() - start_t < timeout:
        if is_meta_stopped():
            raise RuntimeError("🛑 Force Stop: ผู้ใช้สั่งหยุดการทำงาน")
        try:
            res = driver.execute_script(js_expr, *call_args)
            if res:
                return res
        except Exception:
            pass
        time.sleep(poll_interval)
    return None

# ==============================================================================
# Modular Step Functions (Callable individually or in batch)
# ==============================================================================

def step_1_open_composer(driver, composer_url: str) -> bool:
    """Step 1: Focus 9222, close extra tabs, navigate to fresh composer URL and wait until ready."""
    cleanup_browser_tabs(driver)
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.2)

    log(f"[Meta Step 1] Navigating to fresh composer URL: {composer_url}")
    driver.get(composer_url)
    
    # Loop check: document ready + composer container/Add video present
    ready = fast_poll(driver, '''
        if (document.readyState !== 'complete') return false;
        const hasAddVideo = !!Array.from(document.querySelectorAll('div, span, button')).find(el => el.innerText && el.innerText.trim().includes('Add video'));
        const hasComposer = !!document.querySelector('div[role="dialog"], [role="main"], div[class*="composer" i]');
        return hasAddVideo || hasComposer;
    ''', timeout=20.0, poll_interval=0.2)
    
    if not ready:
        raise RuntimeError("หน้าต่าง Composer ไม่พร้อมทำงานภายในเวลาที่กำหนด")

    log("[Meta Step 1] ✅ หน้าต่าง Composer พร้อมใช้งานเรียบร้อยแล้ว")
    return True

def step_2_upload_video(driver, video_path: str) -> bool:
    """Step 2: Poll for 'Add video' button, click, send video file path, and poll upload start."""
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.1)

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"ไม่พบไฟล์วิดีโอ: {video_path}")

    # Loop check: locate Add video button
    target_btn = fast_poll(driver, '''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const direct = allBtns.find(b => b.innerText && b.innerText.trim().includes('Add video') && b.getAttribute('aria-disabled') !== 'true');
        if (direct) return direct;
        const textEl = Array.from(document.querySelectorAll('div, span, button')).find(el => el.innerText && el.innerText.trim() === 'Add video' && el.children.length === 0);
        return textEl ? (textEl.closest('[role="button"]') || textEl) : null;
    ''', timeout=15.0, poll_interval=0.2)

    if not target_btn:
        raise RuntimeError("ไม่พบปุ่ม Add video ที่พร้อมคลิกบนหน้าจอ")

    try:
        ActionChains(driver).move_to_element(target_btn).pause(0.1).click().perform()
    except Exception:
        driver.execute_script("arguments[0].click();", target_btn)
    log(f"[Meta Step 2] ส่งไฟล์วิดีโอผ่าน Dialog: {video_path}")
    upload_macos_file_dialog_fast(video_path, port=9222)

    # Loop check: poll until video is received / upload is recognized
    upload_started = fast_poll(driver, '''
        const hasVideo = !!document.querySelector('video, div[role="progressbar"], div[class*="thumbnail" i], div[class*="preview" i]');
        const shareActive = !!Array.from(document.querySelectorAll('div[role="button"], button')).find(b => b.innerText && b.innerText.trim().startsWith('Share') && b.getAttribute('aria-disabled') !== 'true');
        return hasVideo || shareActive;
    ''', timeout=20.0, poll_interval=0.3)

    if upload_started:
        log(f"[Meta Step 2] ✅ อัปโหลดวิดีโอเข้าระบบเรียบร้อย: {os.path.basename(video_path)}")
    else:
        log(f"[Meta Step 2] ✅ ส่งคำสั่งเลือกไฟล์วิดีโอผ่าน Dialog เรียบร้อย: {os.path.basename(video_path)}")
    return True

def step_3_insert_caption(driver, caption: str) -> bool:
    """Step 3: Poll for Description box, insert Caption, and loop verify value."""
    if not caption:
        log("[Meta Step 3] ไม่มีข้อความ Caption ข้ามขั้นตอนนี้")
        return True

    log(f"[Meta Step 3] กำลังรอช่องข้อความ Description เพื่อวาง Caption ({len(caption)} ตัวอักษร)...")
    
    # Loop check: locate textbox
    tb = fast_poll(driver, '''
        return document.querySelector('div[role="textbox"][contenteditable="true"]');
    ''', timeout=15.0, poll_interval=0.2)

    if not tb:
        raise RuntimeError("ไม่พบกล่องข้อความ Description บนหน้าจอ")

    # Insert text and dispatch events
    driver.execute_script('''
        const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
        if (tb) {
            tb.focus();
            try {
                const dt = new DataTransfer();
                dt.setData('text/plain', arguments[0]);
                const pasteEvt = new ClipboardEvent('paste', {
                    bubbles: true,
                    cancelable: true,
                    clipboardData: dt
                });
                tb.dispatchEvent(pasteEvt);
            } catch (e) {}

            if (!tb.innerText || !tb.innerText.trim()) {
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(tb);
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('delete', false, null);
                document.execCommand('insertText', false, arguments[0]);
            }

            tb.dispatchEvent(new Event('input', { bubbles: true }));
            tb.dispatchEvent(new Event('change', { bubbles: true }));
            tb.blur();
        }
    ''', caption)

    # Loop check: verify textbox value is actually populated
    verified = fast_poll(driver, '''
        const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
        return tb && tb.innerText && tb.innerText.trim().length > 0;
    ''', timeout=5.0, poll_interval=0.2)

    if not verified:
        raise RuntimeError("ไม่สามารถยืนยันข้อความ Caption ในกล่องข้อความได้")

    log("[Meta Step 3] ✅ วางข้อความ Description และยืนยันผลสำเร็จ")
    return True

def step_4_click_share_tab(driver, timeout: float = 60.0) -> bool:
    """Step 4: Poll until 'Share' tab is enabled, click, and poll verify Step 3 screen."""
    log(f"[Meta Step 4] กำลังตรวจสอบสถานะความพร้อมของแท็บ 'Share' (Timeout {timeout}s)...")
    
    top_share_btn = fast_poll(driver, '''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const shareBtn = allBtns.find(b => b.innerText && b.innerText.trim().startsWith('Share') && b.getBoundingClientRect().y < 120 && b.getAttribute('aria-disabled') !== 'true');
        return shareBtn;
    ''', timeout=timeout, poll_interval=0.3)

    if top_share_btn:
        log("[Meta Step 4] แท็บ Share เปิดใช้งานแล้ว! กำลังคลิกเข้าสู่หน้า Share...")
        try:
            ActionChains(driver).move_to_element(top_share_btn).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", top_share_btn)
    else:
        log("[Meta Step 4] แท็บ Share ด้านบนยังไม่พร้อม ลองกดปุ่ม Next...")
        step1_next = fast_poll(driver, '''
            const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
            return allBtns.find(b => b.innerText && b.innerText.trim() === 'Next' && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700 && b.getAttribute('aria-disabled') !== 'true');
        ''', timeout=10.0, poll_interval=0.3)
        if step1_next:
            try:
                ActionChains(driver).move_to_element(step1_next).pause(0.1).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", step1_next)

    # Loop check: verify Step 3 screen is active
    on_step3 = fast_poll(driver, '''
        return !!Array.from(document.querySelectorAll('div, span, [role="radio"]')).find(el => el.innerText && (el.innerText.trim() === 'Scheduling options' || el.innerText.trim() === 'Share now' || el.innerText.trim() === 'Schedule'));
    ''', timeout=15.0, poll_interval=0.2)

    if not on_step3:
        raise RuntimeError("ไม่สามารถเข้าสู่หน้า Step 3 (Share Screen) ได้")

    log("[Meta Step 4] ✅ เข้าสู่หน้า Step 3 (Share Screen) เรียบร้อยแล้ว")
    return True

def step_5_set_schedule(driver, scheduled_dt_str: str) -> bool:
    """Step 5: Poll for Schedule option, select it, input Date via Calendar & Time via spinbutton, loop verify values."""
    log("[Meta Step 5] กำลังรอตัวเลือก 'Schedule'...")
    
    sched_tab = fast_poll(driver, '''
        const allEls = Array.from(document.querySelectorAll('div, span, button, [role="radio"]'));
        const tab = allEls.find(el => el.innerText && el.innerText.trim() === 'Schedule' && el.getBoundingClientRect().y < 350 && el.getBoundingClientRect().y > 100);
        return tab ? (tab.closest('[role="button"], [role="radio"]') || tab) : null;
    ''', timeout=10.0, poll_interval=0.2)

    if sched_tab:
        try:
            ActionChains(driver).move_to_element(sched_tab).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", sched_tab)

    # Loop check: verify date input appears
    date_input_ready = fast_poll(driver, '''
        const d = document.querySelector('input[placeholder="dd/mm/yyyy"]');
        return d && d.offsetParent !== null;
    ''', timeout=10.0, poll_interval=0.2)

    if not date_input_ready:
        raise RuntimeError("ไม่พบช่องใส่วันที่และเวลาของ Schedule หลังคลิกเลือก")

    if scheduled_dt_str:
        try:
            dt = datetime.fromisoformat(scheduled_dt_str)
            target_day = dt.day
            target_month_name = dt.strftime('%B')
            target_year = dt.year
            target_date_label = f"{target_day} {target_month_name} {target_year}"
            hour_str = f"{dt.hour:02d}"
            min_str = f"{dt.minute:02d}"

            log(f"[Meta Step 5] กำหนดวันโพสต์: {target_date_label}, เวลา: {hour_str}:{min_str}")

            # 1. Set Date for ALL platforms (Facebook, Instagram, etc.)
            date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
            for d_idx, date_input in enumerate(date_inputs):
                try:
                    ActionChains(driver).move_to_element(date_input).pause(0.1).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", date_input)

                # Loop check: poll until target day in Calendar popover is found
                day_clicked = fast_poll(driver, '''
                    const targetText = arguments[0];
                    const allEls = Array.from(document.querySelectorAll('div[role="gridcell"], [role="button"], span, div'));
                    const dayEl = allEls.find(el => el.getAttribute('aria-label') && el.getAttribute('aria-label').includes(targetText));
                    if (dayEl) {
                        dayEl.click();
                        return true;
                    }
                    return false;
                ''', timeout=8.0, poll_interval=0.2, js_args=target_date_label)

                if not day_clicked:
                    driver.execute_script('''
                        const dayNum = String(arguments[0]);
                        const allEls = Array.from(document.querySelectorAll('div[role="gridcell"], [role="button"]'));
                        const dayEl = allEls.find(el => el.innerText && el.innerText.trim() === dayNum);
                        if (dayEl) dayEl.click();
                    ''', target_day)
                time.sleep(0.2)

            # Loop check: verify all Date values updated
            fast_poll(driver, '''
                const dates = Array.from(document.querySelectorAll('input[placeholder="dd/mm/yyyy"]'));
                return dates.length > 0 && dates.every(d => d.value && d.value.includes(String(arguments[0])));
            ''', timeout=5.0, poll_interval=0.2, js_args=target_day)

            # 2. Set Hours for ALL platforms (Facebook, Instagram, etc.)
            hours_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[aria-label="hours"]')
            for h_input in hours_inputs:
                try:
                    h_input.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", h_input)
                time.sleep(0.05)
                h_input.send_keys(Keys.BACKSPACE, Keys.BACKSPACE, hour_str)

            # 3. Set Minutes for ALL platforms (Facebook, Instagram, etc.)
            mins_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[aria-label="minutes"]')
            for m_input in mins_inputs:
                try:
                    m_input.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", m_input)
                time.sleep(0.05)
                m_input.send_keys(Keys.BACKSPACE, Keys.BACKSPACE, min_str)

            # Loop check: verify all hours and minutes values
            fast_poll(driver, '''
                const hList = Array.from(document.querySelectorAll('input[aria-label="hours"]'));
                const mList = Array.from(document.querySelectorAll('input[aria-label="minutes"]'));
                const hOk = hList.length > 0 && hList.every(h => (h.getAttribute('aria-valuenow') || h.value) === arguments[0]);
                const mOk = mList.length > 0 && mList.every(m => (m.getAttribute('aria-valuenow') || m.value) === arguments[1]);
                return hOk && mOk;
            ''', timeout=5.0, poll_interval=0.2, js_args=[hour_str, min_str])

            log(f"[Meta Step 5] ✅ กำหนดวัน-เวลาและตรวจสอบค่าใน Schedule ครบทุกแพลตฟอร์ม (Facebook & Instagram: {len(date_inputs)} ช่อง) สำเร็จเรียบร้อยแล้ว")
            return True

        except Exception as ex_dt:
            log(f"[Meta Step 5 Error] แปลงหรือใส่วัน-เวลา '{scheduled_dt_str}' ไม่ถูกต้อง: {ex_dt}")
            raise ex_dt
    return True

def step_6_submit_schedule(driver) -> bool:
    """Step 6: Poll for final Schedule button, click, and wait 5s cooldown before proceeding."""
    log("[Meta Step 6] กำลังรอปุ่ม Schedule ขวาล่าง...")
    sched_submit_el = fast_poll(driver, '''
        const allEls = Array.from(document.querySelectorAll('div[role="button"], button'));
        return allEls.find(el => el.innerText && el.innerText.trim() === 'Schedule' && el.getBoundingClientRect().x > 1400 && el.getBoundingClientRect().y > 700 && el.getAttribute('aria-disabled') !== 'true');
    ''', timeout=15.0, poll_interval=0.2)

    if not sched_submit_el:
        sched_submit_el = driver.execute_script('''
            const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
            return allBtns.find(b => b.innerText && b.innerText.trim() === 'Schedule' && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700);
        ''')

    if sched_submit_el:
        try:
            ActionChains(driver).move_to_element(sched_submit_el).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", sched_submit_el)
    else:
        raise RuntimeError("ไม่พบปุ่ม Schedule ขวาล่างที่พร้อมคลิก")

    log("[Meta Step 6] คลิกปุ่ม Schedule เรียบร้อยแล้ว กำลังรอ Cooldown 5 วินาที...")
    time.sleep(5.0)

    log("[Meta Step 6] ✅ ส่งคำสั่ง Schedule และรอ Cooldown 5 วินาทีเรียบร้อยแล้ว")
    return True

def get_scheduled_posts_url(composer_url: str) -> str:
    """Extracts asset_id and business_id from composer_url to build the scheduled posts URL."""
    url = (composer_url or "").strip()
    if not url:
        return "https://business.facebook.com/latest/posts/scheduled_posts"
    
    asset_id = ""
    business_id = ""
    
    # 1. Parse URL query params
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        asset_id = params.get("asset_id", [""])[0] or params.get("page_id", [""])[0]
        business_id = params.get("business_id", [""])[0]
    except Exception:
        pass

    # 2. Regex fallback
    if not asset_id:
        m = re.search(r'asset_id=(\d+)', url) or re.search(r'page_id=(\d+)', url)
        if m:
            asset_id = m.group(1)
    if not business_id:
        m = re.search(r'business_id=(\d+)', url)
        if m:
            business_id = m.group(1)

    query_params = []
    if asset_id:
        query_params.append(f"asset_id={asset_id}")
    if business_id:
        query_params.append(f"business_id={business_id}")
        
    q_str = f"?{'&'.join(query_params)}" if query_params else ""
    return f"https://business.facebook.com/latest/posts/scheduled_posts{q_str}"

def step_7_view_scheduled(driver, composer_url: str) -> bool:
    """Step 7: Navigate directly to Scheduled Posts management page and poll until ready."""
    sched_url = get_scheduled_posts_url(composer_url)
    log(f"[Meta Step 7] กำลังเปิดหน้ารายการโพสต์ที่ตั้งเวลาไว้ (Scheduled Posts): {sched_url}")
    try:
        driver.execute_script("window.location.assign(arguments[0]);", sched_url)
    except Exception:
        driver.get(sched_url)

    fast_poll(driver, '''
        return document.readyState === 'complete' && window.location.href.includes('scheduled_posts');
    ''', timeout=15.0, poll_interval=0.2)

    log(f"[Meta Step 7] ✅ เปิดหน้ารายการ Scheduled Posts สำเร็จ: {sched_url}")
    return True

# ==============================================================================
# Full Single Post & Batch Runner
# ==============================================================================

def _post_single_reel_core(
    driver,
    item: dict[str, Any],
    composer_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    attempt: int = 1
) -> bool:
    subfolder_name = item.get("subfolder_name", "")
    video_name = item.get("video_name", "")
    video_path = item.get("video_path", "")
    caption = item.get("caption", "")
    scheduled_dt_str = item.get("scheduled_datetime", "")

    attempt_str = f" (รอบที่ {attempt})" if attempt > 1 else ""
    msg = f"[{item_idx}/{total_items}] กำลังโพสต์: {subfolder_name or video_name}{attempt_str}"
    log(f"[Meta Auto Post Script] {msg} (Target: {scheduled_dt_str})")
    if progress_callback:
        progress_callback({
            "current": item_idx,
            "total": total_items,
            "percent": int(((item_idx - 1) / max(total_items, 1)) * 100),
            "message": msg
        })

    # Step 1: Open Composer
    step_1_open_composer(driver, composer_url)

    # Step 2: Upload Video
    step_2_upload_video(driver, video_path)

    # Step 3: Insert Caption
    step_3_insert_caption(driver, caption)

    # Step 4: Click Share Tab to reach Step 3
    step_4_click_share_tab(driver, timeout=100.0)

    # Step 5: Set Schedule Date & Time
    step_5_set_schedule(driver, scheduled_dt_str)

    # Step 6: Submit Schedule (with 5s cooldown)
    step_6_submit_schedule(driver)

    log(f"[Meta Auto Post Script] ✅ สำเร็จการตั้งเวลาโพสต์รายการที่ {item_idx}/{total_items}: {subfolder_name or video_name}")
    return True

def post_single_reel(
    driver,
    item: dict[str, Any],
    composer_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """Executes single reel post sequence with auto-refresh retry on failure."""
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            return _post_single_reel_core(
                driver=driver,
                item=item,
                composer_url=composer_url,
                item_idx=item_idx,
                total_items=total_items,
                progress_callback=progress_callback,
                attempt=attempt
            )
        except Exception as ex:
            log(f"[Meta Auto Post Script] ⚠️ Error on attempt {attempt}/{max_retries}: {ex}")
            if attempt < max_retries:
                log(f"[Meta Auto Post Script] 🔄 Refreshing composer page and restarting flow in 2s...")
                try:
                    cleanup_browser_tabs(driver)
                    driver.get(composer_url)
                    time.sleep(2.0)
                except Exception:
                    pass
            else:
                raise ex
    return False

def run_meta_autopost_batch(
    posts: list[dict[str, Any]],
    target_url: str = "",
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """Runs a batch of scheduled posts through the fast script engine."""
    bot = browser_manager.get()
    driver = bot.driver
    total = len(posts)

    composer_url = target_url.strip() if target_url else ""
    if not composer_url:
        raise ValueError("กรุณาระบุ URL ของเพจ/Composer ใน Preset หรือช่อง URL ก่อนเริ่มทำงาน")

    errors = []
    success_count = 0
    reset_meta_stop()

    log(f"[Meta Auto Post Script Engine] Starting batch of {total} posts on 9222...")

    for idx, post in enumerate(posts):
        if is_meta_stopped():
            log("[Meta Auto Post] 🛑 ยกเลิกการโพสต์รายการที่เหลือเนื่องจากคำสั่ง Force Stop")
            errors.append("🛑 การทำงานถูกยกเลิกด้วย Force Stop")
            break
        try:
            ok = post_single_reel(
                driver=driver,
                item=post,
                composer_url=composer_url,
                item_idx=idx + 1,
                total_items=total,
                progress_callback=progress_callback
            )
            if ok:
                success_count += 1
        except Exception as e:
            if is_meta_stopped() or "Force Stop" in str(e):
                log("[Meta Auto Post] 🛑 หยุดทำงานทันทีตามคำสั่ง Force Stop")
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break
            err_msg = f"[{idx+1}/{total}] {post.get('subfolder_name', 'Item')}: {str(e)}"
            log(f"[Meta Auto Post Script Item Error] {err_msg}")
            errors.append(err_msg)

    # Automatically open Scheduled Posts page after batch completes
    if success_count > 0:
        try:
            log("[Meta Auto Post Script] 🎉 โพสต์ครบทุกรายการแล้ว กำลังเปิดหน้ารายการ Scheduled Posts...")
            step_7_view_scheduled(driver, composer_url)
        except Exception as ex_sched:
            log(f"[Meta Auto Post Script Note] Step 7 view note: {ex_sched}")

    if progress_callback:
        progress_callback({
            "current": total,
            "total": total,
            "percent": 100,
            "status": "completed" if not errors else "completed_with_errors",
            "message": f"✅ โพสต์ตามคิวสำเร็จ {success_count}/{total} รายการ" if not errors else f"เสร็จสิ้น {success_count}/{total} (พบข้อผิดพลาด {len(errors)} รายการ)",
            "errors": errors
        })

    return {
        "ok": len(errors) == 0,
        "total": total,
        "success_count": success_count,
        "errors": errors
    }

def main():
    parser = argparse.ArgumentParser(description="Meta Reels Fast Auto Post Script")
    parser.add_argument("--main-folder", required=True, help="Main folder containing asset subfolders")
    parser.add_argument("--subfolders", default="", help="Subfolder selector (e.g. 1-10 or 1,2,3)")
    parser.add_argument("--prefix", default="combined", help="Video prefix matching (default: combined)")
    parser.add_argument("--start-date", default=datetime.now().strftime("%Y-%m-%d"), help="Start date (YYYY-MM-DD)")
    parser.add_argument("--start-hour", type=int, default=18, help="Start hour 0-23 (default: 18)")
    parser.add_argument("--target-url", default="", help="Target Meta Composer / Page URL")
    args = parser.parse_args()

    # Import scan helper
    from app.main import scan_meta_autopost, MetaScanRequest
    scan_req = MetaScanRequest(
        main_folder=args.main_folder,
        subfolders_str=args.subfolders,
        video_prefix=args.prefix,
        start_date=args.start_date,
        start_hour=args.start_hour
    )
    scan_res = scan_meta_autopost(scan_req)
    items = scan_res.get("items", [])
    if not items:
        print(f"❌ ไม่พบรายการวิดีโอที่ตรงกับเงื่อนไขใน: {args.main_folder}")
        sys.exit(1)

    print(f"🚀 พบ {len(items)} รายการ กำลังเริ่มรัน Auto Post Script Engine...")
    res = run_meta_autopost_batch(items, target_url=args.target_url)
    print("✨ ผลการทำงาน:", res)

if __name__ == "__main__":
    main()
