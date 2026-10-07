#!/usr/bin/env python3
"""
Flow Tile Inspector & Exact Prompt Matcher (flow_tile_inspector.py)
------------------------------------------------------------------
Inspects Google Flow tiles by clicking into the editor view / navigation rail,
reading the actual prompt text from `span.text-part`, and matching 1:1 with local
scene prompts (for both Image and Video modes).

Usage:
    # Check storyboard image prompts:
    python3 scripts/flow_tile_inspector.py \
      --story-path "/path/to/Channels/2 - ผักกาดการละคร - ละครไทย/34" \
      --ep 1 \
      --scenes "1-40" \
      --mode image \
      --check-only

    # Check video animation prompts:
    python3 scripts/flow_tile_inspector.py \
      --story-path "/path/to/Channels/2 - ผักกาดการละคร - ละครไทย/34" \
      --ep 1 \
      --scenes "1-40" \
      --mode video \
      --check-only
"""

import argparse
import base64
import difflib
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple
from PIL import Image


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url: str, timeout: float = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "FlowTileInspector/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def exec_js(api_base: str, js_code: str, timeout: float = 90) -> any:
    url = f"{api_base}/api/flow/inspect-tab?" + urllib.parse.urlencode({"js": js_code})
    data = http_get(url, timeout=timeout)
    return data.get("result", {}).get("res", {}).get("result")


def parse_scene_range(spec: str, max_scenes: int = 40) -> List[int]:
    if not spec or spec.strip().lower() in ("all", "*"):
        return list(range(1, max_scenes + 1))
    scenes = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-", 1)
            scenes.update(range(int(s), int(e) + 1))
        elif part.isdigit():
            scenes.add(int(part))
    return sorted(scenes)


def normalize_prompt(text: str) -> str:
    """Normalizes prompt text for robust string similarity matching."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip().lower()
    # Strip common boilerplate prefixes
    text = re.sub(r"^(9:16|16:9)\s*(vertical|horizontal)?\s*(orientation)?[\s,]*", "", text)
    text = re.sub(r"^full-bleed\s*edge-to-edge\s*frame[\s,]*", "", text)
    return text


def load_local_prompts(story_path: str, ep: int, mode: str = "image") -> Dict[int, str]:
    """Loads all local prompts for an episode based on mode (image vs video)."""
    ep_str = f"EP{ep:02d}"
    if mode == "video":
        prompt_dir = os.path.join(story_path, "4 - Animation Prompt", ep_str)
        if not os.path.isdir(prompt_dir):
            prompt_dir = os.path.join(story_path, "4 - Animation Prompt")
    else:
        prompt_dir = os.path.join(story_path, "4 - Image Prompt", ep_str)
        if not os.path.isdir(prompt_dir):
            prompt_dir = os.path.join(story_path, "4 - Image Prompt")
        if not os.path.isdir(prompt_dir):
            prompt_dir = os.path.join(story_path, "4 - Animation Prompt", ep_str)

    local_prompts = {}
    if not os.path.isdir(prompt_dir):
        log(f"⚠️ Prompt directory not found: {prompt_dir}")
        return local_prompts

    for fname in sorted(os.listdir(prompt_dir)):
        if not fname.endswith(".md"):
            continue
        m = re.search(r"(\d+)", fname)
        if m:
            sc_num = int(m.group(1))
            fpath = os.path.join(prompt_dir, fname)
            try:
                content = open(fpath, encoding="utf-8").read().strip()
                local_prompts[sc_num] = content
            except Exception:
                pass
    return local_prompts


def ensure_editor_view(api_base: str) -> bool:
    """Ensures Google Flow is in editor view where flow-navigation-rail exists."""
    ensure_code = r'''(() => {
        let rail = document.querySelector('flow-navigation-rail');
        if (rail) return { status: 'already_editor' };
        
        const tile = document.querySelector('flow-image-tile img, flow-video-tile img, [class*="tile"]:has(img) img, flow-image-tile, flow-video-tile');
        if (tile) {
            tile.click();
            return { status: 'clicked_tile_to_open' };
        }
        return { status: 'no_tiles_found' };
    })()'''
    res = exec_js(api_base, ensure_code)
    if isinstance(res, dict) and res.get("status") == "clicked_tile_to_open":
        time.sleep(1.5)
    return True


def return_to_grid_view(api_base: str):
    """Cleanly clicks the back button to return to the project grid view."""
    back_code = r'''(() => {
        const backBtn = document.querySelector('button[aria-label*="กลับ"], button[aria-label*="Back" i], flow-back-button, .back-button') ||
                        Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('กลับ') || b.querySelector('mat-icon')?.innerText?.includes('arrow_back'));
        if (backBtn) {
            backBtn.click();
            return { clicked: true };
        }
        return { clicked: false };
    })()'''
    exec_js(api_base, back_code)
    time.sleep(0.5)


def scan_flow_tiles_raw(api_base: str) -> List[Dict]:
    """Iterates through navigation rail thumbnails, clicks each, and reads prompt text."""
    ensure_editor_view(api_base)

    scan_code = r'''(async () => {
        const rail = document.querySelector('flow-navigation-rail');
        if (!rail) return { error: "flow-navigation-rail not found" };

        const thumbButtons = Array.from(rail.querySelectorAll('button.thumbnail-button, button:has(img)'));
        const tilesData = [];
        let lastPrompt = '';

        for (let i = 0; i < thumbButtons.length; i++) {
            const btn = thumbButtons[i];
            const label = btn.getAttribute('aria-label') || '';
            const img = btn.querySelector('img');
            const src = img ? img.src : '';
            if (!src) continue;

            btn.click();

            let prompt = '';
            for (let w = 0; w < 8; w++) {
                await new Promise(r => setTimeout(r, 60));
                const pEl = document.querySelector('span.text-part, .prompt-text, [class*="prompt-text"]');
                const curText = (pEl?.innerText || '').trim();
                if (curText && curText !== lastPrompt && curText.length > 10) {
                    prompt = curText;
                    lastPrompt = curText;
                    break;
                }
            }
            if (!prompt) {
                const pEl = document.querySelector('span.text-part, .prompt-text, [class*="prompt-text"]');
                if (pEl) prompt = (pEl.innerText || '').trim();
            }

            tilesData.push({
                index: i,
                src: src,
                label: label,
                prompt: prompt
            });
        }
        return tilesData;
    })()'''

    res = exec_js(api_base, scan_code)
    if isinstance(res, dict) and "error" in res:
        log(f"⚠️ Scan error: {res.get('error')}")
        return []
    return res or []


def match_tiles_to_scenes(tiles_data: List[Dict], local_prompts: Dict[int, str], target_scenes: List[int]) -> Dict[int, Dict]:
    """Matches raw Flow tiles against local scene prompts using text similarity."""
    scene_match = {}
    used_indices = set()

    # Pre-normalize local prompts
    norm_local = {sc: normalize_prompt(p) for sc, p in local_prompts.items() if sc in target_scenes}

    for sc in target_scenes:
        loc_text = norm_local.get(sc, "")
        if not loc_text:
            continue

        best_score = 0.0
        best_tile = None

        for t in tiles_data:
            if t["index"] in used_indices:
                continue
            fl_text = normalize_prompt(t.get("prompt", ""))
            if not fl_text:
                continue

            # 1. Exact label match (e.g. Scene 03)
            label = t.get("label", "").lower()
            if f"scene {sc:02d}" in label or f"scene_{sc:02d}" in label or f"scene{sc:02d}" in label:
                best_score = 1.0
                best_tile = t
                break

            # 2. Substring match
            if len(loc_text) > 30 and (loc_text[:40] in fl_text or fl_text[:40] in loc_text):
                score = 0.95
            else:
                # 3. SequenceMatcher similarity
                score = difflib.SequenceMatcher(None, loc_text[:120], fl_text[:120]).ratio()

            if score > best_score:
                best_score = score
                best_tile = t

        if best_tile and best_score >= 0.55:
            scene_match[sc] = {
                "tile": best_tile,
                "score": best_score,
                "prompt": best_tile.get("prompt", ""),
                "src": best_tile.get("src", ""),
                "label": best_tile.get("label", "")
            }
            used_indices.add(best_tile["index"])

    return scene_match


def download_image(api_base: str, img_url: str, out_file: str) -> bool:
    """Fetches high-res image via Google Flow browser context and saves locally."""
    full_url = re.sub(r"=s\d+", "=s2048", img_url)
    fetch_js = f'''(async () => {{
        try {{
            const resp = await fetch("{full_url}");
            if (!resp.ok) return {{ error: resp.status }};
            const blob = await resp.blob();
            return new Promise((resolve, reject) => {{
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            }});
        }} catch(e) {{
            return {{ error: e.toString() }};
        }}
    }})()'''

    b64_data = exec_js(api_base, fetch_js, timeout=25)
    if isinstance(b64_data, str) and len(b64_data) > 1000:
        raw_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
        img.save(out_file, "JPEG", quality=95)
        return True

    # Fallback: direct HTTP request
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            img.save(out_file, "JPEG", quality=95)
            return True
    except Exception:
        pass

    return False


def main():
    parser = argparse.ArgumentParser(description="Google Flow Tile Inspector & Exact Prompt Matcher")
    parser.add_argument("--story-path", required=True, help="Path to story directory")
    parser.add_argument("--ep", type=int, required=True, help="Episode number (e.g. 1, 2)")
    parser.add_argument("--scenes", type=str, default="", help="Scene range (e.g. 1-40)")
    parser.add_argument("--mode", choices=["image", "video", "auto"], default="image", help="Mode: image or video")
    parser.add_argument("--api-base", default="http://127.0.0.1:6969", help="FlowKit API URL")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files on download")
    parser.add_argument("--check-only", action="store_true", help="Run verification report only without downloading")
    parser.add_argument("--dry-run", action="store_true", help="Scan only without downloading")

    args = parser.parse_args()

    local_prompts = load_local_prompts(args.story_path, args.ep, mode=args.mode)
    if not local_prompts and args.mode == "auto":
        local_prompts = load_local_prompts(args.story_path, args.ep, mode="video")

    total_local = len(local_prompts)
    target_scenes = parse_scene_range(args.scenes, max_scenes=total_local or 40)

    log(f"🔍 Starting Flow Tile Inspector for EP{args.ep:02d} (Mode: {args.mode.upper()})...")
    log(f"   Story Path: {args.story_path}")
    log(f"   Target Scenes ({len(target_scenes)}): {target_scenes}")
    log(f"   Local Prompts Loaded: {len(local_prompts)}")

    raw_tiles = scan_flow_tiles_raw(args.api_base)
    log(f"   Scanned {len(raw_tiles)} tile(s) from Flow navigation rail.")

    scene_map = match_tiles_to_scenes(raw_tiles, local_prompts, target_scenes)
    found_sc_nums = sorted(list(scene_map.keys()))
    missing_sc_nums = sorted([sc for sc in target_scenes if sc not in found_sc_nums])

    # Cleanly return back to grid view
    return_to_grid_view(args.api_base)

    print("\n" + "="*80)
    print(f"📋 TILE PROMPT VERIFICATION REPORT (EP{args.ep:02d} | Mode: {args.mode.upper()})")
    print("="*80)
    print(f"{'ฉาก':<8} | {'ผลการตรวจ':<12} | {'ความตรงกัน':<10} | {'Flow Prompt (ตัวอย่าง)':<40}")
    print("-" * 80)

    for sc in target_scenes:
        if sc in scene_map:
            m_info = scene_map[sc]
            pct = int(m_info["score"] * 100)
            preview = m_info["prompt"].replace("\n", " ")[:38]
            print(f"Scene {sc:02d} | ✅ MATCH    | {pct}%       | {preview}")
        else:
            print(f"Scene {sc:02d} | ❌ NOT FOUND| 0%         | -")

    print("-" * 80)
    log(f"Summary: {len(found_sc_nums)}/{len(target_scenes)} scenes matched ({len(missing_sc_nums)} missing).")

    if args.check_only or args.dry_run:
        sys.exit(0 if len(missing_sc_nums) == 0 else 1)

    # Download matched images if mode == image
    if args.mode in ("image", "auto"):
        out_dir = os.path.join(args.story_path, "6 - Storyboards", f"EP{args.ep:02d}")
        os.makedirs(out_dir, exist_ok=True)
        downloaded = 0

        for sc in found_sc_nums:
            out_file = os.path.join(out_dir, f"EP{args.ep:02d} - Scene {sc:02d}.jpg")
            if os.path.isfile(out_file) and not args.force:
                continue

            info = scene_map[sc]
            img_url = info.get("src")
            if not img_url:
                continue

            if download_image(args.api_base, img_url, out_file):
                downloaded += 1

        log(f"🎉 Downloaded/updated {downloaded} storyboard image(s).")

    sys.exit(0 if len(missing_sc_nums) == 0 else 1)


if __name__ == "__main__":
    main()
