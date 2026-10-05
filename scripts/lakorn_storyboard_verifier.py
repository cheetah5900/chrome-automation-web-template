#!/usr/bin/env python3
"""
Lakorn Storyboard Dual-Verification Engine (lakorn_storyboard_verifier.py)
--------------------------------------------------------------------------
Implements the 2-step verification pipeline after storyboard images are downloaded:
  Step 2.1: Flow Tile Inspector check (verifies actual prompt text in Flow editor 100%)
  Step 2.2: Multimodal Vision audit (character count, vegetable color fidelity: eggplant=purple, pumpkin=orange, etc.)

Usage:
    python3 scripts/lakorn_storyboard_verifier.py \
      --story-path "/path/to/Channels/2 - ผักกาดการละคร - ละครไทย/28" \
      --ep 2 \
      --scenes "1-20"
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from PIL import Image

# Known Vegetable Character Color Rules for "Set ผักเกม"
VEGETABLE_COLOR_RULES = {
    "eggplant": {
        "th_name": "มะเขือม่วง / พ่อแดง",
        "english_roles": ["Eggplant Herbalist", "Phor Daeng", "Eggplant"],
        "required_color": "ม่วง (Purple / Deep Violet)",
        "forbidden_colors": ["เขียวล้วน", "ส้มล้วน", "ขาวล้วน"]
    },
    "pumpkin": {
        "th_name": "ฟักทอง / ขุนเขียว",
        "english_roles": ["Pumpkin Innkeeper", "Pumpkin Superintendent", "Khun Khiao", "Pumpkin"],
        "required_color": "ส้ม (Warm Orange / Amber)",
        "forbidden_colors": ["ม่วงล้วน", "เขียวล้วน"]
    },
    "daikon": {
        "th_name": "หัวไชเท้า-ผักกาดขาว / มีนา",
        "english_roles": ["Daikon Snow Dancer", "Meena", "Daikon"],
        "required_color": "ขาว + ผมใบไม้เขียว (White clay body, green leaf ponytail)",
        "forbidden_colors": ["ม่วงเข้มทั้งตัว", "ส้มทั้งตัว"]
    },
    "broccoli": {
        "th_name": "บล็อกโคลี่ / นที",
        "english_roles": ["Broccoli Librarian", "Natee", "Broccoli"],
        "required_color": "เขียวบล็อกโคลี่ (Green floret head, round spectacles)",
        "forbidden_colors": ["ม่วง", "ส้ม"]
    },
    "okra": {
        "th_name": "กระเจี๊ยบ / อัญญา",
        "english_roles": ["Okra Tinkerer", "Anya", "Okra"],
        "required_color": "เขียวมิ้นต์ (Mint / Light Green with goggles)",
        "forbidden_colors": ["ม่วง", "ส้ม"]
    },
    "turnip": {
        "th_name": "เทอร์นิพ / แม่เมือง",
        "english_roles": ["Turnip Pastry Chef", "Mae Muang", "Turnip"],
        "required_color": "ม่วงอมขาว (Purple-white gradient turnip)",
        "forbidden_colors": ["ส้มแปร๊ด"]
    }
}


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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


def load_scene_context(story_path: str, ep: int, scene_num: int) -> dict:
    ep_str = f"EP{ep:02d}"
    sc_str = f"{scene_num:02d}"
    
    # Prompt
    prompt_file = os.path.join(story_path, "4 - Image Prompt", ep_str, f"{sc_str} - Scene {sc_str}.md")
    prompt_text = ""
    if os.path.isfile(prompt_file):
        prompt_text = open(prompt_file, encoding="utf-8").read().strip()

    # Character Each Scene
    ces_file = os.path.join(story_path, "4 - Character Each Scene", ep_str, f"{sc_str} - Scene {sc_str}.md")
    characters = []
    if os.path.isfile(ces_file):
        for line in open(ces_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                characters.append(line)

    # Animation Prompt (Parity Check)
    anim_file = os.path.join(story_path, "4 - Animation Prompt", ep_str, f"{sc_str} - Scene {sc_str}.md")
    anim_text = ""
    anim_warnings = []
    if os.path.isfile(anim_file):
        anim_text = open(anim_file, encoding="utf-8").read().strip()
        lower_anim = anim_text.lower()
        if len(characters) == 1:
            if any(w in lower_anim for w in ["friends", "companions", "group of", "crowd", "พวกพ้อง", "เพื่อนๆ", "กลุ่มเพื่อน"]):
                anim_warnings.append("Anim ระบุเพื่อน/กลุ่มคน (แต่ CES มีคนเดียว)")
        # Check if more dialogue speakers than characters
        speakers = re.findall(r"-\s*\[.*?\]\s*([^:]+?)(?:\s*(?:says|shouts|whispers|speaks|exclaims)|:)", anim_text, re.IGNORECASE)
        if len(speakers) > len(characters) and len(characters) > 0:
            anim_warnings.append(f"Anim มีผู้พูด {len(speakers)} คน (เกิน CES ที่มี {len(characters)} คน)")

    # Storyboard image
    img_file = os.path.join(story_path, "6 - Storyboards", ep_str, f"{ep_str} - Scene {sc_str}.jpg")
    img_exists = os.path.isfile(img_file)
    img_size_kb = os.path.getsize(img_file) // 1024 if img_exists else 0

    return {
        "scene_num": scene_num,
        "prompt_text": prompt_text,
        "characters": characters,
        "expected_count": len(characters),
        "anim_file": anim_file,
        "anim_exists": os.path.isfile(anim_file),
        "anim_warnings": anim_warnings,
        "img_file": img_file,
        "img_exists": img_exists,
        "img_size_kb": img_size_kb
    }


def step_2_1_tile_inspector_check(story_path: str, ep: int, target_scenes: list[int], api_base: str = "http://127.0.0.1:6969", auto_recover: bool = True) -> dict:
    """Step 2.1: Calls flow_tile_inspector to verify prompt text from Google Flow editor."""
    log(f"🔎 [Step 2.1] Verifying Prompts with flow_tile_inspector on Google Flow (EP{ep:02d})...")
    
    script_path = os.path.join(os.path.dirname(__file__), "flow_tile_inspector.py")
    if not os.path.isfile(script_path):
        script_path = os.path.join(story_path, "SKILL", "0 - สคริปต์อัตโนมัติประจำช่อง (Scripts Hub)", "flow_tile_inspector.py")

    import subprocess
    cmd = [
        sys.executable, script_path,
        "--story-path", story_path,
        "--ep", str(ep),
        "--scenes", f"{min(target_scenes)}-{max(target_scenes)}",
        "--api-base", api_base
    ]
    if auto_recover:
        cmd.append("--force")
    else:
        cmd.append("--dry-run")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = proc.stdout + proc.stderr
        verified_match = []
        missing = []
        for line in output.splitlines():
            if "Found" in line and "scenes on Flow:" in line:
                log(f"  {line.strip()}")
            if "SAVED:" in line:
                log(f"  ✅ {line.strip()}")
            if "Missing" in line and "scenes on Flow:" in line:
                log(f"  ⚠️ {line.strip()}")
        return {"success": proc.returncode == 0, "output": output}
    except Exception as e:
        log(f"  ❌ Tile inspector execution error: {e}")
        return {"success": False, "error": str(e)}


def generate_vision_audit_checklist(story_path: str, ep: int, target_scenes: list[int]) -> list[dict]:
    """Step 2.2: Generates character count and color audit checklist per scene."""
    checklist = []
    for sc in target_scenes:
        ctx = load_scene_context(story_path, ep, sc)
        chars = ctx["characters"]
        exp_count = ctx["expected_count"]
        
        # Color & vegetable mandates for characters in this scene
        char_mandates = []
        for c in chars:
            c_lower = c.lower()
            for veg_key, veg_data in VEGETABLE_COLOR_RULES.items():
                if any(role.lower() in c_lower for role in veg_data["english_roles"]):
                    char_mandates.append(f"{veg_data['th_name']}: สี{veg_data['required_color']}")
                    break

        anim_warn = ctx["anim_warnings"]
        anim_status = "⚠️ " + "; ".join(anim_warn) if anim_warn else "✅ ตรง 1:1"

        checklist.append({
            "scene": f"EP{ep:02d} - Scene {sc:02d}",
            "scene_num": sc,
            "characters": ", ".join(chars) or "ไม่มีตัวละครหลัก",
            "expected_count": exp_count,
            "color_mandates": "; ".join(char_mandates) if char_mandates else "ฉากสิ่งแวดล้อม/ประกอบ",
            "anim_status": anim_status,
            "img_file": ctx["img_file"],
            "img_exists": ctx["img_exists"],
            "img_size_kb": ctx["img_size_kb"]
        })
    return checklist


def main():
    parser = argparse.ArgumentParser(description="Lakorn Storyboard Dual-Verification Engine (Step 2.1 & 2.2)")
    parser.add_argument("--story-path", required=True, help="Path to story directory")
    parser.add_argument("--ep", type=int, required=True, help="Episode number (e.g. 1, 2)")
    parser.add_argument("--scenes", type=str, default="", help="Scene range (e.g. 1-20)")
    parser.add_argument("--skip-tile-inspector", action="store_true", help="Skip Step 2.1 Flow tile inspection")
    parser.add_argument("--api-base", default="http://127.0.0.1:6969", help="FlowKit API URL")

    args = parser.parse_args()
    target_scenes = parse_scene_range(args.scenes)

    log(f"==================================================================")
    log(f"🎬 LAKORN STORYBOARD DUAL-VERIFICATION ENGINE (EP{args.ep:02d})")
    log(f"   Target Scenes ({len(target_scenes)}): {target_scenes}")
    log(f"==================================================================")

    # Step 2.1: Flow Tile Inspector Check
    if not args.skip_tile_inspector:
        step_2_1_tile_inspector_check(args.story_path, args.ep, target_scenes, api_base=args.api_base, auto_recover=True)
    else:
        log("⏩ Skipping Step 2.1 Tile Inspector as requested.")

    # Step 2.2: Vision Audit Preparation & Checklist
    log(f"\n🎨 [Step 2.2] Generating Vision Semantic & Character Audit Checklist...")
    checklist = generate_vision_audit_checklist(args.story_path, args.ep, target_scenes)

    print("\n" + "=" * 115)
    print(f"| {'ฉาก (Scene)':<18} | {'จำนวน':<8} | {'Anim Prompt เช็ค':<25} | {'สีผัก/ตัวละคร':<32} | {'ไฟล์ภาพ':<15} |")
    print("-" * 115)
    for item in checklist:
        status = f"✅ {item['img_size_kb']} KB" if item["img_exists"] and item["img_size_kb"] > 50 else "❌ MISSING"
        print(f"| {item['scene']:<18} | {item['expected_count']:^8} | {item['anim_status'][:25]:<25} | {item['color_mandates'][:32]:<32} | {status:<15} |")
    print("=" * 115)

    log("\n✨ Dual-Verification preparation complete. Ready for Vision Auditor Subagent review!")


if __name__ == "__main__":
    main()
