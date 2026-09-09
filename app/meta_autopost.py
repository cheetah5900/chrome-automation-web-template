import os
import sys
import time
import random
import subprocess
import argparse
import urllib.parse
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

def ensure_active_window(driver, target_url: str = "") -> str:
    """
    Ensures driver is switched to a valid, responsive window handle.
    If current window is dead or closed, safely switches to an active tab or creates one via CDP.
    Never raises 'no such window: target window already closed'.
    """
    if not driver:
        raise RuntimeError("WebDriver instance is None")

    # 1. Quick test if current handle is responsive
    current_ok = False
    try:
        _ = driver.current_window_handle
        _ = driver.title
        current_ok = True
    except Exception:
        current_ok = False

    # 2. Extract target domain to prioritize tabs matching target domain
    target_host = ""
    if target_url:
        try:
            target_host = urllib.parse.urlparse(target_url).netloc.lower()
        except Exception:
            target_host = ""

    # 3. Retrieve all window handles
    handles = []
    try:
        handles = driver.window_handles
    except Exception as e:
        log(f"[ensure_active_window] Error querying window_handles: {e}")

    live_handles = []
    matched_handle = None

    for h in handles:
        try:
            driver.switch_to.window(h)
            curr = driver.current_url.lower()
            live_handles.append(h)
            if target_host and target_host in curr:
                matched_handle = h
                break
            elif "business.facebook.com" in curr or "facebook.com" in curr:
                matched_handle = h
                break
        except Exception:
            continue

    if matched_handle:
        driver.switch_to.window(matched_handle)
        return matched_handle

    if live_handles:
        driver.switch_to.window(live_handles[0])
        return live_handles[0]

    # If currently responsive, keep current
    if current_ok:
        try:
            return driver.current_window_handle
        except Exception:
            pass

    # 4. If no live handle exists at all (e.g. user closed all tabs), create a new tab via CDP
    try:
        log("[ensure_active_window] ไม่พบแท็บที่เปิดอยู่ กำลังสร้างแท็บใหม่ผ่าน CDP...")
        driver.execute_cdp_cmd("Target.createTarget", {"url": target_url or "about:blank"})
        time.sleep(0.5)
        new_handles = driver.window_handles
        if new_handles:
            driver.switch_to.window(new_handles[-1])
            return new_handles[-1]
    except Exception as cdp_err:
        log(f"[ensure_active_window] CDP createTarget error: {cdp_err}")

    raise RuntimeError("ไม่สามารถเชื่อมต่อหน้าต่าง Chrome ได้ (กรุณาตรวจสอบว่าได้กด Launch Browser แล้ว)")

def cleanup_browser_tabs(driver, target_url: str = "") -> None:
    """Safely ensures active working window without aggressively closing user tabs."""
    try:
        ensure_active_window(driver, target_url=target_url)
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

def focus_9222_browser_tab(driver, port: int | None = None) -> None:
    """Focuses the Chrome window directly through CDP and native macOS NSRunningApplication by PID."""
    target_port = port or getattr(browser_manager, '_current_port', None) or 9222
    if driver:
        try:
            ensure_active_window(driver)
            driver.execute_script("window.focus();")
            driver.execute_cdp_cmd('Page.bringToFront', {})
        except Exception:
            pass

    if sys.platform != "darwin":
        return

    pid = get_browser_window_pid(target_port)
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

    # 1. Set system clipboard directly via pbcopy
    try:
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(input=file_path.encode('utf-8'))
    except Exception as pb_err:
        log(f"[Meta Upload Dialog] pbcopy error: {pb_err}")

    # 2. Send keystrokes to the open file sheet
    script = f"""
    set the clipboard to "{escaped_path}"
    tell application "System Events"
        delay 0.8
        
        -- Press Cmd + Shift + G to open path sheet
        key code 5 using {{command down, shift down}}
        delay 0.8
        
        -- Select all existing text in sheet (Cmd + A) and delete
        key code 0 using {{command down}}
        delay 0.15
        key code 51
        delay 0.2
        
        -- Press Cmd + V to paste filepath (key code 9 is 'v' on any keyboard layout)
        key code 9 using {{command down}}
        delay 0.8
        
        -- Return to confirm path sheet
        key code 36
        delay 1.2
        
        -- Return to confirm open file dialog
        key code 36
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
    """Step 1: Safely focus/recover browser tab, navigate to composer URL, and verify URL & composer readiness."""
    composer_url = (composer_url or "").strip()
    if not composer_url or not (composer_url.startswith("http://") or composer_url.startswith("https://")):
        raise ValueError(f"URL ไม่ถูกต้อง: '{composer_url}' (ต้องขึ้นต้นด้วย http:// หรือ https://)")

    # 1. Ensure driver has a live window handle and focus it
    ensure_active_window(driver, target_url=composer_url)
    focus_9222_browser_tab(driver)
    time.sleep(0.2)

    log(f"[Meta Step 1] กำลังเปิดหน้าต่าง Composer: {composer_url}")

    # Check if already on this exact composer URL or need to navigate
    needs_navigate = True
    try:
        curr_url = driver.current_url
        if curr_url.split("?")[0] == composer_url.split("?")[0] and "reels_composer" in curr_url:
            log("[Meta Step 1] กำลังอยู่ในหน้า Composer เดิม ทำการรีเฟรชเพื่อให้ได้ฟอร์มใหม่...")
            driver.get(composer_url)
            needs_navigate = False
    except Exception:
        needs_navigate = True

    if needs_navigate:
        try:
            driver.get(composer_url)
        except Exception as get_err:
            log(f"[Meta Step 1 Warning] driver.get failed ({get_err}), attempting recovery...")
            ensure_active_window(driver, target_url=composer_url)
            driver.get(composer_url)

    # 2. VERIFY URL NAVIGATION: Check whether browser has actually reached the target link
    log("[Meta Step 1] 🔍 กำลังตรวจสอบการเปิดลิงก์บนเบราว์เซอร์...")
    parsed_target = urllib.parse.urlparse(composer_url)
    target_host = parsed_target.netloc.lower()

    nav_start = time.time()
    navigated = False
    last_detected_url = ""

    while time.time() - nav_start < 20.0:
        if is_meta_stopped():
            raise RuntimeError("🛑 Force Stop: ผู้ใช้สั่งหยุดการทำงาน")
        try:
            curr = driver.current_url.lower()
            last_detected_url = curr
            if target_host in curr or "facebook.com" in curr:
                # Check for login redirect
                if "login" in curr or "checkpoint" in curr:
                    raise RuntimeError(f"⚠️ เบราว์เซอร์ถูกเปลี่ยนเส้นทางไปหน้า Login ({curr}) กรุณาเข้าสู่ระบบ Facebook บนเบราว์เซอร์นี้ก่อนรัน Auto Post")
                navigated = True
                break
        except Exception as e:
            if "login" in str(e).lower():
                raise
        time.sleep(0.5)

    if not navigated:
        raise RuntimeError(
            f"❌ ไม่สามารถเปิดลิงก์ Meta ได้: เบราว์เซอร์ยังคงอยู่ที่ '{last_detected_url or 'ไม่ทราบ URL'}' "
            f"(ไม่ตรงกับปลายทาง {target_host}) กรุณาตรวจสอบว่าเปิด Chrome ถูกต้องและไม่ได้ติดบล็อก"
        )

    log(f"[Meta Step 1] 🌐 ยืนยันการเปิดลิงก์สำเร็จ: {driver.current_url[:80]}...")

    # 3. VERIFY COMPOSER DOM READINESS
    log("[Meta Step 1] ⏳ รอหน้าต่าง Composer โหลดองค์ประกอบ (Add video / Upload input)...")
    ready = fast_poll(driver, '''
        if (document.readyState !== 'complete') return false;

        // 1. Check for Add video button (English / Thai)
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button, span, div'));
        const addBtn = allBtns.find(el => {
            const txt = (el.innerText || '').trim();
            const rect = el.getBoundingClientRect();
            const isVis = rect.width > 10 && rect.height > 10;
            return isVis && (
                txt.includes('Add video') || 
                txt.includes('Add Video') || 
                txt.includes('Upload video') || 
                txt.includes('เพิ่มวิดีโอ')
            );
        });
        if (addBtn) return true;

        // 2. Check for file input accepting video
        const fileInput = document.querySelector('input[type="file"][accept*="video"], input[type="file"]');
        if (fileInput) return true;

        // 3. Check for specific Reels composer dialog
        const composerDialog = document.querySelector('div[aria-label*="Reel" i], div[aria-label*="Composer" i], div[data-pagelet*="Composer" i]');
        if (composerDialog) return true;

        return false;
    ''', timeout=40.0, poll_interval=0.3)

    if not ready:
        raise RuntimeError("หน้าต่าง Composer ไม่พร้อมทำงานภายในเวลา 40 วินาที (ไม่พบปุ่ม Add video หรือช่องอัปโหลดวิดีโอ)")

    log("[Meta Step 1] ✅ หน้าต่าง Composer พร้อมใช้งานเรียบร้อยแล้ว")
    return True

def step_2_upload_video(driver, video_path: str) -> bool:
    """Step 2: Thoroughly poll for 'Add video' button, click immediately when ready, and send video file path."""
    focus_9222_browser_tab(driver, port=9222)
    time.sleep(0.1)

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"ไม่พบไฟล์วิดีโอ: {video_path}")

    log(f"[Meta Step 2] กำลังตรวจสอบความพร้อมของปุ่ม 'Add video' บนหน้าจอ...")

    # Loop check: thoroughly locate visible, enabled Add video button
    target_btn = fast_poll(driver, '''
        const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const direct = allBtns.find(b => {
            const txt = (b.innerText || '').trim();
            const rect = b.getBoundingClientRect();
            const isVis = rect.width > 10 && rect.height > 10;
            const isEnabled = b.getAttribute('aria-disabled') !== 'true';
            return isVis && isEnabled && (txt.includes('Add video') || txt.includes('Add Video') || txt.includes('Upload video'));
        });
        if (direct) return direct;

        const textEls = Array.from(document.querySelectorAll('div, span, button')).filter(el => {
            const t = (el.innerText || '').trim();
            return (t === 'Add video' || t === 'Add Video' || t === 'Upload video') && el.children.length === 0;
        });
        for (const tEl of textEls) {
            const btnParent = tEl.closest('[role="button"], button');
            if (btnParent) {
                const rect = btnParent.getBoundingClientRect();
                if (rect.width > 10 && rect.height > 10 && btnParent.getAttribute('aria-disabled') !== 'true') {
                    return btnParent;
                }
            }
        }
        return null;
    ''', timeout=35.0, poll_interval=0.2)

    if not target_btn:
        raise RuntimeError("ไม่พบปุ่ม Add video ที่พร้อมคลิกบนหน้าจอ (หมดเวลา 35 วินาที)")

    try:
        ActionChains(driver).move_to_element(target_btn).pause(0.05).click().perform()
    except Exception:
        driver.execute_script("arguments[0].click();", target_btn)
    log(f"[Meta Step 2] คลิกปุ่ม 'Add video' สำเร็จ -> กำลังส่งไฟล์วิดีโอผ่าน Dialog: {video_path}")
    upload_macos_file_dialog_fast(video_path, port=9222)

    # Loop check: poll until video is received / upload is recognized
    upload_started = fast_poll(driver, '''
        const hasVideo = !!document.querySelector('video, div[role="progressbar"], div[class*="thumbnail" i], div[class*="preview" i]');
        const shareActive = !!Array.from(document.querySelectorAll('div[role="button"], button')).find(b => b.innerText && b.innerText.trim().startsWith('Share') && b.getAttribute('aria-disabled') !== 'true');
        return hasVideo || shareActive;
    ''', timeout=25.0, poll_interval=0.25)

    if upload_started:
        log(f"[Meta Step 2] ✅ อัปโหลดวิดีโอเข้าระบบเรียบร้อย: {os.path.basename(video_path)}")
    else:
        log(f"[Meta Step 2] ✅ ส่งคำสั่งเลือกไฟล์วิดีโอผ่าน Dialog เรียบร้อย: {os.path.basename(video_path)}")
    return True

def step_3_insert_caption(driver, caption: str) -> bool:
    """Step 3: Poll for Description box, insert Caption, and loop verify value. Retries if not present."""
    if not caption or not str(caption).strip():
        log("[Meta Step 3] ไม่มีข้อความ Caption ข้ามขั้นตอนนี้")
        return True

    caption_clean = str(caption).strip()
    log(f"[Meta Step 3] กำลังรอช่องข้อความ Description เพื่อวาง Caption ({len(caption_clean)} ตัวอักษร)...")
    
    # Loop check: locate textbox
    tb = fast_poll(driver, '''
        return document.querySelector('div[role="textbox"][contenteditable="true"]');
    ''', timeout=15.0, poll_interval=0.2)

    if not tb:
        raise RuntimeError("ไม่พบกล่องข้อความ Description บนหน้าจอ")

    max_paste_attempts = 3
    for attempt in range(1, max_paste_attempts + 1):
        # 1. Check if already properly filled
        existing_text = driver.execute_script('''
            const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
            return tb ? (tb.innerText || tb.textContent || '').trim() : '';
        ''')
        if existing_text and len(existing_text) > 0:
            log(f"[Meta Step 3] ✅ ตรวจสอบพบข้อความใน Description เรียบร้อย ({len(existing_text)} ตัวอักษร)")
            return True

        log(f"[Meta Step 3] 📝 กำลังวางข้อความ Description (ครั้งที่ {attempt}/{max_paste_attempts})...")

        # 2. Try JavaScript insertion (ClipboardEvent + execCommand)
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
            }
        ''', caption_clean)

        # 3. Quick poll check if JS insertion worked
        verified = fast_poll(driver, '''
            const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
            return tb && (tb.innerText || tb.textContent || '').trim().length > 0;
        ''', timeout=2.0, poll_interval=0.2)

        if verified:
            log(f"[Meta Step 3] ✅ ตรวจสอบยืนยันข้อความ Caption ใน Description สำเร็จ ({len(caption_clean)} ตัวอักษร)")
            return True

        # 4. Fallback if still empty: Click textbox and use ActionChains + Clipboard paste
        log(f"[Meta Step 3] ⚠️ ตรวจสอบแล้วยังไม่พบข้อความในช่อง Description (ครั้งที่ {attempt}) -> กำลังลองใช้วิธี Fallback วางด้วย Clipboard...")
        try:
            # Set macOS clipboard
            if sys.platform == "darwin":
                p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                p.communicate(input=caption_clean.encode('utf-8'))
            
            # Click and paste via keyboard
            ActionChains(driver).move_to_element(tb).click().pause(0.2).key_down(Keys.COMMAND).send_keys('v').key_up(Keys.COMMAND).pause(0.3).perform()
        except Exception as paste_err:
            log(f"[Meta Step 3] ActionChains paste fallback error: {paste_err}")

        # 5. Check again for this attempt
        time.sleep(0.5)
        check_text = driver.execute_script('''
            const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
            return tb ? (tb.innerText || tb.textContent || '').trim() : '';
        ''')
        if check_text and len(check_text) > 0:
            log(f"[Meta Step 3] ✅ ตรวจสอบยืนยันข้อความ Caption สำเร็จหลังวางใหม่ ({len(check_text)} ตัวอักษร)")
            return True

    # Final assertion
    final_text = driver.execute_script('''
        const tb = document.querySelector('div[role="textbox"][contenteditable="true"]');
        return tb ? (tb.innerText || tb.textContent || '').trim() : '';
    ''')
    if not final_text:
        raise RuntimeError(f"ไม่สามารถยืนยันข้อความ Caption ในกล่อง Description ได้หลังพยายามวาง {max_paste_attempts} ครั้ง")

    log(f"[Meta Step 3] ✅ วางข้อความ Description และยืนยันผลสำเร็จ")
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

def detect_schedule_platforms(driver) -> dict[str, Any]:
    """Inspects the Schedule section to detect date/time inputs for Facebook and Instagram.
    Returns details on whether an Instagram scheduling box is present or absent, allowing the system
    to skip Instagram cleanly if missing and proceed directly to Schedule button.
    """
    try:
        res = driver.execute_script('''
            const dateInputs = Array.from(document.querySelectorAll('input[placeholder="dd/mm/yyyy"]'));
            const hoursInputs = Array.from(document.querySelectorAll('input[aria-label="hours"]'));
            const minsInputs = Array.from(document.querySelectorAll('input[aria-label="minutes"]'));

            const items = dateInputs.map((inp, idx) => {
                let cur = inp;
                let detectedPlatform = null;
                for (let i = 0; i < 8 && cur && cur !== document.body; i++) {
                    const text = (cur.innerText || '').toLowerCase();
                    const aria = (cur.getAttribute('aria-label') || '').toLowerCase();
                    const hasIg = text.includes('instagram') || aria.includes('instagram') || !!cur.querySelector('[aria-label*="Instagram" i], svg[aria-label*="Instagram" i]');
                    const hasFb = text.includes('facebook') || aria.includes('facebook') || !!cur.querySelector('[aria-label*="Facebook" i], svg[aria-label*="Facebook" i]');
                    if (hasIg && !hasFb) {
                        detectedPlatform = 'instagram';
                        break;
                    }
                    if (hasFb && !hasIg) {
                        detectedPlatform = 'facebook';
                        break;
                    }
                    cur = cur.parentElement;
                }
                if (!detectedPlatform) {
                    detectedPlatform = idx === 0 ? 'facebook' : (idx === 1 ? 'instagram' : `platform_${idx}`);
                }
                return {
                    idx: idx,
                    platform: detectedPlatform,
                    hasHours: idx < hoursInputs.length,
                    hasMins: idx < minsInputs.length
                };
            });

            // True check: Instagram box exists if any item is 'instagram' OR if there are >= 2 date inputs
            const hasFb = dateInputs.length > 0;
            const hasIg = dateInputs.length >= 2 || items.some(it => it.platform === 'instagram');

            return {
                totalDateInputs: dateInputs.length,
                totalHoursInputs: hoursInputs.length,
                totalMinsInputs: minsInputs.length,
                hasFb: hasFb,
                hasIg: hasIg,
                platforms: items
            };
        ''')
        return res or {"totalDateInputs": 0, "hasFb": False, "hasIg": False, "platforms": []}
    except Exception as e:
        log(f"[Meta Step 5] ⚠️ ไม่สามารถตรวจจับแพลตฟอร์มผ่านสคริปต์ได้ ({e}) -> ใช้ fallback ตรวจตามจำนวนช่อง")
        d_len = len(driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]'))
        return {
            "totalDateInputs": d_len,
            "hasFb": d_len > 0,
            "hasIg": d_len >= 2,
            "platforms": [{"idx": i, "platform": "facebook" if i == 0 else "instagram"} for i in range(d_len)]
        }

def step_5_set_schedule(driver, scheduled_dt_str: str) -> bool:
    """Step 5: Poll for Schedule option, select it, input Date via Calendar & Time via spinbutton, loop verify values.
    Specifically checks if an Instagram schedule box exists; if not, skips Instagram and proceeds to Schedule submit."""
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
            target_month = dt.month
            target_month_name = dt.strftime('%B')
            target_year = dt.year
            # Format according to d/m/yyyy as supported by Meta input (e.g. 1/10/2026)
            date_str = f"{target_day}/{target_month}/{target_year}"
            target_date_label = f"{target_day} {target_month_name} {target_year}"
            hour_str = f"{dt.hour:02d}"
            min_str = f"{dt.minute:02d}"

            log(f"[Meta Step 5] กำหนดวันโพสต์: {target_date_label} ({date_str}), เวลา: {hour_str}:{min_str}")

            # 1. Detect platforms (Check if Instagram date/time box exists)
            platform_info = detect_schedule_platforms(driver)
            has_ig = platform_info.get("hasIg", False)
            date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
            platform_count = len(date_inputs)

            if not has_ig:
                log(f"[Meta Step 5] 🔍 ตรวจสอบแพลตฟอร์ม: ตรวจพบช่องตั้งเวลาเฉพาะ Facebook ({platform_count} ช่อง) | ไม่พบช่อง Instagram")
                log(f"[Meta Step 5] ⏩ ระบบจะตั้งเวลาเฉพาะ Facebook และข้าม Instagram เพื่อไปกดยืนยัน Schedule ทันที")
            else:
                log(f"[Meta Step 5] 🔍 ตรวจสอบแพลตฟอร์ม: ตรวจพบช่องตั้งเวลาครบทั้ง Facebook และ Instagram ({platform_count} ช่อง)")

            now = datetime.now()
            months_ahead = (target_year - now.year) * 12 + (target_month - now.month)
            log(f"[Meta Step 5] เป้าหมาย: วันที่ {target_day} เดือน {target_month_name} {target_year} (ต้องเลื่อนเดือนไปข้างหน้า {months_ahead} ครั้ง)")

            # Set Date for available platforms dynamically via Calendar Navigation
            for d_idx, date_input in enumerate(date_inputs):
                plat_label = "Facebook" if d_idx == 0 else ("Instagram" if d_idx == 1 else f"Platform #{d_idx}")
                log(f"[Meta Step 5] แพลตฟอร์ม {plat_label} (#{d_idx}): กำลังเปิดปฏิทินเพื่อเลือกวัน...")
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", date_input)
                except Exception:
                    date_input.click()
                time.sleep(0.4)

                # If target month is ahead, click Next Month
                if months_ahead > 0:
                    for m_step in range(months_ahead):
                        log(f"[Meta Step 5] แพลตฟอร์ม {plat_label} (#{d_idx}): คลิกปุ่มเดือนถัดไป (ครั้งที่ {m_step + 1}/{months_ahead})...")
                        debug_date_click_next_month(driver)
                        time.sleep(0.25)

                # Pick target day
                log(f"[Meta Step 5] แพลตฟอร์ม {plat_label} (#{d_idx}): คลิกเลือกวันที่ {target_day} ในปฏิทิน...")
                debug_date_pick_day(driver, day_str=str(target_day), date_val=date_str)
                time.sleep(0.3)

            # If no IG was found, log that IG is skipped
            if not has_ig:
                log("[Meta Step 5] ℹ️ ไม่มีช่องวันที่/เวลาของ Instagram -> ข้ามขั้นตอนของ IG เรียบร้อย")

            # Loop check: verify all Date values updated to target day/month
            fast_poll(driver, '''
                const dates = Array.from(document.querySelectorAll('input[placeholder="dd/mm/yyyy"]'));
                const dayNum = String(arguments[0]);
                const monthName = String(arguments[1]);
                const yearNum = String(arguments[2]);
                return dates.length > 0 && dates.every(d => {
                    const v = d.value || '';
                    return (v.includes(dayNum) && v.includes(yearNum)) || v.includes(monthName);
                });
            ''', timeout=5.0, poll_interval=0.2, js_args=[target_day, target_month_name, target_year])

            # 2. Set Hours for ALL available platforms
            hours_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[aria-label="hours"]')
            for h_input in hours_inputs:
                try:
                    h_input.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", h_input)
                time.sleep(0.05)
                h_input.send_keys(Keys.BACKSPACE, Keys.BACKSPACE, hour_str)

            # 3. Set Minutes for ALL available platforms
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

            if not has_ig:
                log(f"[Meta Step 5] ✅ กำหนดวัน-เวลา Facebook เรียบร้อยแล้ว (ไม่มีช่อง Instagram จึงข้าม) -> พร้อมกดปุ่ม Schedule ทันที")
            else:
                log(f"[Meta Step 5] ✅ กำหนดวัน-เวลา Facebook & Instagram ({platform_count} แพลตฟอร์ม) สำเร็จเรียบร้อยแล้ว -> พร้อมกดปุ่ม Schedule ทันที")
            return True

        except Exception as ex_dt:
            log(f"[Meta Step 5 Error] แปลงหรือใส่วัน-เวลา '{scheduled_dt_str}' ไม่ถูกต้อง: {ex_dt}")
            raise ex_dt
    return True

# --- Granular Date Debug Helpers for Step-by-Step UI Control ---
def debug_date_open_calendar(driver, platform_idx: str = "all") -> dict[str, Any]:
    """Calendar Step 1: Click date input to open the Calendar popup.
    Gracefully detects if Instagram is requested but not present."""
    date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
    if not date_inputs:
        return {"success": False, "error": "ไม่พบช่อง input[placeholder='dd/mm/yyyy'] บนหน้าจอ"}
    
    # Check if Instagram is specifically selected but no IG box exists
    if platform_idx == "1" and len(date_inputs) < 2:
        return {
            "success": True,
            "skipped": True,
            "has_ig": False,
            "message": "ℹ️ ตรวจสอบแล้ว: ไม่พบช่องวันที่และเวลาของ Instagram บนหน้านี้ (มีเฉพาะ Facebook) -> ข้ามการตั้งค่า IG เรียบร้อย สามารถไปขั้นตอนกดปุ่ม Schedule ได้เลย"
        }

    targets = date_inputs if platform_idx == "all" else [date_inputs[int(platform_idx)]] if int(platform_idx) < len(date_inputs) else []
    if not targets:
        return {"success": False, "error": f"ไม่พบช่องตาม index {platform_idx}"}
    
    target = targets[0]
    try:
        ActionChains(driver).move_to_element(target).pause(0.1).click().perform()
    except Exception:
        driver.execute_script("arguments[0].click();", target)
    time.sleep(0.35)
    
    status = driver.execute_script('''
        const grid = document.querySelector('[role="grid"]');
        const dialog = document.querySelector('div[role="dialog"]');
        const cells = document.querySelectorAll('[role="gridcell"]');
        return {
            hasGrid: !!grid,
            hasDialog: !!dialog,
            cellsCount: cells.length
        };
    ''')
    return {"success": True, "data": status, "message": f"คลิกเปิดปฏิทินสำเร็จ (ตรวจพบ {status.get('cellsCount', 0)} วันในตาราง)"}

def debug_date_click_next_month(driver) -> dict[str, Any]:
    """Calendar Step 2: Click the 'Next Month' button in the open Calendar."""
    res = driver.execute_script('''
        const allEls = Array.from(document.querySelectorAll('div, span, button, a'));
        
        // 1. By innerText or aria-label containing "next month" / "เดือนถัดไป"
        let nextEl = allEls.find(el => {
            const t = (el.innerText || '').toLowerCase().trim();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const isNext = t.includes('next month') || t.includes('เดือนถัดไป') || aria.includes('next month') || aria.includes('เดือนถัดไป');
            const isEnabled = el.getAttribute('aria-disabled') !== 'true';
            return isNext && isEnabled && el.offsetWidth > 15 && el.offsetWidth < 120 && el.offsetHeight > 15 && el.offsetHeight < 120;
        });

        // 2. By chevron-right SVG icon
        if (!nextEl) {
            nextEl = allEls.find(b => {
                const isEnabled = b.getAttribute('aria-disabled') !== 'true';
                if (!isEnabled || b.offsetWidth < 15 || b.offsetWidth > 120) return false;
                const html = b.innerHTML.toLowerCase();
                return (html.includes('chevron-right') || html.includes('arrow-right') || html.includes('chevron_right')) && b.querySelector('svg');
            });
        }

        // 3. Fallback: buttons positioned in calendar header above the true calendar grid
        if (!nextEl) {
            const calGrid = Array.from(document.querySelectorAll('[role="grid"]')).find(g => g.querySelectorAll('[role="gridcell"]').length >= 20);
            if (calGrid) {
                const popover = calGrid.closest('div[role="dialog"]') || calGrid.parentElement?.parentElement?.parentElement || document.body;
                const gRect = calGrid.getBoundingClientRect();
                const topBtns = Array.from(popover.querySelectorAll('button, div[role="button"], div[tabindex="0"]')).filter(b => {
                    const bRect = b.getBoundingClientRect();
                    return bRect.y < gRect.y && b.offsetWidth > 15 && b.offsetHeight > 15 && b.getAttribute('aria-disabled') !== 'true';
                });
                if (topBtns.length >= 2) {
                    topBtns.sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x);
                    nextEl = topBtns[topBtns.length - 1]; // Rightmost is Next Month
                } else if (topBtns.length === 1) {
                    nextEl = topBtns[0];
                }
            }
        }

        if (nextEl) {
            const clickBtn = nextEl.closest('[role="button"]') || nextEl.querySelector('[role="button"]') || nextEl;
            const info = {
                text: (clickBtn.innerText || '').trim(),
                ariaLabel: clickBtn.getAttribute('aria-label') || '',
                tag: clickBtn.tagName
            };
            clickBtn.click();
            return { success: true, info: info };
        }
        return { success: false, error: "ไม่พบปุ่มเดือนถัดไป (Next Month)" };
    ''')
    
    time.sleep(0.35)
    if res.get("success"):
        return {"success": True, "data": res.get("info"), "message": f"กดปุ่มเดือนถัดไปสำเร็จ: {res.get('info')}"}
    return {"success": False, "error": res.get("error", "ไม่พบปุ่มเดือนถัดไป")}

def debug_date_pick_day(driver, day_str: str = "1", date_val: str = "1/10/2026") -> dict[str, Any]:
    """Calendar Step 3: Click target day in the open Calendar grid."""
    day_num = "1"
    month_name = ""
    try:
        if "/" in date_val:
            parts = date_val.split("/")
            day_num = parts[0].strip()
            month_idx = int(parts[1].strip())
            from datetime import date
            month_name = date(2026, month_idx, 1).strftime('%B')
        elif "-" in date_val:
            dt = datetime.fromisoformat(date_val)
            day_num = str(dt.day)
            month_name = dt.strftime('%B')
        else:
            day_num = day_str.strip()
    except Exception:
        day_num = day_str.strip() or "1"
        
    res = driver.execute_script('''
        const targetDay = String(arguments[0]);
        const targetMonth = (arguments[1] || '').toLowerCase();
        
        // Find the actual calendar grid (must have >= 20 cells)
        const calGrid = Array.from(document.querySelectorAll('[role="grid"]')).find(g => g.querySelectorAll('[role="gridcell"]').length >= 20);
        const searchScope = calGrid || document;
        const allCandidates = Array.from(searchScope.querySelectorAll('[role="button"], div[role="gridcell"], button, div'));

        // Strategy 1: Match by exact text and small button dimensions (15px to 60px)
        let dayEl = allCandidates.find(b => {
            if ((b.innerText || '').trim() !== targetDay) return false;
            const isEnabled = b.getAttribute('aria-disabled') !== 'true';
            return isEnabled && b.offsetWidth > 15 && b.offsetWidth < 60 && b.offsetHeight > 15 && b.offsetHeight < 60;
        });

        // Strategy 2: Match by aria-label containing day number and month
        if (!dayEl) {
            dayEl = allCandidates.find(el => {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                if (!aria) return false;
                const hasDay = aria.includes(targetDay);
                const hasMonth = targetMonth ? (aria.includes(targetMonth) || (targetMonth === 'october' && aria.includes('ตุลาคม'))) : true;
                const isDisabled = el.getAttribute('aria-disabled') === 'true';
                return hasDay && hasMonth && !isDisabled;
            });
        }

        if (dayEl) {
            const clickTarget = dayEl.querySelector('[role="button"]') || dayEl;
            const info = {
                text: (clickTarget.innerText || '').trim(),
                ariaLabel: clickTarget.getAttribute('aria-label') || '',
                tag: clickTarget.tagName
            };
            clickTarget.click();
            return { success: true, info: info };
        }
        return { success: false, error: `ไม่พบวันที่ ${targetDay} ในปฏิทิน` };
    ''', day_num, month_name)

    time.sleep(0.4)
    date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
    current_values = [d.get_attribute("value") for d in date_inputs]
    
    if res.get("success"):
        return {"success": True, "data": res.get("info"), "current_values": current_values, "message": f"เลือกวันที่ {day_num} ในปฏิทินสำเร็จ ค่าช่องวันที่ปัจจุบัน: {current_values}"}
    return {"success": False, "error": res.get("error", f"ไม่พบวันที่ {day_num}"), "current_values": current_values}

def debug_date_calendar_full_flow(driver, date_val: str = "1/10/2026", platform_idx: str = "all") -> dict[str, Any]:
    """Full Calendar Flow: Open Calendar -> Click Next Month if target is future month -> Pick Day.
    Specifically checks for Instagram: if no IG box exists, skips IG and reports ready for Schedule submit."""
    date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
    if not date_inputs:
        return {"success": False, "error": "ไม่พบช่อง input[placeholder='dd/mm/yyyy']"}
        
    plat_info = detect_schedule_platforms(driver)
    has_ig = plat_info.get("hasIg", False)

    # If Instagram was selected specifically but no IG box exists
    if platform_idx == "1" and not has_ig:
        return {
            "success": True,
            "skipped": True,
            "has_ig": False,
            "message": "ℹ️ ตรวจสอบแล้ว: ไม่พบช่องวันที่และเวลาของ Instagram บนหน้านี้ (มีเฉพาะ Facebook) -> ข้ามการตั้งค่า IG เรียบร้อย สามารถไปขั้นตอนกดปุ่ม Schedule ได้เลย"
        }

    day_num = 1
    month_num = 10
    year_num = 2026
    try:
        if "/" in date_val:
            parts = date_val.split("/")
            day_num = int(parts[0].strip())
            month_num = int(parts[1].strip())
            year_num = int(parts[2].strip())
        elif "-" in date_val:
            dt = datetime.fromisoformat(date_val)
            day_num = dt.day
            month_num = dt.month
            year_num = dt.year
    except Exception:
        pass
        
    now = datetime.now()
    months_ahead = (year_num - now.year) * 12 + (month_num - now.month)
    
    targets = date_inputs if platform_idx == "all" else [date_inputs[int(platform_idx)]] if int(platform_idx) < len(date_inputs) else []

    results = []
    for idx, inp in enumerate(targets):
        plat_label = "Facebook" if idx == 0 else ("Instagram" if idx == 1 else f"Platform #{idx}")
        # 1. Open calendar
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", inp)
        except Exception:
            inp.click()
        time.sleep(0.4)
        
        # 2. Click next month if target is ahead
        if months_ahead > 0:
            for m in range(months_ahead):
                debug_date_click_next_month(driver)
                time.sleep(0.3)
                
        # 3. Pick day
        pick_res = debug_date_pick_day(driver, day_str=str(day_num), date_val=date_val)
        results.append({"platform_idx": idx, "platform_label": plat_label, "pick_result": pick_res})
        time.sleep(0.4)

    time.sleep(0.3)
    final_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
    final_values = [d.get_attribute("value") for d in final_inputs]
    
    if not has_ig:
        msg = f"รัน Calendar Flow ครบทุกขั้นตอนสำเร็จ (Facebook: ตั้งค่าเรียบร้อย | ไม่มีช่อง Instagram จึงข้ามและพร้อมกดปุ่ม Schedule) ค่าที่ได้: {final_values}"
    else:
        msg = f"รัน Calendar Flow ครบทุกขั้นตอนสำเร็จ (Facebook & Instagram: ตั้งค่าเรียบร้อย) ค่าที่ได้: {final_values}"
        
    return {
        "success": True,
        "results": results,
        "final_values": final_values,
        "has_ig": has_ig,
        "skipped_ig": not has_ig,
        "message": msg
    }

# Backward compatible simulated keystroke helpers
def debug_date_focus_select(driver, platform_idx: str = "all") -> dict[str, Any]:
    return debug_date_open_calendar(driver, platform_idx=platform_idx)

def debug_date_type_first(driver, date_str: str, platform_idx: str = "all") -> dict[str, Any]:
    return debug_date_click_next_month(driver)

def debug_date_type_remaining(driver, date_str: str, platform_idx: str = "all") -> dict[str, Any]:
    return debug_date_pick_day(driver, date_val=date_str)

def debug_date_tab_out(driver, platform_idx: str = "all") -> dict[str, Any]:
    date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="dd/mm/yyyy"]')
    values = [d.get_attribute("value") for d in date_inputs]
    return {"success": True, "values": values, "message": f"ค่าปัจจุบันในช่อง: {values}"}

def debug_date_full_simulate(driver, date_str: str, platform_idx: str = "all") -> dict[str, Any]:
    return debug_date_calendar_full_flow(driver, date_val=date_str, platform_idx=platform_idx)

def step_6_submit_schedule(driver) -> bool:
    """Step 6: Submit schedule button using verified semantic targeting."""
    return _real_step_6_submit_schedule(driver)

def _real_step_6_submit_schedule(driver) -> bool:
    """Step 6: Poll for final Schedule submit button (distinguished from Radio and Nav Header) and click."""
    log("[Meta Step 6] กำลังตรวจจับปุ่มกดยืนยัน Schedule (ตัดตัวเลือก Radio และแท็บด้านบนออก)...")

    sched_submit_el = fast_poll(driver, '''
        const allBtns = Array.from(document.querySelectorAll('button, div[role="button"]'));

        // Strategy A: Find submit button in the same footer container as 'Back' or 'Cancel'
        const backBtn = allBtns.find(b => {
            const t = (b.innerText || '').trim();
            return t === 'Back' || t === 'ย้อนกลับ' || t === 'Cancel' || t === 'ยกเลิก';
        });

        if (backBtn && backBtn.parentElement) {
            const footerParent = backBtn.parentElement;
            const siblingSubmit = Array.from(footerParent.querySelectorAll('button, div[role="button"]')).find(b => {
                const t = (b.innerText || '').trim().toLowerCase();
                const isMatch = t === 'schedule' || t === 'กำหนดเวลา' || t === 'share' || t === 'แชร์';
                const isEnabled = b.getAttribute('aria-disabled') !== 'true';
                return isMatch && b !== backBtn && isEnabled;
            });
            if (siblingSubmit) return siblingSubmit;
        }

        // Strategy B: Semantic filtering across all buttons (must NOT be Radio and must NOT be Nav Header)
        const candidates = allBtns.filter(b => {
            const t = (b.innerText || '').trim().toLowerCase();
            const isMatch = t === 'schedule' || t === 'กำหนดเวลา' || t === 'share' || t === 'แชร์';
            const isNavHeader = !!b.closest('[role="listitem"], [role="list"], nav, header');
            const isRadio = b.getAttribute('role') === 'radio'
                         || !!b.querySelector('input[type="radio"], [role="radio"]')
                         || !!b.closest('[role="radiogroup"], [role="radio"]');
            const isVisible = b.offsetWidth > 20 && b.offsetHeight > 20;
            const isEnabled = b.getAttribute('aria-disabled') !== 'true';
            return isMatch && !isNavHeader && !isRadio && isVisible && isEnabled;
        });

        // The final submit button is always the last action button in document order
        return candidates.length > 0 ? candidates[candidates.length - 1] : null;
    ''', timeout=20.0, poll_interval=0.1)

    if not sched_submit_el:
        # Fallback query without waiting for aria-disabled if it lags
        sched_submit_el = fast_poll(driver, '''
            const allBtns = Array.from(document.querySelectorAll('button, div[role="button"]'));
            const candidates = allBtns.filter(b => {
                const t = (b.innerText || '').trim().toLowerCase();
                const isMatch = t === 'schedule' || t === 'กำหนดเวลา' || t === 'share' || t === 'แชร์';
                const isNavHeader = !!b.closest('[role="listitem"], [role="list"], nav, header');
                const isRadio = b.getAttribute('role') === 'radio'
                             || !!b.querySelector('input[type="radio"], [role="radio"]')
                             || !!b.closest('[role="radiogroup"], [role="radio"]');
                const isVisible = b.offsetWidth > 20 && b.offsetHeight > 20;
                return isMatch && !isNavHeader && !isRadio && isVisible;
            });
            return candidates.length > 0 ? candidates[candidates.length - 1] : null;
        ''', timeout=5.0, poll_interval=0.2)

    if sched_submit_el:
        try:
            ActionChains(driver).move_to_element(sched_submit_el).pause(0.1).click().perform()
        except Exception:
            pass
        driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'}); arguments[0].click();", sched_submit_el)
    else:
        raise RuntimeError("ไม่พบปุ่ม Schedule ยืนยันที่พร้อมคลิก (กรุณาตรวจสอบว่ากรอกวัน-เวลาถูกต้อง)")

    log("[Meta Step 6] ✅ กดปุ่ม Schedule ยืนยันเรียบร้อยแล้ว (กำลังรอการบันทึกข้อมูลโพสต์)...")
    time.sleep(2.0)

    # Fast poll for modal closure / submission confirmation
    fast_poll(driver, '''
        const onPlanner = window.location.href.includes('planner') || window.location.href.includes('posts');
        const modalClosed = !document.querySelector('div[role="textbox"][contenteditable="true"]') &&
                            !Array.from(document.querySelectorAll('div, span')).find(el => el.innerText && el.innerText.trim() === 'Scheduling options');
        return onPlanner || modalClosed;
    ''', timeout=25.0, poll_interval=0.3)

    log("[Meta Step 6] ✅ การตั้งเวลาโพสต์เสร็จสมบูรณ์")
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

    # Step 5: Set Schedule Date & Time (Calendar Navigation)
    step_5_set_schedule(driver, scheduled_dt_str)

    # Step 6: Submit Schedule
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
            ex_str = str(ex)
            # If the error is an unrecoverable navigation/login/URL error, don't blindly retry
            if any(k in ex_str for k in ["Login", "login", "URL ไม่ถูกต้อง", "ไม่สามารถเปิดลิงก์", "Force Stop"]):
                raise ex
            if attempt < max_retries:
                log(f"[Meta Auto Post Script] 🔄 Refreshing composer page and restarting flow in 2s...")
                try:
                    ensure_active_window(driver, target_url=composer_url)
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
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """Runs a batch of scheduled posts through the fast script engine with random anti-bot delays."""
    bot = browser_manager.get()
    driver = bot.driver
    total = len(posts)

    composer_url = target_url.strip() if target_url else ""
    if not composer_url:
        raise ValueError("กรุณาระบุ URL ของเพจ/Composer ใน Preset หรือช่อง URL ก่อนเริ่มทำงาน")

    errors = []
    success_count = 0
    reset_meta_stop()

    log(f"[Meta Auto Post Script Engine] Starting batch of {total} posts on 9222 (Random delay between posts: {delay_min}s - {delay_max}s)...")

    for idx, post in enumerate(posts):
        if is_meta_stopped():
            log("[Meta Auto Post] 🛑 ยกเลิกการโพสต์รายการที่เหลือเนื่องจากคำสั่ง Force Stop")
            errors.append("🛑 การทำงานถูกยกเลิกด้วย Force Stop")
            break

        # Random anti-bot delay before starting next round (from 2nd post onwards)
        if idx > 0 and (delay_max > 0 or delay_min > 0):
            actual_min = min(float(delay_min), float(delay_max))
            actual_max = max(float(delay_min), float(delay_max))
            rand_delay = round(random.uniform(actual_min, actual_max), 1)
            log(f"[Meta Auto Post] ⏳ สุ่มหน่วงเวลา {rand_delay} วินาที (สุ่มระหว่าง {actual_min}-{actual_max}s) ก่อนเริ่มโพสต์ที่ {idx + 1}/{total} เพื่อป้องกันบอท...")
            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total,
                    "percent": int((idx / max(total, 1)) * 100),
                    "message": f"⏳ สุ่มหน่วงเวลา {rand_delay}s ก่อนเริ่มโพสต์ที่ {idx + 1}/{total}..."
                })
            
            wait_start = time.time()
            while time.time() - wait_start < rand_delay:
                if is_meta_stopped():
                    log("[Meta Auto Post] 🛑 หยุดทำงานระหว่างหน่วงเวลาตามคำสั่ง Force Stop")
                    break
                time.sleep(0.3)

            if is_meta_stopped():
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
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
            err_str = str(e)
            if is_meta_stopped() or "Force Stop" in err_str:
                log("[Meta Auto Post] 🛑 หยุดทำงานทันทีตามคำสั่ง Force Stop")
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break

            err_msg = f"[{idx+1}/{total}] {post.get('subfolder_name', 'Item')}: {err_str}"
            log(f"[Meta Auto Post Script Item Error] {err_msg}")
            errors.append(err_msg)

            # CRITICAL CHECK: If fatal error (cannot open link, not logged in, window/driver dead, composer failed to load),
            # ABORT ENTIRE BATCH IMMEDIATELY to avoid futile loop of failing all remaining queue items.
            is_fatal = any(k in err_str for k in [
                "ไม่สามารถเปิดลิงก์", "Login", "login", "URL ไม่ถูกต้อง",
                "no such window", "web view not found", "connection refused",
                "Session info", "target window already closed", "not reachable",
                "ไม่พร้อมทำงานภายในเวลา"
            ])
            if is_fatal:
                fatal_msg = f"🛑 หยุดกระบวนการทั้งหมดทันทีเนื่องจาก: {err_str}"
                log(f"[Meta Auto Post Fatal] {fatal_msg}")
                errors.append(fatal_msg)
                break

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
