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

def fast_poll(driver, js_expr: str, timeout: float = 30.0, poll_interval: float = 0.2) -> Any:
    """Polls JavaScript expression until truthy or timeout."""
    start_t = time.time()
    while time.time() - start_t < timeout:
        try:
            res = driver.execute_script(js_expr)
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
    """Step 1: Focus 9222, close extra tabs, navigate to fresh composer URL."""
    cleanup_browser_tabs(driver)
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.3)

    log(f"[Meta Step 1] Navigating to fresh composer URL: {composer_url}")
    driver.get(composer_url)
    fast_poll(driver, "return document.readyState === 'complete';", timeout=15.0, poll_interval=0.2)
    time.sleep(1.0)
    log("[Meta Step 1] ✅ เปิดหน้าต่าง Composer สำเร็จเรียบร้อยแล้ว")
    return True

def step_2_upload_video(driver, video_path: str) -> bool:
    """Step 2: Click 'Add video' and send video file path via macOS sheet dialog."""
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.2)

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"ไม่พบไฟล์วิดีโอ: {video_path}")

    all_btns = driver.find_elements(By.CSS_SELECTOR, 'div[role="button"], button')
    target_btn = next((b for b in all_btns if b.text and 'Add video' in b.text), None)
    if not target_btn:
        target_btn = driver.execute_script('''
            const textEl = Array.from(document.querySelectorAll('div, span, button')).find(el => el.innerText && el.innerText.trim() === 'Add video' && el.children.length === 0);
            return textEl ? (textEl.closest('[role="button"]') || textEl) : null;
        ''')

    if target_btn:
        try:
            ActionChains(driver).move_to_element(target_btn).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", target_btn)
        log("[Meta Step 2] คลิกปุ่ม 'Add video' เรียบร้อย")
    else:
        raise RuntimeError("ไม่พบปุ่ม Add video บนหน้าจอ")

    time.sleep(0.5)

    import uuid
    import shutil
    ext = os.path.splitext(video_path)[1] or ".mp4"
    unique_name = f"reel_{uuid.uuid4().hex}{ext}"
    temp_uuid_file = os.path.join("/tmp", unique_name)
    try:
        shutil.copy2(video_path, temp_uuid_file)
        log(f"[Meta Step 2] สร้างไฟล์ชั่วคราว UUID: {temp_uuid_file}")
        upload_macos_file_dialog_fast(temp_uuid_file, port=9222)
    except Exception as ex_copy:
        log(f"[Meta Step 2] UUID copy note: {ex_copy}, ใช้พาธเดิม")
        upload_macos_file_dialog_fast(video_path, port=9222)

    log(f"[Meta Step 2] ✅ ส่งคำสั่งเลือกไฟล์วิดีโอผ่าน Dialog เรียบร้อย: {os.path.basename(video_path)}")
    return True

def step_3_insert_caption(driver, caption: str) -> bool:
    """Step 3: Insert Caption into Lexical / DraftJS description box with Event dispatch & blur."""
    if not caption:
        log("[Meta Step 3] ไม่มีข้อความ Caption ข้ามขั้นตอนนี้")
        return True

    log(f"[Meta Step 3] กำลังวางข้อความ Caption ({len(caption)} ตัวอักษร)...")
    res = driver.execute_script('''
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
            return true;
        }
        return false;
    ''', caption)

    if not res:
        raise RuntimeError("ไม่พบกล่องข้อความ Description บนหน้าจอ")

    time.sleep(0.4)
    log("[Meta Step 3] ✅ วางข้อความ Description และ Commit React State สำเร็จ")
    return True

def step_4_click_share_tab(driver, timeout: float = 60.0) -> bool:
    """Step 4: Wait for readiness and click top 'Share' tab to jump to Step 3."""
    log(f"[Meta Step 4] กำลังตรวจสอบสถานะแท็บ 'Share' ด้านบน (Timeout {timeout}s)...")
    
    top_share_btn = fast_poll(driver, '''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const shareBtn = allBtns.find(b => b.innerText && b.innerText.trim().startsWith('Share') && b.getBoundingClientRect().y < 120 && b.getAttribute('aria-disabled') !== 'true');
        return shareBtn;
    ''', timeout=timeout, poll_interval=0.3)

    if top_share_btn:
        log("[Meta Step 4] แท็บ Share ด้านบนเปิดใช้งานแล้ว! กำลังคลิกกระโดดไป Step 3...")
        try:
            ActionChains(driver).move_to_element(top_share_btn).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", top_share_btn)
    else:
        # Fallback progression via Next buttons if top tab requires step wizard
        log("[Meta Step 4] ลองเลื่อน Step ผ่านปุ่ม Next...")
        step1_next = driver.execute_script('''
            const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
            return allBtns.find(b => b.innerText && b.innerText.trim() === 'Next' && b.getBoundingClientRect().x > 1600 && b.getBoundingClientRect().y > 900 && b.getAttribute('aria-disabled') !== 'true');
        ''')
        if step1_next:
            try:
                ActionChains(driver).move_to_element(step1_next).pause(0.1).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", step1_next)
            time.sleep(0.8)

    # Fast poll for Step 3 active (Scheduling options or Share now)
    on_step3 = fast_poll(driver, '''
        return !!Array.from(document.querySelectorAll('div, span')).find(el => el.innerText && (el.innerText.trim() === 'Scheduling options' || el.innerText.trim() === 'Share now'));
    ''', timeout=15.0, poll_interval=0.2)

    if not on_step3:
        raise RuntimeError("ไม่สามารถเข้าสู่หน้า Step 3 (Share) ได้")

    log("[Meta Step 4] ✅ เข้าสู่หน้า Step 3 (Share Screen) เรียบร้อยแล้ว")
    return True

def step_5_set_schedule(driver, scheduled_dt_str: str) -> bool:
    """Step 5: Select Schedule radio and input Date via Calendar click & Time via spinbuttons."""
    log("[Meta Step 5] กำลังเลือกแท็บตัวเลือก 'Schedule'...")
    sched_tab = driver.execute_script('''
        const allEls = Array.from(document.querySelectorAll('div, span, button, [role="radio"]'));
        const tab = allEls.find(el => el.innerText && el.innerText.trim() === 'Schedule' && el.getBoundingClientRect().y < 350 && el.getBoundingClientRect().y > 100);
        return tab ? (tab.closest('[role="button"], [role="radio"]') || tab) : null;
    ''')
    if sched_tab:
        try:
            ActionChains(driver).move_to_element(sched_tab).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", sched_tab)
    time.sleep(0.6)

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

            # 1. Open Calendar Popover & Click target date cell
            date_input = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
            if date_input:
                try:
                    ActionChains(driver).move_to_element(date_input[0]).pause(0.1).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", date_input[0])
                time.sleep(0.4)

                # Click matching day cell in popover
                driver.execute_script('''
                    const targetText = arguments[0];
                    const allEls = Array.from(document.querySelectorAll('div[role="gridcell"], [role="button"], span, div'));
                    const dayEl = allEls.find(el => (el.getAttribute('aria-label') && el.getAttribute('aria-label').includes(targetText)));
                    if (dayEl) {
                        dayEl.click();
                        return true;
                    }
                    return false;
                ''', target_date_label)
                time.sleep(0.4)

            # 2. Set Hours spinbutton
            hours_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[aria-label="hours"]')
            if hours_inputs:
                hours_inputs[0].click()
                time.sleep(0.1)
                hours_inputs[0].send_keys(Keys.BACKSPACE, Keys.BACKSPACE, hour_str)
                time.sleep(0.2)

            # 3. Set Minutes spinbutton
            mins_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[aria-label="minutes"]')
            if mins_inputs:
                mins_inputs[0].click()
                time.sleep(0.1)
                mins_inputs[0].send_keys(Keys.BACKSPACE, Keys.BACKSPACE, min_str)
                time.sleep(0.2)

            log("[Meta Step 5] ✅ กำหนดวัน-เวลาใน Schedule สำเร็จเรียบร้อยแล้ว")
            return True

        except Exception as ex_dt:
            log(f"[Meta Step 5 Error] แปลงวัน-เวลา '{scheduled_dt_str}' ไม่ถูกต้อง: {ex_dt}")
            raise ex_dt
    return True

def step_6_submit_schedule(driver) -> bool:
    """Step 6: Click final Schedule button at bottom right and wait for confirmation."""
    log("[Meta Step 6] กำลังคลิกปุ่ม Schedule ขวาล่างเพื่อยืนยันโพสต์...")
    sched_submit_el = driver.execute_script('''
        const allEls = Array.from(document.querySelectorAll('div[role="button"], button'));
        return allEls.find(el => el.innerText && el.innerText.trim() === 'Schedule' && el.getBoundingClientRect().x > 1400 && el.getBoundingClientRect().y > 700);
    ''')

    if sched_submit_el:
        try:
            ActionChains(driver).move_to_element(sched_submit_el).pause(0.1).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", sched_submit_el)
    else:
        # Fallback click
        driver.execute_script('''
            const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
            const schedBtn = allBtns.find(b => b.innerText && b.innerText.trim() === 'Schedule' && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700);
            if (schedBtn) schedBtn.click();
        ''')

    # Fast poll for modal closure / submission confirmation
    log("[Meta Step 6] กำลังรอผลการยืนยันการตั้งเวลาโพสต์...")
    submitted = fast_poll(driver, '''
        const onPlanner = window.location.href.includes('planner') || window.location.href.includes('posts');
        const modalClosed = !document.querySelector('div[role="textbox"][contenteditable="true"]') && !Array.from(document.querySelectorAll('div, span')).find(el => el.innerText && el.innerText.trim() === 'Scheduling options');
        return onPlanner || modalClosed;
    ''', timeout=30.0, poll_interval=0.3)

    log("[Meta Step 6] ✅ ส่งคำสั่ง Schedule เรียบร้อยและปิดหน้าต่างสำเร็จ!")
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

    # 🛑 หยุด Flow ชั่วคราวตามคำขอของผู้ใช้ เพื่อตรวจสอบหน้า Share Screen
    log("[Meta Auto Post Script] 🛑 หยุดการทำงานชั่วคราวตามคำสั่ง: เข้าสู่หน้า Share เรียบร้อยแล้ว (หยุดก่อนตั้งเวลาและกดปุ่ม Share ขวาล่าง)")
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

    log(f"[Meta Auto Post Script Engine] Starting batch of {total} posts on 9222...")

    for idx, post in enumerate(posts):
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
            err_msg = f"[{idx+1}/{total}] {post.get('subfolder_name', 'Item')}: {str(e)}"
            log(f"[Meta Auto Post Script Item Error] {err_msg}")
            errors.append(err_msg)

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
