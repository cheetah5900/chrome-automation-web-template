#!/usr/bin/env python3
"""
Flow Tile Inspector & Exact Prompt Matcher (flow_tile_inspector.py)
------------------------------------------------------------------
Production tool to inspect Google Flow tiles by clicking into the navigation rail,
reading the actual prompt text from `span.text-part` in the editor view, and
matching images 1:1 with scenes.

Usage:
    python3 scripts/flow_tile_inspector.py \
      --story-path "/path/to/Channels/2 - ผักกาดการละคร - ละครไทย/28" \
      --ep 1 \
      --force
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from PIL import Image


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url: str, timeout: float = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "FlowTileInspector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def exec_js(api_base: str, js_code: str, timeout: float = 90) -> any:
    url = f"{api_base}/api/flow/inspect-tab?" + urllib.parse.urlencode({"js": js_code})
    data = http_get(url, timeout=timeout)
    return data.get("result", {}).get("res", {}).get("result")



def parse_scene_range(spec: str, max_scenes: int = 30) -> list[int]:
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


def load_local_prompts(story_path: str, ep: int) -> dict[int, str]:
    """Loads all local image prompts for an episode."""
    ep_str = f"EP{ep:02d}"
    prompt_dir = os.path.join(story_path, "4 - Image Prompt", ep_str)
    if not os.path.isdir(prompt_dir):
        prompt_dir = os.path.join(story_path, "4 - Animation Prompt", ep_str)
    
    local_prompts = {}
    if not os.path.isdir(prompt_dir):
        return local_prompts

    for fname in os.listdir(prompt_dir):
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
    """Ensures we are in the editor view where flow-navigation-rail exists."""
    ensure_code = r'''(() => {
        let rail = document.querySelector('flow-navigation-rail');
        if (rail) return { status: 'already_editor' };
        
        // If in grid view, click any available tile to open editor
        const tile = document.querySelector('flow-image-tile, flow-grid-tile-container, [class*="tile"]:has(img)');
        if (tile) {
            const clickable = tile.querySelector('img.thumbnail, button, a') || tile;
            clickable.click();
            return { status: 'clicked_tile_to_open' };
        }
        return { status: 'no_tiles_found' };
    })()'''
    res = exec_js(api_base, ensure_code)
    if isinstance(res, dict) and res.get("status") == "clicked_tile_to_open":
        time.sleep(1.5)
    return True


def scan_flow_tiles(api_base: str, target_ep: int, target_scenes: list[int]) -> dict[int, dict]:
    """Clicks into navigation rail thumbnails and reads actual prompt text."""
    ensure_editor_view(api_base)

    scan_code = r'''(async () => {
        const rail = document.querySelector('flow-navigation-rail');
        if (!rail) return { error: "flow-navigation-rail not found" };

        const thumbButtons = Array.from(rail.querySelectorAll('button.thumbnail-button, button:has(img)'));
        const sceneMap = {};
        let lastPrompt = '';

        for (let i = 0; i < thumbButtons.length; i++) {
            const btn = thumbButtons[i];
            const label = btn.getAttribute('aria-label') || '';
            const img = btn.querySelector('img');
            const src = img ? img.src : '';
            if (!src) continue;

            // 1. Direct label check (e.g. EP01 - Scene 17.jpg)
            const labelMatch = label.match(/EP\s*0*(\d+)\s*[-_]\s*Scene\s*0*(\d+)/i);
            if (labelMatch) {
                const ep = parseInt(labelMatch[1], 10);
                const sc = parseInt(labelMatch[2], 10);
                if (ep === target_ep) {
                    if (!sceneMap[sc]) {
                        sceneMap[sc] = { src: src, label: label, prompt: `Label: ${label}` };
                    }
                    continue;
                }
            }

            // 2. Click thumbnail to inspect actual prompt in editor
            btn.click();

            let prompt = '';
            for (let w = 0; w < 6; w++) {
                await new Promise(r => setTimeout(r, 40));
                const pEl = document.querySelector('span.text-part, .prompt-text, [class*="prompt-text"]');
                if (pEl && pEl.innerText.trim() !== lastPrompt && pEl.innerText.trim().length > 15) {
                    prompt = pEl.innerText.trim();
                    lastPrompt = prompt;
                    break;
                }
            }
            if (!prompt) {
                const pEl = document.querySelector('span.text-part, .prompt-text, [class*="prompt-text"]');
                if (pEl) prompt = pEl.innerText.trim();
            }

            // Match prompt text: "Episode: 1 Scene: 2" or "Episode 01 Scene 02"
            const m = prompt.match(/Episode\s*:?\s*(\d+)[\s\S]*?Scene\s*:?\s*(\d+)/i) || 
                      prompt.match(/EP\s*:?\s*(\d+)[\s\S]*?Scene\s*:?\s*(\d+)/i);
            if (m) {
                const ep = parseInt(m[1], 10);
                const sc = parseInt(m[2], 10);
                if (ep === target_ep) {
                    if (!sceneMap[sc]) {
                        sceneMap[sc] = { src: src, label: label, prompt: prompt };
                    }
                }
            }
        }
        return sceneMap;
    })()'''

    script = scan_code.replace("target_ep", str(target_ep))
    res = exec_js(api_base, script)
    if isinstance(res, dict) and "error" in res:
        log(f"⚠️ Scan notice: {res.get('error')}")
        return {}

    scene_map = res or {}

    # Scroll left/right if missing scenes
    for direction, click_count in [('prev', 12), ('next', 24)]:
        missing = [sc for sc in target_scenes if sc not in [int(k) for k in scene_map.keys()]]
        if not missing:
            break
        log(f"  Missing scenes {missing}. Scrolling rail {direction} {click_count} times...")
        scroll_code = f'''(async () => {{
            const rail = document.querySelector('flow-navigation-rail');
            if (!rail) return;
            const btn = Array.from(rail.querySelectorAll('button')).find(b => (b.getAttribute('aria-label') || '').includes('{ 'ก่อนหน้า' if direction == 'prev' else 'ถัดไป' }'));
            if (btn) {{
                for (let c = 0; c < {click_count}; c++) {{
                    btn.click();
                    await new Promise(r => setTimeout(r, 60));
                }}
            }}
        }})()'''
        exec_js(api_base, scroll_code)
        time.sleep(0.5)

        more_map = exec_js(api_base, script) or {}
        for k, v in more_map.items():
            if k not in scene_map:
                scene_map[k] = v

    return scene_map


def download_image(api_base: str, img_url: str, out_file: str) -> bool:
    """Fetches high-res image via Google Flow browser context and saves locally."""
    fetch_js = f'''(async () => {{
        try {{
            const fullUrl = "{img_url}".replace(/=s\\d+/, '=s2048');
            const resp = await fetch(fullUrl);
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
    return False


def main():
    parser = argparse.ArgumentParser(description="Google Flow Tile Inspector & Exact Prompt Matcher")
    parser.add_argument("--story-path", required=True, help="Path to story directory")
    parser.add_argument("--ep", type=int, required=True, help="Episode number (e.g. 1, 2)")
    parser.add_argument("--scenes", type=str, default="", help="Scene range (e.g. 1-20)")
    parser.add_argument("--api-base", default="http://127.0.0.1:6969", help="FlowKit API URL")
    parser.add_argument("--force", action="store_true", help="Overwrite existing storyboard images")
    parser.add_argument("--dry-run", action="store_true", help="Scan only without downloading")

    args = parser.parse_args()

    local_prompts = load_local_prompts(args.story_path, args.ep)
    total_local = len(local_prompts)
    target_scenes = parse_scene_range(args.scenes, max_scenes=total_local or 25)

    log(f"🔍 Starting Flow Tile Inspector for EP{args.ep:02d}...")
    log(f"   Story Path: {args.story_path}")
    log(f"   Target Scenes ({len(target_scenes)}): {target_scenes}")

    scene_map = scan_flow_tiles(args.api_base, args.ep, target_scenes)
    found_sc_nums = sorted([int(k) for k in scene_map.keys() if int(k) in target_scenes])
    missing_sc_nums = sorted([sc for sc in target_scenes if sc not in found_sc_nums])

    log(f"✅ Found {len(found_sc_nums)}/{len(target_scenes)} scenes on Flow: {found_sc_nums}")
    if missing_sc_nums:
        log(f"⚠️ Missing {len(missing_sc_nums)} scenes on Flow: {missing_sc_nums}")

    if args.dry_run:
        log("Dry-run complete. No files downloaded.")
        return

    out_dir = os.path.join(args.story_path, "6 - Storyboards", f"EP{args.ep:02d}")
    os.makedirs(out_dir, exist_ok=True)

    downloaded = 0
    for sc in found_sc_nums:
        out_file = os.path.join(out_dir, f"EP{args.ep:02d} - Scene {sc:02d}.jpg")
        if os.path.isfile(out_file) and not args.force:
            log(f"  Scene {sc:02d}: File already exists, skipping (--force to overwrite)")
            continue

        info = scene_map.get(sc) or scene_map.get(str(sc))
        img_url = info.get("src")
        if not img_url:
            continue

        prompt_preview = (info.get("prompt") or "").replace("\n", " ")[:60]
        log(f"  📥 Downloading Scene {sc:02d} (Prompt: '{prompt_preview}')...")
        if download_image(args.api_base, img_url, out_file):
            size_kb = os.path.getsize(out_file) // 1024
            log(f"     -> SAVED: {os.path.basename(out_file)} ({size_kb} KB)")
            downloaded += 1
        else:
            log(f"     -> ❌ Download failed for Scene {sc:02d}")

    log(f"\n🎉 Inspection & Recovery complete: {downloaded} downloaded/updated, {len(missing_sc_nums)} missing.")


if __name__ == "__main__":
    main()
