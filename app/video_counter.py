import os
import re
from typing import Any, Optional

from app.seedance import (
    parse_seedance_filter,
    extract_leading_number,
    log
)

VALID_VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.mkv', '.webm', '.avi', '.flv', '.m4v', '.wmv', '.ts'
}

IGNORED_FILE_SUFFIXES = (
    '.tmp', '.part', '.crdownload', '.bak', '.log', '.json', '.md', '.txt'
)


def natural_sort_key(name: str):
    """Generates natural sort key so that numbers are ordered numerically (1, 2, 10, ...)."""
    base = os.path.basename(name)
    num = extract_leading_number(base)
    parts = [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', base)]
    if num is not None:
        return (0, num, parts)
    return (1, 0, parts)


def count_videos_in_folder(folder_path: str) -> list[str]:
    """
    Finds and returns a naturally sorted list of video filenames in folder_path.
    If no video files are found directly in folder_path, it inspects immediate subdirectories
    (e.g., 'videos/', 'output/', 'results/').
    Excludes hidden files (.DS_Store, ._*) and incomplete download/temp files.
    """
    if not os.path.isdir(folder_path):
        return []

    root_videos = []
    try:
        for f in os.listdir(folder_path):
            if f.startswith('.'):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in VALID_VIDEO_EXTENSIONS and not f.endswith(IGNORED_FILE_SUFFIXES):
                root_videos.append(f)
    except Exception as e:
        log(f"[Video Counter] Error listing folder {folder_path}: {e}")

    if root_videos:
        root_videos.sort(key=natural_sort_key)
        return root_videos

    # If no videos directly in root, check immediate subfolders
    sub_videos = []
    try:
        for entry in sorted(os.listdir(folder_path)):
            if entry.startswith('.'):
                continue
            sub_path = os.path.join(folder_path, entry)
            if os.path.isdir(sub_path):
                for f in os.listdir(sub_path):
                    if f.startswith('.'):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    if ext in VALID_VIDEO_EXTENSIONS and not f.endswith(IGNORED_FILE_SUFFIXES):
                        sub_videos.append(f"{entry}/{f}")
    except Exception as e:
        log(f"[Video Counter] Error listing subdirectories in {folder_path}: {e}")

    sub_videos.sort(key=natural_sort_key)
    return sub_videos


def get_video_counter_summary(main_folder: str, subfolders_str: str = "") -> dict[str, Any]:
    """
    Quickly scans subfolders matching the filter in main_folder.
    Used for live badge and summary calculation in the UI.
    """
    if not main_folder or not os.path.isdir(main_folder):
        return {
            "ok": False,
            "error": f"ไม่พบโฟลเดอร์หลัก: {main_folder}" if main_folder else "ยังไม่ได้ระบุโฟลเดอร์หลัก",
            "total_folders": 0,
            "folders": []
        }

    filter_data = parse_seedance_filter(subfolders_str)
    folder_targets = filter_data.get("folder_targets", set())

    all_subdirs = []
    try:
        entries = sorted(os.listdir(main_folder))
    except Exception as ex:
        return {
            "ok": False,
            "error": f"ไม่สามารถเปิดอ่านโฟลเดอร์: {ex}",
            "total_folders": 0,
            "folders": []
        }

    for entry in entries:
        full_path = os.path.join(main_folder, entry)
        if os.path.isdir(full_path) and not entry.startswith('.'):
            num = extract_leading_number(entry)
            if folder_targets:
                if num is not None and num in folder_targets:
                    all_subdirs.append((num, entry, full_path))
            else:
                all_subdirs.append((num if num is not None else 999999, entry, full_path))

    # If no child directories exist, check if main_folder itself contains videos
    if not all_subdirs:
        direct_videos = count_videos_in_folder(main_folder)
        if direct_videos:
            base_name = os.path.basename(main_folder.rstrip(os.sep))
            num = extract_leading_number(base_name)
            all_subdirs.append((num if num is not None else 1, base_name, main_folder))

    all_subdirs.sort(key=lambda x: (x[0] is None, x[0], x[1]))

    return {
        "ok": True,
        "total_folders": len(all_subdirs),
        "folders": [{"name": s[1], "num": s[0], "path": s[2]} for s in all_subdirs]
    }


def get_video_counter_report(
    main_folder: str,
    subfolders_str: str = "",
    target_count: int = 10
) -> dict[str, Any]:
    """
    Scans subfolders, counts video files, compares against target_count,
    and returns a structured report including lists of below-threshold folders
    and an executive text report suitable for clipboard copying.
    """
    if not main_folder or not os.path.isdir(main_folder):
        return {
            "ok": False,
            "error": f"ไม่พบโฟลเดอร์หลัก: {main_folder}" if main_folder else "กรุณาระบุโฟลเดอร์หลัก",
            "total_folders": 0,
            "total_videos": 0,
            "target_count": target_count,
            "met_count": 0,
            "below_count": 0,
            "all_met": False,
            "folders": [],
            "below_target_folders": [],
            "met_target_folders": [],
            "text_report": ""
        }

    try:
        target_count = max(1, int(target_count))
    except (ValueError, TypeError):
        target_count = 10

    summary = get_video_counter_summary(main_folder, subfolders_str)
    if not summary.get("ok"):
        return {
            "ok": False,
            "error": summary.get("error", "ไม่สามารถดึงข้อมูลโฟลเดอร์ได้"),
            "total_folders": 0,
            "total_videos": 0,
            "target_count": target_count,
            "met_count": 0,
            "below_count": 0,
            "all_met": False,
            "folders": [],
            "below_target_folders": [],
            "met_target_folders": [],
            "text_report": ""
        }

    raw_folders = summary.get("folders", [])
    if not raw_folders:
        return {
            "ok": True,
            "message": "ไม่พบโฟลเดอร์ย่อยที่ตรงตามเงื่อนไข",
            "total_folders": 0,
            "total_videos": 0,
            "target_count": target_count,
            "met_count": 0,
            "below_count": 0,
            "all_met": False,
            "folders": [],
            "below_target_folders": [],
            "met_target_folders": [],
            "text_report": f"⚠️ ไม่พบโฟลเดอร์ย่อยที่ตรงกับเงื่อนไขใน: {main_folder}"
        }

    folders_result = []
    below_target_folders = []
    met_target_folders = []
    total_videos = 0

    for item in raw_folders:
        folder_name = item["name"]
        folder_num = item["num"]
        folder_path = item["path"]

        videos = count_videos_in_folder(folder_path)
        v_count = len(videos)
        total_videos += v_count

        diff = v_count - target_count
        is_met = v_count >= target_count
        missing_count = max(0, target_count - v_count)

        folder_data = {
            "folder_name": folder_name,
            "folder_num": folder_num,
            "folder_path": folder_path,
            "video_count": v_count,
            "target_count": target_count,
            "is_met": is_met,
            "diff": diff,
            "missing_count": missing_count,
            "video_files": videos
        }

        folders_result.append(folder_data)

        if is_met:
            met_target_folders.append(folder_data)
        else:
            below_target_folders.append(folder_data)

    total_folders = len(folders_result)
    met_count = len(met_target_folders)
    below_count = len(below_target_folders)
    all_met = (below_count == 0 and total_folders > 0)

    # Build Executive Text Report
    report_lines = []
    report_lines.append("📊 รายงานการตรวจสอบจำนวนวิดีโอ (Video Counter Report)")
    report_lines.append(f"📁 โฟลเดอร์หลัก: {main_folder}")
    if subfolders_str.strip():
        report_lines.append(f"🎯 โฟลเดอร์ที่ตรวจสอบ: {subfolders_str.strip()}")
    report_lines.append(f"🎯 เกณฑ์เป้าหมาย: {target_count} วิดีโอ/โฟลเดอร์")
    report_lines.append("=" * 50)
    report_lines.append("📌 สรุปภาพรวม:")
    report_lines.append(f"• โฟลเดอร์ทั้งหมดที่ตรวจสอบ: {total_folders} โฟลเดอร์")
    report_lines.append(f"• ✅ ครบตามเกณฑ์: {met_count} โฟลเดอร์")
    report_lines.append(f"• ⚠️ ไม่ถึงเกณฑ์: {below_count} โฟลเดอร์")
    report_lines.append(f"• 🎬 รวมวิดีโอทั้งหมด: {total_videos} ไฟล์")
    report_lines.append("=" * 50)
    report_lines.append("")

    # Section: Below Threshold Alert
    if below_count > 0:
        report_lines.append(f"⚠️ รายชื่อโฟลเดอร์ที่ไม่ถึงเกณฑ์ที่กำหนด ({below_count} โฟลเดอร์):")
        for bf in below_target_folders:
            report_lines.append(
                f"  ❌ โฟลเดอร์ {bf['folder_name']}: มี {bf['video_count']} วิดีโอ "
                f"(ขาดอีก {bf['missing_count']} วิดีโอ เพื่อให้ครบ {target_count})"
            )
    else:
        report_lines.append(f"🎉 ยอดเยี่ยม! ทุกโฟลเดอร์มีจำนวนวิดีโอครบตามเกณฑ์ที่กำหนด (>= {target_count} ไฟล์)")
    report_lines.append("")

    # Section: All Folders Breakdown
    report_lines.append("📋 รายละเอียดจำนวนวิดีโอทุกโฟลเดอร์:")
    for f in folders_result:
        if f["is_met"]:
            surplus_str = f" (+{f['diff']})" if f["diff"] > 0 else ""
            status_str = f"✅ ครบเกณฑ์{surplus_str}"
        else:
            status_str = f"⚠️ ไม่ถึงเกณฑ์ (ขาด {f['missing_count']} ไฟล์)"
        report_lines.append(f"  • โฟลเดอร์ {f['folder_name']}: {f['video_count']}/{target_count} ไฟล์ - {status_str}")

    text_report = "\n".join(report_lines)

    return {
        "ok": True,
        "main_folder": main_folder,
        "subfolders_str": subfolders_str,
        "target_count": target_count,
        "total_folders": total_folders,
        "total_videos": total_videos,
        "met_count": met_count,
        "below_count": below_count,
        "all_met": all_met,
        "folders": folders_result,
        "below_target_folders": below_target_folders,
        "met_target_folders": met_target_folders,
        "text_report": text_report
    }
