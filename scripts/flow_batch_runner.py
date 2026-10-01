#!/usr/bin/env python3
"""
FlowKit Headless Batch Video Generator CLI
Batch processes scenes across an entire episode or scene range in Google Flow.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Add script directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    check_asset_exists_in_flow
)

def parse_range(range_str: str) -> list[int]:
    """Parses range strings like '1-5', '1,2,5', '1-3,5' into sorted list of scene integers."""
    result = set()
    for part in range_str.split(','):
        part = part.strip()
        if '-' in part:
            sub = part.split('-')
            result.update(range(int(sub[0]), int(sub[1]) + 1))
        elif part.isdigit():
            result.add(int(part))
    return sorted(list(result))

def run_bulk_video_pipeline(
    scenes_data: list[dict],
    api_base: str = DEFAULT_API_BASE,
    project_id: str = DEFAULT_PROJECT_ID,
    aspect_ratio: str = "9:16",
    delay: float = 3.0,
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

    # 1. Lock settings: Video Mode, Aspect Ratio, x1 Output Count
    log(f"\n🔒 Verifying Google Flow video settings (Video Mode, {aspect_ratio}, x1 single video)...")
    ensure_video_settings(api_base, aspect=aspect_ratio, output_count=1)

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
                wait_after_submit=3.0
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

        time.sleep(delay)

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

            time.sleep(delay)

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
    parser.add_argument("--batch-size", "-b", type=int, default=5, help="Number of scenes to queue concurrently (default: 5)")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip scenes where MP4 already exists in Videos folder")
    parser.add_argument("--force", action="store_true", help="Force regenerate even if MP4 exists")
    parser.add_argument("--delay", "-d", type=int, default=3, help="Delay between prompt submissions in seconds")
    parser.add_argument("--timeout", type=int, default=600, help="Max timeout for batch video generation in seconds")
    parser.add_argument("--project-id", type=str, default=DEFAULT_PROJECT_ID, help="Google Flow project ID")
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE, help="FlowKit API base URL")
    parser.add_argument("--auto-capcut", action="store_true", default=True, help="Automatically clone CapCut template and assemble project after batch download")
    parser.add_argument("--no-capcut", dest="auto_capcut", action="store_false", help="Disable automatic CapCut project building")
    parser.add_argument("--skip-upload", action="store_true", help="Skip pre-uploading storyboard images if already in Google Flow library")

    args = parser.parse_args()

    ep_num = int(re.search(r'\d+', args.ep).group(0)) if re.search(r'\d+', args.ep) else 1
    ep_str = f"EP{ep_num:02d}"

    sb_dir = os.path.join(args.story_path, "6 - Storyboards", ep_str)
    base_prompt_dir = args.prompt_dir or os.path.join(args.story_path, "4 - Animation Prompt")
    prompt_dir = os.path.join(base_prompt_dir, ep_str) if os.path.isdir(os.path.join(base_prompt_dir, ep_str)) else base_prompt_dir
    out_dir = os.path.join(args.story_path, "7 - Videos", ep_str)
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isdir(sb_dir):
        print(f"[ERROR] Storyboard directory does not exist: {sb_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover all storyboard image files
    available_scenes = {}
    for f in sorted(os.listdir(sb_dir)):
        m = re.match(r'^(?:EP\d+\s*-\s*)?(?:(\d+)\s*-\s*)?Scene\s*(\d+)\.(jpg|png|jpeg)$', f, re.I)
        if m:
            sc_idx = int(m.group(2)) if m.group(2) else int(m.group(1))
            available_scenes[sc_idx] = os.path.join(sb_dir, f)

    if not available_scenes:
        print(f"[ERROR] No storyboard images found in {sb_dir}", file=sys.stderr)
        sys.exit(1)

    # Determine which scenes to process
    target_scene_nums = []
    if not args.scenes or args.scenes.lower() == 'all':
        target_scene_nums = sorted(list(available_scenes.keys()))
    else:
        requested = parse_range(args.scenes)
        target_scene_nums = [n for n in requested if n in available_scenes]

    log(f"Found {len(available_scenes)} storyboard images in {ep_str}. Target scenes to process: {target_scene_nums}")

    # 1. Identify which scenes actually need generation
    scenes_to_run = []
    results = []
    for sc_idx in target_scene_nums:
        sc_str = f"{sc_idx:02d} - Scene {sc_idx:02d}"
        out_mp4 = os.path.join(out_dir, f"{sc_str}.mp4")
        if not args.force and args.skip_existing and os.path.isfile(out_mp4) and os.path.getsize(out_mp4) > 100000:
            log(f"Skipping {sc_str} — MP4 already exists ({os.path.getsize(out_mp4):,} bytes).")
            results.append({"scene": sc_idx, "status": "SKIPPED_EXISTING", "output": out_mp4})
            continue
        scenes_to_run.append(sc_idx)

    # 2. Pre-check and upload storyboard images (skip duplicate images already on Flow)
    if scenes_to_run and not args.skip_upload:
        log("\n🔍 Checking Google Flow library for existing storyboard assets before upload...")
        existing_assets = get_existing_flow_assets(args.api_base)
        needed_uploads = []
        already_present = []

        for sc_idx in scenes_to_run:
            img_path = available_scenes[sc_idx]
            fname = os.path.basename(img_path)
            if check_asset_exists_in_flow(args.api_base, fname, existing_assets):
                already_present.append(sc_idx)
            else:
                needed_uploads.append(sc_idx)

        if already_present:
            log(f"  ✅ Found {len(already_present)} scenes already on Google Flow (Skipping upload): {already_present}")
        if needed_uploads:
            log(f"  📤 Found {len(needed_uploads)} scenes missing from Google Flow: {needed_uploads}")
            log(f"Pre-uploading {len(needed_uploads)} missing storyboard images to library (zero page reloads)...")
            for sc_idx in needed_uploads:
                img_path = available_scenes[sc_idx]
                for attempt in range(3):
                    try:
                        upload_storyboard_image(args.api_base, img_path, args.project_id)
                        break
                    except Exception as e:
                        if attempt == 2:
                            log(f"⚠️ Pre-upload failed for Scene {sc_idx} after 3 attempts: {e}")
                        time.sleep(2)
            log("Reloading Google Flow tab once so newly uploaded assets appear in the UI...")
            try:
                import subprocess
                subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to reload active tab of front window'], check=False)
                time.sleep(6)
            except Exception as re_err:
                log(f"Notice on reload: {re_err}")
        else:
            log("  🎉 All target storyboard images are already present on Google Flow! 100% duplicate uploads avoided.")
    elif args.skip_upload:
        log("Skipping storyboard image upload as requested (--skip-upload).")

    # 3. Build scenes_data payload
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

    # 4. Run Universal Bulk Pipeline in Chunks (respecting batch_size to prevent Flow queue overload)
    batch_size = max(1, args.batch_size) if hasattr(args, 'batch_size') and args.batch_size else 4
    all_results = []
    completed_sc_nums = set()
    failed_sc_nums = set()

    chunks = [scenes_data[i:i + batch_size] for i in range(0, len(scenes_data), batch_size)]
    for chunk_idx, chunk in enumerate(chunks, start=1):
        log(f"\n{'='*60}")
        log(f" 🚀 Processing Batch {chunk_idx}/{len(chunks)} ({len(chunk)} scenes: {[s['scene_num'] for s in chunk]})")
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

        if chunk_idx < len(chunks):
            log("Cooling down 4 seconds between batches...")
            time.sleep(4.0)

    pipeline_res = {
        "success": len(completed_sc_nums) == len(scenes_data),
        "total": len(scenes_data),
        "completed": len(completed_sc_nums),
        "completed_scenes": sorted(list(completed_sc_nums)),
        "failed_scenes": sorted(list(failed_sc_nums - completed_sc_nums)),
        "results": all_results
    }

    log("\n==================================================")
    log(" Batch Video Generation Summary")
    log("==================================================")
    print(json.dumps(pipeline_res, indent=2, ensure_ascii=False))

    # Trigger CapCut automatic project builder
    if args.auto_capcut:
        story_num = os.path.basename(os.path.normpath(args.story_path))
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

if __name__ == "__main__":
    main()
