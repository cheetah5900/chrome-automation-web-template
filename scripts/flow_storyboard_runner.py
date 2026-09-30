#!/usr/bin/env python3
"""
FlowKit Universal Storyboard Image Generator CLI
Centralized Background Image Generation Engine for all Channels (Lakorn, Stickman, etc.)
Location: chrome-automation-web-template/scripts/flow_storyboard_runner.py
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_API_BASE = "http://127.0.0.1:6969"
DEFAULT_PROJECT_ID = "21a1632e-9926-46fa-954c-240d71d78f41"  # ละคร

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def error_exit(msg: str):
    print(f"\n[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

def http_get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_post(url: str, data: dict, timeout: int = 240) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def parse_range(range_str: str) -> List[int]:
    """Parses range strings like '1-20', '1,2,5', '1-5,8' into sorted list of ints."""
    result = set()
    for part in range_str.split(','):
        part = part.strip()
        if '-' in part:
            sub = part.split('-')
            result.update(range(int(sub[0]), int(sub[1]) + 1))
        elif part.isdigit():
            result.add(int(part))
    return sorted(list(result))

# ─────────────────────────────────────────────────────────────
# Channel-Specific Metadata Resolvers
# ─────────────────────────────────────────────────────────────

def resolve_lakorn_character_sheets(story_path: str, ep_num: int, scene_num: int) -> List[str]:
    """Resolves character sheet image paths for a specific Lakorn scene."""
    ref_map_file = os.path.join(story_path, "4 - Reference Image Map.md")
    if not os.path.isfile(ref_map_file):
        return []

    # 1. Parse Reference Image Map
    ref_map = {}
    with open(ref_map_file, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^-\s*([^:]+):\s*(.+)$", line.strip())
            if m:
                c_name = m.group(1).strip()
                rel_path = m.group(2).strip()
                ref_map[c_name] = rel_path

    # 2. Check scene characters in 4 - Character Each Scene
    ep_str = f"EP{ep_num:02d}"
    char_scene_dir = os.path.join(story_path, "4 - Character Each Scene", ep_str)
    scene_char_names = []
    if os.path.isdir(char_scene_dir):
        # find matching file
        for fname in os.listdir(char_scene_dir):
            if f"Scene {scene_num:02d}" in fname or f"Scene {scene_num}" in fname:
                filepath = os.path.join(char_scene_dir, fname)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    for c_name in ref_map:
                        if c_name in content:
                            scene_char_names.append(c_name)
                break

    # If no specific characters found in scene file, default to main characters in ref map
    if not scene_char_names:
        scene_char_names = list(ref_map.keys())[:2]

    # 3. Resolve absolute paths to Character Sheet images
    found_paths = []
    channel_root = os.path.dirname(os.path.abspath(story_path))
    for c_name in scene_char_names:
        rel = ref_map.get(c_name)
        if not rel:
            continue
        # Check relative to channel_root
        cand1 = os.path.join(channel_root, rel)
        cand2 = os.path.join(story_path, rel)
        if os.path.isfile(cand1):
            found_paths.append(cand1)
        elif os.path.isfile(cand2):
            found_paths.append(cand2)

    return found_paths[:2]  # Flow allows 1-2 clean chips

def load_lakorn_scenes(story_path: str, ep_num: int, aspect_ratio: str) -> Dict[int, Dict]:
    """Loads Lakorn scene prompts and target output paths."""
    ep_str = f"EP{ep_num:02d}"
    prompt_dir = os.path.join(story_path, "4 - Image Prompt", ep_str)
    out_dir = os.path.join(story_path, "6 - Storyboards", ep_str)
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isdir(prompt_dir):
        return {}

    scenes = {}
    for f in sorted(os.listdir(prompt_dir)):
        m = re.match(r'^(?:EP\d+\s*-\s*)?(?:(\d+)\s*-\s*)?Scene\s*(\d+)\.md$', f, re.I)
        if m:
            sc_idx = int(m.group(2)) if m.group(2) else int(m.group(1))
            filepath = os.path.join(prompt_dir, f)
            with open(filepath, "r", encoding="utf-8") as pf:
                prompt_text = pf.read().strip()

            # Ensure prompt aspect ratio tag matches requested
            if aspect_ratio == "9:16" and "Horizontal 16:9" in prompt_text:
                prompt_text = prompt_text.replace("Horizontal 16:9", "Vertical 9:16")
            elif aspect_ratio == "16:9" and "Vertical 9:16" in prompt_text:
                prompt_text = prompt_text.replace("Vertical 9:16", "Horizontal 16:9")

            char_sheets = resolve_lakorn_character_sheets(story_path, ep_num, sc_idx)
            out_file = os.path.join(out_dir, f"{ep_str} - Scene {sc_idx:02d}.jpg")

            scenes[sc_idx] = {
                "prompt": prompt_text,
                "reference_images": char_sheets,
                "output_path": out_file
            }
    return scenes

def load_stickman_scenes(story_path: str, aspect_ratio: str) -> Dict[int, Dict]:
    """Loads Stickman beat prompts and target output paths."""
    prompts_file = os.path.join(story_path, "3 - Image Prompt", "Image_Prompts.md")
    out_dir = os.path.join(story_path, "5 - Storyboards")
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isfile(prompts_file):
        return {}

    scenes = {}
    with open(prompts_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            m = re.match(r"^-\s*\*\*Beat\s*(\d+)[^*]*\*\*:\s*(.+)$", line)
            if m:
                b_num = int(m.group(1))
                desc = m.group(2).strip()
                if "⚪" in desc or "White Background" in desc:
                    clean_desc = desc.replace("⚪ White Background 100%.", "").replace("⚪", "").strip()
                    full_prompt = f"Horizontal 16:9 composition on a plain clean solid 100% pure white textured paper background only. In the center, bold black hand-drawn marker typography and doodle, {clean_desc}, with a bold thick red marker X crossed out where applicable, high contrast, clean doodle explainer aesthetic, 100% pure white paper backdrop, no background environment."
                else:
                    clean_desc = re.sub(r"^Full-bleed 16:9\.?\s*", "", desc).strip()
                    clean_desc = re.sub(r"with comic sound effects\.?", "", clean_desc, flags=re.I).strip()
                    full_prompt = f"Full-bleed 16:9 widescreen composition filling the entire frame from edge to edge, no border, no white margin, no vignette, no comic text bubbles, no sound effect words. Hand-drawn doodle ink explainer style on textured paper, soft muted watercolor wash and gentle gouache shading, fine crosshatching, gentle atmospheric lighting. The minimalist white bald stick figure with completely smooth round head and NO HAIR, {clean_desc}."

                out_file = os.path.join(out_dir, f"Beat_{b_num:02d}.jpg")
                scenes[b_num] = {
                    "prompt": full_prompt,
                    "reference_images": [],
                    "output_path": out_file
                }
    return scenes

# ─────────────────────────────────────────────────────────────
# Main Runner Loop
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Centralized FlowKit Storyboard Image Generator")
    parser.add_argument("--story-path", "-s", required=True, type=str, help="Root path of the story/episode folder")
    parser.add_argument("--ep", "-e", type=str, default="1", help="Episode number (e.g. 1 or EP01)")
    parser.add_argument("--scenes", "-sc", type=str, help="Scene range to generate (e.g. '1-20', '1,3,5' or 'all')")
    parser.add_argument("--aspect-ratio", "-a", type=str, default="9:16", choices=["9:16", "16:9"], help="Aspect ratio (9:16 for Lakorn, 16:9 for Stickman)")
    parser.add_argument("--project-id", type=str, default=DEFAULT_PROJECT_ID, help="Google Flow project UUID")
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE, help="FlowKit API server base URL")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip scenes that already have a completed image file")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing images")
    parser.add_argument("--delay", "-d", type=float, default=3.0, help="Delay between scene submissions in seconds")
    parser.add_argument("--timeout", type=int, default=180, help="Max timeout per scene generation in seconds")

    args = parser.parse_args()

    # 1. Health check FlowKit server
    log(f"Checking FlowKit server at {args.api_base}...")
    try:
        status = http_get(f"{args.api_base}/api/flow/status")
        if not status.get("connected"):
            error_exit("FlowKit Chrome extension is not connected! Ensure Chrome is running with Google Flow open.")
        log("FlowKit server and Chrome extension are CONNECTED.")
    except Exception as e:
        error_exit(f"Could not connect to FlowKit server at {args.api_base}: {e}")

    # 2. Parse episode number
    ep_num = int(re.search(r'\d+', args.ep).group(0)) if re.search(r'\d+', args.ep) else 1

    # 3. Detect Channel / Story Structure
    story_path = os.path.abspath(args.story_path)
    if not os.path.isdir(story_path):
        error_exit(f"Story path does not exist: {story_path}")

    scenes_map = {}
    is_lakorn = os.path.isdir(os.path.join(story_path, "4 - Image Prompt"))
    is_stickman = os.path.isfile(os.path.join(story_path, "3 - Image Prompt", "Image_Prompts.md"))

    if is_lakorn:
        log("Detected format: ผักกาดการละคร (Lakorn Drama)")
        scenes_map = load_lakorn_scenes(story_path, ep_num, args.aspect_ratio)
    elif is_stickman:
        log("Detected format: Stickman Explainer")
        scenes_map = load_stickman_scenes(story_path, args.aspect_ratio)
    else:
        error_exit(f"Could not detect recognized prompt structure in {story_path}")

    if not scenes_map:
        error_exit(f"No scene prompts found in {story_path}")

    # 4. Filter target scenes
    if not args.scenes or args.scenes.lower() == 'all':
        target_scene_nums = sorted(list(scenes_map.keys()))
    else:
        requested = parse_range(args.scenes)
        target_scene_nums = [n for n in requested if n in scenes_map]

    log(f"Total scenes found: {len(scenes_map)}. Target scenes to process: {target_scene_nums}")

    # 5. Process each scene
    completed_count = 0
    skipped_count = 0
    failed_count = 0

    endpoint = f"{args.api_base}/api/flow/generate-storyboard"

    for idx, sc_idx in enumerate(target_scene_nums):
        item = scenes_map[sc_idx]
        out_path = item["output_path"]

        # Check skip existing
        if not args.force and args.skip_existing and os.path.isfile(out_path) and os.path.getsize(out_path) > 30000:
            log(f"[{idx+1}/{len(target_scene_nums)}] Scene {sc_idx:02d}: already exists, skipping ({os.path.basename(out_path)})")
            skipped_count += 1
            continue

        log(f"\n[{idx+1}/{len(target_scene_nums)}] === Rendering Scene {sc_idx:02d} ({args.aspect_ratio}) ===")
        log(f"  Prompt preview: {item['prompt'][:90]}...")
        if item["reference_images"]:
            log(f"  Attached refs: {[os.path.basename(p) for p in item['reference_images']]}")
        log(f"  Target file: {os.path.basename(out_path)}")

        payload = {
            "prompt": item["prompt"],
            "project_id": args.project_id,
            "aspect_ratio": args.aspect_ratio,
            "reference_images": item["reference_images"],
            "output_path": out_path,
            "timeout": args.timeout
        }

        try:
            res = http_post(endpoint, payload, timeout=args.timeout + 30)
            if res.get("success"):
                log(f"  ✅ Successfully rendered Scene {sc_idx:02d}! Saved to: {out_path}")
                completed_count += 1
            else:
                log(f"  ❌ Generation failed for Scene {sc_idx:02d}: {res}")
                failed_count += 1
        except Exception as e:
            log(f"  ❌ Error rendering Scene {sc_idx:02d}: {e}")
            failed_count += 1

        if idx < len(target_scene_nums) - 1:
            time.sleep(args.delay)

    log("\n" + "="*50)
    log(f"Storyboard Generation Finished!")
    log(f"  Total Processed : {len(target_scene_nums)}")
    log(f"  Completed       : {completed_count}")
    log(f"  Skipped         : {skipped_count}")
    log(f"  Failed          : {failed_count}")
    log("="*50)

if __name__ == "__main__":
    main()
