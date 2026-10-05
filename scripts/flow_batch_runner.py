#!/usr/bin/env python3
"""
FlowKit Headless Batch Video Generator CLI
Batch processes scenes across an entire episode or scene range in Google Flow.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import urllib.request

# Add script directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def notify_status_server(story_num, ep_str, current_scene=None, action="", status="RUNNING", fixing_scene=None, failed_scenes=None):
    payload = {
        "story": story_num,
        "ep": ep_str,
        "current_scene": current_scene,
        "current_action": action,
        "current_status": status,
        "fixing_scene": fixing_scene,
    }
    if failed_scenes is not None:
        payload["failed_scenes"] = failed_scenes
    state_file = os.path.join(os.path.dirname(__file__), "generation_status.json")
    try:
        cur = {}
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                cur = json.load(f)
        cur.update(payload)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8181/api/status/update",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass
from flow_video_generator import (
    generate_video_flow,
    dispatch_video_flow,
    monitor_video_batch,
    get_existing_video_ids,
    retrieve_signed_video_url,
    download_video,
    sanitize_prompt,
    sanitize_prompt_for_safety,
    ensure_video_settings,
    DEFAULT_API_BASE,
    DEFAULT_PROJECT_ID,
    log,
    upload_storyboard_image,
    inspect_tab_js,
    get_existing_flow_assets,
    check_asset_exists_in_flow,
    clear_prompt_box_completely
)

def parse_range(range_str: str) -> list[int]:
    """Parses range strings like '1-5', '1,2,5', 'EP01,EP02' into sorted list of scene integers."""
    result = set()
    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            sub = part.split('-')
            m1 = re.search(r'\d+', sub[0])
            m2 = re.search(r'\d+', sub[1])
            if m1 and m2:
                result.update(range(int(m1.group(0)), int(m2.group(0)) + 1))
        else:
            m = re.search(r'\d+', part)
            if m:
                result.add(int(m.group(0)))
    return sorted(list(result))

def find_all_episodes(story_path: str) -> list[int]:
    """Scans 6 - Storyboards directory to find all available EP numbers."""
    sb_base = os.path.join(story_path, "6 - Storyboards")
    if not os.path.isdir(sb_base):
        return [1]
    eps = []
    for d in os.listdir(sb_base):
        m = re.search(r'EP0*(\d+)', d, re.IGNORECASE)
        if m and os.path.isdir(os.path.join(sb_base, d)):
            eps.append(int(m.group(1)))
    return sorted(list(set(eps))) if eps else [1]

def parse_episodes_and_scenes(story_path: str, ep_arg: str, scenes_arg: Optional[str]) -> list[tuple[int, Optional[str]]]:
    """
    Parses episode and scene specifications into a list of (ep_num, scenes_filter_str).
    Supported syntaxes:
    1. Per-episode mapping in ep: --ep "1:4-10,18-19; 2:11-15,19-25"
    2. Per-episode mapping in scenes: --ep "1,2" --scenes "1:4-10,18-19; 2:11-15,19-25"
    3. Comma/range separated: --ep "1,2", --ep "1-3", --ep "all"
    """
    if ep_arg and (':' in ep_arg or ';' in ep_arg):
        parsed = []
        for chunk in ep_arg.split(';'):
            chunk = chunk.strip()
            if not chunk:
                continue
            if ':' in chunk:
                ep_part, sc_part = chunk.split(':', 1)
                m = re.search(r'\d+', ep_part)
                ep_n = int(m.group(0)) if m else 1
                parsed.append((ep_n, sc_part.strip()))
            else:
                m = re.search(r'\d+', chunk)
                ep_n = int(m.group(0)) if m else 1
                parsed.append((ep_n, scenes_arg))
        return parsed

    if ep_arg.strip().lower() == 'all':
        ep_list = find_all_episodes(story_path)
    else:
        ep_list = parse_range(ep_arg)
        if not ep_list:
            m = re.search(r'\d+', ep_arg)
            ep_list = [int(m.group(0))] if m else [1]

    if scenes_arg and (':' in scenes_arg or ';' in scenes_arg):
        sc_map = {}
        for chunk in scenes_arg.split(';'):
            chunk = chunk.strip()
            if not chunk:
                continue
            if ':' in chunk:
                ep_part, sc_part = chunk.split(':', 1)
                m = re.search(r'\d+', ep_part)
                if m:
                    sc_map[int(m.group(0))] = sc_part.strip()
        parsed = []
        for ep_n in ep_list:
            parsed.append((ep_n, sc_map.get(ep_n, None)))
        return parsed

    return [(ep_n, scenes_arg) for ep_n in ep_list]


def run_bulk_video_pipeline(
    scenes_data: list[dict],
    api_base: str = DEFAULT_API_BASE,
    project_id: str = DEFAULT_PROJECT_ID,
    aspect_ratio: str = "9:16",
    delay: float = None,
    timeout: int = 600,
    auto_retry_filters: bool = True,
    force: bool = False
) -> dict:
    """Executes Universal 4-Phase Bulk Video Generation Engine:
    Phase 1: Full-EP Bulk Dispatch (all prompts queued rapidly without stopping)
    Phase 2: Bulk Monitor & Collect (concurrent rendering wait & download)
    Phase 3: Filter Audit & Batch Sanitization (scans for failed/moderated scenes)
    Phase 4: Bulk Retry Dispatch (re-queues all sanitized scenes in a single pass)
    """
    log("="*60)
    log(f"🚀 [6969 Universal Video Pipeline] Starting bulk generation for {len(scenes_data)} scenes")
    log("="*60)

    # 0. Clean slate purge of prompt box
    log("\n🧹 Purging prompt box to guarantee clean state before video batch dispatch...")
    clear_prompt_box_completely(api_base)

    # 1. Lock settings: Video Mode, เฟรม Submode, Aspect Ratio, 6 วินาที Duration, x1 Output Count
    log(f"\n🔒 Verifying Google Flow video settings (Video -> เฟรม -> {aspect_ratio} -> 6 วินาที -> x1)...")
    ensure_video_settings(api_base, aspect=aspect_ratio, duration=6, submode="เฟรม", output_count=1)

    completed_sc_nums = set()
    results = []

    # Filter out already existing/verified files
    pending_scenes = []
    for sc in scenes_data:
        out_mp4 = sc.get("output_path", "")
        sc_num = sc.get("scene_num", 0)
        if not force and out_mp4 and os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 500000:
            log(f"  ✅ [Already Exists] Scene {sc_num:02d} verified on disk: {os.path.basename(out_mp4)}")
            completed_sc_nums.add(sc_num)
            results.append({"scene": sc_num, "status": "SUCCESS", "output": out_mp4, "size": os.path.getsize(out_mp4)})
        else:
            pending_scenes.append(sc)

    if not pending_scenes:
        log("🎉 All requested scenes already have verified video files! Done.")
        return {
            "success": True,
            "total": len(scenes_data),
            "completed": len(completed_sc_nums),
            "completed_scenes": sorted(list(completed_sc_nums)),
            "failed_scenes": [],
            "results": results
        }

    # =========================================================================
    # PHASE 1: FULL BULK DISPATCH (Queue all scenes consecutively without stopping)
    # =========================================================================
    log(f"\n⚡ [Phase 1: Bulk Dispatch] Queueing {len(pending_scenes)} scene(s) into Google Flow...")
    initial_ids = get_existing_video_ids(api_base)
    dispatched_items = []

    for q_idx, sc in enumerate(pending_scenes, start=1):
        sc_num = sc.get("scene_num", 0)
        img_path = sc.get("image_path", "")
        raw_prompt = sc.get("prompt", "")
        out_mp4 = sc.get("output_path", "")

        # Initial Tier 1 sanitization
        prompt_text = sanitize_prompt_for_safety(raw_prompt, tier=1)

        log(f"  ⚡ [{q_idx}/{len(pending_scenes)}] Dispatching Scene {sc_num:02d} with image: {os.path.basename(img_path)}...")
        try:
            dispatch_video_flow(
                image_path=img_path,
                prompt=prompt_text,
                api_base=api_base,
                project_id=project_id,
                aspect_ratio=aspect_ratio,
                wait_after_submit=0.5
            )
            dispatched_items.append({
                "scene_num": sc_num,
                "prompt": raw_prompt,
                "output_path": out_mp4,
                "image_path": img_path
            })
            log(f"     ✅ Queued Scene {sc_num:02d} into Google Flow queue!")
        except Exception as e:
            log(f"     ⚠️ Dispatch error on Scene {sc_num:02d}: {e}")
            results.append({"scene": sc_num, "status": "FAILED", "error": str(e)})

        actual_delay = random.uniform(0.5, 1.0) if delay is None else delay
        time.sleep(actual_delay)

    # =========================================================================
    # PHASE 2: BULK MONITOR & DOWNLOAD
    # =========================================================================
    if dispatched_items:
        log(f"\n⏳ [Phase 2: Bulk Monitor] Waiting for Google Flow concurrent video rendering ({len(dispatched_items)} scenes)...")
        try:
            matched_results = monitor_video_batch(
                api_base=api_base,
                batch_scenes=dispatched_items,
                timeout_seconds=timeout,
                initial_ids=initial_ids
            )
            for sc, tl in matched_results:
                media_id = tl.get("media_id")
                sc_num = sc.get("scene_num")
                out_path = sc.get("output_path")
                try:
                    video_url = retrieve_signed_video_url(api_base, media_id)
                    size_bytes = download_video(video_url, out_path)
                    results.append({"scene": sc_num, "status": "SUCCESS", "output": out_path, "size": size_bytes})
                    completed_sc_nums.add(sc_num)
                    log(f"  ✅ [Bulk Video OK] Scene {sc_num:02d} saved: {os.path.basename(out_path)} ({size_bytes / (1024*1024):.2f} MB)")
                except Exception as dl_err:
                    log(f"  ⚠️ Error downloading Scene {sc_num:02d}: {dl_err}")
        except Exception as b_err:
            log(f"  ⚠️ Bulk monitoring notice: {b_err}")

    # =========================================================================
    # PHASE 3: FILTER AUDIT & BATCH SANITIZATION
    # =========================================================================
    missed_items = [b for b in dispatched_items if b["scene_num"] not in completed_sc_nums]
    # Check if any missed item was actually downloaded
    real_missed = []
    for m_item in missed_items:
        m_out = m_item["output_path"]
        m_sc = m_item["scene_num"]
        if not force and os.path.exists(m_out) and os.path.getsize(m_out) > 500000:
            completed_sc_nums.add(m_sc)
            results.append({"scene": m_sc, "status": "SUCCESS", "output": m_out, "size": os.path.getsize(m_out)})
        else:
            real_missed.append(m_item)

    if real_missed and auto_retry_filters:
        log(f"\n🔍 [Phase 3: Filter Audit] Detected {len(real_missed)} scene(s) missed or flagged by policy filters: {[m['scene_num'] for m in real_missed]}")
        log(f"🧹 Sanitizing all {len(real_missed)} prompts (Tier 2 Moderation Bypass)...")

        # =========================================================================
        # PHASE 4: BULK RETRY DISPATCH (Re-queue all sanitized scenes together)
        # =========================================================================
        log(f"\n🔄 [Phase 4: Bulk Retry Dispatch] Dispatching sanitized repair batch...")
        retry_initial_ids = get_existing_video_ids(api_base)
        retry_items = []

        for r_idx, r_item in enumerate(real_missed, start=1):
            r_sc = r_item["scene_num"]
            r_img = r_item["image_path"]
            r_out = r_item["output_path"]
            sanitized_text = sanitize_prompt_for_safety(r_item["prompt"], tier=2)

            log(f"  ⚡ [Retry Queue {r_idx}/{len(real_missed)}] Dispatching Sanitized Scene {r_sc:02d}...")
            try:
                dispatch_video_flow(
                    image_path=r_img,
                    prompt=sanitized_text,
                    api_base=api_base,
                    project_id=project_id,
                    aspect_ratio=aspect_ratio,
                    wait_after_submit=3.0
                )
                retry_items.append({
                    "scene_num": r_sc,
                    "prompt": sanitized_text,
                    "output_path": r_out,
                    "image_path": r_img
                })
                log(f"     ✅ Re-queued Scene {r_sc:02d} with sanitized prompt!")
            except Exception as e:
                log(f"     ⚠️ Retry dispatch error on Scene {r_sc:02d}: {e}")

            time.sleep(random.uniform(0.5, 1.0) if delay is None else delay)

        if retry_items:
            log(f"\n⏳ [Phase 4: Bulk Retry Monitor] Waiting for repair batch rendering ({len(retry_items)} scenes)...")
            try:
                retry_matched = monitor_video_batch(
                    api_base=api_base,
                    batch_scenes=retry_items,
                    timeout_seconds=timeout,
                    initial_ids=retry_initial_ids
                )
                for sc, tl in retry_matched:
                    media_id = tl.get("media_id")
                    sc_num = sc.get("scene_num")
                    out_path = sc.get("output_path")
                    try:
                        video_url = retrieve_signed_video_url(api_base, media_id)
                        size_bytes = download_video(video_url, out_path)
                        results.append({"scene": sc_num, "status": "SUCCESS", "output": out_path, "size": size_bytes})
                        completed_sc_nums.add(sc_num)
                        log(f"  ✅ [Retry Video OK] Scene {sc_num:02d} saved: {os.path.basename(out_path)} ({size_bytes / (1024*1024):.2f} MB)")
                    except Exception as dl_err:
                        log(f"  ⚠️ Error downloading retry Scene {sc_num:02d}: {dl_err}")
            except Exception as r_err:
                log(f"  ⚠️ Retry batch monitoring notice: {r_err}")

    # Final tally
    all_target_nums = set(s.get("scene_num", 0) for s in scenes_data)
    failed_nums = sorted(list(all_target_nums - completed_sc_nums))

    log("\n" + "="*60)
    log(f"🏁 [6969 Universal Video Pipeline Complete] Success: {len(completed_sc_nums)}/{len(scenes_data)} scenes.")
    if failed_nums:
        log(f"⚠️ Failed/Missed scenes: {failed_nums}")
    log("="*60)

    return {
        "success": len(failed_nums) == 0,
        "total": len(scenes_data),
        "completed": len(completed_sc_nums),
        "completed_scenes": sorted(list(completed_sc_nums)),
        "failed_scenes": failed_nums,
        "results": results
    }

def main():
    parser = argparse.ArgumentParser(description="Headless Google Flow Batch Video Generator")
    parser.add_argument("--story-path", "-s", required=True, type=str, help="Root path of the Lakorn story folder")
    parser.add_argument("--ep", "-e", type=str, default="1", help="Episode number (e.g. 1 or EP01)")
    parser.add_argument("--scenes", "-sc", type=str, help="Scene range (e.g. '1-5' or '1,3,7' or 'all')")
    parser.add_argument("--prompt-dir", type=str, help="Custom directory containing animation prompt markdown files")
    parser.add_argument("--aspect-ratio", "-a", type=str, default="9:16", choices=["16:9", "9:16"], help="Aspect ratio (default: 9:16 for Lakorn)")
    parser.add_argument("--batch-size", "-b", type=int, default=25, help="Number of scenes to queue concurrently (default: 25)")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip scenes where MP4 already exists in Videos folder")
    parser.add_argument("--force", action="store_true", help="Force regenerate even if MP4 exists")
    parser.add_argument("--delay", "-d", type=float, default=None, help="Delay between prompt submissions in seconds (default: randomized 0.5-1.0s)")
    parser.add_argument("--timeout", type=int, default=600, help="Max timeout for batch video generation in seconds")
    parser.add_argument("--project-id", type=str, default=DEFAULT_PROJECT_ID, help="Google Flow project ID")
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE, help="FlowKit API base URL")
    parser.add_argument("--auto-capcut", action="store_true", default=True, help="Automatically clone CapCut template and assemble project after batch download")
    parser.add_argument("--no-capcut", dest="auto_capcut", action="store_false", help="Disable automatic CapCut project building")
    parser.add_argument("--skip-upload", action="store_true", help="Skip pre-uploading storyboard images if already in Google Flow library")

    args = parser.parse_args()

def process_single_episode_videos(story_path: str, ep_num: int, scenes_spec: Optional[str], args, story_num: str) -> dict:
    """Processes video generation for a single episode."""
    ep_str = f"EP{ep_num:02d}"
    sb_dir = os.path.join(story_path, "6 - Storyboards", ep_str)
    base_prompt_dir = args.prompt_dir or os.path.join(story_path, "4 - Animation Prompt")
    prompt_dir = os.path.join(base_prompt_dir, ep_str) if os.path.isdir(os.path.join(base_prompt_dir, ep_str)) else base_prompt_dir
    out_dir = os.path.join(story_path, "7 - Videos", ep_str)
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isdir(sb_dir):
        log(f"[ERROR] Storyboard directory does not exist: {sb_dir}")
        return {"ep": ep_num, "ep_str": ep_str, "total": 0, "completed": 0, "failed": 0, "failed_scenes": []}

    # Discover all storyboard image files
    available_scenes = {}
    for f in sorted(os.listdir(sb_dir)):
        m = re.match(r'^(?:EP\d+\s*-\s*)?(?:(\d+)\s*-\s*)?Scene\s*(\d+)\.(jpg|png|jpeg)$', f, re.I)
        if m:
            sc_idx = int(m.group(2)) if m.group(2) else int(m.group(1))
            available_scenes[sc_idx] = os.path.join(sb_dir, f)

    if not available_scenes:
        log(f"[ERROR] No storyboard images found in {sb_dir}")
        return {"ep": ep_num, "ep_str": ep_str, "total": 0, "completed": 0, "failed": 0, "failed_scenes": []}

    # Determine which scenes to process
    if not scenes_spec or scenes_spec.lower() == 'all':
        target_scene_nums = sorted(list(available_scenes.keys()))
    else:
        requested = parse_range(scenes_spec)
        target_scene_nums = [n for n in requested if n in available_scenes]

    log(f"\n{'='*60}")
    log(f"🎬 Processing Videos for {ep_str}: Found {len(available_scenes)} storyboards. Target scenes: {target_scene_nums}")
    log(f"{'='*60}")

    scenes_to_run = []
    skipped_existing = []
    for sc_idx in target_scene_nums:
        sc_str = f"{sc_idx:02d} - Scene {sc_idx:02d}"
        out_mp4 = os.path.join(out_dir, f"{sc_str}.mp4")
        if not args.force and args.skip_existing and os.path.isfile(out_mp4) and os.path.getsize(out_mp4) > 100000:
            log(f"Skipping {sc_str} — MP4 already exists ({os.path.getsize(out_mp4):,} bytes).")
            skipped_existing.append(sc_idx)
            continue
        scenes_to_run.append(sc_idx)

    # Pre-check and upload storyboard images (force re-upload if args.force is True)
    if scenes_to_run and not args.skip_upload:
        log(f"\n🔍 Pre-checking Google Flow library for {ep_str} storyboard assets...")
        existing_assets = get_existing_flow_assets(args.api_base)
        needed_uploads = []
        already_present = []

        for sc_idx in scenes_to_run:
            img_path = available_scenes[sc_idx]
            fname = os.path.basename(img_path)
            if not args.force and check_asset_exists_in_flow(args.api_base, fname, existing_assets):
                already_present.append(sc_idx)
            else:
                needed_uploads.append(sc_idx)

        if already_present:
            log(f"  ✅ Found {len(already_present)} scenes already on Google Flow (Skipping upload): {already_present}")
        if needed_uploads:
            log(f"  📤 Uploading {len(needed_uploads)} fresh storyboard images to Google Flow library...")
            for sc_idx in needed_uploads:
                img_path = available_scenes[sc_idx]
                for attempt in range(3):
                    try:
                        upload_storyboard_image(args.api_base, img_path, args.project_id, force=True)
                        break
                    except Exception as e:
                        if attempt == 2:
                            log(f"⚠️ Pre-upload failed for Scene {sc_idx} after 3 attempts: {e}")
                        time.sleep(2)
            log("Reloading Google Flow tab once so newly uploaded assets appear in the UI...")
            try:
                inspect_tab_js(args.api_base, "window.location.reload()")
                time.sleep(8)
            except Exception as re_err:
                log(f"Notice on reload: {re_err}")
        else:
            log("  🎉 All target storyboard images are already present on Google Flow!")
    elif args.skip_upload:
        log("Skipping storyboard image upload as requested (--skip-upload).")

    # Build scenes_data payload
    scenes_data = []
    for sc_idx in scenes_to_run:
        sc_str = f"{sc_idx:02d} - Scene {sc_idx:02d}"
        img_path = available_scenes[sc_idx]
        out_mp4 = os.path.join(out_dir, f"{sc_str}.mp4")
        prompt_file = os.path.join(prompt_dir, f"{sc_str}.md")
        if not os.path.isfile(prompt_file):
            log(f"  ⚠️ Warning: Prompt file not found: {prompt_file}, skipping.")
            continue
        with open(prompt_file, "r", encoding="utf-8") as pf:
            prompt_text = pf.read().strip()
        scenes_data.append({
            "scene_num": sc_idx,
            "prompt": prompt_text,
            "image_path": img_path,
            "output_path": out_mp4
        })

    # Run Universal Bulk Pipeline in Chunks
    batch_size = max(1, args.batch_size) if hasattr(args, 'batch_size') and args.batch_size else 25
    all_results = []
    completed_sc_nums = set()
    failed_sc_nums = set()

    chunks = [scenes_data[i:i + batch_size] for i in range(0, len(scenes_data), batch_size)]
    for chunk_idx, chunk in enumerate(chunks, start=1):
        scenes_in_chunk = [s['scene_num'] for s in chunk]
        notify_status_server(story_num, ep_str, current_scene=scenes_in_chunk[0] if scenes_in_chunk else None, action=f"กำลังสร้างวิดีโอ {ep_str} Batch {chunk_idx}/{len(chunks)} (ฉาก {scenes_in_chunk})", status="RUNNING")
        log(f"\n{'='*60}")
        log(f" 🚀 [{ep_str}] Processing Batch {chunk_idx}/{len(chunks)} ({len(chunk)} scenes: {[s['scene_num'] for s in chunk]})")
        log(f"{'='*60}")
        sub_res = run_bulk_video_pipeline(
            scenes_data=chunk,
            api_base=args.api_base,
            project_id=args.project_id,
            aspect_ratio=args.aspect_ratio,
            delay=args.delay,
            timeout=args.timeout,
            auto_retry_filters=True,
            force=args.force
        )
        for r in sub_res.get("results", []):
            all_results.append(r)
            if r.get("status") == "SUCCESS":
                completed_sc_nums.add(r.get("scene"))
            else:
                failed_sc_nums.add(r.get("scene"))

        notify_status_server(story_num, ep_str, current_scene=None, action=f"สร้างวิดีโอ {ep_str} สำเร็จแล้ว {len(completed_sc_nums)}/{len(scenes_data)} ฉาก", status="RUNNING")

        if chunk_idx < len(chunks):
            log("Cooling down 4 seconds between batches...")
            time.sleep(4.0)

    final_status = "COMPLETED" if len(completed_sc_nums) == len(scenes_data) else "FAILED"
    notify_status_server(story_num, ep_str, current_scene=None, action=f"สร้างวิดีโอ {ep_str} เสร็จสิ้น ({len(completed_sc_nums)}/{len(scenes_data)} ฉาก)", status=final_status)

    # Trigger CapCut automatic project builder if requested
    if args.auto_capcut:
        target_proj_name = f"{story_num}-{ep_num}"
        log("\n==================================================")
        log(f" Auto-Triggering CapCut Lakorn Builder -> Project '{target_proj_name}'")
        log("==================================================")
        try:
            from capcut_lakorn_builder import build_lakorn_project
            build_lakorn_project(story_num=story_num, ep_name=ep_str, target_project_name=target_proj_name)
            log(f"CapCut Project '{target_proj_name}' built and ready successfully!")
        except Exception as e:
            log(f"Warning: Failed to auto-build CapCut project: {e}")

    return {
        "ep": ep_num,
        "ep_str": ep_str,
        "total": len(scenes_data),
        "completed": len(completed_sc_nums),
        "skipped": len(skipped_existing),
        "failed": len(failed_sc_nums - completed_sc_nums),
        "completed_scenes": sorted(list(completed_sc_nums)),
        "failed_scenes": sorted(list(failed_sc_nums - completed_sc_nums)),
        "results": all_results
    }


def main():
    parser = argparse.ArgumentParser(description="Headless Google Flow Batch Video Generator")
    parser.add_argument("--story-path", "-s", required=True, help="Root path of the Lakorn story folder")
    parser.add_argument("--ep", "-e", default="1", help="Episode number(s) (e.g. '1', '1,2', '1-3', 'all', or per-EP: '1:4-10; 2:11-20')")
    parser.add_argument("--scenes", "-sc", default=None, help="Scene range (e.g. '1-5', 'all', or per-EP '1:4-10; 2:11-20')")
    parser.add_argument("--prompt-dir", default=None, help="Custom directory containing animation prompt markdown files")
    parser.add_argument("--aspect-ratio", "-a", choices=["16:9", "9:16"], default="9:16", help="Aspect ratio (default: 9:16 for Lakorn)")
    parser.add_argument("--batch-size", "-b", type=int, default=25, help="Number of scenes to queue concurrently (default: 25)")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip scenes where MP4 already exists in Videos folder")
    parser.add_argument("--force", action="store_true", help="Force regenerate even if MP4 exists")
    parser.add_argument("--delay", "-d", type=float, default=None, help="Delay between prompt submissions in seconds (default: randomized 0.5-1.0s)")
    parser.add_argument("--timeout", type=int, default=600, help="Max timeout for batch video generation in seconds")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="Google Flow project ID")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="FlowKit API base URL")
    parser.add_argument("--auto-capcut", action="store_true", help="Automatically clone CapCut template and assemble project after batch download")
    parser.add_argument("--no-capcut", action="store_true", help="Disable automatic CapCut project building")
    parser.add_argument("--skip-upload", action="store_true", help="Skip pre-uploading storyboard images if already in Google Flow library")

    args = parser.parse_args()

    story_num = os.path.basename(os.path.normpath(args.story_path))
    episodes_to_run = parse_episodes_and_scenes(args.story_path, args.ep, args.scenes)
    plan_desc = [f"EP{ep:02d} ({sc if sc else 'all'})" for ep, sc in episodes_to_run]
    log(f"📋 Video Generation Execution Plan: {plan_desc}")

    all_ep_results = []
    for ep_num, ep_scenes in episodes_to_run:
        res = process_single_episode_videos(
            story_path=args.story_path,
            ep_num=ep_num,
            scenes_spec=ep_scenes,
            args=args,
            story_num=story_num
        )
        all_ep_results.append(res)

    log("\n" + "="*60)
    log("🏁 ALL EPISODE VIDEOS PROCESSED! FINAL SUMMARY:")
    log(f"{'Episode':<10} | {'Target':<8} | {'Completed':<10} | {'Skipped':<8} | {'Failed':<8}")
    log("-" * 60)
    total_completed = 0
    total_skipped = 0
    total_failed = 0
    for r in all_ep_results:
        log(f"{r['ep_str']:<10} | {r['total']:<8} | {r['completed']:<10} | {r['skipped']:<8} | {r['failed']:<8}")
        total_completed += r['completed']
        total_skipped += r['skipped']
        total_failed += r['failed']
    log("-" * 60)
    log(f"TOTAL: Completed={total_completed}, Skipped={total_skipped}, Failed={total_failed}")
    log("="*60)

if __name__ == "__main__":
    main()
