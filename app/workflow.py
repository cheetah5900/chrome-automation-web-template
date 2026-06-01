import os
import re
import shutil
import time
from typing import Any, Callable

from send2trash import send2trash

from PIL import Image

from .browser_focus import focus_chrome_tab

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


def clean_name_from_folder_name(folder_name: str) -> str:
    return folder_name.split(" - ", 1)[1] if " - " in folder_name else folder_name


def trash(path: str, log: Callable[[str], None]) -> None:
    if not path or not os.path.exists(path):
        return
    try:
        send2trash(path)
    except Exception as e:
        log(f"Error moving to Trash: {path} ({e})")
        raise


def step8_downloads_images_to_local(folder_name: str, local_path: str, log: Callable[[str], None]) -> None:
    clean_name = clean_name_from_folder_name(folder_name)
    base = os.path.join(local_path, folder_name)
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    img_d = os.path.join(downloads, "images")
    if not os.path.exists(img_d):
        raise FileNotFoundError("No 'images' folder in Downloads")

    d4000 = os.path.join(base, "4000x4000")
    os.makedirs(d4000, exist_ok=True)

    img_files: list[str] = []
    for root, dirs, files in os.walk(img_d):
        for f in files:
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                img_files.append(os.path.join(root, f))

    if not img_files:
        log("No images found in Downloads/images")
        return

    for i, fp in enumerate(sorted(img_files)):
        ext = os.path.splitext(fp)[1]
        shutil.copy2(fp, os.path.join(d4000, f"{clean_name} ({i+1}){ext}"))

    trash(img_d, log)
    log("Step 8: Moved & Renamed images to Local.")


def step14_local_to_remote(
    folder_name: str,
    local_path: str,
    remote_path: str,
    element_name: str,
    element_path: str,
    log: Callable[[str], None],
) -> None:
    clean_name = clean_name_from_folder_name(folder_name)

    elements_src = os.path.join(element_path, element_name)
    if not os.path.exists(elements_src):
        raise FileNotFoundError(f"Elements folder not found: {elements_src}")

    def _normalize_dir(dir_path: str, desired_name: Callable[[int, str], str]) -> list[str]:
        if not os.path.exists(dir_path):
            return []

        allowed_exts = (".png", ".jpg", ".jpeg", ".webp")
        files = sorted(
            [
                f
                for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f))
                and not f.startswith(".")
                and os.path.splitext(f)[1].lower() in allowed_exts
            ],
        )

        renames: list[tuple[str, str]] = []
        for i, f in enumerate(files):
            ext = os.path.splitext(f)[1]
            want = desired_name(i + 1, ext)
            if f != want:
                renames.append((f, want))

        if not renames:
            return files

        # Two-phase rename to avoid collisions.
        tmp_map: list[tuple[str, str, str]] = []
        for src, dst in renames:
            tmp = f".{src}.tmp_step14"
            os.replace(os.path.join(dir_path, src), os.path.join(dir_path, tmp))
            tmp_map.append((tmp, dst, src))

        for tmp, dst, _orig in tmp_map:
            os.replace(os.path.join(dir_path, tmp), os.path.join(dir_path, dst))

        return sorted(
            [
                f
                for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f)) and not f.startswith(".")
            ],
        )

    # Normalize local names first, then copy as-is.
    total_copied = 0
    for sub in ["4000x4000", "Sticker Set"]:
        src_dir = os.path.join(local_path, folder_name, sub)
        dst_dir = os.path.join(remote_path, folder_name, sub)
        if not os.path.exists(src_dir):
            continue
        os.makedirs(dst_dir, exist_ok=True)
        local_files = _normalize_dir(src_dir, lambda n, ext: f"{clean_name} ({n}){ext}")
        for it in local_files:
            if not os.path.isfile(os.path.join(src_dir, it)) or it.startswith("."):
                continue
            shutil.copy2(os.path.join(src_dir, it), os.path.join(dst_dir, it))
            total_copied += 1

    # Normalize element names at source, then copy to Remote 4000x4000.
    rd = os.path.join(remote_path, folder_name, "4000x4000")
    os.makedirs(rd, exist_ok=True)

    el_files = _normalize_dir(elements_src, lambda n, ext: f"element ({n}){ext}")
    el_copied = 0
    for it in el_files:
        if not os.path.isfile(os.path.join(elements_src, it)) or it.startswith("."):
            continue
        shutil.copy2(os.path.join(elements_src, it), os.path.join(rd, it))
        el_copied += 1
        total_copied += 1

    log(f"Step 14: Done! Copied {total_copied} files total ({el_copied} elements).")


def step14_local_to_remote_no_elements(
    folder_name: str,
    local_path: str,
    remote_path: str,
    log: Callable[[str], None],
) -> None:
    clean_name = clean_name_from_folder_name(folder_name)

    def _normalize_dir(dir_path: str, desired_name: Callable[[int, str], str]) -> list[str]:
        if not os.path.exists(dir_path):
            return []

        allowed_exts = (".png", ".jpg", ".jpeg", ".webp")
        files = sorted(
            [
                f
                for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f))
                and not f.startswith(".")
                and os.path.splitext(f)[1].lower() in allowed_exts
            ],
        )

        renames: list[tuple[str, str]] = []
        for i, f in enumerate(files):
            ext = os.path.splitext(f)[1]
            want = desired_name(i + 1, ext)
            if f != want:
                renames.append((f, want))

        if not renames:
            return files

        tmp_map: list[tuple[str, str]] = []
        for src, dst in renames:
            tmp = f".{src}.tmp_step14"
            os.replace(os.path.join(dir_path, src), os.path.join(dir_path, tmp))
            tmp_map.append((tmp, dst))

        for tmp, dst in tmp_map:
            os.replace(os.path.join(dir_path, tmp), os.path.join(dir_path, dst))

        return sorted(
            [
                f
                for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f)) and not f.startswith(".")
            ],
        )

    total_copied = 0
    for sub in ["4000x4000", "Sticker Set"]:
        src_dir = os.path.join(local_path, folder_name, sub)
        dst_dir = os.path.join(remote_path, folder_name, sub)
        if not os.path.exists(src_dir):
            continue
        os.makedirs(dst_dir, exist_ok=True)
        local_files = _normalize_dir(src_dir, lambda n, ext: f"{clean_name} ({n}){ext}")
        for it in local_files:
            if not os.path.isfile(os.path.join(src_dir, it)) or it.startswith("."):
                continue
            shutil.copy2(os.path.join(src_dir, it), os.path.join(dst_dir, it))
            total_copied += 1

    log(f"Step 14: Done! Copied {total_copied} files total (no elements).")


def step2_create_folders(
    folder_name: str,
    local_path: str,
    remote_path: str,
    log: Callable[[str], None],
) -> None:
    if not folder_name or not local_path or not remote_path:
        raise ValueError("folder_name/local_path/remote_path required")
    configs = [
        {"path": local_path, "folder": folder_name, "subfolders": ["4000x4000", "Download file", "Original", "Preview", "Sticker Set"]},
        {"path": remote_path, "folder": folder_name, "subfolders": ["4000x4000", "Sticker Set"]},
    ]
    for i, c in enumerate(configs):
        base, name, subs = c["path"], c["folder"], c["subfolders"]
        f = os.path.join(base, name)
        os.makedirs(f, exist_ok=True)
        for sub in subs:
            os.makedirs(os.path.join(f, sub), exist_ok=True)
        log(f"Step 2: Path {i+1} ready")


def step6_classify_resolution(log: Callable[[str], None]) -> None:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    img_d = os.path.join(downloads, "images")
    if not os.path.exists(img_d):
        raise FileNotFoundError("No 'images' in Downloads")

    counts: dict[str, int] = {}
    for f in os.listdir(img_d):
        fp = os.path.join(img_d, f)
        if not os.path.isfile(fp):
            continue
        if not f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        try:
            with Image.open(fp) as img:
                w, h = img.size
        except Exception:
            continue
        res_folder = f"{w}x{h}"
        target_d = os.path.join(img_d, res_folder)
        os.makedirs(target_d, exist_ok=True)
        shutil.move(fp, os.path.join(target_d, f))
        counts[res_folder] = counts.get(res_folder, 0) + 1
    if counts:
        summary = ", ".join([f"{k}({v})" for k, v in sorted(counts.items())])
        log(f"Step 6: Classified: {summary}")
    else:
        log("Step 6: No images classified")


def step12_unzip_downloads(log: Callable[[str], None]) -> None:
    import zipfile

    dp = os.path.join(os.path.expanduser("~"), "Downloads")
    zips = [f for f in os.listdir(dp) if f.lower().endswith(".zip")]
    for zfn in zips:
        zp = os.path.join(dp, zfn)
        ep = os.path.join(dp, os.path.splitext(zfn)[0])
        with zipfile.ZipFile(zp, "r") as zr:
            os.makedirs(ep, exist_ok=True)
            zr.extractall(ep)
        log(f"Step 12: Unzipped {zfn}")
    log("Step 12: Unzip Complete")


def step13_download_to_local(folder_name: str, local_path: str, log: Callable[[str], None]) -> None:
    base = os.path.join(local_path, folder_name)
    downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")

    for search_key, target_sub in [("png", "Sticker Set"), ("jpg", "Preview")]:
        target_dir = os.path.join(base, target_sub)
        if not os.path.exists(target_dir):
            continue
        matched_folders = [
            f
            for f in os.listdir(downloads_path)
            if os.path.isdir(os.path.join(downloads_path, f)) and f.lower().startswith(search_key)
        ]
        for folder in matched_folders:
            src = os.path.join(downloads_path, folder)
            for it in os.listdir(src):
                if os.path.isfile(os.path.join(src, it)):
                    shutil.copy2(os.path.join(src, it), os.path.join(target_dir, it))
            trash(src, log)

        matched_zips = [
            f
            for f in os.listdir(downloads_path)
            if os.path.isfile(os.path.join(downloads_path, f)) and f.lower().startswith(search_key) and f.lower().endswith(".zip")
        ]
        for zip_file in matched_zips:
            trash(os.path.join(downloads_path, zip_file), log)

    pdfs = [f for f in os.listdir(downloads_path) if f.lower().endswith(".pdf")]
    if pdfs:
        pdf_target_dir = os.path.join(base, "Download file")
        if os.path.exists(pdf_target_dir):
            target_pdf = next((p for p in pdfs if "pdf_for_downloading" in p.lower()), pdfs[0])
            shutil.copy2(os.path.join(downloads_path, target_pdf), os.path.join(pdf_target_dir, target_pdf))
            trash(os.path.join(downloads_path, target_pdf), log)

    log("Step 13: Finished Copy & Cleanup")


def step9_elements_to_local(element_name: str, element_path: str, log: Callable[[str], None]) -> None:
    if not element_name or not element_path:
        raise ValueError("element_name/element_path required")
    dp = os.path.join(os.path.expanduser("~"), "Downloads")
    el_d = os.path.join(dp, "elements")
    if not os.path.exists(el_d):
        raise FileNotFoundError("No 'elements' in Downloads")

    target_dir = os.path.join(element_path, element_name)
    os.makedirs(target_dir, exist_ok=True)

    copied = 0
    for root, _dirs, files in os.walk(el_d):
        if "upscayl" not in root.lower():
            continue
        img_files = sorted([f for f in files if os.path.isfile(os.path.join(root, f))])
        for i, it in enumerate(img_files):
            shutil.copy2(
                os.path.join(root, it),
                os.path.join(target_dir, f"{element_name} ({i+1}){os.path.splitext(it)[1]}"),
            )
            copied += 1

    trash(el_d, log)
    log(f"Step 9: Elements moved & cleaned ({copied} files).")


def _apply_watermark(src: str, dst: str, wm_path: str | None, convert_to_jpg: bool = False) -> None:
    with Image.open(src) as img:
        img = img.convert("RGBA")
        if wm_path and os.path.exists(wm_path):
            with Image.open(wm_path) as wm:
                wm = wm.convert("RGBA")
                wm.thumbnail(img.size, Image.LANCZOS)
                x = (img.width - wm.width) // 2
                y = (img.height - wm.height) // 2
                img.alpha_composite(wm, (x, y))
        if convert_to_jpg:
            final_img = Image.new("RGB", img.size, (255, 255, 255))
            final_img.paste(img, mask=img.split()[3])
            final_img.save(dst, "JPEG", quality=95)
        else:
            img.save(dst, "PNG")


def step10_create_preview_sheet(
    folder_name: str,
    local_path: str,
    watermark_path: str | None,
    first_preview_watermark_path: str | None,
    element_name: str,
    element_path: str,
    log: Callable[[str], None],
) -> None:
    import math

    if not folder_name or not local_path:
        raise ValueError("folder_name/local_path required")
    base = os.path.join(local_path, folder_name)
    src_dir = os.path.join(base, "4000x4000")
    target_dir = os.path.join(base, "Sticker Set")
    if not os.path.exists(src_dir):
        raise FileNotFoundError("Folder NOT FOUND: 4000x4000")
    os.makedirs(target_dir, exist_ok=True)

    img_files = sorted([f for f in os.listdir(src_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))])
    if not img_files:
        raise FileNotFoundError("No images in 4000x4000")

    cw, ch, max_p = 4000, 4000, 16
    pages = [img_files[i : i + max_p] for i in range(0, len(img_files), max_p)]

    max_num = 0
    for f in os.listdir(target_dir):
        m = re.search(r"Sticker Set \((\d+)\)\.png", f)
        if m:
            max_num = max(max_num, int(m.group(1)))
    start_idx = max_num + 1

    for p_idx, page_imgs in enumerate(pages):
        n = len(page_imgs)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cell_w, cell_h = cw // cols, ch // rows
        for i, img_file in enumerate(page_imgs):
            c, r = i % cols, i // cols
            with Image.open(os.path.join(src_dir, img_file)) as img:
                img = img.convert("RGBA")
                img_ratio = img.width / img.height
                cell_ratio = cell_w / cell_h
                if img_ratio > cell_ratio:
                    nw = cell_w
                    nh = int(nw / img_ratio)
                else:
                    nh = cell_h
                    nw = int(nh * img_ratio)
                img_res = img.resize((nw, nh), Image.LANCZOS)
                x = c * cell_w + (cell_w - nw) // 2
                y = r * cell_h + (cell_h - nh) // 2
                canvas.paste(img_res, (x, y), img_res)
        file_name = f"Sticker Set ({start_idx + p_idx}).png"
        canvas.save(os.path.join(target_dir, file_name), "PNG")
        log(f"Step 10: Saved {file_name}")

    # Elements: create additional Sticker Set pages after main pages.
    if element_name and element_path:
        elements_dir = os.path.join(element_path, element_name)
        if not os.path.exists(elements_dir):
            raise FileNotFoundError(f"Elements folder NOT FOUND: {elements_dir}")

        el_files = sorted(
            [
                f
                for f in os.listdir(elements_dir)
                if os.path.isfile(os.path.join(elements_dir, f))
                and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ],
        )
        if el_files:
            el_pages = [el_files[i : i + max_p] for i in range(0, len(el_files), max_p)]
            el_start = start_idx + len(pages)
            for p_idx, page_imgs in enumerate(el_pages):
                n = len(page_imgs)
                cols = math.ceil(math.sqrt(n))
                rows = math.ceil(n / cols)
                canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                cell_w, cell_h = cw // cols, ch // rows
                for i, img_file in enumerate(page_imgs):
                    c, r = i % cols, i // cols
                    with Image.open(os.path.join(elements_dir, img_file)) as img:
                        img = img.convert("RGBA")
                        img_ratio = img.width / img.height
                        cell_ratio = cell_w / cell_h
                        if img_ratio > cell_ratio:
                            nw = cell_w
                            nh = int(nw / img_ratio)
                        else:
                            nh = cell_h
                            nw = int(nh * img_ratio)
                        img_res = img.resize((nw, nh), Image.LANCZOS)
                        x = c * cell_w + (cell_w - nw) // 2
                        y = r * cell_h + (cell_h - nh) // 2
                        canvas.paste(img_res, (x, y), img_res)
                file_name = f"Sticker Set ({el_start + p_idx}).png"
                canvas.save(os.path.join(target_dir, file_name), "PNG")
                log(f"Step 10: Saved {file_name} (elements)")

    preview_dir = os.path.join(base, "Preview")
    os.makedirs(preview_dir, exist_ok=True)
    for f in os.listdir(target_dir):
        if not f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        src_path = os.path.join(target_dir, f)
        target_name = f.replace("Sticker Set", "Preview") if f.startswith("Sticker Set") else f
        target_name = os.path.splitext(target_name)[0] + ".jpg"
        dst_path = os.path.join(preview_dir, target_name)

        wm = watermark_path
        if os.path.splitext(target_name)[0] == "Preview" and first_preview_watermark_path:
            wm = first_preview_watermark_path

        _apply_watermark(src_path, dst_path, wm, convert_to_jpg=True)

    log(f"Step 10: Created {len(pages)} sheets and updated Preview.")


def _execute_steps(driver, steps: list[tuple[str, str, str | None]], log: Callable[[str], None]) -> bool:
    for name, xp, val in steps:
        # Canva: when there's only 1 page, the "Select pages" control may not exist.
        # Don't wait 20s; just skip immediately.
        if ("Select pages" in xp or name.startswith("Set Pages")) and not driver.find_elements(By.XPATH, xp):
            log(f"Skip: {name} (no page selector)")
            continue

        ok = False
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                # Match gui.py behavior: wait for presence, then click (JS fallback).
                is_pages_step = ("Select pages" in xp) or name.startswith("Set Pages")
                timeout_s = 3 if is_pages_step else 20
                el = WebDriverWait(driver, timeout_s).until(EC.presence_of_element_located((By.XPATH, xp)))

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                time.sleep(0.5)

                if val is not None:
                    if any(k in xp for k in ["Select pages", "spinbutton", "Design title"]):
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5)

                        # Canva title/page fields are sometimes stubborn; clear via select-all + backspace.
                        try:
                            el.send_keys(Keys.COMMAND, "a")
                        except Exception:
                            try:
                                el.send_keys(Keys.CONTROL, "a")
                            except Exception:
                                pass
                        try:
                            el.send_keys(Keys.BACKSPACE)
                        except Exception:
                            pass

                        # Extra-clear via JS to avoid sticky previous values.
                        try:
                            driver.execute_script(
                                "arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
                                el,
                            )
                        except Exception:
                            pass

                        if "spinbutton" in xp:
                            # Canva's numeric input can drop punctuation; set value via JS.
                            driver.execute_script(
                                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
                                el,
                                val,
                            )
                            time.sleep(0.5)
                            el.send_keys(Keys.ENTER)
                            time.sleep(0.5)
                        else:
                            el.send_keys(val)
                            time.sleep(0.5)
                            if "Design title" in xp:
                                el.send_keys(Keys.ENTER)
                                time.sleep(0.5)
                            else:
                                el.send_keys(Keys.TAB)
                                time.sleep(0.5)
                    else:
                        driver.execute_script(
                            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
                            el,
                            val,
                        )
                        time.sleep(0.5)
                else:
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.5)

                    # Canva's final submit button is sometimes ignored on the first click.
                    if "Final Download" in name:
                        for _ in range(2):
                            try:
                                def _still_there(d):
                                    els = d.find_elements(By.XPATH, xp)
                                    if not els:
                                        return False
                                    btn = els[0]
                                    if not btn.is_displayed():
                                        return False
                                    disabled = btn.get_attribute("disabled")
                                    aria_disabled = btn.get_attribute("aria-disabled")
                                    return not (disabled is not None or aria_disabled == "true")

                                # If it remains clickable, click again.
                                if _still_there(driver):
                                    driver.execute_script("arguments[0].click();", driver.find_elements(By.XPATH, xp)[0])
                                    time.sleep(0.7)
                                else:
                                    break
                            except Exception:
                                break

                ok = True
                break
            except Exception as e:
                last_err = e
                time.sleep(0.8)

        if not ok:
            # Canva: when there's only 1 page, the "Select pages" control may not exist.
            if "Select pages" in xp or name.startswith("Set Pages"):
                log(f"Skip: {name} (page selector not usable)")
                continue
            log(f"Error [{name}]: {str(last_err)[:120] if last_err else 'unknown'}")
            return False

        log(f"Success: {name}")
    return True


def step11_canva_export_all(driver, png_pages: str | None, jpg_pages: str | None, pdf_pages: str | None, log: Callable[[str], None]) -> None:
    if not (driver and hasattr(driver, "current_url")):
        raise ValueError("driver required")
    png_pages = (png_pages or "").strip() or "1-4"
    jpg_pages = (jpg_pages or "").strip() or "6-9"
    pdf_pages = (pdf_pages or "").strip() or "10"

    def export_png() -> bool:
        steps = [
            ("Rename Design to 'Sticker Set'", "//input[@aria-label='Design title']", "Sticker Set"),
            ("Click Share", "//button[.//span[text()='Share']]", None),
            ("Click Download", "//button[@aria-label='Download']", None),
            ("Click File Type", "//button[@aria-label='File type']", None),
            ("Select PNG", "//*[@role='option']//div[text()='PNG']", None),
            ("Set Size to 1", "//input[@role='spinbutton']", "1"),
            ("Click Transparent", "//label[.//p[contains(text(), 'Transparent background')]]", None),
            ("Set Pages", "//input[@placeholder='Select pages']", png_pages),
            ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]", None),
        ]
        return _execute_steps(driver, steps, log)

    def export_jpg() -> bool:
        steps = [
            ("Rename Design to 'jpg'", "//input[@aria-label='Design title']", "jpg"),
            ("Click Share", "//button[.//span[text()='Share']]", None),
            ("Click Download", "//button[@aria-label='Download']", None),
            ("Click File Type", "//button[@aria-label='File type']", None),
            ("Select JPG", "//*[@role='option']//div[text()='JPG']", None),
            ("Set Size to 0.5", "//input[@role='spinbutton']", "0.5"),
            ("Set Pages", "//input[@placeholder='Select pages']", jpg_pages),
            ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]", None),
        ]
        return _execute_steps(driver, steps, log)

    def export_pdf() -> bool:
        steps = [
            ("Rename Design to 'pdf_for_downloading'", "//input[@aria-label='Design title']", "pdf_for_downloading"),
            ("Click Share", "//button[.//span[text()='Share']]", None),
            ("Click Download", "//button[@aria-label='Download']", None),
            ("Click File Type", "//button[@aria-label='File type']", None),
            ("Select PDF Standard", "//*[@role='option']//div[text()='PDF Standard']", None),
            ("Set Pages", "//input[@placeholder='Select pages']", pdf_pages),
            ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]", None),
        ]
        return _execute_steps(driver, steps, log)

    log("Step 11: Starting ALL Exports...")
    if not export_png():
        raise RuntimeError("Export PNG failed")
    time.sleep(8)
    if not export_jpg():
        raise RuntimeError("Export JPG failed")
    time.sleep(8)
    if not export_pdf():
        raise RuntimeError("Export PDF failed")
    log("Step 11: Export ALL complete")


def step11_canva_export(driver, kind: str, pages: str | None, log: Callable[[str], None]) -> None:
    kind = kind.lower().strip()
    if kind not in ("png", "jpg", "pdf"):
        raise ValueError("kind must be png/jpg/pdf")
    if not (driver and hasattr(driver, "current_url")):
        raise ValueError("driver required")
    pages = (pages or "").strip()

    # Keep timing consistent with gui.py.
    if kind == "png":
        pages = pages or "1-4"
        steps = [
            ("Rename Design to 'Sticker Set'", "//input[@aria-label='Design title']", "Sticker Set"),
            ("Click Share", "//button[.//span[text()='Share']]", None),
            ("Click Download", "//button[@aria-label='Download']", None),
            ("Click File Type", "//button[@aria-label='File type']", None),
            ("Select PNG", "//*[@role='option']//div[text()='PNG']", None),
            ("Set Size to 1", "//input[@role='spinbutton']", "1"),
            ("Click Transparent", "//label[.//p[contains(text(), 'Transparent background')]]", None),
            ("Set Pages", "//input[@placeholder='Select pages']", pages),
            ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]", None),
        ]
        if not _execute_steps(driver, steps, log):
            raise RuntimeError("Export PNG failed")
        return
    if kind == "jpg":
        pages = pages or "6-9"
        steps = [
            ("Rename Design to 'jpg'", "//input[@aria-label='Design title']", "jpg"),
            ("Click Share", "//button[.//span[text()='Share']]", None),
            ("Click Download", "//button[@aria-label='Download']", None),
            ("Click File Type", "//button[@aria-label='File type']", None),
            ("Select JPG", "//*[@role='option']//div[text()='JPG']", None),
            ("Set Size to 0.5", "//input[@role='spinbutton']", "0.5"),
            ("Set Pages", "//input[@placeholder='Select pages']", pages),
            ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]", None),
        ]
        if not _execute_steps(driver, steps, log):
            raise RuntimeError("Export JPG failed")
        return
    pages = pages or "10"
    steps = [
        ("Rename Design to 'pdf_for_downloading'", "//input[@aria-label='Design title']", "pdf_for_downloading"),
        ("Click Share", "//button[.//span[text()='Share']]", None),
        ("Click Download", "//button[@aria-label='Download']", None),
        ("Click File Type", "//button[@aria-label='File type']", None),
        ("Select PDF Standard", "//*[@role='option']//div[text()='PDF Standard']", None),
        ("Set Pages", "//input[@placeholder='Select pages']", pages),
        ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]", None),
    ]
    if not _execute_steps(driver, steps, log):
        raise RuntimeError("Export PDF failed")


def step11_canva_export_bot(
    bot: Any,
    kind: str,
    pages: str | None,
    log: Callable[[str], None],
    *,
    focus_tab: bool = False,
    canva_url_part: str = "canva.com",
) -> None:
    canva_url_part = canva_url_part or "canva.com"
    log(f"Step 11: Switching to Canva tab containing: {canva_url_part}")
    if focus_tab:
        focus_chrome_tab(canva_url_part)
    if not bot.switch_to_tab_containing(canva_url_part):
        raise RuntimeError(f"Canva tab not found for: {canva_url_part}")
    try:
        bot.driver.switch_to.window(bot.driver.current_window_handle)
        bot.driver.execute_script("window.focus();")
    except Exception:
        pass
    step11_canva_export(bot.driver, kind, pages, log)


def step11_canva_export_all_bot(
    bot: Any,
    png_pages: str | None,
    jpg_pages: str | None,
    pdf_pages: str | None,
    log: Callable[[str], None],
    *,
    focus_tab: bool = False,
    canva_url_part: str = "canva.com",
) -> None:
    canva_url_part = canva_url_part or "canva.com"
    log(f"Step 11: Switching to Canva tab containing: {canva_url_part}")
    if focus_tab:
        focus_chrome_tab(canva_url_part)
    if not bot.switch_to_tab_containing(canva_url_part):
        raise RuntimeError(f"Canva tab not found for: {canva_url_part}")
    try:
        bot.driver.switch_to.window(bot.driver.current_window_handle)
        bot.driver.execute_script("window.focus();")
    except Exception:
        pass
    step11_canva_export_all(bot.driver, png_pages, jpg_pages, pdf_pages, log)


def step4_download_images(driver, log: Callable[[str], None]) -> None:
    # Assumes we are already on Gemini tab.
    driver.execute_script("window.scrollTo(0, 0);")
    scs = driver.find_elements(By.CSS_SELECTOR, ".infinite-scroller, .conversation-container, main")
    for s in scs:
        driver.execute_script("arguments[0].scrollTop = 0;", s)

    def get_buttons():
        return driver.find_elements(By.CSS_SELECTOR, "download-generated-image-button > button")

    # Wait for buttons to render (Gemini lazily loads them).
    # Gemini UI can flicker right after navigation/scroll; let it settle first.
    time.sleep(2)
    btns = get_buttons()
    if not btns:
        driver.execute_script("window.scrollTo(0, 1000);")
        try:
            WebDriverWait(driver, 10).until(lambda d: len(get_buttons()) > 0)
        except Exception:
            pass
        btns = get_buttons()
    if not btns:
        raise RuntimeError("No download buttons found")

    cnt = len(btns)
    log(f"Step 4: Found {cnt} images")
    for i in range(cnt):
        log(f"Step 4: Downloading {i+1}/{cnt}...")

        # Re-query each time to avoid stale elements while scrolling.
        curr_btns = get_buttons()
        if i >= len(curr_btns):
            break

        btn = curr_btns[i]
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        time.sleep(0.4)

        try:
            ohtml = btn.get_attribute("innerHTML")
        except Exception:
            ohtml = ""

        clicked = False
        for _ in range(3):
            try:
                btn.click()
                clicked = True
                break
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    break
                except Exception:
                    # Re-acquire element if it got stale.
                    time.sleep(0.6)
                    curr_btns = get_buttons()
                    if i < len(curr_btns):
                        btn = curr_btns[i]

        if not clicked:
            log(f"Step 4: Failed clicking button {i+1}")
            continue

        # Wait for UI to reflect download action (button often shows a spinner briefly).
        try:
            WebDriverWait(driver, 5).until(lambda d: get_buttons()[i].get_attribute("innerHTML") != ohtml)
        except Exception:
            pass
        try:
            WebDriverWait(driver, 20).until(lambda d: get_buttons()[i].get_attribute("innerHTML") == ohtml)
        except Exception:
            pass
        time.sleep(0.8)

    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    ip = os.path.join(downloads, "images")
    os.makedirs(ip, exist_ok=True)
    mc = 0
    for f in os.listdir(downloads):
        if f.lower().endswith(".png"):
            src, dst = os.path.join(downloads, f), os.path.join(ip, f)
            if os.path.exists(dst):
                trash(dst, log)
            shutil.move(src, dst)
            mc += 1
    log(f"Step 4: Moved {mc} PNG files to 'Downloads/images'.")


def step4_download_images_bot(bot: Any, log: Callable[[str], None]) -> None:
    if not bot.switch_to_tab_containing("gemini.google.com/app"):
        raise RuntimeError("Gemini tab not found")
    step4_download_images(bot.driver, log)


def step3_gemini_gen(driver, mode: str, single_count: int | None, companion_count: int | None, elements_count: int | None, log: Callable[[str], None]) -> None:
    # Assumes we can navigate tabs externally; here we just perform the in-tab logic.
    if mode not in ("single", "companion", "elements"):
        raise ValueError("mode must be single/companion/elements")
    containers: list[tuple[str, str]]
    if mode == "single":
        containers = [("Set 1", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(1) > div:nth-child(2)")]
        clip_limit = single_count
    elif mode == "companion":
        containers = [("Set 2", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(2) > div:nth-child(2)")]
        clip_limit = companion_count
    else:
        containers = [("Elements", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(3) > div:nth-child(2)")]
        clip_limit = elements_count

    prompts: list[str] = []
    for n, sel in containers:
        try:
            cont = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cont)
            bs = cont.find_elements(By.TAG_NAME, "button") or cont.find_elements(By.XPATH, ".//button")
            for b in bs:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                    try:
                        b.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", b)
                    time.sleep(1.0)
                    # Clipboard read is handled by browser/site; we can't access OS clipboard reliably here.
                    # gui.py relies on Tk clipboard. For backend, we read from `navigator.clipboard` via JS.
                    text = driver.execute_async_script(
                        "const cb = navigator.clipboard; if(!cb) { arguments[0](null); return; } cb.readText().then(t=>arguments[0](t)).catch(()=>arguments[0](null));"
                    )
                    if text:
                        prompts.append(str(text))
                except Exception:
                    pass
        except Exception as e:
            log(f"Step 3: Error {n}: {e}")

    if not prompts:
        raise RuntimeError("No prompts collected")
    lim = clip_limit if isinstance(clip_limit, int) and clip_limit > 0 else 5
    prompts = prompts[:lim]
    log(f"Step 3: Collected {len(prompts)} prompts")

    input_strats = [
        "//div[contains(@class, 'ql-editor') and @contenteditable='true']",
        "//rich-textarea//div[@contenteditable='true']",
        "//div[@contenteditable='true' and @role='textbox']",
    ]
    for i, p in enumerate(prompts):
        log(f"Step 3: Sending {i+1}/{len(prompts)}")
        box = None
        for s in input_strats:
            try:
                tmp = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, s)))
                if tmp.is_displayed():
                    box = tmp
                    break
            except Exception:
                continue
        if not box:
            raise RuntimeError("No input box")
        try:
            box.click()
        except Exception:
            driver.execute_script("arguments[0].click();", box)
        driver.execute_script(
            "if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }",
            box,
        )
        box.send_keys(p)
        box.send_keys(Keys.ENTER)
        time.sleep(3)
        st_xp = "//mat-icon[contains(@data-mat-icon-name, 'stop') or @fonticon='stop']"
        el = 0
        while el < 120:
            try:
                driver.find_element(By.XPATH, st_xp)
                time.sleep(2)
                el += 2
            except Exception:
                break
        time.sleep(3)
    log("Step 3: Gemini Automation Complete!")


def step3_gemini_gen_bot(
    bot: Any,
    mode: str,
    single_count: int | None,
    companion_count: int | None,
    elements_count: int | None,
    log: Callable[[str], None],
) -> None:
    log(f"Step 3: Starting Gemini Gen ({mode})")
    if not bot.switch_to_tab_containing("ddcm.litarandfriends.uk"):
        raise RuntimeError("DDCM tab not found")
    step3_gemini_gen(bot.driver, mode, single_count, companion_count, elements_count, log)
    # step3_gemini_gen expects to run on Gemini for sending; switch now.
    if not bot.switch_to_tab_containing("gemini.google.com/app"):
        raise RuntimeError("Gemini tab not found")
    # Re-run only the sending portion is not split; keeping behavior identical would require refactor.
    # For now, do a full run on the current tab by collecting prompts first, then sending.
    # This wrapper is intentionally not used; call step3_gemini_gen_full_bot instead.


def step3_gemini_gen_full_bot(
    bot: Any,
    mode: str,
    single_count: int | None,
    companion_count: int | None,
    elements_count: int | None,
    log: Callable[[str], None],
) -> None:
    if mode not in ("single", "companion", "elements"):
        raise ValueError("mode must be single/companion/elements")
    if not bot.switch_to_tab_containing("ddcm.litarandfriends.uk"):
        raise RuntimeError("DDCM tab not found")

    # Collect prompts (same selectors as gui.py)
    if mode == "single":
        containers = [("Set 1", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(1) > div:nth-child(2)")]
        clip_limit = single_count
    elif mode == "companion":
        containers = [("Set 2", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(2) > div:nth-child(2)")]
        clip_limit = companion_count
    else:
        containers = [("Elements", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(3) > div:nth-child(2)")]
        clip_limit = elements_count

    prompts: list[str] = []
    for n, sel in containers:
        try:
            cont = WebDriverWait(bot.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cont)
            bs = cont.find_elements(By.TAG_NAME, "button") or cont.find_elements(By.XPATH, ".//button")
            for b in bs:
                try:
                    bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                    try:
                        b.click()
                    except Exception:
                        bot.driver.execute_script("arguments[0].click();", b)
                    time.sleep(1.0)
                    text = bot.driver.execute_async_script(
                        "const cb = navigator.clipboard; if(!cb) { arguments[0](null); return; } cb.readText().then(t=>arguments[0](t)).catch(()=>arguments[0](null));"
                    )
                    if text:
                        prompts.append(str(text))
                except Exception:
                    pass
        except Exception as e:
            log(f"Step 3: Error {n}: {e}")

    if not prompts:
        raise RuntimeError("No prompts collected")
    lim = clip_limit if isinstance(clip_limit, int) and clip_limit > 0 else 5
    prompts = prompts[:lim]
    log(f"Step 3: Collected {len(prompts)} prompts")

    if not bot.switch_to_tab_containing("gemini.google.com/app"):
        raise RuntimeError("Gemini tab not found")

    # Send prompts
    input_strats = [
        "//div[contains(@class, 'ql-editor') and @contenteditable='true']",
        "//rich-textarea//div[@contenteditable='true']",
        "//div[@contenteditable='true' and @role='textbox']",
    ]
    for i, p in enumerate(prompts):
        log(f"Step 3: Processing Gemini {i+1}/{len(prompts)}")
        box = None
        for s in input_strats:
            try:
                tmp = WebDriverWait(bot.driver, 5).until(EC.presence_of_element_located((By.XPATH, s)))
                if tmp.is_displayed():
                    box = tmp
                    break
            except Exception:
                continue
        if not box:
            raise RuntimeError("No input box")
        try:
            box.click()
        except Exception:
            bot.driver.execute_script("arguments[0].click();", box)
        bot.driver.execute_script(
            "if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }",
            box,
        )
        box.send_keys(p)
        time.sleep(1)
        box.send_keys(Keys.ENTER)
        time.sleep(3)
        st_xp = "//mat-icon[contains(@data-mat-icon-name, 'stop') or @fonticon='stop']"
        el = 0
        while el < 120:
            try:
                bot.driver.find_element(By.XPATH, st_xp)
                time.sleep(2)
                el += 2
            except Exception:
                break
        time.sleep(3)

    log("Step 3: Gemini Automation Complete!")


def step15_etsy_listing(driver, primary_color: str, secondary_color: str, log: Callable[[str], None]) -> None:
    if not primary_color or not secondary_color:
        raise ValueError("primary_color/secondary_color required")
    ddcm_fields = [
        ("name", "//div[span[contains(., 'Clipart Name')]]//div[last()]"),
        ("tag", "//div[span[contains(., 'Tags')]]//div[last()]"),
        ("description", "//div[span[contains(., 'Description')]]//div[last()]"),
        ("theme", "//div[span[contains(., 'Theme')]]//div[last()]"),
        ("price", "//div[span[contains(., 'Price')]]//div[last()]"),
    ]
    data: dict[str, str] = {}
    for fn, xp in ddcm_fields:
        el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
        data[fn] = el.text.strip()
        log(f"Step 15: Extracted {fn}")

    driver.switch_to.new_window("tab")
    driver.get("https://www.etsy.com/your/shops/me/listing-editor/create")
    WebDriverWait(driver, 20).until(lambda d: "etsy.com" in d.current_url)
    time.sleep(2)

    setup = [
        ("Category", "//div[contains(@class, 'le-category-action-item') and .//h2[contains(text(), 'Clip Art')]]", None),
        ("Digital", "//label[contains(., 'Digital')]", None),
        ("I did", "//label[contains(., 'I did')]", None),
        ("Supply", "//label[contains(., 'A supply')]", None),
        ("Year", "//select[@id='when-made-select']", "2020_2026"),
        ("AI", "//label[contains(., 'AI')] | //input[contains(@value, 'ai_gen')] | //label[contains(., 'Yes, I used AI')]", None),
    ]
    for n, x, v in setup:
        try:
            el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, x)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            if v is not None:
                Select(el).select_by_value(v)
            else:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(0.8)
        except Exception:
            log(f"Step 15: Warning at {n}")

    def special_esc():
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            driver.execute_script("if(document.activeElement) document.activeElement.blur(); document.body.click();")
        except Exception:
            pass
        time.sleep(1)

    steps = [
        ("INPUT", "//textarea[@id='listing-title-input']", data.get("name", "")),
        ("INPUT", "//textarea[@id='listing-description-textarea' or @name='description']", data.get("description", "")),
        ("INPUT", "//input[@id='listing-tags-input']", data.get("tag", "")),
        ("CLICK", "//button[@id='listing-tags-button']", None),
    ]
    for cmd, xp, val in steps:
        el = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, xp)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        if cmd == "INPUT":
            driver.execute_script(
                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
                el,
                str(val or ""),
            )
        else:
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
        time.sleep(0.5)

    # Craft type
    craft_input = None
    for st in [
        "//div[.//label[contains(., 'Craft type')]]//input",
        "//label[contains(., 'Craft type')]/following::input[1]",
        "//input[@placeholder='Type to search…']",
    ]:
        try:
            tmp = driver.find_element(By.XPATH, st)
            if tmp.is_displayed():
                craft_input = tmp
                break
        except Exception:
            continue
    if not craft_input:
        raise RuntimeError("Craft type input not found")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", craft_input)
    craft_input.click()
    driver.execute_script(
        "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
        craft_input,
        "Scrapbooking",
    )
    craft_input.send_keys(Keys.SPACE)
    craft_input.send_keys(Keys.BACKSPACE)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//label[contains(., 'Scrapbooking')]")))
    lb = driver.find_element(By.XPATH, "//label[contains(., 'Scrapbooking')]")
    cid = lb.get_attribute("for")
    cb = driver.find_element(By.ID, cid)
    if not (cb.is_selected() or driver.execute_script("return arguments[0].checked;", cb)):
        driver.execute_script("arguments[0].click();", lb)
    special_esc()

    def pick_color(label: str, value: str) -> None:
        inp = None
        for st in [
            f"//div[.//label[contains(., '{label}')]]//input",
            f"//label[contains(., '{label}')]/following::input[1]",
            "//input[@placeholder='Type to search…']",
        ]:
            try:
                tmp = driver.find_element(By.XPATH, st)
                if tmp.is_displayed():
                    inp = tmp
                    break
            except Exception:
                continue
        if not inp:
            raise RuntimeError(f"{label} input not found")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
        inp.click()
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            inp,
            value,
        )
        inp.send_keys(Keys.SPACE)
        inp.send_keys(Keys.BACKSPACE)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//button[@role='menuitemradio']//p[text()='{value}']"),
            ),
        )
        driver.execute_script(
            "arguments[0].click();",
            driver.find_element(By.XPATH, f"//button[@role='menuitemradio']//p[text()='{value}']"),
        )
        special_esc()

    pick_color("Primary color", primary_color)
    pick_color("Secondary color", secondary_color)

    # Price, quantity, ads off, section
    def set_input(xp: str, v: str) -> None:
        el = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, xp)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            el,
            v,
        )
        time.sleep(0.5)

    set_input("//input[@id='listing-price-input']", data.get("price", "5.99") or "5.99")
    set_input("//input[@id='listing-quantity-input']", "999")

    promo_cb = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//*[@id='listing-is-promoted-checkbox']")))
    if promo_cb.is_selected() or driver.execute_script("return arguments[0].checked;", promo_cb):
        try:
            promo_cb.click()
        except Exception:
            driver.execute_script("arguments[0].click();", promo_cb)
    time.sleep(0.5)

    section_sel = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//select[@id='shop-section-select']")))
    Select(section_sel).select_by_visible_text(data.get("theme", "General") or "General")
    log("Step 15: Etsy Listing populated!")


def step15_etsy_listing_bot(bot: Any, primary_color: str, secondary_color: str, log: Callable[[str], None]) -> None:
    if not bot.switch_to_tab_containing("ddcm.litarandfriends.uk"):
        raise RuntimeError("DDCM tab not found")
    step15_etsy_listing(bot.driver, primary_color, secondary_color, log)
