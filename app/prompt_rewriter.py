import os
import re
import json
import shutil
from typing import Any, Optional
import urllib.request
import urllib.error

from app.seedance import (
    parse_seedance_filter,
    extract_leading_number,
    get_animation_prompt_files,
    extract_prompt_file_index,
    log
)

DEFAULT_SYSTEM_PROMPT = """You are an expert AI Video Prompt Engineer and Content Safety Specialist.
Your task is to rewrite the provided video generation prompt so that it passes strict AI content safety filters (e.g. Dreamina, Seedance, Sora, Kling, Runway, Luma) while strictly preserving its cinematic quality, shot composition, characters, action pacing, and exact timestamp/duration cues (e.g., '0-2s: ...', '2-4s: ...').

Strict Rules:
1. PRESERVE STRUCTURE: Retain all timeline markers ('0-2s:', '2.5-6s:', etc.), camera direction cues ('vertical 9:16', 'handheld camera shake', 'one continuous shot'), lighting, and overall style.
2. REMOVE VIOLENCE & GORE: Remove all gore, severe injuries, blood, fatal collisions, or graphic harm. Replace deadly trauma with high-stakes close calls, miraculous comedic evasions, slapstick timing, or safe thrilling rescues.
3. REMOVE 3RD-PARTY IP & REAL PERSONS: Replace any real-world celebrity names, politician names, copyrighted characters (e.g., Disney, Marvel, Anime IP), and trademarked brand logos with descriptive, fictional equivalents.
4. COMPLIANCE & CLEANUP: Eliminate trigger words that trip automated AI safety filters (such as 'kill', 'mutilated', 'corpse', 'suicide', 'child endangerment', 'blood splatter').
5. OUTPUT ONLY THE REWRITTEN PROMPT: Do not output any preamble, markdown code fences (```), greetings, or explanations. Return strictly the rewritten prompt text only.
"""

SAFETY_PRESETS = {
    "violence": {
        "title": "🩸 ลดทอนความรุนแรง / เลือด / อุบัติเหตุ (Violence & Disaster Softening)",
        "instruction": "Ensure zero blood, zero graphic injuries, and zero fatal trauma. Transform deadly moments into comedic near-misses, dramatic rescues, or slapstick humor where everyone survives unharmed."
    },
    "third_party": {
        "title": "🚫 หลีกเลี่ยงลิขสิทธิ์ / บุคคลที่ 3 / แบรนด์ (Avoid 3rd Party IP & Brands)",
        "instruction": "Strictly replace any references to real living celebrities, famous public figures, copyrighted characters, franchises, or commercial brand names with generic, high-fidelity fictional descriptions."
    },
    "ai_compliance": {
        "title": "🛡️ แก้ไขคำต้องห้ามตามมาตรฐาน AI Content Safety",
        "instruction": "Eliminate all policy trigger words that cause AI video models to reject requests. Maintain cinematic realism and emotional weight without using forbidden vocabulary."
    }
}


def get_prompt_rewriter_summary(
    main_folder: str,
    subfolders_str: str = "",
    prompt_files_str: str = ""
) -> dict[str, Any]:
    """
    Scans subfolders in main_folder and counts animation prompt files matching the filter.
    Returns summary identical to Seedance Gen.
    """
    if not main_folder or not os.path.isdir(main_folder):
        return {
            "ok": False,
            "error": f"ไม่พบโฟลเดอร์หลัก: {main_folder}",
            "total_folders": 0,
            "total_prompt_files": 0,
            "folders": []
        }

    filter_data = parse_seedance_filter(subfolders_str, prompt_files_str)
    folder_targets = filter_data["folder_targets"]
    folder_file_map = filter_data["folder_file_map"]
    raw_numbers = filter_data["raw_numbers"]

    all_subdirs = []
    try:
        entries = sorted(os.listdir(main_folder))
    except Exception as ex:
        return {
            "ok": False,
            "error": f"ไม่สามารถเข้าถึงโฟลเดอร์: {ex}",
            "total_folders": 0,
            "total_prompt_files": 0,
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

    is_leaf = False
    if not all_subdirs:
        direct_files = get_animation_prompt_files(main_folder)
        if direct_files:
            base_name = os.path.basename(main_folder.rstrip(os.sep))
            num = extract_leading_number(base_name)
            all_subdirs.append((num if num is not None else 999999, base_name, main_folder))
            is_leaf = True

    all_subdirs.sort(key=lambda x: (x[0] is None, x[0], x[1]))

    folder_summaries = []
    total_prompt_files = 0

    for num, sub_name, sub_path in all_subdirs:
        files = get_animation_prompt_files(sub_path)
        allowed = folder_file_map.get(num) if num is not None else None
        if allowed is None and is_leaf and raw_numbers:
            allowed = set(raw_numbers)

        if allowed is not None:
            filtered_files = []
            for p_pos, f in enumerate(files, 1):
                f_idx = extract_prompt_file_index(f, fallback_idx=p_pos)
                if f_idx in allowed:
                    filtered_files.append(f)
            files = filtered_files

        count = len(files)
        total_prompt_files += count
        folder_summaries.append({
            "name": sub_name,
            "num": num if num != 999999 else None,
            "path": sub_path,
            "prompt_file_count": count,
            "prompt_files": files
        })

    return {
        "ok": True,
        "main_folder": main_folder,
        "subfolders_filter": subfolders_str,
        "prompt_files_filter": prompt_files_str,
        "total_folders": len(folder_summaries),
        "total_prompt_files": total_prompt_files,
        "folders": folder_summaries
    }


def scan_prompt_rewriter_items(
    main_folder: str,
    subfolders_str: str = "",
    prompt_files_str: str = ""
) -> dict[str, Any]:
    """
    Scans matching markdown prompt files for rewriting.
    Returns list of items with prompt text, file path, and backup status.
    """
    if not main_folder or not os.path.isdir(main_folder):
        return {
            "ok": False,
            "error": f"ไม่พบโฟลเดอร์หลัก: {main_folder}",
            "items": []
        }

    filter_data = parse_seedance_filter(subfolders_str, prompt_files_str)
    folder_targets = filter_data["folder_targets"]
    folder_file_map = filter_data["folder_file_map"]
    raw_numbers = filter_data["raw_numbers"]

    all_subdirs = []
    try:
        entries = sorted(os.listdir(main_folder))
    except Exception as ex:
        return {"ok": False, "error": f"ไม่สามารถเข้าถึงโฟลเดอร์: {ex}", "items": []}

    for entry in entries:
        full_path = os.path.join(main_folder, entry)
        if os.path.isdir(full_path) and not entry.startswith('.'):
            num = extract_leading_number(entry)
            if folder_targets:
                if num is not None and num in folder_targets:
                    all_subdirs.append((num, entry, full_path))
            else:
                all_subdirs.append((num if num is not None else 999999, entry, full_path))

    is_leaf = False
    if not all_subdirs:
        direct_files = get_animation_prompt_files(main_folder)
        if direct_files:
            base_name = os.path.basename(main_folder.rstrip(os.sep))
            num = extract_leading_number(base_name)
            all_subdirs.append((num if num is not None else 999999, base_name, main_folder))
            is_leaf = True

    all_subdirs.sort(key=lambda x: (x[0] is None, x[0], x[1]))

    items = []
    global_idx = 1

    for num, sub_name, sub_path in all_subdirs:
        files = get_animation_prompt_files(sub_path)
        allowed = folder_file_map.get(num) if num is not None else None
        if allowed is None and is_leaf and raw_numbers:
            allowed = set(raw_numbers)

        p_pairs = []
        for p_pos, f in enumerate(files, 1):
            f_idx = extract_prompt_file_index(f, fallback_idx=p_pos)
            if allowed is not None and f_idx not in allowed:
                continue
            p_pairs.append((f_idx, f))

        total_in_sub = len(files)
        for f_idx, f_name in p_pairs:
            f_path = os.path.join(sub_path, f_name)
            prompt_content = ""
            try:
                with open(f_path, "r", encoding="utf-8") as f_obj:
                    prompt_content = f_obj.read().strip()
            except Exception as read_ex:
                log(f"[Prompt Rewriter Warning] ไม่สามารถอ่านไฟล์ '{f_name}': {read_ex}")

            bak_path = f"{f_path}.bak"
            has_backup = os.path.isfile(bak_path)

            base_name = os.path.splitext(f_name)[0]
            items.append({
                "id": f"{num or 'sub'}_{f_idx}_{global_idx}",
                "global_index": global_idx,
                "num": num if num != 999999 else None,
                "subfolder_name": sub_name,
                "subfolder_path": sub_path,
                "prompt_file": f_name,
                "prompt_path": f_path,
                "prompt_base_name": base_name,
                "prompt_text": prompt_content,
                "sub_index": f_idx,
                "total_prompts": total_in_sub,
                "has_backup": has_backup,
                "checked": True
            })
            global_idx += 1

    return {
        "ok": True,
        "main_folder": main_folder,
        "subfolders_filter": subfolders_str,
        "prompt_files_filter": prompt_files_str,
        "total_items": len(items),
        "items": items
    }


def call_ai_rewrite(
    prompt_text: str,
    rules: list[str],
    custom_instruction: str = "",
    provider: str = "gemini",
    api_key: str = "",
    model_name: str = ""
) -> dict[str, Any]:
    """
    Calls Gemini, OpenAI, OpenRouter, or falls back to rule-based safety rewriter.
    """
    if not prompt_text or not prompt_text.strip():
        return {"ok": False, "error": "Prompt text is empty"}

    # Build active instructions
    active_instructions = []
    for r in rules:
        if r in SAFETY_PRESETS:
            active_instructions.append(f"- {SAFETY_PRESETS[r]['title']}: {SAFETY_PRESETS[r]['instruction']}")

    if custom_instruction and custom_instruction.strip():
        active_instructions.append(f"- Custom User Instruction: {custom_instruction.strip()}")

    instructions_text = "\n".join(active_instructions) if active_instructions else "- Soften violence and ensure strict content safety."

    full_system = f"{DEFAULT_SYSTEM_PROMPT}\n\nSpecific Focus Areas for this Request:\n{instructions_text}"

    # 1. Google Gemini Provider
    if provider == "gemini":
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            # Check settings file fallback
            key = _get_key_from_settings("gemini_api_key")

        if not key:
            # Fallback to rule-based transformer if no API key
            log("[Prompt Rewriter] ⚠️ ไม่พบ Gemini API Key สลับไปใช้ Rule-Based Safety Rewriter ชั่วคราว")
            return _rule_based_rewrite(prompt_text, rules, custom_instruction)

        model = model_name or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{full_system}\n\nOriginal Video Prompt to Rewrite:\n{prompt_text}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "topP": 0.95,
                "maxOutputTokens": 2048
            }
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        rewritten = parts[0].get("text", "").strip()
                        # Strip accidental code blocks
                        rewritten = re.sub(r'^```[a-zA-Z]*\n', '', rewritten)
                        rewritten = re.sub(r'\n```$', '', rewritten).strip()
                        return {
                            "ok": True,
                            "rewritten_text": rewritten,
                            "provider": "gemini",
                            "model": model
                        }
                return {"ok": False, "error": f"Gemini returned no candidates: {data}"}
        except Exception as ex:
            log(f"[Prompt Rewriter Gemini Error]: {ex}")
            return {"ok": False, "error": f"Gemini API Error: {ex}"}

    # 2. OpenAI Provider
    elif provider == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY", "") or _get_key_from_settings("openai_api_key")
        if not key:
            log("[Prompt Rewriter] ⚠️ ไม่พบ OpenAI API Key สลับไปใช้ Rule-Based Safety Rewriter ชั่วคราว")
            return _rule_based_rewrite(prompt_text, rules, custom_instruction)

        model = model_name or "gpt-4o-mini"
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": f"Please rewrite this video prompt:\n\n{prompt_text}"}
            ],
            "temperature": 0.4
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    rewritten = choices[0].get("message", {}).get("content", "").strip()
                    rewritten = re.sub(r'^```[a-zA-Z]*\n', '', rewritten)
                    rewritten = re.sub(r'\n```$', '', rewritten).strip()
                    return {"ok": True, "rewritten_text": rewritten, "provider": "openai", "model": model}
                return {"ok": False, "error": f"OpenAI returned no choices: {data}"}
        except Exception as ex:
            log(f"[Prompt Rewriter OpenAI Error]: {ex}")
            return {"ok": False, "error": f"OpenAI API Error: {ex}"}

    # 3. OpenRouter Provider
    elif provider == "openrouter":
        key = api_key or os.environ.get("OPENROUTER_API_KEY", "") or _get_key_from_settings("openrouter_api_key")
        if not key:
            log("[Prompt Rewriter] ⚠️ ไม่พบ OpenRouter API Key สลับไปใช้ Rule-Based Safety Rewriter ชั่วคราว")
            return _rule_based_rewrite(prompt_text, rules, custom_instruction)

        model = model_name or "google/gemini-2.5-flash"
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": f"Please rewrite this video prompt:\n\n{prompt_text}"}
            ],
            "temperature": 0.4
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                    "HTTP-Referer": "http://localhost:6969"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    rewritten = choices[0].get("message", {}).get("content", "").strip()
                    rewritten = re.sub(r'^```[a-zA-Z]*\n', '', rewritten)
                    rewritten = re.sub(r'\n```$', '', rewritten).strip()
                    return {"ok": True, "rewritten_text": rewritten, "provider": "openrouter", "model": model}
                return {"ok": False, "error": f"OpenRouter returned no choices: {data}"}
        except Exception as ex:
            log(f"[Prompt Rewriter OpenRouter Error]: {ex}")
            return {"ok": False, "error": f"OpenRouter API Error: {ex}"}

    # Default fallback
    return _rule_based_rewrite(prompt_text, rules, custom_instruction)


def _get_key_from_settings(key_name: str) -> str:
    """Reads API key from runtime/settings.json if available."""
    try:
        settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime", "settings.json")
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return (data.get(key_name) or "").strip()
    except Exception:
        pass
    return ""


def _rule_based_rewrite(prompt_text: str, rules: list[str], custom_instruction: str = "") -> dict[str, Any]:
    """
    Fallback rule-based safety replacer when no API key is supplied.
    Softens violent phrasing and removes common trigger terms.
    """
    text = prompt_text

    # Violence and injury softening
    replacements = [
        (r'\b(?:blood\s*splatter|bloody?)\b', 'water spray and mist'),
        (r'\b(?:gore|gory|mutilat\w+)\b', 'comic disarray'),
        (r'\b(?:kill\w*|murder\w*|slaughter\w*)\b', 'subdue cleanly'),
        (r'\b(?:crushed|smashed to pieces)\b', 'tumbled safely'),
        (r'\b(?:deadly|fatal)\b', 'turbulent'),
        (r'\b(?:corpses?|dead body|bodies)\b', 'stunned civilians'),
        (r'\b(?:drowning|choking)\b', 'splashing franticly'),
        (r'\b(?:suicide|self-harm)\b', 'chaotic stunt'),
        (r'\b(?:severed|dismembered)\b', 'covered in dust'),
        (r'\b(?:bleeding)\b', 'wiping mud'),
    ]

    for pat, rep in replacements:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)

    # Add safety assurance token if not present
    if "no blood, no gore" not in text.lower():
        text += " (strictly no blood, no gore, family-safe comedic disaster resolution)"

    return {
        "ok": True,
        "rewritten_text": text,
        "provider": "rule_based_fallback",
        "model": "regex_safety_softener"
    }


def execute_prompt_rewriter_batch(
    items: list[dict[str, Any]],
    rules: list[str],
    custom_instruction: str = "",
    provider: str = "gemini",
    api_key: str = "",
    model_name: str = "",
    make_backup: bool = True
) -> dict[str, Any]:
    """
    Executes prompt rewriting for all selected items.
    Saves the rewritten text to the target file (with optional .bak backup).
    """
    results = []
    success_count = 0
    total = len(items)

    for idx, item in enumerate(items):
        f_path = item.get("prompt_path", "")
        f_name = item.get("prompt_file", "")
        orig_text = item.get("prompt_text", "")

        if not orig_text and f_path and os.path.isfile(f_path):
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    orig_text = f.read().strip()
            except Exception:
                orig_text = ""

        if not orig_text:
            results.append({
                "id": item.get("id"),
                "prompt_file": f_name,
                "prompt_path": f_path,
                "ok": False,
                "error": "ไฟล์ข้อความว่างเปล่าหรือไม่พบไฟล์"
            })
            continue

        # Call AI Rewrite
        ai_res = call_ai_rewrite(
            prompt_text=orig_text,
            rules=rules,
            custom_instruction=custom_instruction,
            provider=provider,
            api_key=api_key,
            model_name=model_name
        )

        if not ai_res.get("ok"):
            results.append({
                "id": item.get("id"),
                "prompt_file": f_name,
                "prompt_path": f_path,
                "original_text": orig_text,
                "ok": False,
                "error": ai_res.get("error", "AI Rewrite Failed")
            })
            continue

        rewritten_text = ai_res.get("rewritten_text", "")

        # Write to file
        saved_ok = False
        backup_created = False
        try:
            if make_backup and f_path and os.path.isfile(f_path):
                bak_path = f"{f_path}.bak"
                if not os.path.isfile(bak_path):
                    shutil.copy2(f_path, bak_path)
                backup_created = True

            with open(f_path, "w", encoding="utf-8") as f:
                f.write(rewritten_text)
            saved_ok = True
            success_count += 1
        except Exception as write_err:
            log(f"[Prompt Rewriter Write Error] {write_err}")

        results.append({
            "id": item.get("id"),
            "prompt_file": f_name,
            "prompt_path": f_path,
            "original_text": orig_text,
            "rewritten_text": rewritten_text,
            "provider": ai_res.get("provider"),
            "model": ai_res.get("model"),
            "backup_created": backup_created,
            "saved_ok": saved_ok,
            "ok": saved_ok
        })

    return {
        "ok": success_count > 0,
        "total": total,
        "success_count": success_count,
        "results": results
    }


def restore_prompt_backup(file_path: str) -> dict[str, Any]:
    """
    Restores the original prompt file from its .bak backup.
    """
    if not file_path:
        return {"ok": False, "error": "ไม่ได้ระบุพาธไฟล์"}

    bak_path = f"{file_path}.bak"
    if not os.path.isfile(bak_path):
        return {"ok": False, "error": f"ไม่พบไฟล์สำรอง (.bak): {bak_path}"}

    try:
        shutil.copy2(bak_path, file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            restored_text = f.read()

        return {
            "ok": True,
            "file_path": file_path,
            "restored_text": restored_text,
            "message": "กู้คืนไฟล์ต้นฉบับสำเร็จ"
        }
    except Exception as ex:
        return {"ok": False, "error": f"กู้คืนไฟล์ไม่สำเร็จ: {ex}"}
