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

def find_all_images_in_folder(
    folder_path: str,
    subfolder_name: str = "images"
) -> list[tuple[str, str]]:
    """
    Finds all image files in folder_path.
    If subfolder_name is provided and exists inside folder_path (e.g. 'images'),
    searches inside that subfolder first.
    Returns list of (filename, filepath) sorted naturally.
    """
    valid_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif'}
    if not os.path.isdir(folder_path):
        return []

    target_dir = folder_path
    if subfolder_name and subfolder_name.strip():
        clean_name = subfolder_name.strip().strip('/')
        sub_dir = os.path.join(folder_path, clean_name)
        if os.path.isdir(sub_dir):
            target_dir = sub_dir
        else:
            # Case-insensitive match for subfolder
            for entry in os.listdir(folder_path):
                if entry.lower() == clean_name.lower() and os.path.isdir(os.path.join(folder_path, entry)):
                    target_dir = os.path.join(folder_path, entry)
                    break

    candidates = []
    if os.path.isdir(target_dir):
        for fname in sorted(os.listdir(target_dir)):
            if fname.startswith('.'):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in valid_exts:
                candidates.append((fname, os.path.join(target_dir, fname)))

    # Fallback to parent folder if subfolder had no images and target_dir was a subfolder
    if not candidates and target_dir != folder_path and os.path.isdir(folder_path):
        for fname in sorted(os.listdir(folder_path)):
            if fname.startswith('.'):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in valid_exts:
                candidates.append((fname, os.path.join(folder_path, fname)))

    # Sort naturally by number if present (e.g. 1.png, 2.png, 10.png)
    def _sort_key(item):
        name = item[0]
        num = extract_leading_number(name)
        if num is not None:
            return (0, num, name)
        return (1, 0, name)

    candidates.sort(key=_sort_key)
    return candidates

def find_image_in_folder(
    folder_path: str,
    prefer_number: Optional[int] = None,
    subfolder_name: str = "images"
) -> tuple[Optional[str], Optional[str]]:
    """Finds an image file in folder_path or its images subfolder.
    Returns (filename, filepath) or (None, None).
    """
    all_imgs = find_all_images_in_folder(folder_path, subfolder_name)
    if not all_imgs:
        return None, None

    # 1. Match subfolder number (e.g. '01.png', '1.png', '1_cover.png')
    if prefer_number is not None:
        num_str = str(prefer_number)
        num_pad = f"{prefer_number:02d}"
        for fname, fpath in all_imgs:
            c_base = os.path.splitext(fname)[0].lower()
            if c_base == num_str or c_base == num_pad or c_base.startswith(f"{num_str}_") or c_base.startswith(f"{num_pad}_"):
                return fname, fpath

    # 2. Match keywords: 'storyboard', 'image', 'ref', 'char', 'cover', 'start'
    for kw in ['storyboard', 'ref', 'image', 'char', 'start', 'cover']:
        for fname, fpath in all_imgs:
            if kw in fname.lower():
                return fname, fpath

    # 3. Fallback: first candidate
    return all_imgs[0][0], all_imgs[0][1]

def clear_seedance_image(driver) -> bool:
    """Removes all currently attached reference images from Dreamina."""
    try:
        from selenium.webdriver.common.action_chains import ActionChains

        # Loop up to 15 attempts to ensure ALL images are deleted if multiple exist
        total_removed = 0
        for iteration in range(15):
            # Check how many images are currently attached in composer
            img_count = driver.execute_script("""
                const refs = document.querySelector('[data-content-generator-references="true"]');
                if (!refs) return 0;
                return refs.querySelectorAll('img').length;
            """)
            if img_count == 0:
                break

            # 1. Click any remove buttons that are already rendered in the DOM
            clicked_any = driver.execute_script("""
                const refs = document.querySelector('[data-content-generator-references="true"]');
                if (!refs) return 0;
                const btns = Array.from(refs.querySelectorAll('[data-reference-remove-button="true"], .remove-button-f7uCBH, div[class*="remove-button"], button[class*="remove"], [class*="delete"]'));
                let clicked = 0;
                for (const btn of btns) {
                    btn.click();
                    clicked++;
                }
                return clicked;
            """)

            if clicked_any > 0:
                total_removed += clicked_any
                time.sleep(0.4)
                continue

            # 2. If buttons are only visible on hover, hover over each reference item containing an img
            try:
                target_elems = driver.execute_script("""
                    const refs = document.querySelector('[data-content-generator-references="true"]');
                    if (!refs) return [];
                    const imgs = refs.querySelectorAll('img');
                    const targets = [];
                    for (const img of imgs) {
                        const container = img.closest('div[data-index]') ||
                                          img.closest('.reference-item-ZGVyJs') ||
                                          img.closest('.reference-a5qJDc') ||
                                          img.parentElement ||
                                          img;
                        if (container && !targets.includes(container)) {
                            targets.push(container);
                        }
                    }
                    return targets;
                """)

                for target in target_elems:
                    try:
                        ActionChains(driver).move_to_element(target).perform()
                        time.sleep(0.2)
                        driver.execute_script("""
                            const target = arguments[0];
                            let clicked = false;
                            if (target) {
                                const btn = target.querySelector('[data-reference-remove-button="true"], .remove-button-f7uCBH, div[class*="remove-button"], button[class*="remove"], [class*="delete"]');
                                if (btn) {
                                    btn.click();
                                    clicked = true;
                                }
                            }
                            if (!clicked) {
                                const refs = document.querySelector('[data-content-generator-references="true"]');
                                if (refs) {
                                    const btn = refs.querySelector('[data-reference-remove-button="true"], .remove-button-f7uCBH, div[class*="remove-button"], button[class*="remove"], [class*="delete"]');
                                    if (btn) btn.click();
                                }
                            }
                        """, target)
                        time.sleep(0.3)
                    except Exception:
                        pass
            except Exception as hover_err:
                log(f"[Seedance] Warning on hover remove button: {hover_err}")

            time.sleep(0.4)

        # Final verification
        remaining_count = driver.execute_script("""
            const refs = document.querySelector('[data-content-generator-references="true"]');
            if (!refs) return 0;
            return refs.querySelectorAll('img').length;
        """)

        if remaining_count == 0:
            if total_removed > 0:
                log(f"[Seedance] 🗑️ นำรูปภาพอ้างอิงทั้งหมด ({total_removed} รูป) ออกเรียบร้อยแล้ว")
            else:
                log("[Seedance] 🗑️ นำรูปภาพอ้างอิงเดิมออกเรียบร้อยแล้ว")
            return True
        else:
            log(f"[Seedance] ⚠️ ยังมีรูปภาพอ้างอิงเหลืออยู่ {remaining_count} รูปบน Dreamina")
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

def set_seedance_images(driver, image_paths: list[str]) -> bool:
    """Uploads/attaches multiple images to Dreamina via React handler, synthetic drop, or file input."""
    import base64
    import mimetypes

    valid_paths = [p for p in image_paths if p and os.path.isfile(p)]
    if not valid_paths:
        log("[Seedance] ⚠️ ไม่มีไฟล์รูปภาพที่ถูกต้องสำหรับอัปโหลด")
        return False

    log(f"[Seedance] 🖼️ กำลังแนบรูปภาพ {len(valid_paths)} รูป: {', '.join([os.path.basename(p) for p in valid_paths])}...")

    # Clear existing images if any first
    clear_seedance_image(driver)
    time.sleep(0.4)

    # Tier 1: Check if direct input[type="file"] is already present in DOM
    try:
        file_inp = driver.execute_script("""
            return document.querySelector('[data-content-generator-references="true"] input[type="file"]') ||
                   document.querySelector('input.file-input-AykBQ0') ||
                   document.querySelector('.reference-upload-goGAYf input[type="file"]') ||
                   document.querySelector('input[type="file"][accept*="image"]');
        """)
        if file_inp:
            for idx, img_path in enumerate(valid_paths):
                file_inp.send_keys(os.path.abspath(img_path))
                time.sleep(0.5)
            log(f"[Seedance] 📤 แนบไฟล์ผ่าน input[type=file] สำเร็จ {len(valid_paths)} รูป")
            return True
    except Exception as e:
        log(f"[Seedance] Direct file input check notice: {e}")

    # Tier 2 & 3: React Fiber onChange handler or synthetic onDrop
    payload = []
    for p in valid_paths:
        mime = mimetypes.guess_type(p)[0] or "image/jpeg"
        try:
            with open(p, "rb") as f:
                payload.append({
                    "name": os.path.basename(p),
                    "mime": mime,
                    "b64": base64.b64encode(f.read()).decode("utf-8")
                })
        except Exception as read_err:
            log(f"[Seedance] ⚠️ ไม่สามารถอ่านไฟล์รูป {os.path.basename(p)}: {read_err}")

    if not payload:
        return False

    res = driver.execute_script("""
        const payload = arguments[0];
        if (!payload || payload.length === 0) return { ok: false, error: "Empty payload" };

        // Convert base64 payload to File objects
        const files = payload.map(item => {
            const byteChars = atob(item.b64);
            const byteNumbers = new Array(byteChars.length);
            for (let i = 0; i < byteChars.length; i++) {
                byteNumbers[i] = byteChars.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const blob = new Blob([byteArray], { type: item.mime });
            return new File([blob], item.name, { type: item.mime, lastModified: Date.now() });
        });

        // Find visible reference upload button/container
        const visibleEl = Array.from(document.querySelectorAll(".reference-upload-goGAYf, div[class*=reference-upload]"))
                               .find(el => el.getBoundingClientRect().width > 0);
        if (!visibleEl) {
            return { ok: false, error: "ไม่พบปุ่มอัปโหลดรูปภาพบนหน้าเว็บ Dreamina" };
        }

        // Method A: React Fiber onChange handler (invokes videoGeneratorManager.importResourcesFromLocal)
        const fiberKey = Object.keys(visibleEl).find(k => k.startsWith("__reactFiber") || k.startsWith("__reactInternalInstance"));
        let f = visibleEl[fiberKey];
        let targetFn = null;
        while (f) {
            if (f.memoizedProps && typeof f.memoizedProps.onChange === "function") {
                targetFn = f.memoizedProps.onChange;
                break;
            }
            f = f.return;
        }

        if (targetFn) {
            try {
                targetFn(files);
                return { ok: true, method: "react_fiber_onChange", count: files.length };
            } catch (err) {
                console.warn("React fiber onChange error:", err);
            }
        }

        // Method B: Synthetic Drag & Drop Event
        const propsKey = Object.keys(visibleEl).find(k => k.startsWith("__reactProps"));
        if (propsKey && visibleEl[propsKey] && typeof visibleEl[propsKey].onDrop === "function") {
            try {
                const dt = new DataTransfer();
                for (const file of files) dt.items.add(file);
                const fakeEvent = {
                    preventDefault: () => {},
                    stopPropagation: () => {},
                    dataTransfer: dt
                };
                visibleEl[propsKey].onDrop(fakeEvent);
                return { ok: true, method: "react_props_onDrop", count: files.length };
            } catch (err) {
                console.warn("React props onDrop error:", err);
            }
        }

        // Method C: Native DOM drop dispatch
        try {
            const dt = new DataTransfer();
            for (const file of files) dt.items.add(file);
            const dropEvt = new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt });
            visibleEl.dispatchEvent(dropEvt);
            return { ok: true, method: "dom_dispatch_drop", count: files.length };
        } catch (err) {
            return { ok: false, error: err.message };
        }
    """, payload)

    if not res or not res.get("ok"):
        log(f"[Seedance] ⚠️ แนบรูปภาพไม่สำเร็จ: {res.get('error') if res else 'Unknown error'}")
        return False

    log(f"[Seedance] 📤 แนบไฟล์ผ่าน {res.get('method')} สำเร็จ {res.get('count')} รูป")
    time.sleep(0.8)

    # Verify upload thumbnail count
    img_count = driver.execute_script("""
        const refs = document.querySelectorAll("[data-content-generator-references=true] img, .reference-item-ZGVyJs img, img[class*=reference], img[class*=image-]");
        return Array.from(refs).filter(img => img.src && (img.src.startsWith("blob:") || img.src.includes("byteimg") || img.src.includes("dreamina"))).length;
    """)

    log(f"[Seedance] ✅ แนบรูปภาพสำเร็จ {len(valid_paths)} รูป (แสดงบนเว็บ {img_count} รูป)")
    return True

def set_seedance_image(driver, image_path: str) -> bool:
    """Uploads/attaches a single image to Dreamina."""
    if not image_path:
        return False
    return set_seedance_images(driver, [image_path])

def scan_seedance_folders(
    main_folder: str,
    subfolders_str: str = "",
    image_mode: str = "none",
    character_sheet_path: str = "",
    image_subfolder: str = "images"
) -> dict[str, Any]:
    """
    Scans main folder, filters subfolders by numbers/ranges,
    and locates markdown prompt files containing 'prompt' (case-insensitive) in filename.
    Also detects images based on image_mode: 'subfolder', 'character_sheet', or 'none'.
    In 'subfolder' mode, searches for images in the folder named image_subfolder (default: 'images').
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

        # 2. Image Detection: Always scan subfolder images so UI or batch mode can access them
        subfolder_imgs = find_all_images_in_folder(sub_path, subfolder_name=image_subfolder)
        subfolder_image_files = [item[0] for item in subfolder_imgs]
        subfolder_image_paths = [item[1] for item in subfolder_imgs]

        image_files = []
        image_paths = []
        image_file = None
        image_path = None
        has_image = False

        if image_mode == "subfolder":
            if subfolder_imgs:
                image_files = subfolder_image_files
                image_paths = subfolder_image_paths
                image_file = ", ".join(image_files) if len(image_files) <= 2 else f"{len(image_files)} รูป ({', '.join(image_files[:2])}...)"
                image_path = image_paths[0]
                has_image = True
        elif image_mode == "character_sheet":
            if character_sheet_path and os.path.isfile(character_sheet_path):
                char_name = os.path.basename(character_sheet_path)
                image_files = [char_name]
                image_paths = [character_sheet_path]
                image_file = char_name
                image_path = character_sheet_path
                has_image = True
        # If "none", image_files and image_paths remain empty

        items.append({
            "id": idx,
            "num": num,
            "checked": True if (prompt_file and prompt_text) else False,
            "subfolder_name": sub_name,
            "subfolder_path": sub_path,
            "prompt_file": prompt_file or "ไม่พบไฟล์ prompt (.md)",
            "prompt_path": prompt_path or "",
            "prompt_text": prompt_text,
            "has_prompt": bool(prompt_file and prompt_text),
            "image_mode": image_mode,
            "image_subfolder": image_subfolder,
            "image_file": image_file or "",
            "image_path": image_path or "",
            "image_files": image_files,
            "image_paths": image_paths,
            "subfolder_image_files": subfolder_image_files,
            "subfolder_image_paths": subfolder_image_paths,
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

def toggle_seedance_download_enhancer(driver, enabled: Optional[bool] = None) -> dict[str, Any]:
    """
    Ensures download buttons remain at their normal size and removes any previously injected enlarged styles.
    """
    script = """
    const STYLE_ID = "seedance-always-download-style";
    const existing = document.getElementById(STYLE_ID);
    if (existing) existing.remove();
    if (window.__seedanceObserver) {
        window.__seedanceObserver.disconnect();
        window.__seedanceObserver = null;
    }
    if (window.__seedanceInterval) {
        clearInterval(window.__seedanceInterval);
        window.__seedanceInterval = null;
    }
    document.querySelectorAll(".dreamina-download-enlarged").forEach(el => {
        el.classList.remove("dreamina-download-enlarged");
        el.style.transform = "";
        el.style.filter = "";
        el.style.zIndex = "";
    });
    window.__seedanceDownloadEnhancerActive = false;
    return {
        ok: true,
        enabled: false,
        count: 0,
        message: "ปุ่ม Download ขนาดปกติเรียบร้อยแล้ว (ไม่ขยายขนาด)"
    };
    """
    try:
        res = driver.execute_script(script)
        if not isinstance(res, dict):
            res = {"ok": True, "enabled": False, "count": 0, "message": "ปุ่ม Download ขนาดปกติเรียบร้อยแล้ว"}
        log("[Seedance] 📥 คืนค่าขนาดปุ่ม Download บน Dreamina ให้เป็นขนาดปกติเรียบร้อยแล้ว")
        return res
    except Exception as e:
        log(f"[Seedance] ⚠️ ข้อผิดพลาดขณะคืนค่าขนาดปุ่ม Download: {e}")
        return {"ok": False, "detail": str(e)}

def find_record_on_dreamina(
    driver,
    num: Optional[Any] = None,
    name: str = "",
    prompt_snippet: str = "",
    scroll_to_found: bool = True
) -> dict[str, Any]:
    """
    Searches for a record card on Dreamina virtual list matching num, name, or prompt_snippet.
    Checks current viewport first; if not found, scans through the viewport scroll positions.
    Returns:
      {
        "found": bool,
        "match_type": str,
        "text": str,
        "has_video": bool,
        "video_src": str or None,
        "is_generating": bool
      }
    """
    if not driver:
        return {"found": False, "reason": "no_driver"}

    num_str = str(num) if num is not None else ""
    name = (name or "").strip()
    prompt_snippet = (prompt_snippet or "").strip().replace("\n", " ")[:50]

    check_code = r"""
    function checkTarget(num, name, snippet) {
        const items = document.querySelectorAll('.content-_w2B98 > div > div, [class*="record-item"], [class*="slot-card"], [class*="record-card"]');
        for (const el of items) {
            if (el.classList.contains('record-list-container-GKMHFh') || el.classList.contains('record-virtual-list')) continue;
            const text = (el.innerText || '').trim();
            if (!text) continue;

            let matched = false;
            let matchType = '';
            if (name && text.includes(name)) {
                matched = true;
                matchType = 'name';
            } else if (num && (text.includes(num + ' -') || text.includes(num + '-') || text.startsWith(num + ' '))) {
                matched = true;
                matchType = 'num';
            } else if (snippet && snippet.length > 15 && text.includes(snippet)) {
                matched = true;
                matchType = 'snippet';
            }

            if (matched) {
                const vid = el.querySelector('video');
                const isGen = !!el.querySelector('[class*="generating"], [class*="progress"], [class*="loading"]');
                const dlBtn = el.querySelector('.dreamina-download-enlarged, [class*="button-group-top"] span, [class*="download"]');
                return {
                    found: true,
                    matchType: matchType,
                    text: text.slice(0, 120),
                    hasVideo: !!vid,
                    videoSrc: vid ? (vid.src || vid.currentSrc) : null,
                    isGenerating: isGen,
                    hasDlBtn: !!dlBtn,
                    el: el
                };
            }
        }
        return null;
    }
    """

    try:
        res = driver.execute_script(check_code + r"""
            const found = checkTarget(arguments[0], arguments[1], arguments[2]);
            if (found) {
                if (arguments[3] && found.el) {
                    found.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                return {
                    found: true,
                    matchType: found.matchType,
                    text: found.text,
                    hasVideo: found.hasVideo,
                    videoSrc: found.videoSrc,
                    isGenerating: found.isGenerating,
                    hasDlBtn: found.hasDlBtn
                };
            }
            const vp = document.querySelector('.viewport-M4gznV') || document.querySelector('[class*="viewport"]');
            return {
                found: false,
                maxScroll: vp ? vp.scrollHeight : 0,
                clientHeight: vp ? vp.clientHeight : 800,
                currScroll: vp ? vp.scrollTop : 0
            };
        """, num_str, name, prompt_snippet, scroll_to_found)

        if isinstance(res, dict) and res.get("found"):
            return res

        if not isinstance(res, dict):
            return {"found": False}

        max_scroll = res.get("maxScroll", 0)
        client_h = res.get("clientHeight", 800)
        curr_scroll = res.get("currScroll", 0)

        if max_scroll <= client_h:
            return {"found": False}

        # Step-scan through virtual list
        positions = list(range(curr_scroll, max_scroll + client_h, client_h)) + list(range(0, curr_scroll, client_h))
        
        for pos in positions:
            if is_seedance_stopped():
                log("[Seedance Find Record] 🛑 ยกเลิกการค้นหาเนื่องจากคำสั่ง Force Stop")
                return {"found": False, "stopped": True}
            driver.execute_script(r"""
                const vp = document.querySelector('.viewport-M4gznV') || document.querySelector('[class*="viewport"]');
                if (vp) vp.scrollTop = arguments[0];
            """, pos)
            time.sleep(0.12)
            match = driver.execute_script(check_code + r"""
                const found = checkTarget(arguments[0], arguments[1], arguments[2]);
                if (found) {
                    if (arguments[3] && found.el) {
                        found.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    return {
                        found: true,
                        matchType: found.matchType,
                        text: found.text,
                        hasVideo: found.hasVideo,
                        videoSrc: found.videoSrc,
                        isGenerating: found.isGenerating,
                        hasDlBtn: found.hasDlBtn
                    };
                }
                return null;
            """, num_str, name, prompt_snippet, scroll_to_found)
            if match and isinstance(match, dict) and match.get("found"):
                return match

    except Exception as ex:
        log(f"[Seedance Find Record Warning] {ex}")

    return {"found": False}


def pair_seedance_items(driver, local_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Pairs scanned local items with corresponding generation records on Dreamina web tab.
    Checks:
      1. Local disk: does subfolder have prompt, image, and already existing .mp4?
      2. Dreamina web: does record exist on page, is video ready to download, or still generating?
    """
    paired = []
    
    # Revert download enhancer so buttons stay normal size
    if driver:
        try:
            toggle_seedance_download_enhancer(driver, enabled=False)
        except Exception:
            pass

    for item in local_items:
        if is_seedance_stopped():
            log("[Seedance Matcher] 🛑 ยกเลิกการจับคู่เนื่องจากคำสั่ง Force Stop")
            break
        sub_name = item.get("subfolder_name", "")
        sub_path = item.get("subfolder_path", "")
        num = item.get("num")
        prompt_text = item.get("prompt_text", "")
        prompt_snippet = prompt_text.strip().replace("\n", " ")[:50] if prompt_text else ""

        # Check local mp4
        local_mp4 = os.path.join(sub_path, f"{sub_name}.mp4") if (sub_path and os.path.isdir(sub_path)) else None
        local_video_exists = bool(local_mp4 and os.path.isfile(local_mp4))
        local_video_size_mb = round(os.path.getsize(local_mp4) / (1024 * 1024), 1) if local_video_exists else 0

        # Check Dreamina web
        web_matched = False
        web_has_video = False
        web_video_src = None
        web_status = "offline"
        web_snippet = ""

        if driver:
            try:
                web_res = find_record_on_dreamina(driver, num=num, name=sub_name, prompt_snippet=prompt_snippet, scroll_to_found=False)
                if web_res.get("found"):
                    web_matched = True
                    web_has_video = bool(web_res.get("hasVideo") and web_res.get("videoSrc"))
                    web_video_src = web_res.get("videoSrc")
                    web_snippet = web_res.get("text", "")
                    if web_has_video:
                        web_status = "ready"
                    elif web_res.get("isGenerating"):
                        web_status = "generating"
                    else:
                        web_status = "card_no_video"
                else:
                    web_status = "not_found"
            except Exception as ex:
                log(f"[Seedance Pair Warning] {ex}")
                web_status = "error"
        else:
            web_status = "offline"

        paired.append({
            **item,
            "local_video_exists": local_video_exists,
            "local_video_path": local_mp4 if local_video_exists else None,
            "local_video_size_mb": local_video_size_mb,
            "web_matched": web_matched,
            "web_has_video": web_has_video,
            "web_video_src": web_video_src,
            "web_status": web_status,
            "web_snippet": web_snippet,
            "can_download": web_has_video
        })

    return paired


def download_seedance_videos(
    driver,
    items: list[dict[str, Any]],
    save_to_subfolder: bool = True,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """
    Downloads generated videos from Dreamina for the specified items.
    For each item:
      1. Uses already paired videoSrc or locates record in Dreamina DOM via smart scroll search.
      2. Clicks download button on Dreamina.
      3. Streams and saves the MP4 directly into the item's subfolder (or ~/Downloads as fallback).
    """
    if not items:
        return {"ok": False, "detail": "ไม่มีรายการที่เลือกสำหรับดาวน์โหลด"}

    # Ensure download buttons stay at normal size
    try:
        toggle_seedance_download_enhancer(driver, enabled=False)
    except Exception as enh_err:
        log(f"[Seedance Download Enhancer Warning]: {enh_err}")

    results = []
    success_count = 0
    total = len(items)

    for idx, item in enumerate(items):
        if is_seedance_stopped():
            log("[Seedance Download] 🛑 ยกเลิกการดาวน์โหลดเนื่องจากคำสั่ง Force Stop")
            break

        num = item.get("num")
        sub_name = item.get("subfolder_name", f"Item #{idx+1}")
        sub_path = item.get("subfolder_path", "")
        prompt_text = item.get("prompt_text", "")
        prompt_snippet = prompt_text.strip().replace("\n", " ")[:50] if prompt_text else ""

        log(f"[Seedance Download] 🔍 กำลังค้นหาวิดีโอสำหรับ [{idx+1}/{total}] {sub_name} (เลข: {num})...")
        if progress_callback:
            progress_callback({
                "current": idx,
                "total": total,
                "percent": int((idx / max(total, 1)) * 100),
                "message": f"กำลังดาวน์โหลด [{idx+1}/{total}] {sub_name}..."
            })

        # 1. Check if video_src is already paired from search
        video_src = item.get("web_video_src")
        match_res = None

        if not video_src:
            match_res = find_record_on_dreamina(driver, num=num, name=sub_name, prompt_snippet=prompt_snippet, scroll_to_found=True)
            if match_res.get("found"):
                video_src = match_res.get("videoSrc")

        if not video_src:
            err_msg = f"ไม่พบคลิปสำหรับ '{sub_name}' บนหน้า Dreamina ในขณะนี้"
            log(f"[Seedance Download Warning] ⚠️ {err_msg}")
            results.append({
                "num": num,
                "name": sub_name,
                "ok": False,
                "detail": err_msg
            })
            continue

        # Click download button on Dreamina if possible
        btn_clicked = False
        try:
            btn_clicked = bool(driver.execute_script(r"""
                const dlBtn = document.querySelector('.dreamina-download-enlarged, [class*="button-group-top"] span, [class*="download"]');
                if (dlBtn) {
                    dlBtn.click();
                    return true;
                }
                return false;
            """))
        except Exception:
            pass

        saved_file = None
        if video_src and save_to_subfolder:
            # Determine destination folder
            dest_dir = sub_path if (sub_path and os.path.isdir(sub_path)) else os.path.expanduser("~/Downloads")
            dest_filename = f"{sub_name}.mp4"
            dest_path = os.path.join(dest_dir, dest_filename)

            try:
                import urllib.request
                req = urllib.request.Request(
                    video_src,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                )
                with urllib.request.urlopen(req, timeout=35) as resp, open(dest_path, "wb") as out_f:
                    while chunk := resp.read(65536):
                        if is_seedance_stopped():
                            log("[Seedance Download] 🛑 ยกเลิกการดาวน์โหลดไฟล์เนื่องจากคำสั่ง Force Stop")
                            break
                        out_f.write(chunk)
                saved_file = dest_path
                file_size_mb = round(os.path.getsize(dest_path) / (1024 * 1024), 1)
                log(f"[Seedance Download] ✅ ดาวน์โหลดไฟล์ MP4 สำเร็จ: {dest_filename} ({file_size_mb} MB) -> {dest_path}")
            except Exception as dl_err:
                log(f"[Seedance Download Warning] ไม่สามารถบันทึกไฟล์ MP4 โดยตรงได้: {dl_err}")

        success_count += 1
        results.append({
            "num": num,
            "name": sub_name,
            "ok": True,
            "button_clicked": btn_clicked,
            "video_src": video_src,
            "saved_file": saved_file
        })

        if idx < total - 1:
            time.sleep(1.5)

    if progress_callback:
        progress_callback({
            "current": total,
            "total": total,
            "percent": 100,
            "message": f"✅ ดาวน์โหลดเสร็จสิ้น {success_count}/{total} รายการ"
        })

    return {
        "ok": success_count > 0,
        "total": total,
        "success_count": success_count,
        "results": results
    }

def apply_all_seedance_settings(
    driver,
    model: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    duration: Optional[int] = None,
    prompt_text: Optional[str] = None,
    image_path: Optional[str] = None,
    image_paths: Optional[list[str]] = None,
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

    # Determine target image paths
    target_imgs = []
    if image_paths:
        target_imgs = [p for p in image_paths if p and os.path.isfile(p)]
    elif image_path and os.path.isfile(image_path):
        target_imgs = [image_path]

    # 1. Handle Image based on clear_mode
    if clear_mode in ("both", "image"):
        if target_imgs:
            results["image"] = set_seedance_images(driver, target_imgs)
        elif clear_image or clear_mode == "image":
            results["image"] = clear_seedance_image(driver)
    else:
        # clear_mode == "prompt" -> Do NOT clear image on Dreamina unless target_imgs provided
        if target_imgs:
            results["image"] = set_seedance_images(driver, target_imgs)

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
    image_subfolder: str = "images",
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
            item_img_paths = item.get("image_paths") or item.get("subfolder_image_paths") or ([item.get("image_path")] if item.get("image_path") else [])
            item_img_paths = [p for p in item_img_paths if p and os.path.isfile(p)]

            # If subfolder mode but paths are empty, dynamically scan subfolder_path on disk
            if item_mode == "subfolder" and not item_img_paths:
                sub_path = item.get("subfolder_path")
                if sub_path and os.path.isdir(sub_path):
                    found_imgs = find_all_images_in_folder(sub_path, subfolder_name=image_subfolder)
                    if found_imgs:
                        item_img_paths = [tpl[1] for tpl in found_imgs]
                        log(f"[Seedance] 🔍 ค้นพบรูปภาพเพิ่มเติมใน '{sub_name}': {len(item_img_paths)} รูป")
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
                    if item_img_paths:
                        log(f"[Seedance] 🖼️ กำลังแนบรูปภาพประจำโฟลเดอร์ {len(item_img_paths)} รูป: {', '.join([os.path.basename(p) for p in item_img_paths])}")
                        set_seedance_images(driver, item_img_paths)
                    else:
                        log(f"[Seedance] ℹ️ โฟลเดอร์ {sub_name} ไม่มีไฟล์รูปภาพ -> ลบรูปอ้างอิงเดิม (ถ้ามี)")
                        clear_seedance_image(driver)
                elif item_mode == "character_sheet":
                    target_char_img = character_sheet_path or (item_img_paths[0] if item_img_paths else None)
                    if target_char_img and os.path.isfile(target_char_img):
                        has_img = driver.execute_script("""
                            const refs = document.querySelector('[data-content-generator-references="true"]');
                            return !!(refs && refs.querySelector('img'));
                        """)
                        if not has_img:
                            log(f"[Seedance] 👤 แนบรูป Character Sheet: {os.path.basename(target_char_img)}")
                            set_seedance_images(driver, [target_char_img])
                    else:
                        clear_seedance_image(driver)
                elif item_mode == "none":
                    clear_seedance_image(driver)
            else:
                # clear_mode == "prompt" -> Do NOT clear existing image on Dreamina!
                if item_mode == "subfolder" and item_img_paths:
                    set_seedance_images(driver, item_img_paths)
                elif item_mode == "character_sheet":
                    target_char_img = character_sheet_path or (item_img_paths[0] if item_img_paths else None)
                    if target_char_img and os.path.isfile(target_char_img):
                        has_img = driver.execute_script("""
                            const refs = document.querySelector('[data-content-generator-references="true"]');
                            return !!(refs && refs.querySelector('img'));
                        """)
                        if not has_img:
                            set_seedance_images(driver, [target_char_img])
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
