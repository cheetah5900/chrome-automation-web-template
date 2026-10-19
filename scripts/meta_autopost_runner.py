#!/usr/bin/env python3
"""
Meta Reels Auto Post Runner CLI & Python Client
Enables automated headless batch scheduling to Meta Business Suite / Facebook Reels via 6969 FastAPI.

Usage:
    # 1. Scan and schedule automatically from a folder:
    python scripts/meta_autopost_runner.py \
        --main-folder "/Users/litar/Downloads/Reels" \
        --subfolders "1-5" \
        --prefix "combined" \
        --start-date "2026-10-20" \
        --start-hour 18

    # 2. Preview only (Dry run):
    python scripts/meta_autopost_runner.py \
        --main-folder "/path/to/folder" \
        --dry-run

    # 3. Custom items JSON list:
    python scripts/meta_autopost_runner.py \
        --items-json '[{"video_path": "/path/v.mp4", "caption": "Hello world", "scheduled_datetime": "2026-10-20T18:00"}]'
"""

import os
import sys
import time
import json
import argparse
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

API_DEFAULT_URL = "http://127.0.0.1:6969"

def scan_meta_items(
    main_folder: str,
    subfolders: str = "",
    prefix: str = "combined",
    start_date: str = "",
    start_hour: int = 18,
    api_url: str = API_DEFAULT_URL
) -> List[Dict[str, Any]]:
    """Calls /api/meta-autopost/scan to detect videos and captions on disk."""
    url = f"{api_url.rstrip('/')}/api/meta-autopost/scan"
    payload = {
        "main_folder": main_folder,
        "subfolders_str": subfolders,
        "video_prefix": prefix,
        "start_date": start_date or datetime.now().strftime("%Y-%m-%d"),
        "start_hour": start_hour,
        "folder_mode": "generic"
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Scan API failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data.get("items", [])

def print_items_table(items: List[Dict[str, Any]]):
    """Prints a structured summary table of the items scheduled for posting."""
    print("\n" + "=" * 80)
    print(f"📋 รายการโพสต์ที่ตรวจพบ ({len(items)} รายการ):")
    print("=" * 80)
    print(f"{'#':<3} | {'โฟลเดอร์/ชื่อ':<25} | {'ไฟล์วิดีโอ':<22} | {'วัน-เวลาโพสต์':<16} | {'สถานะ':<8}")
    print("-" * 80)
    for idx, it in enumerate(items, 1):
        name = (it.get("subfolder_name") or it.get("title") or f"Item {idx}")[:25]
        vid = (it.get("video_name") or os.path.basename(it.get("video_path", "")) or "ไม่พบวิดีโอ")[:22]
        sched = (it.get("scheduled_datetime") or it.get("datetime") or "N/A")[:16]
        status = "✅ พร้อม" if it.get("has_video", True) and it.get("video_path") else "⚠️ ขาดไฟล์"
        print(f"{idx:<3} | {name:<25} | {vid:<22} | {sched:<16} | {status:<8}")
    print("=" * 80 + "\n")

def run_meta_runner(
    main_folder: str = "",
    subfolders: str = "",
    prefix: str = "combined",
    start_date: str = "",
    start_hour: int = 18,
    target_url: str = "",
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    items: Optional[List[Dict[str, Any]]] = None,
    api_url: str = API_DEFAULT_URL,
    poll_interval: float = 2.5,
    timeout_seconds: int = 1800,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Submits a batch auto-post job to Meta via 6969 FastAPI and monitors progress like a runner.
    """
    api_url = api_url.rstrip("/")

    # 1. Resolve Items
    if not items:
        if not main_folder:
            raise ValueError("ต้องระบุ main_folder หรือส่ง items รายการโพสต์")
        print(f"🔍 [Runner] กำลังสแกนหาไฟล์วิดีโอและแคปชันใน: {main_folder}...")
        items = scan_meta_items(
            main_folder=main_folder,
            subfolders=subfolders,
            prefix=prefix,
            start_date=start_date,
            start_hour=start_hour,
            api_url=api_url
        )

    # Filter to items having videos
    valid_items = [it for it in items if it.get("video_path") and (it.get("checked", True) or it.get("has_video"))]
    if not valid_items:
        print("❌ ไม่พบไฟล์วิดีโอที่พร้อมสำหรับจัดตารางโพสต์")
        return {"ok": False, "error": "ไม่มีรายการวิดีโอที่พร้อมโพสต์", "total": 0}

    print_items_table(valid_items)

    if dry_run:
        print("💡 [Dry-Run] สแกนและแสดงแผนจัดตารางเวลาเรียบร้อย (ไม่ส่งคำสั่งรันจริง)")
        return {"ok": True, "dry_run": True, "total": len(valid_items), "items": valid_items}

    # 2. Submit to API /api/meta-autopost/run
    print(f"🚀 [Runner] กำลังส่งคำสั่ง Auto Post {len(valid_items)} รายการไปยังระบบ 6969...")
    run_payload = {
        "items": valid_items,
        "target_url": target_url,
        "delay_min": delay_min,
        "delay_max": delay_max
    }

    run_endpoint = f"{api_url}/api/meta-autopost/run"
    try:
        resp = requests.post(run_endpoint, json=run_payload, timeout=20)
    except Exception as ex:
        raise ConnectionError(f"ไม่สามารถเชื่อมต่อไปยังระบบ 6969 ที่ {api_url}: {ex}")

    if resp.status_code != 200:
        raise RuntimeError(f"API run failed ({resp.status_code}): {resp.text}")

    run_res = resp.json()
    print(f"⚡ [Runner] ได้รับการตอบรับ: {run_res.get('message', 'เริ่มกระบวนการเรียบร้อย')}")
    print(f"⏳ เริ่มติดตามความคืบหน้าแบบ Real-time (Poll ทุก {poll_interval}s)...\n")

    # 3. Poll Progress
    prog_endpoint = f"{api_url}/api/meta-autopost/progress"
    start_time = time.time()
    last_msg = ""
    last_percent = -1

    while time.time() - start_time < timeout_seconds:
        time.sleep(poll_interval)
        try:
            p_resp = requests.get(prog_endpoint, timeout=10)
            if p_resp.status_code == 200:
                prog = p_resp.json()
                status = prog.get("status", "idle")
                percent = prog.get("percent", 0)
                current = prog.get("current", 0)
                total = prog.get("total", len(valid_items))
                msg = prog.get("message", "")
                errors = prog.get("errors", [])

                if percent != last_percent or msg != last_msg:
                    bar_len = 24
                    filled = int(bar_len * (percent / 100))
                    bar = "█" * filled + "░" * (bar_len - filled)
                    print(f"[{status.upper()}] [{bar}] {percent}% ({current}/{total}) - {msg}")
                    last_percent = percent
                    last_msg = msg

                if status in ("completed", "completed_with_errors", "error"):
                    print("\n" + "=" * 80)
                    if status == "completed":
                        print(f"🎉 [Runner] สำเร็จสมบูรณ์! โพสต์ครบ {current}/{total} รายการ")
                    else:
                        print(f"⚠️ [Runner] เสร็จสิ้นด้วยสถานะ: {status} ({current}/{total} รายการ)")
                        if errors:
                            print("\nรายการข้อผิดพลาด:")
                            for err in errors:
                                print(f"  - {err}")
                    print("=" * 80)
                    return prog

        except Exception as poll_err:
            print(f"⚠️ Polling warning: {poll_err}")

    raise TimeoutError(f"การทำงานเกินกำหนดเวลา {timeout_seconds} วินาที")

def main():
    parser = argparse.ArgumentParser(description="Meta Reels Auto Post Runner (6969 Client)")
    parser.add_argument("--main-folder", default="", help="Main folder containing episode/asset subfolders")
    parser.add_argument("--subfolders", default="", help="Subfolder selector (e.g. 1-10 or 438 or 1,2,3)")
    parser.add_argument("--prefix", default="combined", help="Video prefix matching (e.g. combined, Part, final)")
    parser.add_argument("--start-date", default=datetime.now().strftime("%Y-%m-%d"), help="Schedule start date (YYYY-MM-DD)")
    parser.add_argument("--start-hour", type=int, default=18, help="Schedule start hour 0-23 (default: 18)")
    parser.add_argument("--target-url", default="", help="Target Meta Composer / Page URL")
    parser.add_argument("--delay-min", type=float, default=5.0, help="Min delay between posts (seconds)")
    parser.add_argument("--delay-max", type=float, default=15.0, help="Max delay between posts (seconds)")
    parser.add_argument("--api-url", default=API_DEFAULT_URL, help=f"6969 FastAPI base URL (default: {API_DEFAULT_URL})")
    parser.add_argument("--items-json", default="", help="Optional JSON string or file path containing items list")
    parser.add_argument("--dry-run", action="store_true", help="Scan and preview schedule table only without posting")

    args = parser.parse_args()

    items = None
    if args.items_json:
        raw = args.items_json.strip()
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                items = json.load(f)
        else:
            items = json.loads(raw)

    try:
        run_meta_runner(
            main_folder=args.main_folder,
            subfolders=args.subfolders,
            prefix=args.prefix,
            start_date=args.start_date,
            start_hour=args.start_hour,
            target_url=args.target_url,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
            items=items,
            api_url=args.api_url,
            dry_run=args.dry_run
        )
    except Exception as ex:
        print(f"\n❌ Error: {ex}")
        sys.exit(1)

if __name__ == "__main__":
    main()
