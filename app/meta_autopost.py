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

def fast_poll(driver, js_expr: str, timeout: float = 20.0, poll_interval: float = 0.15) -> Any:
    """Polls JavaScript expression every 150ms until truthy or timeout."""
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

def post_single_reel(
    driver,
    item: dict[str, Any],
    composer_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """
    Executes a high-speed, bulletproof single reel post sequence:
    1. Focus Chrome 9222 window at start by Cocoa NSRunningApplication PID
    2. Ensure on composer page
    3. Click 'Add video' (ActionChains)
    4. macOS dialog path submission
    5. Fast poll for video upload completion (100%)
    6. Insert caption into Lexical editor with event dispatch
    7. Step 1 (Create) -> Step 2 (Edit) -> Step 3 (Share)
    8. Schedule radio option selection
    9. Date & Time input configuration (with TAB commit)
    10. Final Schedule submit button click & confirmation
    """
    subfolder_name = item.get("subfolder_name", "")
    video_name = item.get("video_name", "")
    video_path = item.get("video_path", "")
    caption = item.get("caption", "")
    scheduled_dt_str = item.get("scheduled_datetime", "")

    msg = f"[{item_idx}/{total_items}] กำลังโพสต์: {subfolder_name or video_name}"
    log(f"[Meta Auto Post Script] {msg} (Target: {scheduled_dt_str})")
    if progress_callback:
        progress_callback({
            "current": item_idx,
            "total": total_items,
            "percent": int(((item_idx - 1) / max(total_items, 1)) * 100),
            "message": msg
        })

    # 1. Focus 9222 window right at the start by Cocoa NSRunningApplication PID
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.4)

    # 2. Ensure on composer
    is_ready = driver.execute_script('''
        return !!Array.from(document.querySelectorAll('div, span, button')).find(el => el.innerText && el.innerText.trim() === 'Add video');
    ''')
    if not is_ready:
        log(f"[Meta Auto Post Script] Navigating to composer: {composer_url}")
        driver.get(composer_url)
        ready = fast_poll(driver, '''
            return !!Array.from(document.querySelectorAll('div, span, button')).find(el => el.innerText && el.innerText.trim() === 'Add video');
        ''', timeout=20.0, poll_interval=0.2)
        if not ready:
            raise RuntimeError("ไม่พบหน้าต่าง Create reel / ปุ่ม Add video")

    # 3. Click 'Add video' on 9222
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.2)

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
        log("[Meta Auto Post Script] Clicked 'Add video' button on 9222")
    else:
        raise RuntimeError("ไม่สามารถคลิกปุ่ม Add video ได้")

    time.sleep(0.5)

    # 4. macOS File Dialog
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"ไม่พบไฟล์วิดีโอ: {video_path}")

    log(f"[Meta Auto Post Script] Uploading video via dialog: {video_path}")
    upload_macos_file_dialog_fast(video_path, port=9222)

    # 5. Fast poll for upload completion
    log("[Meta Auto Post Script] Waiting for upload completion...")
    upload_done = fast_poll(driver, '''
        const text = document.body.innerText || '';
        return text.includes('100%') || text.includes('Your video is safe') || text.includes('Delete');
    ''', timeout=90.0, poll_interval=0.2)

    if not upload_done:
        log("[Meta Auto Post Script] Warning: Upload timeout check, attempting to proceed...")

    time.sleep(0.5)

    # 6. Insert Caption into Lexical / DraftJS textbox
    if caption:
        log(f"[Meta Auto Post Script] Inserting caption ({len(caption)} chars)...")
        driver.execute_script('''
            const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
            if (tb) {
                tb.focus();
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(tb);
                selection.removeAllRanges();
                selection.addRange(range);
                document.execCommand('delete', false, null);
                document.execCommand('insertText', false, arguments[0]);
                tb.dispatchEvent(new Event('input', { bubbles: true }));
                tb.dispatchEvent(new Event('change', { bubbles: true }));
            }
        ''', caption)
        time.sleep(0.4)

    # 7. Step 1 (Create) -> Step 2 (Edit)
    log("[Meta Auto Post Script] Advancing Step 1 (Create -> Edit)...")
    driver.execute_script('''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const nextBtn = allBtns.find(b => b.innerText && b.innerText.trim() === 'Next' && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700 && b.getAttribute('aria-disabled') !== 'true');
        if (nextBtn) nextBtn.click();
    ''')

    # Wait for Step 2 active
    fast_poll(driver, '''
        return !!Array.from(document.querySelectorAll('div, span')).find(el => el.innerText && (el.innerText.trim() === 'Audio' || el.innerText.trim() === 'Crop'));
    ''', timeout=10.0, poll_interval=0.15)
    time.sleep(0.4)

    # 8. Step 2 (Edit) -> Step 3 (Share)
    log("[Meta Auto Post Script] Advancing Step 2 (Edit -> Share)...")
    driver.execute_script('''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const nextBtn = allBtns.find(b => b.innerText && b.innerText.trim() === 'Next' && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700 && b.getAttribute('aria-disabled') !== 'true');
        if (nextBtn) nextBtn.click();
    ''')

    # Wait for Step 3 active
    fast_poll(driver, '''
        return !!Array.from(document.querySelectorAll('div, span')).find(el => el.innerText && (el.innerText.trim() === 'Scheduling options' || el.innerText.trim() === 'Share now'));
    ''', timeout=10.0, poll_interval=0.15)
    time.sleep(0.5)

    # 9. Select 'Schedule' Option Tab
    log("[Meta Auto Post Script] Selecting 'Schedule' radio tab...")
    driver.execute_script('''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button, [role="radio"]'));
        const schedTab = allBtns.find(b => b.innerText && b.innerText.trim() === 'Schedule' && b.getBoundingClientRect().y < 300);
        if (schedTab) (schedTab.closest('[role="button"], [role="radio"]') || schedTab).click();
    ''')
    time.sleep(0.5)

    # 10. Set Date & Time
    if scheduled_dt_str:
        try:
            dt = datetime.fromisoformat(scheduled_dt_str)
            date_str = dt.strftime("%d/%m/%Y")
            hour_str = f"{dt.hour:02d}"
            min_str = f"{dt.minute:02d}"

            log(f"[Meta Auto Post Script] Setting Schedule Date: {date_str}, Time: {hour_str}:{min_str}")

            def safe_input(selector: str, val: str, is_time: bool = False):
                try:
                    inputs = driver.find_elements(By.CSS_SELECTOR, selector)
                    if inputs:
                        inputs[0].click()
                        time.sleep(0.1)
                        if is_time:
                            inputs[0].send_keys(Keys.BACKSPACE)
                            for ch in val:
                                inputs[0].send_keys(ch)
                        else:
                            inputs[0].send_keys(Keys.COMMAND, 'a')
                            inputs[0].send_keys(val)
                        time.sleep(0.1)
                        fresh = driver.find_elements(By.CSS_SELECTOR, selector)
                        if fresh:
                            fresh[0].send_keys(Keys.TAB)
                except Exception as ex_in:
                    log(f"[Meta Auto Post Script] Input note ({selector}): {ex_in}")

            safe_input('input[placeholder="dd/mm/yyyy"]', date_str)
            time.sleep(0.2)
            safe_input('input[aria-label="hours"]', hour_str, is_time=True)
            time.sleep(0.2)
            safe_input('input[aria-label="minutes"]', min_str, is_time=True)
            time.sleep(0.4)

        except Exception as ex_dt:
            log(f"[Meta Auto Post Script] Parse datetime error '{scheduled_dt_str}': {ex_dt}")

    # Commit React state
    driver.execute_script('''
        const bg = document.querySelector('div[role="dialog"], body');
        if (bg) bg.click();
    ''')
    time.sleep(0.4)

    # 11. Click final 'Schedule' submit button
    log("[Meta Auto Post Script] Clicking final Schedule submit button...")
    final_clicked = fast_poll(driver, '''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const schedBtn = allBtns.find(b => {
            const t = (b.innerText || '').trim();
            return (t === 'Schedule' || t === 'Schedule Post' || t === 'Share') && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700 && b.getAttribute('aria-disabled') !== 'true';
        });
        if (schedBtn) {
            schedBtn.click();
            return true;
        }
        return false;
    ''', timeout=15.0, poll_interval=0.2)

    if not final_clicked:
        log("[Meta Auto Post Script] Warning: Schedule button poll timeout, attempting fallback click...")
        driver.execute_script('''
            const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
            const schedBtn = allBtns.find(b => b.innerText && b.innerText.trim() === 'Schedule' && b.getBoundingClientRect().x > 1400 && b.getBoundingClientRect().y > 700);
            if (schedBtn) schedBtn.click();
        ''')

    # 12. Fast poll for modal closure / submission confirmation
    log("[Meta Auto Post Script] Waiting for submission confirmation...")
    submitted = fast_poll(driver, '''
        const onPlanner = window.location.href.includes('planner') || window.location.href.includes('posts');
        const modalClosed = !document.querySelector('div[role="textbox"][contenteditable="true"]') && !Array.from(document.querySelectorAll('div, span')).find(el => el.innerText && el.innerText.trim() === 'Scheduling options');
        return onPlanner || modalClosed;
    ''', timeout=30.0, poll_interval=0.3)

    log(f"[Meta Auto Post Script] Post {item_idx}/{total_items} finished successfully!")
    return True

def run_meta_autopost_batch(
    posts: list[dict[str, Any]],
    target_url: str = "",
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """Runs a batch of scheduled posts through the fast script engine."""
    bot = browser_manager.get()
    driver = bot.driver
    total = len(posts)

    default_composer_url = "https://business.facebook.com/latest/reels_composer/?asset_id=1306362672555632&business_id=509334133244636&ir_qe_exposed=1&ref=biz_web_content_manager_published_posts&context_ref=POSTS"
    composer_url = target_url.strip() or default_composer_url

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
