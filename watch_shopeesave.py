#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
watch_shopeesave.py - Background Worker Daemon for ShopeeSave Extension.

Watches ~/Downloads/ShopeeSave_* in real-time:
1. Prevents folder collisions (e.g., '_', '___', 'mini_') by immediately renaming to 'item_{Product_ID}'.
2. Matches product info with target episode folders in project directory.
3. Moves main_images, copies product.jpg and info_product.txt, creates video/ directory.
4. Cleans up empty source folders.
5. Writes logs to ~/.shopeesave_watcher.log and PID to ~/.shopeesave_watcher.pid.
"""

import os
import sys
import time
import glob
import shutil
import re
import signal
import atexit
import argparse

DEFAULT_DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
DEFAULT_PROJECT_V1_DIR = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/9 - ป้ายยาที่ตาซ้าย/0 - รอสร้างวิดีโอ/V1 - ดราม่าขายของ"
LOG_FILE = os.path.expanduser("~/.shopeesave_watcher.log")
PID_FILE = os.path.expanduser("~/.shopeesave_watcher.pid")


def log(msg: str):
    t = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{t} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Failed to write log: {e}", file=sys.stderr)


def write_pid():
    pid = os.getpid()
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception as e:
        log(f"Warning: Failed to write PID file: {e}")


def remove_pid():
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass


def cleanup(*args):
    log("ShopeeSave Watcher Stopping gracefully...")
    remove_pid()
    sys.exit(0)


def get_product_info(info_path: str) -> tuple[str | None, str]:
    if not os.path.exists(info_path):
        return None, ""
    prod_id, prod_name = None, ""
    try:
        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
            for i, line in enumerate(lines):
                if "Product ID" in line and i + 1 < len(lines):
                    prod_id = lines[i + 1]
                if "Product name" in line and i + 1 < len(lines):
                    prod_name = lines[i + 1]
    except Exception as e:
        log(f"Error reading info from {info_path}: {e}")
    return prod_id, prod_name


def match_episode_folder(prod_name: str, prod_id: str | None = None, project_dir: str = DEFAULT_PROJECT_V1_DIR) -> str | None:
    if not os.path.exists(project_dir):
        return None
    try:
        episodes = [
            d for d in os.listdir(project_dir)
            if os.path.isdir(os.path.join(project_dir, d)) and " - " in d
        ]
    except Exception as e:
        log(f"Error reading episodes from {project_dir}: {e}")
        return None

    # Strategy 1 (100% Deterministic): Match by Product ID inside Product Link.md or info_product.txt
    if prod_id:
        prod_id_str = str(prod_id).strip()
        for ep in episodes:
            ep_dir = os.path.join(project_dir, ep)
            pl_path = os.path.join(ep_dir, "Product Link.md")
            if os.path.exists(pl_path):
                try:
                    with open(pl_path, "r", encoding="utf-8", errors="ignore") as f:
                        if prod_id_str in f.read():
                            return ep
                except Exception:
                    pass
            info_p = os.path.join(ep_dir, "info_product.txt")
            if os.path.exists(info_p):
                try:
                    with open(info_p, "r", encoding="utf-8", errors="ignore") as f:
                        if prod_id_str in f.read():
                            return ep
                except Exception:
                    pass

    if not prod_name:
        return None

    # Strategy 2: High-confidence keyword matching against episode title
    for ep in sorted(episodes, key=lambda x: int(x.split(" - ")[0]) if x.split(" - ")[0].isdigit() else 9999):
        ep_prod = ep.split("ใช้")[-1] if "ใช้" in ep else ep.split(" - ")[-1]
        keywords = [k for k in re.split(r'[\s/,-]+', ep_prod) if len(k) >= 3]
        match_count = sum(1 for k in keywords if k.lower() in prod_name.lower())
        if match_count >= 1:
            return ep

    # Strategy 3: Token matching from product name against episode name
    prod_tokens = [t for t in re.split(r'[\s/,-]+', prod_name) if len(t) >= 4]
    for ep in sorted(episodes, key=lambda x: int(x.split(" - ")[0]) if x.split(" - ")[0].isdigit() else 9999):
        ep_prod = ep.split("ใช้")[-1] if "ใช้" in ep else ep.split(" - ")[-1]
        if any(t.lower() in ep_prod.lower() for t in prod_tokens):
            return ep

    return None


def process_product_folder(prod_dir: str, project_dir: str = DEFAULT_PROJECT_V1_DIR) -> bool:
    info_path = os.path.join(prod_dir, "info_product.txt")
    main_imgs_path = os.path.join(prod_dir, "main_images")

    # ตรวจสอบว่าดาวน์โหลดเสร็จสมบูรณ์หรือยัง (มีไฟล์ info และรูปภาพ)
    if not os.path.exists(info_path) or not os.path.exists(main_imgs_path):
        return False

    try:
        imgs = [f for f in os.listdir(main_imgs_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    except Exception:
        return False

    if not imgs:
        return False

    prod_id, prod_name = get_product_info(info_path)
    if not prod_name:
        return False

    # ป้องกันชื่อโฟลเดอร์ซ้ำทันที (File Collision Prevention)
    base_name = os.path.basename(prod_dir)
    if (base_name in ["_", "___", "mini_"] or base_name.startswith("_")) and prod_id:
        new_prod_dir = os.path.join(os.path.dirname(prod_dir), f"item_{prod_id}")
        if not os.path.exists(new_prod_dir):
            try:
                os.rename(prod_dir, new_prod_dir)
                prod_dir = new_prod_dir
                main_imgs_path = os.path.join(prod_dir, "main_images")
                info_path = os.path.join(prod_dir, "info_product.txt")
                log(f"🛡️ Renamed collision folder '{base_name}' -> 'item_{prod_id}'")
            except Exception as e:
                log(f"⚠️ Failed to rename collision folder {base_name}: {e}")

    matched_ep = match_episode_folder(prod_name, prod_id=prod_id, project_dir=project_dir)
    if matched_ep:
        target_dir = os.path.join(project_dir, matched_ep)
        dst_main = os.path.join(target_dir, "main_images")

        try:
            # 1. ย้าย main_images
            if os.path.exists(dst_main):
                shutil.rmtree(dst_main)
            shutil.move(main_imgs_path, dst_main)

            # 2. คัดลอก product.jpg
            dst_imgs = sorted([f for f in os.listdir(dst_main) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
            if dst_imgs:
                shutil.copy2(os.path.join(dst_main, dst_imgs[0]), os.path.join(target_dir, "product.jpg"))

            # 3. คัดลอก info_product.txt
            shutil.copy2(info_path, os.path.join(target_dir, "info_product.txt"))

            # 4. สร้าง video/
            os.makedirs(os.path.join(target_dir, "video"), exist_ok=True)

            # ลบโฟลเดอร์ต้นทางที่ว่างเปล่า
            shutil.rmtree(prod_dir, ignore_errors=True)
            log(f"✅ SUCCESS: Auto-moved [{prod_name[:45]}] -> {matched_ep}")
            return True
        except Exception as e:
            log(f"❌ Error moving [{prod_name[:40]}] to {matched_ep}: {e}")
            return False
    else:
        log(f"⏳ WAIT: No match found yet for: [{prod_name[:40]}] (ID: {prod_id or '-'})")
        return False


def main():
    parser = argparse.ArgumentParser(description="ShopeeSave Auto-Watcher Background Service")
    parser.add_argument("--downloads-dir", default=DEFAULT_DOWNLOADS_DIR, help="Path to Downloads directory")
    parser.add_argument("--project-dir", default=DEFAULT_PROJECT_V1_DIR, help="Path to Project V1 directory")
    args = parser.parse_args()

    downloads_dir = os.path.expanduser(args.downloads_dir)
    project_dir = os.path.expanduser(args.project_dir)

    write_pid()
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    atexit.register(remove_pid)

    log(f"🚀 ShopeeSave Watcher Started (PID: {os.getpid()})")
    log(f"   📁 Downloads Dir: {downloads_dir}")
    log(f"   🎯 Project Dir:   {project_dir}")

    while True:
        try:
            shopee_dirs = glob.glob(os.path.join(downloads_dir, "ShopeeSave_*"))
            for s_dir in shopee_dirs:
                if not os.path.isdir(s_dir):
                    continue

                # Case A: Nested folders (ShopeeSave_xxx/product_folder/)
                try:
                    items = os.listdir(s_dir)
                except Exception:
                    continue

                for item in items:
                    sub = os.path.join(s_dir, item)
                    if os.path.isdir(sub):
                        process_product_folder(sub, project_dir=project_dir)

                # Case B: Flat folder where info_product.txt is directly in ShopeeSave_xxx
                if os.path.exists(os.path.join(s_dir, "info_product.txt")):
                    process_product_folder(s_dir, project_dir=project_dir)

        except Exception as e:
            log(f"⚠️ Error in watcher scan loop: {e}")

        time.sleep(2)  # สแกนทุก 2 วินาที


if __name__ == "__main__":
    main()
