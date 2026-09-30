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
                try:
                    upload_storyboard_image(args.api_base, img_path, args.project_id)
                except Exception as e:
                    log(f"Notice on pre-uploading Scene {sc_idx}: {e}")
        else:
            log("  🎉 All target storyboard images are already present on Google Flow! 100% duplicate uploads avoided.")
    elif args.skip_upload:
        log("Skipping storyboard image upload as requested (--skip-upload).")

    # 3. Process scenes in batches of batch_size (default: 5)
    batch_size = max(1, args.batch_size)
    batches = [scenes_to_run[i:i + batch_size] for i in range(0, len(scenes_to_run), batch_size)]

    log(f"\n🚀 Starting video generation: {len(batches)} batches for {len(scenes_to_run)} scenes (Batch size: {batch_size})")

    for batch_idx, batch in enumerate(batches):
        log("\n" + "="*50)
        log(f"📦 VIDEO BATCH {batch_idx + 1}/{len(batches)} : Scenes {batch}")
        log("="*50)

        if len(batch) > 1 and batch_size > 1:
            # 3.1 Snapshot existing video IDs before dispatching
            initial_ids = get_existing_video_ids(args.api_base)
            log(f"  Recorded {len(initial_ids)} existing video tiles before dispatching.")

            # 3.2 Dispatch all scenes in batch rapidly with storyboard images attached
            batch_items = []
            for q_idx, sc_idx in enumerate(batch, 1):
                sc_str = f"{sc_idx:02d} - Scene {sc_idx:02d}"
                img_path = available_scenes[sc_idx]
                out_mp4 = os.path.join(out_dir, f"{sc_str}.mp4")

                prompt_file = os.path.join(prompt_dir, f"{sc_str}.md")
                if not os.path.isfile(prompt_file):
                    log(f"  ⚠️ Warning: Prompt file not found: {prompt_file}, skipping.")
                    results.append({"scene": sc_idx, "status": "FAILED", "error": "Prompt file not found"})
                    continue

                with open(prompt_file, "r", encoding="utf-8") as pf:
                    prompt_text = pf.read().strip()

                log(f"\n  ⚡ [Queue {q_idx}/{len(batch)}] Dispatching Scene {sc_idx:02d} with image: {os.path.basename(img_path)}...")
                try:
                    dispatch_video_flow(
                        image_path=img_path,
                        prompt=prompt_text,
                        api_base=args.api_base,
                        project_id=args.project_id,
                        aspect_ratio=args.aspect_ratio,
                        wait_after_submit=3.0
                    )
                    batch_items.append({
                        "scene_num": sc_idx,
                        "prompt": prompt_text,
                        "output_path": out_mp4,
                        "image_path": img_path
                    })
                    log(f"     ✅ Queued Scene {sc_idx:02d} into Google Flow with storyboard chip attached!")
                except Exception as e:
                    log(f"     ⚠️ Dispatch error on Scene {sc_idx:02d}: {e}")
                    results.append({"scene": sc_idx, "status": "FAILED", "error": str(e)})

                time.sleep(args.delay)

            # 3.3 Concurrently monitor and download rendered video batch
            if batch_items:
                log(f"\n  ⏳ All {len(batch_items)} video prompts queued with storyboard chips! Waiting for Google Flow concurrent video rendering...")
                try:
                    matched_results = monitor_video_batch(
                        api_base=args.api_base,
                        batch_scenes=batch_items,
                        timeout_seconds=args.timeout,
                        initial_ids=initial_ids
                    )
                    for sc, tl in matched_results:
                        media_id = tl.get("media_id")
                        sc_num = sc.get("scene_num")
                        out_path = sc.get("output_path")
                        try:
                            video_url = retrieve_signed_video_url(args.api_base, media_id)
                            size_bytes = download_video(video_url, out_path)
                            results.append({"scene": sc_num, "status": "SUCCESS", "output": out_path, "size": size_bytes})
                            log(f"  ✅ [Batch Video OK] Scene {sc_num:02d} saved: {os.path.basename(out_path)} ({size_bytes / (1024*1024):.2f} MB)")
                        except Exception as dl_err:
                            log(f"  ⚠️ Error downloading Scene {sc_num:02d}: {dl_err}")
                            results.append({"scene": sc_num, "status": "FAILED", "error": str(dl_err)})
                except Exception as b_err:
                    log(f"  ⚠️ Batch monitoring error: {b_err}")
                    for bi in batch_items:
                        results.append({"scene": bi["scene_num"], "status": "FAILED", "error": str(b_err)})
        else:
            # Single-scene sequential fallback
            for sc_idx in batch:
                sc_str = f"{sc_idx:02d} - Scene {sc_idx:02d}"
                img_path = available_scenes[sc_idx]
                out_mp4 = os.path.join(out_dir, f"{sc_str}.mp4")

                prompt_file = os.path.join(prompt_dir, f"{sc_str}.md")
                if not os.path.isfile(prompt_file):
                    log(f"Warning: Prompt file not found: {prompt_file}, skipping.")
                    results.append({"scene": sc_idx, "status": "FAILED", "error": "Prompt file not found"})
                    continue

                with open(prompt_file, "r", encoding="utf-8") as pf:
                    prompt_text = pf.read().strip()

                log(f"\n  🎬 Rendering Scene {sc_idx:02d} ({args.aspect_ratio}) [Single Scene] -> {os.path.basename(img_path)}...")
                try:
                    gen_res = generate_video_flow(
                        image_path=img_path,
                        prompt=prompt_text,
                        output_path=out_mp4,
                        api_base=args.api_base,
                        project_id=args.project_id,
                        aspect_ratio=args.aspect_ratio,
                        skip_upload=True
                    )
                    results.append({"scene": sc_idx, "status": "SUCCESS", "output": out_mp4, "size": gen_res.get("file_size_bytes")})
                    log(f"  ✅ Successfully rendered Scene {sc_idx:02d}! Saved to: {os.path.basename(out_mp4)}")
                except Exception as e:
                    log(f"  ⚠️ ERROR on Scene {sc_idx}: {e}")
                    results.append({"scene": sc_idx, "status": "FAILED", "error": str(e)})

    log("\n==================================================")
    log(" Batch Video Generation Summary")
    log("==================================================")
    print(json.dumps(results, indent=2, ensure_ascii=False))

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
