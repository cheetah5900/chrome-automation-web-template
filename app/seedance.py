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

def find_image_in_folder(folder_path: str, prefer_number: Optional[int] = None) -> tuple[Optional[str], Optional[str]]:
    """Finds an image file in folder_path.
    Returns (filename, filepath) or (None, None).
    """
    valid_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif'}
    if not os.path.isdir(folder_path):
        return None, None
    
    candidates = []
    for fname in sorted(os.listdir(folder_path)):
        if fname.startswith('.'):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in valid_exts:
            candidates.append(fname)
            
    if not candidates:
        return None, None
        
    # 1. Match subfolder number (e.g. '01.png', '1.png', '1_cover.png')
    if prefer_number is not None:
        num_str = str(prefer_number)
        num_pad = f"{prefer_number:02d}"
        for c in candidates:
            c_base = os.path.splitext(c)[0].lower()
            if c_base == num_str or c_base == num_pad or c_base.startswith(f"{num_str}_") or c_base.startswith(f"{num_pad}_"):
                return c, os.path.join(folder_path, c)
                
    # 2. Match keywords: 'storyboard', 'image', 'ref', 'char', 'cover', 'start'
    for kw in ['storyboard', 'ref', 'image', 'char', 'start', 'cover']:
        for c in candidates:
            if kw in c.lower():
                return c, os.path.join(folder_path, c)
                
    # 3. Fallback: first candidate alphabetically
    return candidates[0], os.path.join(folder_path, candidates[0])

def clear_seedance_image(driver) -> bool:
    """Removes any currently attached reference image from Dreamina."""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.by import By

        # Loop up to 4 attempts in case multiple images exist or hover takes a beat
        for attempt in range(4):
            # 1. Check if there are any attached reference images in composer
            has_img = driver.execute_script("""
                const refs = document.querySelector('[data-content-generator-references="true"]');
                if (!refs) return false;
                return refs.querySelectorAll('img').length > 0;
            """)
            if not has_img:
                if attempt == 0:
                    log("[Seedance] ไม่พบรูปภาพอ้างอิงที่ต้องลบบน Dreamina")
                else:
                    log("[Seedance] 🗑️ นำรูปภาพอ้างอิงเดิมออกเรียบร้อยแล้ว")
                return True

            # 2. Try direct click if remove button is already rendered
            clicked = driver.execute_script("""
                const refs = document.querySelector('[data-content-generator-references="true"]');
                if (!refs) return false;
                const btn = refs.querySelector('[data-reference-remove-button="true"]') ||
                            refs.querySelector('.remove-button-f7uCBH') ||
                            refs.querySelector('div[class*="remove-button"]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            """)

            # 3. If button wasn't already rendered, hover over the specific reference item containing an image
            if not clicked:
                try:
                    target_elem = driver.execute_script("""
                        const refs = document.querySelector('[data-content-generator-references="true"]');
                        if (!refs) return null;
                        const img = refs.querySelector('img');
                        if (img) {
                            return img.closest('div[data-index]') ||
                                   img.closest('.reference-item-ZGVyJs') ||
                                   img.closest('.reference-a5qJDc') ||
                                   img;
                        }
                        const items = refs.querySelectorAll('div[data-index]');
                        for (const item of items) {
                            if (!item.querySelector('input[type="file"]')) return item;
                        }
                        return null;
                    """)

                    if target_elem:
                        ActionChains(driver).move_to_element(target_elem).perform()
                        time.sleep(0.3)

                        # Click remove button via JS
                        clicked = driver.execute_script("""
                            const refs = document.querySelector('[data-content-generator-references="true"]');
                            if (!refs) return false;
                            const btn = refs.querySelector('[data-reference-remove-button="true"]') ||
                                        refs.querySelector('.remove-button-f7uCBH') ||
                                        refs.querySelector('div[class*="remove-button"]');
                            if (btn) {
                                btn.click();
                                return true;
                            }
                            return false;
                        """)

                        if not clicked:
                            # Fallback to Selenium click if element is present
                            btns = driver.find_elements(By.CSS_SELECTOR,
                                '[data-content-generator-references="true"] [data-reference-remove-button="true"], '
                                '[data-content-generator-references="true"] .remove-button-f7uCBH'
                            )
                            if btns:
                                btns[0].click()
                                clicked = True
                except Exception as hover_err:
                    log(f"[Seedance] Warning on hover remove button: {hover_err}")

            time.sleep(0.4)

        # Final verification
        still_has_img = driver.execute_script("""
            const refs = document.querySelector('[data-content-generator-references="true"]');
            if (!refs) return false;
            return refs.querySelectorAll('img').length > 0;
        """)

        if not still_has_img:
            log("[Seedance] 🗑️ นำรูปภาพอ้างอิงเดิมออกเรียบร้อยแล้ว")
            return True
        else:
            log("[Seedance] ⚠️ รูปภาพอ้างอิงยังไม่ถูกลบออก")
            return False

    except Exception as e:
        log(f"[Seedance] ⚠️ ข้อผิดพลาดขณะลบรูปภาพ: {e}")
        return False

def clear_seedance_prompt(driver) -> bool:
    """Clears prompt text from ProseMirror editor on Dreamina."""
    try:
        cleared = driver.execute_script("""
        const editor = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]') ||
                       document.querySelector('div.tiptap.ProseMirror');
        if (editor) {
            // 1. TipTap API
            if (editor.editor && typeof editor.editor.commands?.setContent === 'function') {
                editor.editor.commands.setContent('');
            } else if (editor.editor && typeof editor.editor.commands?.clearContent === 'function') {
                editor.editor.commands.clearContent();
            }

            // 2. ProseMirror internal view transaction
            if (editor.pmViewDesc && editor.pmViewDesc.view) {
                try {
                    const view = editor.pmViewDesc.view;
                    const tr = view.state.tr;
                    tr.delete(0, view.state.doc.content.size);
                    view.dispatch(tr);
                } catch(e) {}
            }

            // 3. Selection delete
            editor.focus();
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(editor);
            sel.removeAllRanges();
            sel.addRange(range);
            document.execCommand('delete', false, null);

            // 4. Force empty paragraph if text still remains
            if (editor.innerText && editor.innerText.trim() !== '') {
                editor.innerHTML = '<p></p>';
            }

            editor.dispatchEvent(new Event('input', { bubbles: true }));
            editor.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        return false;
        """)
        time.sleep(0.3)
        if cleared:
            log("[Seedance] 🗑️ ลบข้อความ Prompt บน Dreamina เรียบร้อยแล้ว")
        return bool(cleared)
    except Exception as e:
        log(f"[Seedance] ⚠️ ข้อผิดพลาดขณะเคลียร์ Prompt: {e}")
        return False

def clear_seedance_image_and_prompt(driver) -> dict[str, bool]:
    """Clears both reference image and prompt text on Dreamina."""
    img_cleared = clear_seedance_image(driver)
    prompt_cleared = clear_seedance_prompt(driver)
    return {"image_cleared": img_cleared, "prompt_cleared": prompt_cleared}

def set_seedance_image(driver, image_path: str) -> bool:
    """Uploads/attaches an image to Dreamina via the hidden file input."""
    if not image_path or not os.path.isfile(image_path):
        raise ValueError(f"ไม่พบไฟล์รูปภาพ: {image_path}")

    log(f"[Seedance] 🖼️ กำลังแนบรูปภาพ: {os.path.basename(image_path)}...")

    # Clear existing image if any first
    clear_seedance_image(driver)

    # Locate input[type="file"]
    file_inp = fast_poll(driver, """
        return document.querySelector('[data-content-generator-references="true"] input[type="file"]') ||
               document.querySelector('input.file-input-AykBQ0') ||
               document.querySelector('.reference-upload-goGAYf input[type="file"]') ||
               document.querySelector('input[type="file"][accept*="image"]');
    """, timeout=8.0, poll_interval=0.2)

    if not file_inp:
        raise RuntimeError("ไม่พบช่องอัปโหลดรูปภาพ (input[type=file]) บนหน้าเว็บ Dreamina")

    file_inp.send_keys(os.path.abspath(image_path))
    time.sleep(0.8)

    # Verify upload thumbnail
    uploaded = fast_poll(driver, """
        const refs = document.querySelector('[data-content-generator-references="true"]');
        if (!refs) return null;
        const img = refs.querySelector('img');
        return (img && img.complete && img.naturalWidth > 0) ? img : null;
    """, timeout=8.0, poll_interval=0.3)

    if not uploaded:
        log("[Seedance] ⚠️ ตรวจไม่พบ thumbnail รูปภาพหลัง send_keys")
        return False

    log(f"[Seedance] ✅ แนบรูปภาพ {os.path.basename(image_path)} บน Dreamina สำเร็จ")
    time.sleep(0.3)
    return True

def scan_seedance_folders(
    main_folder: str,
    subfolders_str: str = "",
    image_mode: str = "none",
    character_sheet_path: str = ""
) -> dict[str, Any]:
    """
    Scans main folder, filters subfolders by numbers/ranges,
    and locates markdown prompt files containing 'prompt' (case-insensitive) in filename.
    Also detects images based on image_mode: 'subfolder', 'character_sheet', or 'none'.
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
        num = extract_leading_number(sub_name)

        # 1. Find markdown file with 'prompt' in name
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

        # 2. Image Detection based on image_mode
        image_file = None
        image_path = None
        has_image = False

        if image_mode == "subfolder":
            img_fname, img_fpath = find_image_in_folder(sub_path, prefer_number=num)
            if img_fname and img_fpath:
                image_file = img_fname
                image_path = img_fpath
                has_image = True
        elif image_mode == "character_sheet":
            if character_sheet_path and os.path.isfile(character_sheet_path):
                image_file = os.path.basename(character_sheet_path)
                image_path = character_sheet_path
                has_image = True
        # If "none", image_file and image_path remain None / empty

        items.append({
            "id": idx,
            "checked": True if (prompt_file and prompt_text) else False,
            "subfolder_name": sub_name,
            "subfolder_path": sub_path,
            "prompt_file": prompt_file or "ไม่พบไฟล์ prompt (.md)",
            "prompt_path": prompt_path or "",
            "prompt_text": prompt_text,
            "has_prompt": bool(prompt_file and prompt_text),
            "image_mode": image_mode,
            "image_file": image_file or "",
            "image_path": image_path or "",
            "has_image": has_image,
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

    # Open ratio popover if not open
    opened = driver.execute_script("""
    const btn = Array.from(document.querySelectorAll('.toolbar-button-EJ0kAg, button')).find(b => {
        const t = (b.innerText || '');
        return t.includes('16:9') || t.includes('9:16') || t.includes('1:1') || t.includes('3:4') || t.includes('4:3') || t.includes('21:9');
    });
    if (btn) {
        if (!btn.classList.contains('lv-popover-open')) {
            btn.click();
        }
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
    const labels = Array.from(document.querySelectorAll('.lv-popover-content label, label.lv-radio, input[type="radio"], [role="radiogroup"] label'));
    for (const el of labels) {
        const t = (el.innerText || '').trim();
        if (t === target || el.value === target) {
            (el.tagName === 'INPUT' ? el.closest('label') || el : el).click();
            return true;
        }
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

    # Open duration popover if not open
    opened = driver.execute_script("""
    const btn = Array.from(document.querySelectorAll('.toolbar-button-EJ0kAg, button')).find(b => {
        const t = (b.innerText || '').trim();
        return t === '5s' || t === '10s' || t === '15s' || t.endsWith('s');
    });
    if (btn) {
        if (!btn.classList.contains('lv-popover-open')) {
            btn.click();
        }
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
    const tickBtns = Array.from(document.querySelectorAll('.tick-button-T1cxZR, .lv-popover-content button'));
    for (const b of tickBtns) {
        if ((b.innerText || '').trim() === targetSec) {
            b.click();
            return true;
        }
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
    """Inserts prompt text into ProseMirror editor cleanly without duplicates."""
    if not prompt_text or not prompt_text.strip():
        raise ValueError("ข้อความ Prompt ว่างเปล่า")

    clean_prompt = prompt_text.strip()
    log(f"[Seedance] กำลังวาง Prompt ({len(clean_prompt)} ตัวอักษร)...")

    # Locate editor
    editor = fast_poll(driver, """
        return document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
    """, timeout=10.0, poll_interval=0.2)

    if not editor:
        raise RuntimeError("ไม่พบกล่องข้อความ Prompt (ProseMirror Editor)")

    res = driver.execute_script("""
    const editor = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
    if (!editor) return false;

    // 1. Primary: Use native TipTap API if exposed on the DOM element
    if (editor.editor && typeof editor.editor.commands?.setContent === 'function') {
        editor.editor.commands.setContent(arguments[0]);
    } else {
        // 2. Fallback: Select all node contents across all paragraphs, delete, and insert text
        editor.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, arguments[0]);
    }
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    editor.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
    """, clean_prompt)

    time.sleep(0.4)
    log(f"[Seedance] ✅ วางข้อความ Prompt สำเร็จ ({len(clean_prompt)} ตัวอักษร)")
    return bool(res)

def click_seedance_generate(driver, timeout: float = 6.0) -> bool:
    """Clicks the active Generate/Submit button on Dreamina, avoiding collapsed dummy buttons."""
    time.sleep(0.5)  # Allow React state to enable button
    start_t = time.time()
    while time.time() - start_t < timeout:
        res = driver.execute_script("""
        const buttons = Array.from(document.querySelectorAll('button[class*="submit-button"], button.submit-button-IG_OEx'));
        const activeBtn = buttons.find(b => {
            const cls = b.className || '';
            const isDisabled = b.disabled || b.classList.contains('lv-btn-disabled') || b.getAttribute('aria-disabled') === 'true';
            const isCollapsed = cls.includes('collapsed');
            const rect = b.getBoundingClientRect();
            return !isDisabled && !isCollapsed && rect.width > 0 && rect.height > 0;
        });

        if (activeBtn) {
            activeBtn.scrollIntoView({ block: 'nearest' });
            activeBtn.click();
            return true;
        }
        return false;
        """)

        if res:
            log("[Seedance] ✅ กดปุ่ม Generate บน Dreamina สำเร็จ")
            return True
        time.sleep(0.3)

    # Fallback with Selenium element click
    real_btn = fast_poll(driver, """
        return document.querySelector('button.submit-button-IG_OEx:not([disabled]):not(.lv-btn-disabled)') ||
               document.querySelector('button[class*="submit-button"]:not([class*="collapsed"]):not([disabled]):not(.lv-btn-disabled)');
    """, timeout=2.0)
    if real_btn:
        real_btn.click()
        log("[Seedance] ✅ กดปุ่ม Generate สำเร็จ (Fallback)")
        return True

    raise RuntimeError("ไม่สามารถกดปุ่ม Generate ได้ (ปุ่มยังคง Disabled หรือไม่พบปุ่ม Generate ที่พร้อมใช้งาน)")

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
    prompt_text: Optional[str] = None,
    image_path: Optional[str] = None,
    clear_image: bool = False,
    clear_mode: str = "both",
    click_generate: bool = False
) -> dict[str, Any]:
    """Applies generation settings (prompt, image) to Dreamina and optionally clicks generate."""
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

    # 1. Handle Image based on clear_mode
    if clear_mode in ("both", "image"):
        if image_path and os.path.isfile(image_path):
            results["image"] = set_seedance_image(driver, image_path)
        elif clear_image or clear_mode == "image":
            results["image"] = clear_seedance_image(driver)
    else:
        # clear_mode == "prompt" -> Do NOT clear image on Dreamina
        if image_path and os.path.isfile(image_path):
            results["image"] = set_seedance_image(driver, image_path)

    # 2. Handle Prompt based on clear_mode
    if prompt_text and prompt_text.strip():
        results["prompt"] = set_seedance_prompt(driver, prompt_text)
    elif clear_mode in ("both", "prompt"):
        results["prompt"] = clear_seedance_prompt(driver)

    # 3. Click Generate if requested
    if click_generate:
        results["generate"] = click_seedance_generate(driver)

        # 4. Post-Generate Clearing (ล้างข้อมูลหลังกดสั่งงานและกดส่งเรียบร้อยแล้ว)
        time.sleep(1.2)
        if clear_mode in ("both", "prompt"):
            log("[Seedance] 🧹 กำลังล้างข้อความ Prompt หลังกดส่งตาม Clear Mode...")
            results["post_clear_prompt"] = clear_seedance_prompt(driver)
        if clear_mode in ("both", "image"):
            log("[Seedance] 🧹 กำลังล้างรูปภาพอ้างอิงหลังกดส่งตาม Clear Mode...")
            results["post_clear_image"] = clear_seedance_image(driver)

    return results

def run_seedance_batch(
    items: list[dict[str, Any]],
    model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    duration: Optional[int] = None,
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    click_generate: bool = False,
    image_mode: str = "none",
    character_sheet_path: str = "",
    clear_mode: str = "both",
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """
    Runs a batch of Seedance prompt submissions.
    If click_generate is False, only sets the prompt and image without submitting.
    """
    bot = browser_manager.get()
    if not bot or not bot.driver:
        raise RuntimeError("เบราว์เซอร์ Chrome 9222 ไม่ได้เปิดใช้งาน")

    driver = bot.driver
    total = len(items)
    errors = []
    success_count = 0
    reset_seedance_stop()

    model_desc = model or "คงเดิม"
    ratio_desc = aspect_ratio or "คงเดิม"
    dur_desc = f"{duration}s" if duration else "คงเดิม"
    log(f"[Seedance Engine] เริ่มกระบวนการ Seedance Batch จำนวน {total} รายการ (Model: {model_desc}, Ratio: {ratio_desc}, Duration: {dur_desc}, Image Mode: {image_mode}, Clear Mode: {clear_mode}, Submit: {click_generate})...")

    # Switch to Dreamina tab
    ensure_seedance_tab(bot)

    # 1. Apply global settings upfront before item loop
    try:
        if model:
            set_seedance_model(driver, model)
        if aspect_ratio:
            set_seedance_aspect_ratio(driver, aspect_ratio)
        if duration and duration > 0:
            set_seedance_duration(driver, duration)
    except Exception as setup_err:
        log(f"[Seedance Setup Warning] {setup_err}")

    # For character sheet mode, check if global character sheet path exists
    char_sheet_valid = character_sheet_path and os.path.isfile(character_sheet_path)
    if image_mode == "character_sheet" and not char_sheet_valid:
        log(f"[Seedance Warning] ⚠️ ไม่พบไฟล์ Character Sheet: {character_sheet_path}")

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
            item_mode = image_mode or item.get("image_mode", "none")
            item_img = item.get("image_path")
            log(f"[Seedance] 🎬 กำลังประมวลผล [{idx+1}/{total}] โฟลเดอร์: {sub_name} (Image Mode: {item_mode}, Clear: {clear_mode})...")

            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total,
                    "percent": int((idx / max(total, 1)) * 100),
                    "message": f"[{idx+1}/{total}] กำลังตั้งค่าและวางข้อมูลสำหรับ {sub_name}..."
                })

            # 1. Handle Image Attachment based on mode and clear_mode
            if clear_mode in ("both", "image"):
                if item_mode == "subfolder":
                    if item_img and os.path.isfile(item_img):
                        log(f"[Seedance] 🖼️ กำลังแนบรูปภาพประจำโฟลเดอร์: {os.path.basename(item_img)}")
                        set_seedance_image(driver, item_img)
                    else:
                        log(f"[Seedance] ℹ️ โฟลเดอร์ {sub_name} ไม่มีไฟล์รูปภาพ -> ลบรูปอ้างอิงเดิม (ถ้ามี)")
                        clear_seedance_image(driver)
                elif item_mode == "character_sheet":
                    target_char_img = character_sheet_path or item_img
                    if target_char_img and os.path.isfile(target_char_img):
                        has_img = driver.execute_script("""
                            const refs = document.querySelector('[data-content-generator-references="true"]');
                            return !!(refs && refs.querySelector('img'));
                        """)
                        if not has_img:
                            log(f"[Seedance] 👤 แนบรูป Character Sheet: {os.path.basename(target_char_img)}")
                            set_seedance_image(driver, target_char_img)
                    else:
                        clear_seedance_image(driver)
                elif item_mode == "none":
                    clear_seedance_image(driver)
            else:
                # clear_mode == "prompt" -> Do NOT clear existing image on Dreamina!
                if item_mode == "subfolder" and item_img and os.path.isfile(item_img):
                    set_seedance_image(driver, item_img)
                elif item_mode == "character_sheet":
                    target_char_img = character_sheet_path or item_img
                    if target_char_img and os.path.isfile(target_char_img):
                        has_img = driver.execute_script("""
                            const refs = document.querySelector('[data-content-generator-references="true"]');
                            return !!(refs && refs.querySelector('img'));
                        """)
                        if not has_img:
                            set_seedance_image(driver, target_char_img)
                else:
                    log("[Seedance] ℹ️ ข้ามการลบรูปภาพตาม Clear Mode: ล้างเฉพาะ Prompt (คงรูปเดิมไว้)")

            # 2. Handle Prompt based on clear_mode
            if prompt_text and prompt_text.strip():
                set_seedance_prompt(driver, prompt_text)
            elif clear_mode in ("both", "prompt"):
                clear_seedance_prompt(driver)

            # Click generate IF AND ONLY IF explicitly requested
            if click_generate:
                log(f"[Seedance] 🚀 กำลังกดปุ่ม Generate สำหรับ {sub_name}...")
                click_seedance_generate(driver)

                # Post-Generate Clearing (ล้างข้อมูลหลังกดสั่งงานและกดส่งเรียบร้อยแล้ว)
                time.sleep(1.2)
                if clear_mode in ("both", "prompt"):
                    log(f"[Seedance] 🧹 ล้างข้อความ Prompt หลังส่งสำเร็จ ({sub_name})")
                    clear_seedance_prompt(driver)
                if clear_mode in ("both", "image"):
                    log(f"[Seedance] 🧹 ล้างรูปภาพหลังส่งสำเร็จ ({sub_name})")
                    clear_seedance_image(driver)
            else:
                log(f"[Seedance] 🛡️ โหมด Safe: ตั้งค่าและวาง Prompt/รูปภาพ เรียบร้อยแล้ว (ไม่กด Generate ตามคำสั่ง)")

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
