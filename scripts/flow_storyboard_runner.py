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
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_API_BASE = "http://127.0.0.1:6969"
DEFAULT_PROJECT_ID = "21a1632e-9926-46fa-954c-240d71d78f41"  # ละคร
DEFAULT_STICKMAN_PROJECT_ID = "527f23e9-8586-4712-934e-dcf0b7d87417"  # Stickman

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def error_exit(msg: str):
    print(f"\n[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

def http_get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"connected": False, "error": str(e)}

def http_post(url: str, data: dict, timeout: int = 240) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_json = json.loads(e.read().decode("utf-8"))
            if isinstance(err_json, dict):
                err_json["status_code"] = e.code
                return err_json
            return {"success": False, "status_code": e.code, "detail": str(err_json)}
        except Exception:
            return {"success": False, "status_code": e.code, "detail": str(e)}
    except Exception as e:
        return {"success": False, "detail": str(e)}

def post_with_busy_retry(endpoint: str, payload: dict, timeout: int, max_busy_retries: int = 30) -> dict:
    """Posts payload to endpoint, automatically entering a Retry Queue on HTTP 429 Busy responses."""
    busy_attempts = 0
    while True:
        res = http_post(endpoint, payload, timeout=timeout)
        if res.get("status_code") == 429 or res.get("status") == "busy":
            curr_proj = res.get("current_project") or payload.get("project_id") or "unknown"
            busy_attempts += 1
            if busy_attempts <= max_busy_retries:
                log(f"  ⏳ [Busy 429 Queue] Google Flow is busy rendering another task (Project: {curr_proj}). Retrying in 10s ({busy_attempts}/{max_busy_retries})...")
                time.sleep(10)
                continue
        return res


def parse_range(range_str: str) -> List[int]:
    """Parses range strings like '1-20', '1,2,5', '1-5,8', 'EP01,EP02' into sorted list of ints."""
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

def find_all_episodes(story_path: str) -> List[int]:
    """Scans 4 - Image Prompt directory to find all available EP numbers."""
    prompt_base = os.path.join(story_path, "4 - Image Prompt")
    if not os.path.isdir(prompt_base):
        return [1]
    eps = []
    for d in os.listdir(prompt_base):
        m = re.search(r'EP0*(\d+)', d, re.IGNORECASE)
        if m and os.path.isdir(os.path.join(prompt_base, d)):
            eps.append(int(m.group(1)))
    return sorted(list(set(eps))) if eps else [1]

def parse_episodes_and_scenes(story_path: str, ep_arg: str, scenes_arg: Optional[str]) -> List[Tuple[int, Optional[str]]]:
    """
    Parses episode and scene specifications into a list of (ep_num, scenes_filter_str).
    Supported syntaxes:
    1. Per-episode mapping in ep:
       --ep "1:4-10,18-19; 2:11-15,19-25"
    2. Per-episode mapping in scenes:
       --ep "1,2" --scenes "1:4-10,18-19; 2:11-15,19-25"
    3. Comma or range separated episodes:
       --ep "1,2", --ep "1-3", --ep "all"
       paired with standard scenes="1-10" or scenes="all"
    Returns:
       [(1, "4-10,18-19"), (2, "11-15,19-25")]
    """
    # 1. Check if per-ep scenes syntax is embedded directly in ep_arg
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

    # 2. Determine list of episodes
    if ep_arg.strip().lower() == 'all':
        ep_list = find_all_episodes(story_path)
    else:
        ep_list = parse_range(ep_arg)
        if not ep_list:
            m = re.search(r'\d+', ep_arg)
            ep_list = [int(m.group(0))] if m else [1]

    # 3. Check if scenes_arg contains per-episode mapping
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

    # 4. Standard case: same scenes_arg for each episode in ep_list
    return [(ep_n, scenes_arg) for ep_n in ep_list]

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

def is_valid_image_file(filepath: str) -> bool:
    """Verifies that the file exists, is non-empty, and is a valid image (not HTML redirect)."""
    if not filepath or not os.path.isfile(filepath):
        return False
    if os.path.getsize(filepath) < 20480:  # < 20KB is corrupt/placeholder
        return False
    try:
        with open(filepath, "rb") as f:
            h = f.read(32)
        if h.startswith(b"<!doctype") or h.startswith(b"<html") or b"<body" in h.lower():
            return False
        if h.startswith(b"\xff\xd8\xff") or h.startswith(b"\x89PNG\r\n\x1a\n") or (h[:4] == b"RIFF" and h[8:12] == b"WEBP"):
            return True
    except Exception:
        pass
    return False

# ─────────────────────────────────────────────────────────────
# Content Safety & Moderation Bypass Rule Engine
# ─────────────────────────────────────────────────────────────

SAFETY_REPLACEMENTS = [
    # Multi-word patterns first
    (r"\btorture\s*dungeon\b", "dim shadowy chamber"),
    (r"\btorture\s*room\b", "dim punishment chamber"),
    (r"\bscreaming\s+in\s+agony\b", "looking upward in deep emotional sorrow"),
    (r"\bcrying\s+bloody\s+tears\b", "tears glistening in dramatic firelight"),
    (r"\bblood(?:y)?\s+tears\b", "glistening tears"),
    (r"\btied\s+up\b", "standing constrained"),
    (r"\bchained\s+up\b", "standing constrained"),
    (r"\bholding\s+(?:a\s+)?(?:knife|blade|gun|weapon)\b", "gesturing with a dramatically pointed finger"),
    (r"\bpointing\s+(?:a\s+)?(?:knife|blade|gun|weapon)\b", "pointing a stern finger"),

    # Single-word violence & weapons
    (r"\b(blood|bloody|bleeding)\b", "glistening tear streaks"),
    (r"\b(wounds?|injur(?:y|ies|ed))\b", "fatigued posture"),
    (r"\b(knife|knives|blade|gun|guns|weapons?)\b", "glowing crystal amulet"),
    (r"\b(stab|stabbing|shot|shooting)\b", "striking a dramatic confrontational pose"),
    (r"\b(kill|killing|killed|murder|murdered|murdering)\b", "confronting fiercely"),
    (r"\b(death|dead|corpse)\b", "fallen unconscious"),
    (r"\b(tortur(?:e|ed|ing)|abus(?:e|ed|ing))\b", "harsh reprimand"),
    (r"\b(dungeon)\b", "dim stone chamber"),
    (r"\b(shackled)\b", "held firmly"),
    (r"\b(strangl(?:e|ed|ing)|chok(?:e|ed|ing))\b", "gripping collar in fierce confrontation"),
    (r"\b(slap|slapping|punch|punching|beat|beating)\b", "dramatic emotional outburst"),
    (r"\b(agony|excruciating)\b", "deep emotional distress"),
    (r"\b(cruel|brutal)\b", "stern and uncompromising"),
    (r"\b(scam|scammer|fraud)\b", "illicit scheme"),
    (r"\b(hostage|kidnap(?:ped)?)\b", "detained person"),
]

def soften_prompt_for_safety(prompt: str, round_num: int = 1) -> str:
    """Softens sensitive or blocked keywords in prompt according to Content Safety & Moderation Bypass Skill."""
    res = prompt
    for pattern, repl in SAFETY_REPLACEMENTS:
        res = re.sub(pattern, repl, res, flags=re.IGNORECASE)
    if round_num >= 2:
        res += " Family-friendly emotional Thai melodrama, non-violent cinematic tension."
    return res

# ─────────────────────────────────────────────────────────────
# Channel-Specific Metadata Resolvers
# ─────────────────────────────────────────────────────────────

def resolve_lakorn_character_sheets(story_path: str, ep_num: int, scene_num: int) -> List[str]:
    """Resolves character sheet image paths for a specific Lakorn scene."""
    ref_map_file = os.path.join(story_path, "4 - Reference Image Map.md")
    if not os.path.isfile(ref_map_file):
        return []

    # 1. Parse Reference Image Map (supports both Markdown table and bullet list)
    ref_map = {}
    with open(ref_map_file, "r", encoding="utf-8") as f:
        for line in f:
            line_s = line.strip()
            # 1.1 Markdown Table format: | Col1 | Col2 | Col3 |
            if line_s.startswith("|") and not re.search(r"^\|\s*[-:]+\s*\|", line_s):
                cols = [c.strip() for c in line_s.split("|") if c.strip()]
                if len(cols) >= 3 and not any(h in cols[0].lower() for h in ["thai", "ชื่อ", "character"]):
                    th_name, en_name, rel_path = cols[0], cols[1], cols[2]
                    ref_map[th_name] = rel_path
                    ref_map[en_name] = rel_path
                elif len(cols) == 2 and not any(h in cols[0].lower() for h in ["thai", "ชื่อ", "character"]):
                    name, rel_path = cols[0], cols[1]
                    ref_map[name] = rel_path
            # 1.2 Bullet list format: - Name: Path
            m = re.match(r"^-\s*([^:]+):\s*(.+)$", line_s)
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
            if re.search(rf"(?:Scene\s*0*{scene_num}(?:\D|$)|^0*{scene_num}\s*-)", fname, re.IGNORECASE):
                filepath = os.path.join(char_scene_dir, fname)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    for c_name, rel_path in ref_map.items():
                        c_base = os.path.splitext(os.path.basename(rel_path))[0]
                        char_root = c_base.split(' - ')[0]
                        if c_name.lower() in content.lower() or c_base.lower() in content.lower() or char_root.lower() in content.lower():
                            if rel_path not in [ref_map.get(x) for x in scene_char_names]:
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
    """Loads Stickman beat prompts and target output paths with 9:16 / 16:9 support."""
    prompts_file = os.path.join(story_path, "3 - Image Prompt", "Image_Prompts.md")
    out_dir = os.path.join(story_path, "5 - Storyboards")
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.isfile(prompts_file):
        return {}

    # Robust multi-level lookup for Character Sheet
    cur = os.path.abspath(story_path)
    bald_sheet = None
    for _ in range(4):
        candidate = os.path.join(cur, "Character Sheet", "stickman_bald_master_sheet.jpg")
        if os.path.isfile(candidate):
            bald_sheet = candidate
            break
        cur = os.path.dirname(cur)

    scenes = {}
    with open(prompts_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            m = re.match(r"^-\s*\*\*Beat\s*(\d+)[^*]*\*\*:\s*(.+)$", line)
            if m:
                b_num = int(m.group(1))
                desc = m.group(2).strip()
                is_white_bg = "⚪" in desc or "White Background" in desc

                # Extract filename if defined in beat line, e.g. Beat_01_cozy_bed.jpg
                fn_match = re.search(r'`(Beat_\d+[^`]+)`', line)
                if fn_match:
                    out_filename = fn_match.group(1)
                    if not out_filename.lower().endswith((".jpg", ".jpeg", ".png")):
                        out_filename += ".jpg"
                else:
                    out_filename = f"Beat_{b_num:02d}.jpg"

                if aspect_ratio == "9:16":
                    if is_white_bg:
                        clean_desc = desc.replace("⚪ White Background 100%.", "").replace("⚪", "").strip()
                        full_prompt = f"Vertical 9:16 tall vertical composition on a plain clean solid 100% pure white textured paper background only. In the center, bold black hand-drawn marker typography and doodle, {clean_desc}, with a bold thick red marker X crossed out where applicable, high contrast, clean doodle explainer aesthetic, 100% pure white paper backdrop, no background environment."
                        ref_imgs = []
                    else:
                        clean_desc = re.sub(r"^Full-bleed (?:16:9|9:16)\.?\s*", "", desc, flags=re.I).strip()
                        clean_desc = re.sub(r"with comic sound effects\.?", "", clean_desc, flags=re.I).strip()
                        full_prompt = f"Vertical 9:16 tall vertical composition filling the entire frame from top to bottom, no border, no white margin, no vignette, no comic text bubbles, no sound effect words. Hand-drawn doodle ink explainer style on textured paper, soft muted watercolor wash and gentle gouache shading, fine crosshatching, gentle atmospheric lighting. The minimalist white bald stick figure with completely smooth round head and NO HAIR, {clean_desc}."
                        ref_imgs = [bald_sheet] if (bald_sheet and os.path.isfile(bald_sheet)) else []
                else:
                    if is_white_bg:
                        clean_desc = desc.replace("⚪ White Background 100%.", "").replace("⚪", "").strip()
                        full_prompt = f"Horizontal 16:9 composition on a plain clean solid 100% pure white textured paper background only. In the center, bold black hand-drawn marker typography and doodle, {clean_desc}, with a bold thick red marker X crossed out where applicable, high contrast, clean doodle explainer aesthetic, 100% pure white paper backdrop, no background environment."
                        ref_imgs = []
                    else:
                        clean_desc = re.sub(r"^Full-bleed (?:16:9|9:16)\.?\s*", "", desc, flags=re.I).strip()
                        clean_desc = re.sub(r"with comic sound effects\.?", "", clean_desc, flags=re.I).strip()
                        full_prompt = f"Full-bleed 16:9 widescreen composition filling the entire frame from edge to edge, no border, no white margin, no vignette, no comic text bubbles, no sound effect words. Hand-drawn doodle ink explainer style on textured paper, soft muted watercolor wash and gentle gouache shading, fine crosshatching, gentle atmospheric lighting. The minimalist white bald stick figure with completely smooth round head and NO HAIR, {clean_desc}."
                        ref_imgs = [bald_sheet] if (bald_sheet and os.path.isfile(bald_sheet)) else []

                out_file = os.path.join(out_dir, out_filename)
                scenes[b_num] = {
                    "prompt": full_prompt,
                    "reference_images": ref_imgs,
                    "output_path": out_file
                }
    return scenes

def ensure_main_project_view(api_base: str) -> bool:
    """Ensures Google Flow is on the main project page (closes any tile inspector/editor)."""
    try:
        check_js = """(() => {
            const url = window.location.href || '';
            const inEdit = url.includes('/edit/') || !!document.querySelector('flow-image-editor, flow-edit-image-prompt-box');
            if (inEdit) {
                const backBtn = document.querySelector('button.back-button, [aria-label*="กลับ"], [aria-label*="Back"]');
                if (backBtn) {
                    backBtn.click();
                    return { action: 'clicked_back', from: url };
                }
                const base = url.split('/edit/')[0];
                window.location.href = base;
                return { action: 'navigated', target: base };
            }
            return { action: 'already_main_page', url: url };
        })()"""
        encoded = urllib.parse.quote(check_js)
        res = http_get(f"{api_base}/api/flow/inspect-tab?js={encoded}")
        script_res = res.get("result", {}).get("res", {}).get("result")
        if isinstance(script_res, dict) and script_res.get("action") in ("clicked_back", "navigated"):
            log(f"  🔙 Navigated from tile detail/editor back to main project page ({script_res.get('action')}).")
            time.sleep(1.5)
            return True
        return True
    except Exception as e:
        log(f"  Notice on ensuring main project view: {e}")
        return False


def ensure_storyboard_settings(api_base: str, aspect_ratio: str = "9:16", model: str = "nano banana pro", count: int = 1) -> bool:
    """Pre-checks and enforces Google Flow settings via 6969 backend."""
    try:
        ensure_main_project_view(api_base)
        payload = {
            "mode": "image",
            "aspect_ratio": aspect_ratio,
            "model": model,
            "output_count": count
        }
        res = http_post(f"{api_base}/api/flow/settings", payload, timeout=30)
        if isinstance(res, dict) and res.get("success"):
            log(f"🎯 Google Flow image settings verified via 6969: {res.get('summary')}")
            return True
        else:
            log(f"⚠️ Failed to configure image settings via 6969: {res.get('error') or res}")
            return False
    except Exception as e:
        log(f"Notice on ensuring storyboard settings via 6969: {e}")
        return False



def ensure_image_mode(api_base: str, aspect_ratio: str = "9:16") -> bool:
    """Backwards-compatible alias for ensure_storyboard_settings."""
    return ensure_storyboard_settings(api_base, aspect_ratio=aspect_ratio, model="nano banana pro", count=1)

def process_single_episode(
    story_path: str,
    ep_num: int,
    scenes_spec: Optional[str],
    args,
    round_idx: int = 1,
    total_rounds: int = 1,
    story_num: int = 26,
    is_lakorn: bool = True
) -> dict:
    """Processes storyboard image generation for a single episode."""
    ep_str = f"EP{ep_num:02d}"

    if is_lakorn:
        scenes_map = load_lakorn_scenes(story_path, ep_num, args.aspect_ratio)
    else:
        scenes_map = load_stickman_scenes(story_path, args.aspect_ratio)

    if not scenes_map:
        log(f"⚠️ No scene prompts found for {ep_str} in {story_path}")
        return {"ep": ep_num, "ep_str": ep_str, "round": round_idx, "total": 0, "completed": 0, "skipped": 0, "failed": 0, "failed_scenes": []}

    # Filter target scenes for this episode
    if not scenes_spec or scenes_spec.lower() == 'all':
        target_scene_nums = sorted(list(scenes_map.keys()))
    else:
        requested = parse_range(scenes_spec)
        target_scene_nums = [n for n in requested if n in scenes_map]

    total_scenes_to_run = len(target_scene_nums)
    log(f"\n{'='*60}")
    log(f"🎬 [{ep_str} | Round {round_idx}/{total_rounds}] Found {len(scenes_map)} scenes. Target to process: {target_scene_nums}")
    log(f"{'='*60}")

    if not target_scene_nums:
        log(f"No target scenes to process for {ep_str}.")
        return {"ep": ep_num, "ep_str": ep_str, "round": round_idx, "total": 0, "completed": 0, "skipped": 0, "failed": 0, "failed_scenes": []}

    completed_count = 0
    skipped_count = 0
    failed_count = 0
    all_failed_scenes = []

    endpoint = f"{args.api_base}/api/flow/generate-storyboard"
    batch_size = max(1, args.batch_size)
    batches = [target_scene_nums[i:i + batch_size] for i in range(0, len(target_scene_nums), batch_size)]

    log(f"🚀 Starting {ep_str} batch processing: {len(batches)} batches (Batch size: {batch_size}, Max retries: {args.max_retries})")

    # Clear server-side dispatch order queue before this batch session
    try:
        clear_res = http_post(f"{args.api_base}/api/flow/clear-dispatch-queue", {}, timeout=10)
        log(f"  🗑️ Server dispatch queue cleared (removed {clear_res.get('cleared', 0)} stale entries).")
    except Exception as e:
        log(f"  ⚠️ Could not clear dispatch queue (non-fatal): {e}")

    for batch_idx, batch in enumerate(batches):
        log("\n" + "="*50)
        log(f"📦 [{ep_str}] BATCH {batch_idx + 1}/{len(batches)} : Scenes {batch}")
        log("="*50)

        # 1. Check skip existing first
        scenes_to_process = []
        for sc_idx in batch:
            item = scenes_map[sc_idx]
            out_path = item["output_path"]
            if not args.force and args.skip_existing and is_valid_image_file(out_path):
                log(f"  ⏭️ Scene {sc_idx:02d}: valid image already exists, skipping ({os.path.basename(out_path)})")
                skipped_count += 1
            else:
                if os.path.isfile(out_path) and not is_valid_image_file(out_path):
                    log(f"  ⚠️ Scene {sc_idx:02d}: existing file is corrupt/HTML redirect ({os.path.getsize(out_path)} bytes), removing to re-generate!")
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass
                scenes_to_process.append(sc_idx)

        if not scenes_to_process:
            log(f"  All scenes in Batch {batch_idx + 1} already exist. Moving to next batch.")
            continue

        failed_scenes = []

        # 2. Initial generation for batch
        if len(scenes_to_process) >= 1:
            log(f"\n  🚀 [Rapid Batch Dispatch] Queueing {len(scenes_to_process)} scenes into Google Flow...")

            # 0. Ensure main project page (exit any tile detail/editor view)
            ensure_main_project_view(args.api_base)

            # 1. Snapshot existing tiles before dispatching
            snap = http_get(f"{args.api_base}/api/flow/snapshot-existing-tiles")
            known_urls = snap.get("urls", [])
            known_media_ids = snap.get("media_ids", [])
            log(f"     Recorded {len(known_urls)} existing tiles in project before queueing.")

            # 2. Dispatch prompts rapidly into Google Flow queue
            dispatched_scenes = []
            for q_idx, sc_idx in enumerate(scenes_to_process, 1):
                item = scenes_map[sc_idx]
                notify_status_server(story_num, ep_str, current_scene=sc_idx, action=f"กำลังส่งสร้างภาพฉาก {sc_idx:02d} เข้า Google Flow...", status="RUNNING")
                log(f"\n  ⚡ [Queue {q_idx}/{len(scenes_to_process)}] Dispatching Scene {sc_idx:02d} ({args.aspect_ratio})...")
                log(f"     Prompt: {item['prompt'][:85]}...")
                if item["reference_images"]:
                    log(f"     Attached refs: {[os.path.basename(p) for p in item['reference_images']]}")

                dispatch_payload = {
                    "prompt": item["prompt"],
                    "project_id": args.project_id,
                    "aspect_ratio": args.aspect_ratio,
                    "reference_images": item["reference_images"],
                    "wait_after_submit": 0.5,
                    "scene_num": sc_idx,
                    "output_path": item["output_path"]
                }

                try:
                    res = post_with_busy_retry(f"{args.api_base}/api/flow/dispatch-storyboard-prompt", dispatch_payload, timeout=60)
                    if res.get("success"):
                        dispatched_scenes.append(sc_idx)
                        mid = res.get("media_id")
                        item["media_id"] = mid
                        if mid:
                            log(f"     ✅ Queued Scene {sc_idx:02d} successfully! (media_id: {mid})")
                        else:
                            log(f"     ✅ Queued Scene {sc_idx:02d} successfully into Google Flow queue!")
                    else:
                        err_msg = res.get("detail") or res.get("message") or str(res)
                        log(f"     ⚠️ Dispatch failed for Scene {sc_idx:02d}: {err_msg}")
                        failed_scenes.append((sc_idx, err_msg))
                except Exception as e:
                    log(f"     ⚠️ Dispatch error for Scene {sc_idx:02d}: {e}")
                    failed_scenes.append((sc_idx, str(e)))

                actual_delay = random.uniform(0.5, 1.0) if args.delay is None else args.delay
                log(f"     ⏱️ Inter-scene delay: {actual_delay:.2f}s")
                time.sleep(actual_delay)

            # 3. Concurrently collect rendered batch
            if dispatched_scenes:
                notify_status_server(story_num, ep_str, current_scene=None, action=f"กำลังรอ Google Flow เรนเดอร์ {len(dispatched_scenes)} ภาพพร้อมกัน...", status="RUNNING")
                log(f"\n  ⏳ All {len(dispatched_scenes)} prompts queued! Waiting for Google Flow concurrent rendering & collection...")
                collect_payload = {
                    "scenes": [
                        {
                            "scene_num": sc_idx,
                            "prompt": scenes_map[sc_idx]["prompt"],
                            "output_path": scenes_map[sc_idx]["output_path"],
                            "reference_images": scenes_map[sc_idx]["reference_images"],
                            "media_id": scenes_map[sc_idx].get("media_id")
                        }
                        for sc_idx in dispatched_scenes
                    ],
                    "known_existing_urls": known_urls,
                    "known_existing_media_ids": known_media_ids,
                    "timeout": args.timeout
                }

                try:
                    collect_res = http_post(f"{args.api_base}/api/flow/collect-storyboard-batch", collect_payload, timeout=args.timeout + 30)
                    if collect_res.get("success"):
                        for r in collect_res.get("results", []):
                            sc_num = r.get("scene_num")
                            target_out = scenes_map[sc_num]["output_path"]
                            if r.get("success") and is_valid_image_file(target_out):
                                log(f"  ✅ [Batch OK] Scene {sc_num:02d} rendered & saved: {os.path.basename(r.get('output_path', ''))} ({r.get('footer_title', '')})")
                                completed_count += 1
                                notify_status_server(story_num, ep_str, current_scene=None, action=f"สร้างภาพฉาก {sc_num:02d} สำเร็จแล้ว", status="RUNNING")
                            else:
                                err_msg = r.get("error", "Collection failed or corrupt image")
                                log(f"  ⚠️ Scene {sc_num:02d} generation failed: {err_msg}")
                                failed_scenes.append((sc_num, err_msg))
                                notify_status_server(story_num, ep_str, current_scene=None, action=f"ฉาก {sc_num:02d} ติดปัญหา: {err_msg}", status="FIXING", fixing_scene=sc_num, failed_scenes=[{"scene_num": s[0], "error": s[1]} for s in failed_scenes])
                                if os.path.isfile(target_out) and not is_valid_image_file(target_out):
                                    try:
                                        os.remove(target_out)
                                    except Exception:
                                        pass
                    else:
                        err_msg = collect_res.get("detail") or collect_res.get("message") or str(collect_res)
                        log(f"  ⚠️ Batch collection failed: {err_msg}")
                        for sc_idx in dispatched_scenes:
                            failed_scenes.append((sc_idx, err_msg))
                except Exception as e:
                    log(f"  ⚠️ Batch collection error: {e}")
                    for sc_idx in dispatched_scenes:
                        failed_scenes.append((sc_idx, str(e)))
        else:
            # Single-scene sequential execution
            for sc_idx in scenes_to_process:
                item = scenes_map[sc_idx]
                out_path = item["output_path"]

                log(f"\n  🎬 Rendering Scene {sc_idx:02d} ({args.aspect_ratio}) [Single Scene]")
                log(f"     Prompt: {item['prompt'][:90]}...")
                if item["reference_images"]:
                    log(f"     Attached refs: {[os.path.basename(p) for p in item['reference_images']]}")
                log(f"     Target file: {os.path.basename(out_path)}")

                payload = {
                    "prompt": item["prompt"],
                    "project_id": args.project_id,
                    "aspect_ratio": args.aspect_ratio,
                    "reference_images": item["reference_images"],
                    "output_path": out_path,
                    "timeout": args.timeout
                }

                try:
                    res = post_with_busy_retry(endpoint, payload, timeout=args.timeout + 30)
                    if res.get("success") and is_valid_image_file(out_path):
                        log(f"  ✅ Successfully rendered Scene {sc_idx:02d}! Saved to: {os.path.basename(out_path)}")
                        completed_count += 1
                    else:
                        err_msg = res.get("detail") or res.get("message") or "Corrupt image or download failed"
                        log(f"  ⚠️ Generation failed for Scene {sc_idx:02d}: {err_msg}")
                        failed_scenes.append((sc_idx, err_msg))
                        if os.path.isfile(out_path) and not is_valid_image_file(out_path):
                            try:
                                os.remove(out_path)
                            except Exception:
                                pass
                except Exception as e:
                    log(f"  ⚠️ Error rendering Scene {sc_idx:02d}: {e}")
                    failed_scenes.append((sc_idx, str(e)))

                time.sleep(random.uniform(0.5, 1.0) if args.delay is None else args.delay)

        # 3. Retry Pass for failed scenes in this batch with prompt softening
        retry_round = 1
        while failed_scenes and retry_round <= args.max_retries:
            log(f"\n  🔄 [Batch {batch_idx + 1}] Retrying {len(failed_scenes)} failed scene(s) (Attempt {retry_round}/{args.max_retries}) with softened prompts...")
            still_failed = []

            for sc_idx, prev_err in failed_scenes:
                item = scenes_map[sc_idx]
                out_path = item["output_path"]

                softened_prompt = soften_prompt_for_safety(item["prompt"], round_num=retry_round)
                notify_status_server(story_num, ep_str, current_scene=sc_idx, action=f"กำลังปรับแก้และลองใหม่ฉาก {sc_idx:02d} (รอบ {retry_round}/{args.max_retries})...", status="FIXING", fixing_scene=sc_idx, failed_scenes=[{"scene_num": s[0], "error": s[1]} for s in failed_scenes])
                log(f"\n  🛡️ Retrying Scene {sc_idx:02d} with softened prompt:")
                log(f"     Original : {item['prompt'][:70]}...")
                log(f"     Softened : {softened_prompt[:70]}...")

                payload = {
                    "prompt": softened_prompt,
                    "project_id": args.project_id,
                    "aspect_ratio": args.aspect_ratio,
                    "reference_images": item["reference_images"],
                    "output_path": out_path,
                    "timeout": args.timeout
                }

                try:
                    res = post_with_busy_retry(endpoint, payload, timeout=args.timeout + 30)
                    if res.get("success") and is_valid_image_file(out_path):
                        log(f"  ✅ [Retry {retry_round} OK] Rendered Scene {sc_idx:02d}! Saved to: {os.path.basename(out_path)}")
                        completed_count += 1
                        notify_status_server(story_num, ep_str, current_scene=None, action=f"แก้ไขและสร้างภาพฉาก {sc_idx:02d} สำเร็จแล้ว", status="RUNNING", fixing_scene=None)
                    else:
                        err_msg = res.get("detail") or res.get("message") or "Corrupt image or download failed"
                        log(f"  ⚠️ [Retry {retry_round} Failed] Scene {sc_idx:02d}: {err_msg}")
                        still_failed.append((sc_idx, err_msg))
                        if os.path.isfile(out_path) and not is_valid_image_file(out_path):
                            try:
                                os.remove(out_path)
                            except Exception:
                                pass
                except Exception as e:
                    log(f"  ⚠️ [Retry {retry_round} Error] Scene {sc_idx:02d}: {e}")
                    still_failed.append((sc_idx, str(e)))

                time.sleep(random.uniform(0.5, 1.0) if args.delay is None else args.delay)

            failed_scenes = still_failed
            retry_round += 1

        if failed_scenes:
            for sc_idx, err in failed_scenes:
                log(f"  ❌ Permanently failed Scene {sc_idx:02d} after {args.max_retries} retries: {err}")
                failed_count += 1
                all_failed_scenes.append((sc_idx, err))

        log(f"📦 Finished Batch {batch_idx + 1}/{len(batches)}. Current Progress: {completed_count}/{total_scenes_to_run} completed, {skipped_count} skipped, {failed_count} failed.")

    final_status = "COMPLETED" if failed_count == 0 else "PARTIAL"
    notify_status_server(story_num, ep_str, current_scene=None, action=f"สร้างภาพสตอรี่บอร์ด {ep_str} เสร็จสิ้น (สำเร็จ {completed_count}/{total_scenes_to_run} ฉาก)", status=final_status, fixing_scene=None, failed_scenes=[{"scene_num": s[0], "error": s[1]} for s in all_failed_scenes])

    return {
        "ep": ep_num,
        "ep_str": ep_str,
        "round": round_idx,
        "total": total_scenes_to_run,
        "completed": completed_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "failed_scenes": all_failed_scenes
    }


def main():
    parser = argparse.ArgumentParser(description="Centralized FlowKit Storyboard Image Generator")
    parser.add_argument("--story-path", "-s", required=True, type=str, help="Root path of the story/episode folder")
    parser.add_argument("--ep", "-e", type=str, default="1", help="Episode number(s) to process. E.g. '1', '1,2', '1-3', 'all', or per-EP scenes: '1:4-10; 2:11-20'")
    parser.add_argument("--scenes", "-sc", type=str, help="Scene range to generate. E.g. '1-20', '1,3,5', 'all', or per-EP scenes: '1:4-10,18-19; 2:11,13-15,19-25'")
    parser.add_argument("--rounds", type=int, default=1, help="Number of continuous passes/rounds to execute across all specified episodes (default: 1, e.g. 2 for two continuous passes)")
    parser.add_argument("--aspect-ratio", "-a", type=str, default="9:16", choices=["9:16", "16:9"], help="Aspect ratio (9:16 for Lakorn, 16:9 for Stickman)")
    parser.add_argument("--project-id", type=str, default=DEFAULT_PROJECT_ID, help="Google Flow project UUID")
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE, help="FlowKit API server base URL")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip scenes that already have a completed image file")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing images")
    parser.add_argument("--batch-size", "-b", type=int, default=25, help="Number of scenes to process per batch (default: 25 for continuous pipeline)")
    parser.add_argument("--max-retries", "-r", type=int, default=2, help="Max retry attempts for failed scenes with softened prompts (default: 2)")
    parser.add_argument("--delay", "-d", type=float, default=None, help="Delay between scene submissions in seconds (default: randomized 0.5-1.0s)")
    parser.add_argument("--timeout", type=int, default=60, help="Max timeout per scene generation in seconds (default: 60)")

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

    # Pre-check and enforce Google Flow storyboard settings (Image mode, Nano Banana Pro, aspect ratio, count=1)
    ensure_storyboard_settings(args.api_base, aspect_ratio=args.aspect_ratio, model="nano banana pro", count=1)

    story_path = os.path.abspath(args.story_path)
    if not os.path.isdir(story_path):
        error_exit(f"Story path does not exist: {story_path}")

    story_dir_name = os.path.basename(os.path.normpath(args.story_path))
    try:
        story_num = int(story_dir_name)
    except ValueError:
        story_num = 26

    # 2. Detect Channel / Story Structure
    is_lakorn = os.path.isdir(os.path.join(story_path, "4 - Image Prompt"))
    is_stickman = os.path.isfile(os.path.join(story_path, "3 - Image Prompt", "Image_Prompts.md"))

    if is_lakorn:
        log("Detected format: ผักกาดการละคร (Lakorn Drama)")
    elif is_stickman:
        log("Detected format: Stickman Explainer")
        if args.project_id == DEFAULT_PROJECT_ID:
            args.project_id = DEFAULT_STICKMAN_PROJECT_ID
    else:
        error_exit(f"Could not detect recognized prompt structure in {story_path}")

    # 3. Pre-sync Character Sheets for story
    log(f"Pre-syncing Character Sheets for {os.path.basename(story_path)}...")
    try:
        preload_payload = {
            "project_id": args.project_id,
            "story_path": story_path
        }
        preload_res = post_with_busy_retry(f"{args.api_base}/api/flow/preload-characters", preload_payload, timeout=60)
        if preload_res.get("success"):
            exists = preload_res.get("already_exists", [])
            up = preload_res.get("uploaded", [])
            log(f"  Character Sheets verified! Already in project: {len(exists)}, Newly uploaded: {len(up)}")
        else:
            log(f"  Character preload notice: {preload_res.get('message') or preload_res.get('detail')}")
    except Exception as e:
        log(f"  Character preload check warning: {e}")

    # 4. Parse episode plan
    episodes_to_run = parse_episodes_and_scenes(story_path, args.ep, args.scenes)
    plan_desc = [f"EP{ep:02d} ({sc if sc else 'all'})" for ep, sc in episodes_to_run]
    log(f"📋 Generation Execution Plan: {plan_desc} across {args.rounds} continuous round(s).")

    all_round_results = []
    for r_idx in range(1, args.rounds + 1):
        if args.rounds > 1:
            log("\n" + "#"*60)
            log(f"🔁 EXECUTING CONTINUOUS ROUND {r_idx}/{args.rounds}")
            log("#"*60)

        for ep_num, ep_scenes in episodes_to_run:
            res = process_single_episode(
                story_path=story_path,
                ep_num=ep_num,
                scenes_spec=ep_scenes,
                args=args,
                round_idx=r_idx,
                total_rounds=args.rounds,
                story_num=story_num,
                is_lakorn=is_lakorn
            )
            all_round_results.append(res)

    # 5. Final Summary Table
    log("\n" + "="*60)
    log("🏁 ALL ROUNDS & EPISODES PROCESSED! FINAL SUMMARY:")
    log(f"{'Episode':<10} | {'Round':<6} | {'Target':<8} | {'Completed':<10} | {'Skipped':<8} | {'Failed':<8}")
    log("-" * 60)
    total_completed = 0
    total_skipped = 0
    total_failed = 0
    for r in all_round_results:
        log(f"{r['ep_str']:<10} | {r['round']:<6} | {r['total']:<8} | {r['completed']:<10} | {r['skipped']:<8} | {r['failed']:<8}")
        total_completed += r['completed']
        total_skipped += r['skipped']
        total_failed += r['failed']
    log("-" * 60)
    log(f"TOTAL: Completed={total_completed}, Skipped={total_skipped}, Failed={total_failed}")
    log("="*60)


if __name__ == "__main__":
    main()
