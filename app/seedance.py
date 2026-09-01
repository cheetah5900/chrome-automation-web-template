import os
import sys
import re
import time
import random
import subprocess
from typing import Any, Callable, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from app.browser import browser_manager

_seedance_stop_requested = False

def request_seedance_stop() -> None:
    global _seedance_stop_requested
    _seedance_stop_requested = True
    log("[Seedance] 🛑 ผู้ใช้สั่ง Force Stop การทำงาน")

def reset_seedance_stop() -> None:
    global _seedance_stop_requested
    _seedance_stop_requested = False

def is_seedance_stopped() -> bool:
    return _seedance_stop_requested

def log(msg: str) -> None:
    print(msg)
    try:
        from app.main import log_bus
        log_bus.publish(msg)
    except Exception:
        pass

def parse_range_string(range_str: str) -> list[int]:
    """Parses range strings like '1-10, 15, 20-25' into a list of ints."""
    if not range_str or not range_str.strip():
        return []
    result = set()
    parts = [p.strip() for p in range_str.split(',') if p.strip()]
    for part in parts:
        if '-' in part:
            sub = part.split('-')
            if len(sub) == 2 and sub[0].strip().isdigit() and sub[1].strip().isdigit():
                start, end = int(sub[0].strip()), int(sub[1].strip())
                for num in range(min(start, end), max(start, end) + 1):
                    result.add(num)
        elif part.isdigit():
            result.add(int(part))
    return sorted(list(result))

def extract_leading_number(folder_name: str) -> Optional[int]:
    """Extracts leading number from folder name like '01_intro' -> 1, '15' -> 15."""
    match = re.match(r'^(\d+)', folder_name.strip())
    if match:
        return int(match.group(1))
    return None

def scan_seedance_folders(main_folder: str, subfolders_str: str = "") -> dict[str, Any]:
    """
    Scans main folder, filters subfolders by numbers/ranges,
    and locates markdown prompt files containing 'prompt' (case-insensitive) in filename.
    """
    if not main_folder or not os.path.isdir(main_folder):
        raise ValueError(f"ไม่พบโฟลเดอร์หลัก: {main_folder}")

    target_numbers = parse_range_string(subfolders_str)
    all_subdirs = []

    for entry in sorted(os.listdir(main_folder)):
        full_path = os.path.join(main_folder, entry)
        if os.path.isdir(full_path) and not entry.startswith('.'):
            num = extract_leading_number(entry)
            if target_numbers:
                if num is not None and num in target_numbers:
                    all_subdirs.append((num, entry, full_path))
            else:
                all_subdirs.append((num if num is not None else 999999, entry, full_path))

    # Sort numerically by leading number then name
    all_subdirs.sort(key=lambda x: (x[0] is None, x[0], x[1]))

    items = []
    for idx, (_, sub_name, sub_path) in enumerate(all_subdirs, 1):
        # Find markdown file with 'prompt' in name
        prompt_file = None
        prompt_path = None
        prompt_text = ""

        for fname in sorted(os.listdir(sub_path)):
            if fname.startswith('.'):
                continue
            fname_lower = fname.lower()
            if (fname_lower.endswith('.md') or fname_lower.endswith('.txt') or fname_lower.endswith('.markdown')) and 'prompt' in fname_lower:
                prompt_file = fname
                prompt_path = os.path.join(sub_path, fname)
                try:
                    with open(prompt_path, 'r', encoding='utf-8', errors='ignore') as f:
                        prompt_text = f.read().strip()
                except Exception as ex:
                    log(f"[Seedance Scan] Warning: Cannot read {prompt_path}: {ex}")
                break

        # Fallback: any .md file if none matched 'prompt'
        if not prompt_file:
            for fname in sorted(os.listdir(sub_path)):
                if fname.lower().endswith('.md') and not fname.startswith('.'):
                    prompt_file = fname
                    prompt_path = os.path.join(sub_path, fname)
                    try:
                        with open(prompt_path, 'r', encoding='utf-8', errors='ignore') as f:
                            prompt_text = f.read().strip()
                    except Exception:
                        pass
                    break

        items.append({
            "id": idx,
            "checked": True if (prompt_file and prompt_text) else False,
            "subfolder_name": sub_name,
            "subfolder_path": sub_path,
            "prompt_file": prompt_file or "ไม่พบไฟล์ prompt (.md)",
            "prompt_path": prompt_path or "",
            "prompt_text": prompt_text,
            "has_prompt": bool(prompt_file and prompt_text),
            "status": "ready" if (prompt_file and prompt_text) else "warning"
        })

    return {
        "ok": True,
        "total": len(items),
        "valid_count": sum(1 for i in items if i["has_prompt"]),
        "items": items
    }

def fast_poll(driver, js_condition: str, timeout: float = 15.0, poll_interval: float = 0.2):
    """Executes a JS condition repeatedly until it returns a truthy value or timeout expires."""
    start = time.time()
    while time.time() - start < timeout:
        if is_seedance_stopped():
            raise RuntimeError("🛑 Force Stop: ผู้ใช้สั่งหยุดการทำงาน")
        try:
            res = driver.execute_script(js_condition)
            if res:
                return res
        except Exception:
            pass
        time.sleep(poll_interval)
    return None

def set_seedance_model(driver, model_key: str = "fast") -> str:
    """Selects model on Dreamina: 'mini', 'fast', '2.0', '2.5'."""
    key = (model_key or "fast").lower().strip()
    log(f"[Seedance] กำลังตั้งค่าโมเดลเป็น '{model_key}'...")

    # Open model dropdown
    opened = driver.execute_script("""
    const select = Array.from(document.querySelectorAll('.lv-select')).find(el => {
        const t = (el.innerText || '');
        return t.includes('Seedance') || t.includes('Dreamina') || t.includes('Fast') || t.includes('Mini') || t.includes('2.0') || t.includes('2.5');
    });
    if (select) {
        select.click();
        return true;
    }
    return false;
    """)
    if not opened:
        raise RuntimeError("ไม่พบเมนูเลือกโมเดล (Model Selector) บนหน้าเว็บ Dreamina")
    time.sleep(0.4)

    # Click target model
    selected = driver.execute_script("""
    const key = arguments[0];
    const opts = Array.from(document.querySelectorAll('.lv-select-option, [role="option"]'));
    const matched = opts.find(o => {
        const t = (o.querySelector('.option-label-jKuNta')?.innerText || o.innerText || '').toLowerCase().trim();
        if (key === 'mini') {
            return t === 'dreamina seedance 2.0 mini' || (t.includes('seedance') && t.includes('mini'));
        }
        if (key === 'fast') {
            return t === 'dreamina seedance 2.0 fast' || (t.includes('seedance') && t.includes('fast') && !t.includes('1.0'));
        }
        if (key === '2.0' || key === 'v2') {
            return t === 'dreamina seedance 2.0' || (t.includes('seedance 2.0') && !t.includes('mini') && !t.includes('fast'));
        }
        if (key === '2.5') {
            return t === 'dreamina seedance 2.5' || (t.includes('seedance 2.5'));
        }
        return t.includes(key);
    });
    if (matched) {
        matched.click();
        return (matched.querySelector('.option-label-jKuNta')?.innerText || matched.innerText || '').replace(/\\n+/g, ' | ');
    }
    return null;
    """, key)

    if not selected:
        driver.execute_script("document.body.click();")
        raise RuntimeError(f"ไม่พบตัวเลือกโมเดล '{model_key}' ในรายการ")

    log(f"[Seedance] ✅ เลือกโมเดลสำเร็จ: {selected}")
    time.sleep(0.4)
    return selected

def set_seedance_aspect_ratio(driver, ratio_target: str = "9:16") -> bool:
    """Selects aspect ratio: '9:16', '16:9', '1:1', '4:3', '3:4', '21:9'."""
    target = (ratio_target or "9:16").strip()
    log(f"[Seedance] กำลังตั้งค่าอัตราส่วนภาพเป็น '{target}'...")

    # Click ratio button
    opened = driver.execute_script("""
    const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = (b.innerText || '');
        return (t.includes('16:9') || t.includes('9:16') || t.includes('1:1') || t.includes('4:3') || t.includes('3:4') || t.includes('21:9')) && b.getBoundingClientRect().y > 1100;
    });
    if (btn) {
        btn.click();
        return true;
    }
    return false;
    """)
    if not opened:
        raise RuntimeError("ไม่พบปุ่มเลือกอัตราส่วน (Aspect Ratio Button)")
    time.sleep(0.4)

    # Click ratio in popover
    selected = driver.execute_script("""
    const target = arguments[0].trim();
    const radios = Array.from(document.querySelectorAll('.lv-radio, .radio-N0Z9nR, [role="radio"], label'));
    const matched = radios.find(el => (el.innerText || '').trim() === target);
    if (matched) {
        matched.click();
        return true;
    }
    return false;
    """, target)

    time.sleep(0.2)
    driver.execute_script("document.body.click();")
    if not selected:
        raise RuntimeError(f"ไม่พบตัวเลือกอัตราส่วน '{target}' ใน Popover")

    log(f"[Seedance] ✅ เลือกอัตราส่วนสำเร็จ: {target}")
    time.sleep(0.4)
    return True

def set_seedance_duration(driver, duration_seconds: int = 15) -> bool:
    """Selects duration: 5, 10, 15."""
    target_sec = str(duration_seconds or 15).strip()
    log(f"[Seedance] กำลังตั้งค่าระยะเวลาวิดีโอเป็น {target_sec}s...")

    # Click duration button
    opened = driver.execute_script("""
    const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = (b.innerText || '').trim();
        return (t === '5s' || t === '10s' || t === '15s' || t.match(/^\\d+s$/)) && b.getBoundingClientRect().y > 1100;
    });
    if (btn) {
        btn.click();
        return true;
    }
    return false;
    """)
    if not opened:
        raise RuntimeError("ไม่พบปุ่มเลือกระยะเวลา (Duration Button)")
    time.sleep(0.4)

    # Click duration tick or type number
    selected = driver.execute_script("""
    const targetSec = arguments[0];
    const tickBtns = Array.from(document.querySelectorAll('.tick-button-T1cxZR, button'));
    const matched = tickBtns.find(b => (b.innerText || '').trim() === targetSec);
    if (matched) {
        matched.click();
        return true;
    }
    const numInput = document.querySelector('.duration-input-sipuPP input, .duration-panel-kl0UWV input, .lv-input-number input');
    if (numInput) {
        numInput.focus();
        numInput.value = targetSec;
        numInput.dispatchEvent(new Event('input', { bubbles: true }));
        numInput.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }
    return false;
    """, target_sec)

    time.sleep(0.2)
    driver.execute_script("document.body.click();")
    if not selected:
        raise RuntimeError(f"ไม่สามารถเลือกตัวเลือกระยะเวลา {target_sec}s ได้")

    log(f"[Seedance] ✅ ตั้งค่าระยะเวลาสำเร็จ: {target_sec}s")
    time.sleep(0.4)
    return True

def set_seedance_prompt(driver, prompt_text: str) -> bool:
    """Inserts prompt text into ProseMirror editor with verification."""
    if not prompt_text or not prompt_text.strip():
        raise ValueError("ข้อความ Prompt ว่างเปล่า")

    clean_prompt = prompt_text.strip()
    log(f"[Seedance] กำลังวางข้อความ Prompt ({len(clean_prompt)} ตัวอักษร)...")

    # Locate editor
    editor = fast_poll(driver, """
        return document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
    """, timeout=10.0, poll_interval=0.2)

    if not editor:
        raise RuntimeError("ไม่พบกล่องข้อความ Prompt (ProseMirror Editor)")

    # Insert via execCommand / Lexical events
    driver.execute_script("""
    const editor = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
    if (editor) {
        editor.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, arguments[0]);
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
    }
    """, clean_prompt)

    time.sleep(0.4)

    # Verify content
    verified_text = driver.execute_script("""
    const editor = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
    return editor ? (editor.innerText || editor.textContent || '').trim() : '';
    """)

    if not verified_text:
        # Fallback via clipboard
        log("[Seedance] ⚠️ ยังไม่พบข้อความในกล่อง Prompt -> ลองวางด้วย Clipboard...")
        try:
            if sys.platform == "darwin":
                p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                p.communicate(input=clean_prompt.encode('utf-8'))
            ActionChains(driver).move_to_element(editor).click().pause(0.2).key_down(Keys.COMMAND).send_keys('v').key_up(Keys.COMMAND).pause(0.3).perform()
        except Exception as ex:
            log(f"[Seedance] Clipboard paste error: {ex}")

        time.sleep(0.4)
        verified_text = driver.execute_script("""
        const editor = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
        return editor ? (editor.innerText || editor.textContent || '').trim() : '';
        """)

    if not verified_text:
        raise RuntimeError("ไม่สามารถยืนยันข้อความ Prompt ในกล่องข้อความได้")

    log(f"[Seedance] ✅ วางข้อความ Prompt สำเร็จ ({len(verified_text)} ตัวอักษร)")
    return True

def ensure_seedance_tab(bot) -> bool:
    """Ensures Selenium driver is switched to the Dreamina / Seedance tab."""
    if not bot or not bot.driver:
        return False
    for url_part in ["dreamina.capcut.com", "dreamina", "workspace=0&type=video", "capcut.com/ai-tool"]:
        if bot.switch_to_tab_containing(url_part):
            return True
    return False

def apply_all_seedance_settings(
    driver,
    model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    duration: Optional[int] = None,
    prompt_text: Optional[str] = None
) -> dict[str, Any]:
    """Applies generation settings (model, ratio, duration, prompt) to Dreamina without clicking submit."""
    bot = browser_manager.get()
    if bot:
        ensure_seedance_tab(bot)

    results = {}
    if model:
        results["model"] = set_seedance_model(driver, model)
    if aspect_ratio:
        results["aspect_ratio"] = set_seedance_aspect_ratio(driver, aspect_ratio)
    if duration is not None and duration > 0:
        results["duration"] = set_seedance_duration(driver, duration)
    if prompt_text and prompt_text.strip():
        results["prompt"] = set_seedance_prompt(driver, prompt_text)
    return results

def run_seedance_batch(
    items: list[dict[str, Any]],
    model: str = "fast",
    aspect_ratio: str = "9:16",
    duration: int = 15,
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    click_generate: bool = False,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """
    Runs a batch of Seedance prompt submissions.
    If click_generate is False, only sets the model, ratio, duration, and prompt without submitting.
    """
    bot = browser_manager.get()
    if not bot or not bot.driver:
        raise RuntimeError("เบราว์เซอร์ Chrome 9222 ไม่ได้เปิดใช้งาน")

    driver = bot.driver
    total = len(items)
    errors = []
    success_count = 0
    reset_seedance_stop()

    log(f"[Seedance Engine] เริ่มกระบวนการ Seedance Batch จำนวน {total} รายการ (Model: {model}, Ratio: {aspect_ratio}, Duration: {duration}s, Submit: {click_generate})...")

    for idx, item in enumerate(items):
        if is_seedance_stopped():
            log("[Seedance] 🛑 ยกเลิกรายการที่เหลือเนื่องจากคำสั่ง Force Stop")
            errors.append("🛑 การทำงานถูกยกเลิกด้วย Force Stop")
            break

        # Random anti-bot delay between items
        if idx > 0 and (delay_max > 0 or delay_min > 0):
            actual_min = min(float(delay_min), float(delay_max))
            actual_max = max(float(delay_min), float(delay_max))
            rand_delay = round(random.uniform(actual_min, actual_max), 1)
            log(f"[Seedance] ⏳ สุ่มหน่วงเวลา {rand_delay} วินาที ก่อนเริ่มรายการที่ {idx + 1}/{total}...")
            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total,
                    "percent": int((idx / max(total, 1)) * 100),
                    "message": f"⏳ สุ่มหน่วงเวลา {rand_delay}s ก่อนเริ่มรายการถัดไป..."
                })

            wait_start = time.time()
            while time.time() - wait_start < rand_delay:
                if is_seedance_stopped():
                    break
                time.sleep(0.3)

            if is_seedance_stopped():
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break

        try:
            prompt_text = item.get("prompt_text", "")
            sub_name = item.get("subfolder_name", f"Item #{idx+1}")
            log(f"[Seedance] 🎬 กำลังประมวลผล [{idx+1}/{total}] โฟลเดอร์: {sub_name}...")

            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total,
                    "percent": int((idx / max(total, 1)) * 100),
                    "message": f"[{idx+1}/{total}] กำลังตั้งค่าและวาง Prompt สำหรับ {sub_name}..."
                })

            # 1. Set model
            set_seedance_model(driver, model)

            # 2. Set aspect ratio
            set_seedance_aspect_ratio(driver, aspect_ratio)

            # 3. Set duration
            set_seedance_duration(driver, duration)

            # 4. Insert prompt
            set_seedance_prompt(driver, prompt_text)

            # 5. Click generate IF AND ONLY IF explicitly requested
            if click_generate:
                log(f"[Seedance] 🚀 กำลังกดปุ่ม Generate สำหรับ {sub_name}...")
                gen_btn = fast_poll(driver, """
                    return document.querySelector('button.submit-button-g5Q97D, button[class*="submit-button"]:not([disabled])');
                """, timeout=5.0)
                if gen_btn:
                    gen_btn.click()
                    log(f"[Seedance] ✅ กดปุ่ม Generate สำเร็จสำหรับ {sub_name}")
                else:
                    raise RuntimeError("ไม่พบปุ่ม Generate หรือปุ่มถูกปิดการใช้งาน")
            else:
                log(f"[Seedance] 🛡️ โหมด Safe: ตั้งค่าและวาง Prompt เรียบร้อยแล้ว (ไม่กด Generate ตามคำสั่ง)")

            success_count += 1

        except Exception as e:
            if is_seedance_stopped():
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break
            err_msg = f"[{idx+1}/{total}] {item.get('subfolder_name', 'Item')}: {str(e)}"
            log(f"[Seedance Item Error] {err_msg}")
            errors.append(err_msg)

    if progress_callback:
        progress_callback({
            "current": total,
            "total": total,
            "percent": 100,
            "status": "completed" if not errors else "completed_with_errors",
            "message": f"✅ ดำเนินการสำเร็จ {success_count}/{total} รายการ" if not errors else f"เสร็จสิ้น {success_count}/{total} (พบข้อผิดพลาด {len(errors)} รายการ)",
            "errors": errors
        })

    return {
        "ok": len(errors) == 0,
        "total": total,
        "success_count": success_count,
        "errors": errors
    }
