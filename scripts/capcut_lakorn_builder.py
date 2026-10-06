#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapCut Lakorn Project Builder & Auto-Editor
Channel: ผักกาดการละคร - ละครไทย

Automates cloning 'ละคร template', importing all scene videos, adding Mix transitions,
stretching/locking watermark & atmosphere filter, positioning outro text & jingle,
looping BGM with crossfade, and locking timeline layers according to Channel Standards.
"""

import os
import sys
import glob
import json
import time
import math
import uuid
import shutil
import hashlib
import argparse
import subprocess
from pythainlp import word_tokenize

CAPCUT_DRAFTS_ROOT = "/Users/litarcopperkaikem/Movies/CapCut/User Data/Projects/com.lveditor.draft"
TEMPLATE_PROJECT_NAME = "ละคร template"
BASE_CHANNEL_DIR = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย"

WHISPER_CLI_PATH = "/opt/homebrew/bin/whisper-cli"
WHISPER_MODEL_PATH = "/Users/litarcopperkaikem/.cache/whisper/ggml-base.bin"
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"


def extract_scene_num(p):
    base = os.path.basename(p)
    parts = base.split(" - ")
    if parts and parts[0].isdigit():
        return int(parts[0])
    return 999


def get_video_files(story_num: str, ep_name: str, scene_range: str = None):
    """Finds and sorts all scene video files for given story and episode."""
    ep_dir = os.path.join(BASE_CHANNEL_DIR, str(story_num), "7 - Videos", ep_name)
    if not os.path.isdir(ep_dir):
        raise FileNotFoundError(f"Video directory not found: {ep_dir}")
    
    all_mp4s = sorted(glob.glob(os.path.join(ep_dir, "*.mp4")))
    if not all_mp4s:
        raise FileNotFoundError(f"No MP4 files found in {ep_dir}")
    
    # Strictly pull File 1 / primary scene file (exclude alternate _v2 files)
    primary_files = [f for f in all_mp4s if not (f.endswith("_v2.mp4") or f.endswith("_v1.mp4"))]
    if not primary_files:
        # Fallback to _v1 if main file does not exist
        primary_files = [f for f in all_mp4s if not f.endswith("_v2.mp4")]
    mp4_files = primary_files or all_mp4s
    
    mp4_files.sort(key=extract_scene_num)
    if scene_range:
        parts = scene_range.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            s_start, s_end = int(parts[0]), int(parts[1])
            mp4_files = [f for f in mp4_files if s_start <= extract_scene_num(f) <= s_end]
    return mp4_files


def create_video_material(mat_id: str, file_path: str, duration_us: int = 8000000):
    """Creates materials.videos entry for CapCut draft."""
    file_name = os.path.basename(file_path)
    unique_id = hashlib.md5(file_path.encode("utf-8")).hexdigest()
    return {
        "id": mat_id,
        "unique_id": unique_id,
        "type": "video",
        "duration": duration_us,
        "path": file_path,
        "media_path": "",
        "local_id": "",
        "has_audio": True,
        "reverse_path": "",
        "intensifies_path": "",
        "reverse_intensifies_path": "",
        "intensifies_audio_path": "",
        "cartoon_path": "",
        "width": 720,
        "height": 1280,
        "category_id": "",
        "category_name": "",
        "material_id": "",
        "material_name": file_name,
        "material_url": "",
        "crop": {
            "upper_left_x": 0.0,
            "upper_left_y": 0.0,
            "upper_right_x": 1.0,
            "upper_right_y": 0.0,
            "lower_left_x": 0.0,
            "lower_left_y": 1.0,
            "lower_right_x": 1.0,
            "lower_right_y": 1.0
        },
        "crop_ratio": "free",
        "audio_fade": None,
        "crop_scale": 1.0,
        "extra_type_option": 0,
        "stable": {
            "stable_level": 0,
            "matrix_path": "",
            "time_range": {"start": 0, "duration": 0}
        },
        "matting": {
            "flag": 0,
            "path": "",
            "interactiveTime": [],
            "has_use_quick_brush": False,
            "strokes": [],
            "has_use_quick_eraser": False,
            "expansion": 0,
            "feather": 0,
            "reverse": False,
            "custom_matting_id": "",
            "enable_matting_stroke": False,
            "is_clould": False,
            "mask_video_path": "",
            "cloud_product_fps": 0.0
        },
        "source": 0,
        "source_platform": 0,
        "formula_id": "",
        "check_flag": 62978047,
        "video_algorithm": {
            "algorithms": [],
            "time_range": None,
            "path": "",
            "gameplay_configs": [],
            "ai_in_painting_config": [],
            "complement_frame_config": None,
            "motion_blur_config": None,
            "deflicker": None,
            "noise_reduction": None,
            "quality_enhance": None,
            "super_resolution": None,
            "ai_background_configs": [],
            "smart_complement_frame": None,
            "aigc_generate": None,
            "aigc_generate_list": [],
            "mouth_shape_driver": None,
            "ai_expression_driven": None,
            "ai_motion_driven": None,
            "image_interpretation": None,
            "story_video_modify_video_config": {
                "task_id": "",
                "is_overwrite_last_video": False,
                "tracker_task_id": "",
                "generate_id": "",
                "generate_card_id": ""
            },
            "skip_algorithm_index": []
        },
        "is_unified_beauty_mode": False,
        "is_set_beauty_mode": False,
        "object_locked": None,
        "smart_motion": None,
        "multi_camera_info": None,
        "freeze": None,
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "team_id": "",
        "local_material_id": "",
        "origin_material_id": "",
        "request_id": "",
        "has_sound_separated": False,
        "is_text_edit_overdub": False,
        "is_ai_generate_content": False,
        "is_video_copilot_aigc_content": False,
        "aigc_type": "none",
        "is_copyright": False,
        "aigc_history_id": "",
        "aigc_item_id": "",
        "local_material_from": "",
        "smart_match_info": None,
        "beauty_face_preset_infos": [],
        "beauty_body_preset_id": "",
        "beauty_face_auto_preset": {
            "preset_id": "",
            "name": "",
            "rate_map": "",
            "scene": ""
        },
        "beauty_face_auto_preset_infos": [],
        "beauty_body_auto_preset": None,
        "live_photo_timestamp": -1,
        "live_photo_cover_path": "",
        "content_feature_info": None,
        "corner_pin": None,
        "surface_trackings": [],
        "video_mask_stroke": {
            "resource_id": "",
            "path": "",
            "type": "",
            "color": "",
            "size": 0.0,
            "alpha": 0.0,
            "distance": 0.0,
            "texture": 0.0,
            "horizontal_shift": 0.0,
            "vertical_shift": 0.0
        },
        "video_mask_shadow": {
            "resource_id": "",
            "path": "",
            "color": "",
            "alpha": 0.0,
            "blur": 0.0,
            "distance": 0.0,
            "angle": 0.0
        },
        "pre_applied_vip_materials": [],
        "workflow_node_id": ""
    }


def create_video_segment(seg_id: str, mat_id: str, start_us: int, dur_us: int, extra_refs: list, speed: float = 1.4, source_dur_us: int = None):
    """Creates a Track 0 video segment."""
    if source_dur_us is None:
        source_dur_us = int(round(dur_us * speed))
    return {
        "id": seg_id,
        "source_timerange": {
            "start": 0,
            "duration": source_dur_us
        },
        "target_timerange": {
            "start": start_us,
            "duration": dur_us
        },
        "render_timerange": {
            "start": 0,
            "duration": 0
        },
        "desc": "",
        "state": 0,
        "speed": speed,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": {
            "scale": {"x": 1.0, "y": 1.0},
            "rotation": 0.0,
            "transform": {"x": 0.0, "y": 0.0},
            "flip": {"vertical": False, "horizontal": False},
            "alpha": 1.0
        },
        "uniform_scale": {
            "on": True,
            "value": 1.0
        },
        "material_id": mat_id,
        "extra_material_refs": extra_refs,
        "render_index": 0,
        "keyframe_refs": [],
        "enable_lut": True,
        "enable_adjust": True,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 0,
        "hdr_settings": {
            "mode": 1,
            "intensity": 1.0,
            "nits": 1000
        },
        "hdr_vivid_settings": None,
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {
            "enable": False,
            "target_follow": "",
            "size_layout": 0,
            "horizontal_pos_layout": 0,
            "vertical_pos_layout": 0
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
        "segment_color_tag": ""
    }


def build_lakorn_project(story_num: str, ep_name: str, target_project_name: str, scene_range: str = None):
    """
    Clones 'ละคร template', injects scene videos, adds transitions,
    and applies all Channel editing standards.
    """
    print(f"\n=======================================================")
    print(f"Building CapCut Project: '{target_project_name}' (Story {story_num}, {ep_name})")
    print(f"=======================================================")
    
    # Ensure standard final output directory exists
    final_dir = os.path.join(BASE_CHANNEL_DIR, str(story_num), "10 - Final")
    os.makedirs(final_dir, exist_ok=True)
    
    template_dir = os.path.join(CAPCUT_DRAFTS_ROOT, TEMPLATE_PROJECT_NAME)
    if not os.path.isdir(template_dir):
        raise FileNotFoundError(f"Template project not found: {template_dir}")
    
    target_project_dir = os.path.join(CAPCUT_DRAFTS_ROOT, target_project_name)
    if os.path.exists(target_project_dir):
        print(f"Target project directory already exists. Removing old copy: {target_project_dir}")
        shutil.rmtree(target_project_dir)
    
    # 1. Clone template
    print(f"Cloning template '{TEMPLATE_PROJECT_NAME}' -> '{target_project_name}'...")
    shutil.copytree(template_dir, target_project_dir)
    
    # 1.1 Purge any leftover cache / tmp / patch files in cloned project
    for tmp_file in glob.glob(os.path.join(target_project_dir, "**", "*.tmp"), recursive=True):
        try: os.remove(tmp_file)
        except: pass
    for bak_file in glob.glob(os.path.join(target_project_dir, "**", "*.bak"), recursive=True):
        try: os.remove(bak_file)
        except: pass
    for patch_dir in glob.glob(os.path.join(target_project_dir, "Timelines", "*", "attachment", "patch")):
        try: shutil.rmtree(patch_dir)
        except: pass
    
    # Generate new UUIDs
    new_draft_id = str(uuid.uuid4()).upper()
    now_us = int(time.time() * 1000000)
    
    # 2. Update draft_meta_info.json
    draft_meta_path = os.path.join(target_project_dir, "draft_meta_info.json")
    with open(draft_meta_path, "r", encoding="utf-8") as f:
        meta_info = json.load(f)
    
    meta_info["draft_id"] = new_draft_id
    meta_info["draft_name"] = target_project_name
    meta_info["draft_fold_path"] = target_project_dir
    meta_info["tm_draft_create"] = now_us
    meta_info["tm_draft_modified"] = now_us
    
    # 3. Locate Timeline
    timelines_dir = os.path.join(target_project_dir, "Timelines")
    subdirs = [d for d in os.listdir(timelines_dir) if os.path.isdir(os.path.join(timelines_dir, d))]
    if not subdirs:
        raise RuntimeError("No timeline directory found under Timelines/")
    timeline_uuid = subdirs[0]
    timeline_draft_path = os.path.join(timelines_dir, timeline_uuid, "draft_info.json")
    root_draft_path = os.path.join(target_project_dir, "draft_info.json")
    
    with open(timeline_draft_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 4. Get video files
    video_files = get_video_files(story_num, ep_name, scene_range)
    print(f"Found {len(video_files)} video clips for {target_project_name} in {ep_name}")
    
    # Resolve tracks dynamically
    video_track = None
    logo_track = None
    outro_text_track = None
    filter_track = None
    outro_audio_track = None
    bgm_track = None
    
    logo_material_id = None
    outro_material_id = None
    bgm_material_id = None
    outro_audio_material_id = None
    
    for txt in data.get("materials", {}).get("texts", []):
        try:
            cj = json.loads(txt.get("content", "{}"))
            tv = cj.get("text", "")
            if "ผักกาดการละคร" in tv:
                logo_material_id = txt.get("id")
            elif "โปรดติดตามตอนต่อไป" in tv:
                outro_material_id = txt.get("id")
        except:
            pass
            
    for aud in data.get("materials", {}).get("audios", []):
        path_a = aud.get("path", "").lower()
        name_a = aud.get("name", "").lower()
        dur_a = aud.get("duration", 0)
        if "ดราม่า" in name_a or "ดราม่า" in path_a or "music" in path_a or dur_a > 30000000:
            bgm_material_id = aud.get("id")
        elif "continued" in name_a or "continued" in path_a or "outro" in name_a:
            outro_audio_material_id = aud.get("id")
            
    # Deduplicate materials.audios by ID
    unique_audios = []
    seen_aud_ids = set()
    for aud in data.get("materials", {}).get("audios", []):
        aud_id = aud.get("id")
        if aud_id and aud_id not in seen_aud_ids:
            seen_aud_ids.add(aud_id)
            unique_audios.append(aud)
        elif not aud_id:
            unique_audios.append(aud)
    data.setdefault("materials", {})["audios"] = unique_audios

    # Ensure Fade In animation exists in materials.material_animations
    fade_anim_id = None
    for ma in data.get("materials", {}).get("material_animations", []):
        for a in ma.get("animations", []):
            if a.get("name") == "Fade In" and a.get("type") == "in":
                fade_anim_id = ma.get("id")
                break
    if not fade_anim_id:
        fade_anim_id = str(uuid.uuid4()).upper()
        data.setdefault("materials", {}).setdefault("material_animations", []).append({
            "id": fade_anim_id,
            "type": "sticker_animation",
            "animations": [{
                "id": "6724916044072227332",
                "type": "in",
                "start": 0,
                "duration": 500000,
                "path": "/Users/litarcopperkaikem/Movies/CapCut/User Data/Cache/effect/6724916044072227332/3ed092e2c06abae5644f5f12014e3020",
                "platform": "all",
                "resource_id": "6724916044072227332",
                "third_resource_id": "6724916044072227332",
                "source_platform": 1,
                "name": "Fade In",
                "category_id": "ruchang",
                "category_name": "text",
                "panel": "",
                "material_type": "sticker",
                "anim_adjust_params": None,
                "request_id": "20260929091926000000000000216A42E"
            }],
            "multi_language_current": "none"
        })

    # Style outro text material ("โปรดติดตามตอนต่อไป")
    for t in data.get("materials", {}).get("texts", []):
        if t.get("id") == outro_material_id:
            t["font_size"] = 25.0
            t["text_size"] = 30
            t["text_color"] = "#000000"
            t["border_color"] = "#ffffff"
            t["border_width"] = 0.08
            t["border_alpha"] = 1.0
            c_obj = {
                "styles": [{
                    "fill": {"content": {"solid": {"color": [0, 0, 0]}, "render_type": "solid"}},
                    "range": [0, 18],
                    "strokes": [{"width": 0.0599999986588955, "mode": 0, "content": {"solid": {"color": [1, 1, 1]}, "render_type": "solid"}}],
                    "useLetterColor": True,
                    "size": 25,
                    "font": {"path": "/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf", "id": ""}
                }],
                "text": "โปรดติดตามตอนต่อไป"
            }
            t["content"] = json.dumps(c_obj, ensure_ascii=False)

    main_video_track = None
    filter_track = None
    bgm_candidates = []
    logo_seg = None
    outro_seg = None
    logo_track_orig = None
    outro_track_orig = None

    for track in data.get("tracks", []):
        t_type = track.get("type")
        segs = track.get("segments", [])
        if t_type == "video":
            if track.get("flag") == 0 and main_video_track is None:
                main_video_track = track
        elif t_type == "filter":
            filter_track = track
        elif t_type == "text":
            for s in segs:
                if s.get("material_id") == logo_material_id and not logo_seg:
                    logo_seg = s
                    logo_track_orig = track
                elif s.get("material_id") == outro_material_id and not outro_seg:
                    outro_seg = s
                    outro_track_orig = track
        elif t_type == "audio":
            for s in segs:
                if s.get("material_id") == bgm_material_id:
                    bgm_candidates.append(track)
                    break
                    
    if not main_video_track:
        raise RuntimeError("No main video track found in template!")

    # Resolve exactly ONE main BGM track (prefer the one starting at 0 and not named loop)
    bgm_track = None
    if bgm_candidates:
        bgm_track = next((t for t in bgm_candidates if t.get("name") != "BG Music Loop" and t.get("segments", [{}])[0].get("target_timerange", {}).get("start", 0) == 0), None)
        if not bgm_track:
            bgm_track = next((t for t in bgm_candidates if t.get("name") != "BG Music Loop"), None)
        if not bgm_track:
            bgm_track = bgm_candidates[0]

    # Build clean separated text tracks
    outro_text_track = {
        "id": outro_track_orig.get("id") if outro_track_orig and outro_track_orig != logo_track_orig else str(uuid.uuid4()).upper(),
        "type": "text",
        "flag": 0,
        "attribute": 0,
        "name": "",
        "segments": [outro_seg] if outro_seg else []
    }
    logo_track = {
        "id": logo_track_orig.get("id") if logo_track_orig else str(uuid.uuid4()).upper(),
        "type": "text",
        "flag": 0,
        "attribute": 4,
        "name": "",
        "segments": [logo_seg] if logo_seg else []
    }

    ordered_tracks = [main_video_track, outro_text_track, logo_track]
    if filter_track:
        ordered_tracks.append(filter_track)
    if bgm_track:
        ordered_tracks.append(bgm_track)
    data["tracks"] = ordered_tracks

    print(f"Tracks resolved: Main Video Track ID={main_video_track.get('id')[:8]}, Outro Text Track ID={outro_text_track.get('id')[:8]}, Logo Track ID={logo_track.get('id')[:8]}, BGM Track ID={bgm_track.get('id')[:8] if bgm_track else 'N/A'}")
    
    # 5. Clean template video materials & populate with new scene clips
    # Discard old template videos (including 'to be continued') completely!
    data["materials"]["videos"] = []
    video_materials = data["materials"]["videos"]
    data["materials"]["transitions"] = []
    transitions = data["materials"]["transitions"]
    
    main_video_track["segments"] = []
    video_track = main_video_track
    
    speeds = data.setdefault("materials", {}).setdefault("speeds", [])
    placeholders = data.setdefault("materials", {}).setdefault("placeholder_infos", [])
    canvases = data.setdefault("materials", {}).setdefault("canvases", [])
    sound_channel_mappings = data.setdefault("materials", {}).setdefault("sound_channel_mappings", [])
    material_colors = data.setdefault("materials", {}).setdefault("material_colors", [])
    vocal_separations = data.setdefault("materials", {}).setdefault("vocal_separations", [])
    
    clip_speed = 1.4
    source_clip_dur_us = 8000000  # 8.0s per Google Flow clip
    target_clip_dur_us = int(round(source_clip_dur_us / clip_speed))  # 5,714,286 us (~5.71s per clip at 1.4x)
    total_clips = len(video_files)
    total_video_dur = total_clips * target_clip_dur_us
    
    current_time_us = 0
    for idx, vpath in enumerate(video_files):
        v_mat_id = str(uuid.uuid4()).upper()
        v_mat = create_video_material(v_mat_id, vpath, source_clip_dur_us)
        video_materials.append(v_mat)
        
        speed_id = str(uuid.uuid4()).upper()
        speeds.append({"id": speed_id, "type": "speed", "mode": 0, "speed": clip_speed, "curve_speed": None})
        
        ph_id = str(uuid.uuid4()).upper()
        placeholders.append({"id": ph_id, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        
        canvas_id = str(uuid.uuid4()).upper()
        canvases.append({"id": canvas_id, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        
        scm_id = str(uuid.uuid4()).upper()
        sound_channel_mappings.append({"id": scm_id, "type": "none", "audio_channel_mapping": 0, "is_config_open": False})
        
        mc_id = str(uuid.uuid4()).upper()
        material_colors.append({"id": mc_id, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        
        vs_id = str(uuid.uuid4()).upper()
        vocal_separations.append({"id": vs_id, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})
        
        extra_refs = [speed_id, ph_id]
        
        # Mix transition between adjacent video clips (clips 0 to N-2)
        if idx < total_clips - 1:
            trans_id = str(uuid.uuid4()).upper()
            trans_mat = {
                "id": trans_id,
                "type": "transition",
                "name": "Mix",
                "effect_id": "6724845717472416269",
                "resource_id": "6724845717472416269",
                "third_resource_id": "6724845717472416269",
                "source_platform": 1,
                "path": "/Users/litarcopperkaikem/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/6724845717472416269/7b53f4c008c4c684fccf8c7d4d46cc92",
                "duration": 500000,
                "is_overlap": True,
                "platform": "all",
                "category_id": "100000",
                "category_name": "",
                "request_id": "",
                "is_ai_transition": False,
                "video_path": "",
                "task_id": ""
            }
            transitions.append(trans_mat)
            extra_refs.append(trans_id)
            
        extra_refs.extend([canvas_id, scm_id, mc_id, vs_id])
        
        seg_id = str(uuid.uuid4()).upper()
        seg = create_video_segment(seg_id, v_mat_id, current_time_us, target_clip_dur_us, extra_refs, speed=clip_speed, source_dur_us=source_clip_dur_us)
        video_track["segments"].append(seg)
        
        current_time_us += target_clip_dur_us

    print(f"Added {len(video_track['segments'])} video segments. Total Video Duration: {total_video_dur / 1000000:.2f}s ({total_video_dur} us)")

    # 6. Stretch Logo and Filter & Lock with Padlock
    if logo_seg:
        logo_track["flag"] = 0
        logo_track["attribute"] = (logo_track.get("attribute", 0) & 3) | 4
        logo_seg["target_timerange"]["start"] = 0
        logo_seg["target_timerange"]["duration"] = total_video_dur
        print(f"Locked Logo Track and stretched to {total_video_dur / 1000000:.2f}s")
        
    if filter_track:
        filter_track["flag"] = 0
        filter_track["attribute"] = (filter_track.get("attribute", 0) & 3) | 4
        for seg in filter_track.get("segments", []):
            seg["target_timerange"]["start"] = 0
            seg["target_timerange"]["duration"] = total_video_dur
        print(f"Locked Filter Track and stretched to {total_video_dur / 1000000:.2f}s")

    # 7. Position Outro Text ('โปรดติดตามตอนต่อไป') with Fade In at tail of last scene
    if outro_seg:
        outro_dur = 2616667
        outro_seg["target_timerange"]["start"] = max(0, total_video_dur - outro_dur)
        outro_seg["target_timerange"]["duration"] = outro_dur
        outro_seg["clip"] = {
            "scale": {"x": 1.0, "y": 1.0},
            "rotation": 0.0,
            "transform": {"x": 0.0, "y": 0.594758064516129},
            "flip": {"vertical": False, "horizontal": False},
            "alpha": 1.0
        }
        outro_seg["render_index"] = 14001
        outro_seg["track_render_index"] = 1
        outro_seg["extra_material_refs"] = [fade_anim_id]
        print(f"Positioned Outro Text ('โปรดติดตามตอนต่อไป') with Fade In at tail: {total_video_dur - outro_dur} us")

    # 8. Loop and Configure BGM with Cross-Fade (-15 dB volume)
    if bgm_track and len(bgm_track.get("segments", [])) > 0:
        bgm_track["flag"] = 0
        bgm_track["attribute"] = (bgm_track.get("attribute", 0) & 3) | 4
        bgm_track["name"] = "BG Music"
        bgm_track["is_default_name"] = False
        template_seg = json.loads(json.dumps(bgm_track["segments"][0]))
        
        bgm_volume = 10 ** (-15 / 20)  # -15 dB
        bgm_track["segments"] = []
        
        loop_track_id = str(uuid.uuid4()).upper()
        loop_track = {
            "id": loop_track_id,
            "type": "audio",
            "segments": [],
            "flag": 0,
            "attribute": bgm_track["attribute"],
            "name": "BG Music Loop",
            "is_default_name": False
        }
        
        chunk_dur = 55366666
        overlap_dur = 2000000
        step_dur = chunk_dur - overlap_dur  # 53366666
        source_start = 39066666
        
        curr_start = 0
        seg_idx = 0
        while curr_start < total_video_dur:
            dur = min(chunk_dur, total_video_dur - curr_start)
            is_first = (curr_start == 0)
            is_last = (curr_start + dur >= total_video_dur)
            
            fade_in = 0 if is_first else overlap_dur
            fade_out = overlap_dur if not is_last else 2000000
            
            fade_id = str(uuid.uuid4()).upper()
            data.setdefault("materials", {}).setdefault("audio_fades", []).append({
                "id": fade_id,
                "type": "audio_fade",
                "fade_type": 0,
                "fade_in_duration": fade_in,
                "fade_out_duration": fade_out
            })
            
            seg = json.loads(json.dumps(template_seg))
            seg["id"] = str(uuid.uuid4()).upper()
            seg["target_timerange"]["start"] = curr_start
            seg["target_timerange"]["duration"] = dur
            seg["source_timerange"]["start"] = source_start
            seg["source_timerange"]["duration"] = dur
            seg["volume"] = bgm_volume
            seg["last_nonzero_volume"] = bgm_volume
            seg["extra_material_refs"] = [fade_id]
            
            if seg_idx % 2 == 0:
                bgm_track["segments"].append(seg)
            else:
                loop_track["segments"].append(seg)
                
            curr_start += step_dur
            seg_idx += 1
            
        if loop_track["segments"]:
            data["tracks"].append(loop_track)
        print(f"Configured {seg_idx} BGM segments across BG Music and BG Music Loop tracks (-15 dB, cross-fade {overlap_dur / 1000000:.1f}s)")

    # 9. Set project duration
    data["duration"] = total_video_dur
    meta_info["tm_duration"] = total_video_dur

    # 9.1 Update draft_materials in meta_info (CapCut Import Media panel)
    cleaned_materials = []
    for entry in meta_info.get("draft_materials", []):
        if entry.get("type") == 0:
            cleaned_val = [item for item in entry.get("value", []) if os.path.exists(item.get("file_Path", "")) and "continued" not in item.get("file_Path", "").lower()]
            entry["value"] = cleaned_val
            cleaned_materials.append(entry)
        else:
            cleaned_materials.append(entry)

    type0_entry = next((e for e in cleaned_materials if e.get("type") == 0), None)
    if not type0_entry:
        type0_entry = {"type": 0, "value": []}
        cleaned_materials.insert(0, type0_entry)

    existing_paths = {item.get("file_Path") for item in type0_entry.get("value", [])}
    for vpath in video_files:
        if vpath not in existing_paths:
            v_id = hashlib.md5(vpath.encode("utf-8")).hexdigest()
            type0_entry["value"].append({
                "ai_group_type": "",
                "create_time": now_us // 1000000,
                "duration": source_clip_dur_us,
                "enter_from": "",
                "extra_info": "",
                "file_Path": vpath,
                "height": 1280,
                "id": str(uuid.uuid4()).upper(),
                "import_time": now_us // 1000000,
                "import_time_ms": now_us // 1000,
                "item_source": 1,
                "material_color_tag": 0,
                "md5": v_id,
                "metetype": "video",
                "roughcut_time_range": {"duration": 0, "start": 0},
                "sub_time_range": {"duration": -1, "start": -1},
                "type": 0,
                "width": 720
            })
    meta_info["draft_materials"] = cleaned_materials

    # 10. Sync save to both timeline draft and project root
    paths_to_write = [
        timeline_draft_path,
        timeline_draft_path + ".bak",
        root_draft_path,
        root_draft_path + ".bak"
    ]
    for p in paths_to_write:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            
    with open(draft_meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_info, f, ensure_ascii=False, indent=2)
        
    print(f"Draft files saved synchronized across all timeline and root paths.")

    # 11. Register in root_meta_info.json
    root_meta_path = os.path.join(CAPCUT_DRAFTS_ROOT, "root_meta_info.json")
    with open(root_meta_path, "r", encoding="utf-8") as f:
        root_meta = json.load(f)
        
    all_drafts = root_meta.get("all_draft_store", [])
    # Find template entry to copy fields
    template_entry = None
    for d in all_drafts:
        if d.get("draft_name") == TEMPLATE_PROJECT_NAME:
            template_entry = d
            break
            
    if not template_entry and all_drafts:
        template_entry = all_drafts[0]
        
    # Remove existing entry for target_project_name if exists
    all_drafts = [d for d in all_drafts if d.get("draft_name") != target_project_name]
    
    new_entry = dict(template_entry)
    new_entry["draft_id"] = new_draft_id
    new_entry["draft_name"] = target_project_name
    new_entry["draft_fold_path"] = target_project_dir
    new_entry["draft_cover"] = os.path.join(target_project_dir, "draft_cover.jpg")
    new_entry["draft_json_file"] = root_draft_path
    new_entry["tm_draft_create"] = now_us
    new_entry["tm_draft_modified"] = now_us
    new_entry["tm_duration"] = total_video_dur
    
    all_drafts.insert(0, new_entry)
    root_meta["all_draft_store"] = all_drafts
    
    with open(root_meta_path, "w", encoding="utf-8") as f:
        json.dump(root_meta, f, ensure_ascii=False)
        
    print(f"Registered project '{target_project_name}' (ID: {new_draft_id}) into root_meta_info.json!")
    print(f"Project '{target_project_name}' successfully built and ready in CapCut!\n")
    return new_draft_id


def subtract_intervals(cut_ints, silent_ints):
    """Subtracts silent interval protection zones from cut intervals."""
    result = []
    for c_start, c_end in cut_ints:
        current_pieces = [(c_start, c_end)]
        for s_start, s_end in silent_ints:
            next_pieces = []
            for p_start, p_end in current_pieces:
                if s_end <= p_start or s_start >= p_end:
                    next_pieces.append((p_start, p_end))
                else:
                    if s_start > p_start:
                        next_pieces.append((p_start, s_start))
                    if s_end < p_end:
                        next_pieces.append((s_end, p_end))
            current_pieces = next_pieces
        result.extend(current_pieces)
    return result


def split_interval_by_speech(S_seg, E_seg, speech_ranges):
    """Splits an audio segment interval into speech (kept) and non-speech (discarded) parts."""
    overlapping = []
    for S_sp, E_sp in speech_ranges:
        if not (E_sp <= S_seg or S_sp >= E_seg):
            overlap_S = max(S_seg, S_sp)
            overlap_E = min(E_seg, E_sp)
            overlapping.append((overlap_S, overlap_E))
            
    parts = []
    curr = S_seg
    for S_sp, E_sp in overlapping:
        if S_sp > curr:
            parts.append((curr, S_sp, False))
        parts.append((S_sp, E_sp, True))
        curr = E_sp
    if curr < E_seg:
        parts.append((curr, E_seg, False))
    return parts


def refine_project_captions(project_name: str):
    """
    Phase 2: Caption-driven timeline refinement.
    Runs after user generates Auto Captions in CapCut:
    - Splits captions > 4s into two parts
    - Formats subtitles (font size 17, white with black border 0.06, 5-word balanced wrapping)
    - Detects Dead Air (>1s gap with 0.2s buffer) and ripple cuts timeline
    - Preserves silent action scenes (no speech)
    - Prevents sliver glitch cuts (<0.25s)
    - Removes silent gaps from dialogue audio tracks
    - Syncs project duration, logo, filter, outro, and BGM loops
    """
    project_dir = os.path.join(CAPCUT_DRAFTS_ROOT, project_name)
    if not os.path.isdir(project_dir):
        raise FileNotFoundError(f"Project '{project_name}' not found at: {project_dir}")

    # Locate timeline draft_info.json
    timelines_pattern = os.path.join(project_dir, "Timelines", "*", "draft_info.json")
    timeline_matches = glob.glob(timelines_pattern)
    if not timeline_matches:
        raise FileNotFoundError(f"No timeline draft_info.json found in {project_dir}")
    timeline_draft_path = timeline_matches[0]
    root_draft_path = os.path.join(project_dir, "draft_info.json")
    draft_meta_path = os.path.join(project_dir, "draft_meta_info.json")

    with open(timeline_draft_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Identify caption track (text track with highest segment count)
    caption_track = None
    max_segs = 0
    for track in data.get("tracks", []):
        if track.get("type") == "text":
            segs = track.get("segments", [])
            if len(segs) > max_segs:
                max_segs = len(segs)
                caption_track = track

    if not caption_track or max_segs <= 1:
        print(f"⚠️ Project '{project_name}': No auto-caption track found (segments: {max_segs}).")
        print("   Please generate Auto Captions inside CapCut first before running Phase 2 refinement.")
        return False

    caption_track_id = caption_track.get("id")
    print(f"[{project_name}] Found Caption Track with {max_segs} segments. Starting Phase 2 refinement...")

    # Identify Logo and Outro material IDs
    logo_material_id = None
    outro_material_id = None
    for txt_mat in data.get("materials", {}).get("texts", []):
        try:
            content_json = json.loads(txt_mat.get("content", "{}"))
            text_val = content_json.get("text", "")
            if "ผักกาดการละคร" in text_val:
                logo_material_id = txt_mat.get("id")
            elif "โปรดติดตามตอนต่อไป" in text_val:
                outro_material_id = txt_mat.get("id")
        except:
            pass

    # 1.1 Split captions > 4s
    texts_materials = data.setdefault("materials", {}).setdefault("texts", [])
    new_caption_segments = []
    split_threshold_time = 4000000  # 4 seconds

    for seg in caption_track.get("segments", []):
        mat_id = seg.get("material_id")
        if mat_id == logo_material_id or mat_id == outro_material_id:
            new_caption_segments.append(seg)
            continue
        
        target = seg.get("target_timerange", {})
        S = target.get("start", 0)
        D = target.get("duration", 0)
        
        if D > split_threshold_time:
            orig_txt_mat = next((t for t in texts_materials if t.get("id") == mat_id), None)
            old_text = ""
            if orig_txt_mat:
                try:
                    old_text = json.loads(orig_txt_mat.get("content", "{}")).get("text", "")
                except:
                    pass
            tokens = word_tokenize(old_text)
            ratio = float(split_threshold_time) / float(D)
            idx_split = max(1, int(len(tokens) * ratio))
            text_1 = "".join(tokens[:idx_split])
            text_2 = "".join(tokens[idx_split:])
            if not text_2.strip():
                text_2 = "..."
                
            new_mat_id = str(uuid.uuid4()).upper()
            if orig_txt_mat:
                new_txt_mat = json.loads(json.dumps(orig_txt_mat))
                new_txt_mat["id"] = new_mat_id
                
                try:
                    c_json = json.loads(new_txt_mat.get("content", "{}"))
                    c_json["text"] = text_2
                    new_txt_mat["content"] = json.dumps(c_json, ensure_ascii=False)
                except:
                    pass
                if new_txt_mat.get("base_content"):
                    try:
                        bc_json = json.loads(new_txt_mat["base_content"])
                        bc_json["text"] = text_2
                        new_txt_mat["base_content"] = json.dumps(bc_json, ensure_ascii=False)
                    except:
                        pass
                texts_materials.append(new_txt_mat)
                
                try:
                    c_json = json.loads(orig_txt_mat.get("content", "{}"))
                    c_json["text"] = text_1
                    orig_txt_mat["content"] = json.dumps(c_json, ensure_ascii=False)
                except:
                    pass
                if orig_txt_mat.get("base_content"):
                    try:
                        bc_json = json.loads(orig_txt_mat["base_content"])
                        bc_json["text"] = text_1
                        orig_txt_mat["base_content"] = json.dumps(bc_json, ensure_ascii=False)
                    except:
                        pass
            
            seg_1 = json.loads(json.dumps(seg))
            seg_1["target_timerange"]["duration"] = split_threshold_time
            
            seg_2 = json.loads(json.dumps(seg))
            seg_2["id"] = str(uuid.uuid4()).upper()
            seg_2["target_timerange"]["start"] = S + split_threshold_time
            seg_2["target_timerange"]["duration"] = D - split_threshold_time
            seg_2["material_id"] = new_mat_id
            
            new_caption_segments.append(seg_1)
            new_caption_segments.append(seg_2)
        else:
            new_caption_segments.append(seg)

    caption_track["segments"] = new_caption_segments

    # Gather subtitle material IDs
    subtitle_material_ids = {
        seg.get("material_id") for seg in caption_track.get("segments", [])
        if seg.get("material_id") not in [logo_material_id, outro_material_id]
    }

    if not subtitle_material_ids:
        print(f"⚠️ Project '{project_name}': No dialogue subtitles found (only logo/outro present).")
        print("   Please open CapCut, click 'Auto Captions' to generate captions, then run this command again.")
        return False

    # Format subtitles: size 17, white with black stroke, ~5 words per line
    for txt in texts_materials:
        txt_id = txt.get("id")
        if txt_id in subtitle_material_ids:
            txt["font_size"] = 17.0
            txt["text_size"] = 17
            try:
                content_json = json.loads(txt.get("content", "{}"))
                old_text = content_json.get("text", "")
                tokens = word_tokenize(old_text)
                n_tok = len(tokens)
                L = math.ceil(n_tok / 5)
                new_text_parts = []
                idx = 0
                if L > 0:
                    base_size = n_tok // L
                    extra = n_tok % L
                    for i in range(L):
                        size = base_size + (1 if i < extra else 0)
                        new_text_parts.append("".join(tokens[idx:idx+size]))
                        idx += size
                new_text = "\n".join(new_text_parts) if new_text_parts else old_text
                txt["recognize_text"] = new_text
                if "words" in txt and "text" in txt["words"]:
                    txt["words"]["text"] = [new_text]
                
                style_obj = {
                    "fill": {
                        "alpha": 1.0,
                        "content": {
                            "render_type": "solid",
                            "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]}
                        }
                    },
                    "font": {
                        "id": "",
                        "path": "/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf"
                    },
                    "range": [0, len(new_text)],
                    "size": 17,
                    "strokes": [
                        {
                            "alpha": 1.0,
                            "content": {
                                "render_type": "solid",
                                "solid": {"alpha": 1.0, "color": [0.0, 0.0, 0.0]}
                            },
                            "width": 0.05999999865889549
                        }
                    ],
                    "useLetterColor": True
                }
                content_json["text"] = new_text
                content_json["styles"] = [style_obj]
                txt["content"] = json.dumps(content_json, ensure_ascii=False)
                if txt.get("base_content"):
                    bc_json = json.loads(txt["base_content"])
                    bc_json["text"] = new_text
                    bc_json["styles"] = [style_obj]
                    txt["base_content"] = json.dumps(bc_json, ensure_ascii=False)
            except Exception as e:
                pass

    # Find logo, outro, filter, BGM tracks
    logo_track_id = None
    outro_track_id = None
    filter_track_id = None
    music_track_ids = set()

    for track in data.get("tracks", []):
        t_type = track.get("type")
        if t_type == "filter":
            filter_track_id = track.get("id")
        elif t_type == "text":
            for s in track.get("segments", []):
                if s.get("material_id") == logo_material_id:
                    logo_track_id = track.get("id")
                elif s.get("material_id") == outro_material_id:
                    outro_track_id = track.get("id")
        elif t_type == "audio":
            t_name = track.get("name", "").lower()
            if "bg music" in t_name or "bgm" in t_name or "loop" in t_name:
                music_track_ids.add(track.get("id"))
            else:
                for seg in track.get("segments", []):
                    mat_id = seg.get("material_id")
                    for a in data.get("materials", {}).get("audios", []):
                        if a.get("id") == mat_id and ("ดราม่า" in a.get("name", "") or a.get("duration", 0) > 30000000):
                            music_track_ids.add(track.get("id"))

    # Video segments
    video_track = next((t for t in data.get("tracks", []) if t.get("type") == "video" and t.get("flag") == 0), None)
    if not video_track:
        video_track = next((t for t in data.get("tracks", []) if t.get("type") == "video"), None)
    video_segments = video_track.get("segments", []) if video_track else []

    # 2. Dead Air Calculation
    buffer = 200000     # 0.2s buffer
    threshold = 1000000  # 1.0s gap
    cuts = []
    segs = sorted(caption_track.get("segments", []), key=lambda s: s.get("target_timerange", {}).get("start", 0))
    for i in range(len(segs) - 1):
        end_a = segs[i].get("target_timerange", {}).get("start", 0) + segs[i].get("target_timerange", {}).get("duration", 0)
        start_b = segs[i+1].get("target_timerange", {}).get("start", 0)
        gap = start_b - end_a
        if gap > threshold:
            cut_start = end_a + buffer
            cut_end = start_b - buffer
            if cut_end > cut_start:
                cuts.append((cut_start, cut_end - cut_start))

    # Exclude silent video segments (action scenes with no speech)
    silent_video_segments = []
    for seg in video_segments:
        v_start = seg.get("target_timerange", {}).get("start", 0)
        v_end = v_start + seg.get("target_timerange", {}).get("duration", 0)
        has_speech = False
        for cap in caption_track.get("segments", []):
            c_start = cap.get("target_timerange", {}).get("start", 0)
            c_end = c_start + cap.get("target_timerange", {}).get("duration", 0)
            if not (c_end <= v_start or c_start >= v_end):
                has_speech = True
                break
        if not has_speech:
            silent_video_segments.append((v_start, v_end))

    cut_intervals = [(c_s, c_s + c_d) for c_s, c_d in cuts]
    adjusted_cut_intervals = subtract_intervals(cut_intervals, silent_video_segments)
    cuts = [(c_s, c_e - c_s) for c_s, c_e in adjusted_cut_intervals]

    # Sliver glitch prevention (sliver_threshold = 0.25s)
    sliver_threshold = 250000
    adjusted_cuts = []
    for cut_start, cut_dur in cuts:
        cut_end = cut_start + cut_dur
        for seg in video_segments:
            S = seg.get("target_timerange", {}).get("start", 0)
            E = S + seg.get("target_timerange", {}).get("duration", 0)
            if S < cut_start and (cut_start - S) < sliver_threshold:
                cut_start = S
            if E > cut_end and (E - cut_end) < sliver_threshold:
                cut_end = E
        if cut_end > cut_start:
            adjusted_cuts.append((cut_start, cut_end - cut_start))

    # Sort descending so cuts don't invalidate upcoming time offsets
    adjusted_cuts.sort(key=lambda c: c[0], reverse=True)

    # 4. Ripple Cut Timeline
    skip_tracks = set([logo_track_id, filter_track_id, outro_track_id] + list(music_track_ids))
    for cut_start, cut_dur in adjusted_cuts:
        for track in data.get("tracks", []):
            if track.get("id") in skip_tracks:
                continue
            new_segs = []
            for seg in track.get("segments", []):
                target = seg.get("target_timerange", {})
                S = target.get("start", 0)
                D = target.get("duration", 0)
                E = S + D
                if E <= cut_start:
                    new_segs.append(seg)
                elif S >= cut_start + cut_dur:
                    target["start"] = S - cut_dur
                    new_segs.append(seg)
                else:
                    source = seg.get("source_timerange")
                    S_src = source.get("start", 0) if source else 0
                    speed = seg.get("speed", 1.0)
                    if S < cut_start and E > cut_start + cut_dur:
                        seg_l = json.loads(json.dumps(seg))
                        t_dur_l = cut_start - S
                        seg_l["target_timerange"]["duration"] = t_dur_l
                        if source:
                            seg_l["source_timerange"]["duration"] = int(round(t_dur_l * speed))
                        new_segs.append(seg_l)
                        
                        seg_r = json.loads(json.dumps(seg))
                        seg_r["id"] = str(uuid.uuid4()).upper()
                        t_dur_r = E - (cut_start + cut_dur)
                        seg_r["target_timerange"]["start"] = cut_start
                        seg_r["target_timerange"]["duration"] = t_dur_r
                        if source:
                            seg_r["source_timerange"]["start"] = S_src + int(round(((cut_start - S) + cut_dur) * speed))
                            seg_r["source_timerange"]["duration"] = int(round(t_dur_r * speed))
                        new_segs.append(seg_r)
                    elif S < cut_start and E <= cut_start + cut_dur:
                        t_dur = cut_start - S
                        seg["target_timerange"]["duration"] = t_dur
                        if source:
                            seg["source_timerange"]["duration"] = int(round(t_dur * speed))
                        new_segs.append(seg)
                    elif S >= cut_start and E > cut_start + cut_dur:
                        t_dur = E - (cut_start + cut_dur)
                        seg["target_timerange"]["start"] = cut_start
                        seg["target_timerange"]["duration"] = t_dur
                        if source:
                            seg["source_timerange"]["start"] = S_src + int(round((cut_start + cut_dur - S) * speed))
                            seg["source_timerange"]["duration"] = int(round(t_dur * speed))
                        new_segs.append(seg)
            track["segments"] = new_segs

    # 5. New video duration
    new_video_dur = 0
    for track in data.get("tracks", []):
        if track.get("type") == "video":
            for seg in track.get("segments", []):
                end = seg.get("target_timerange", {}).get("start", 0) + seg.get("target_timerange", {}).get("duration", 0)
                if end > new_video_dur:
                    new_video_dur = end

    print(f"[{project_name}] Post-refine video duration: {new_video_dur / 1000000:.2f}s (Cuts applied: {len(adjusted_cuts)})")

    # 6. Stretch logo & filter, and lock them
    for track in data.get("tracks", []):
        t_id = track.get("id")
        if t_id in [logo_track_id, filter_track_id]:
            track["flag"] = 0
            track["attribute"] = (track.get("attribute", 0) & 3) | 4
            for seg in track.get("segments", []):
                seg["target_timerange"]["start"] = 0
                seg["target_timerange"]["duration"] = new_video_dur

    # 7. Re-align Outro video / text
    for track in data.get("tracks", []):
        for seg in track.get("segments", []):
            mat_id = seg.get("material_id")
            if mat_id == outro_material_id:
                dur = seg.get("target_timerange", {}).get("duration", 0)
                seg["target_timerange"]["start"] = max(0, new_video_dur - dur)

    # 8. Adjust BGM tracks
    first_music_dur = min(new_video_dur, 55366666)
    for track in data.get("tracks", []):
        if track.get("id") in music_track_ids:
            track["flag"] = 0
            track["attribute"] = (track.get("attribute", 0) & 3) | 4
            t_name = track.get("name", "").lower()
            if "loop" in t_name:
                overlap_time = 53366666
                if new_video_dur > overlap_time:
                    for seg in track.get("segments", []):
                        seg["target_timerange"]["start"] = overlap_time
                        seg["target_timerange"]["duration"] = new_video_dur - overlap_time
                        seg["source_timerange"]["start"] = 39066666
                        seg["source_timerange"]["duration"] = new_video_dur - overlap_time
                else:
                    track["segments"] = []
            else:
                for seg in track.get("segments", []):
                    seg["target_timerange"]["start"] = 0
                    seg["target_timerange"]["duration"] = first_music_dur
                    seg["source_timerange"]["start"] = 39066666
                    seg["source_timerange"]["duration"] = first_music_dur

    # 9. Cut silent intervals on original dialogue audio tracks
    speech_ranges = []
    for seg in caption_track.get("segments", []):
        S_c = seg.get("target_timerange", {}).get("start", 0)
        D_c = seg.get("target_timerange", {}).get("duration", 0)
        speech_ranges.append((S_c, S_c + D_c))

    for track in data.get("tracks", []):
        if track.get("type") == "audio" and track.get("id") not in music_track_ids:
            new_audio_segs = []
            for seg in track.get("segments", []):
                S_seg = seg.get("target_timerange", {}).get("start", 0)
                D_seg = seg.get("target_timerange", {}).get("duration", 0)
                E_seg = S_seg + D_seg
                orig_src_start = seg.get("source_timerange", {}).get("start", 0)
                speed = seg.get("speed", 1.0)
                parts = split_interval_by_speech(S_seg, E_seg, speech_ranges)
                for part_S, part_E, is_speech in parts:
                    if not is_speech:
                        continue
                    part_D = part_E - part_S
                    offset = part_S - S_seg
                    new_seg = json.loads(json.dumps(seg))
                    new_seg["id"] = str(uuid.uuid4()).upper()
                    new_seg["target_timerange"]["start"] = part_S
                    new_seg["target_timerange"]["duration"] = part_D
                    new_seg["source_timerange"]["start"] = orig_src_start + int(round(offset * speed))
                    new_seg["source_timerange"]["duration"] = int(round(part_D * speed))
                    new_audio_segs.append(new_seg)
            track["segments"] = new_audio_segs

    # 10. Sync-save and metadata update
    data["duration"] = new_video_dur
    for p in [timeline_draft_path, timeline_draft_path + ".bak", root_draft_path, root_draft_path + ".bak"]:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    if os.path.exists(draft_meta_path):
        with open(draft_meta_path, "r", encoding="utf-8") as f:
            meta_info = json.load(f)
        meta_info["tm_duration"] = new_video_dur
        meta_info["tm_draft_modified"] = int(time.time() * 1000000)
        with open(draft_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, ensure_ascii=False, indent=2)

    root_meta_path = os.path.join(CAPCUT_DRAFTS_ROOT, "root_meta_info.json")
    if os.path.exists(root_meta_path):
        with open(root_meta_path, "r", encoding="utf-8") as f:
            root_meta = json.load(f)
        for d in root_meta.get("all_draft_store", []):
            if d.get("draft_name") == project_name:
                d["tm_duration"] = new_video_dur
                d["tm_draft_modified"] = int(time.time() * 1000000)
                break
        with open(root_meta_path, "w", encoding="utf-8") as f:
            json.dump(root_meta, f, ensure_ascii=False)

    print(f"✅ Phase 2 Caption Refinement for '{project_name}' completed successfully!\n")
    return True


def transcribe_and_inject_captions(project_name: str, story_num: str, ep_name: str):
    """
    Transcribes all scene videos using Whisper (with Metal GPU acceleration),
    creates a native CapCut Auto Caption track in draft_info.json,
    and returns True on success.
    """
    if not os.path.exists(WHISPER_CLI_PATH) or not os.path.exists(WHISPER_MODEL_PATH):
        print(f"⚠️ Whisper CLI or Model not found at {WHISPER_CLI_PATH} / {WHISPER_MODEL_PATH}")
        return False
        
    project_dir = os.path.join(CAPCUT_DRAFTS_ROOT, project_name)
    if not os.path.isdir(project_dir):
        raise FileNotFoundError(f"Project '{project_name}' not found at: {project_dir}")
        
    timelines_pattern = os.path.join(project_dir, "Timelines", "*", "draft_info.json")
    timeline_matches = glob.glob(timelines_pattern)
    if not timeline_matches:
        raise FileNotFoundError(f"No timeline draft_info.json found in {project_dir}")
    timeline_path = timeline_matches[0]
    root_draft_path = os.path.join(project_dir, "draft_info.json")

    with open(timeline_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Prototype objects from existing template
    proto_mat = data.get("materials", {}).get("texts", [])[0] if data.get("materials", {}).get("texts") else {}
    proto_seg = None
    for tr in data.get("tracks", []):
        if tr.get("type") == "text" and tr.get("segments"):
            proto_seg = tr["segments"][0]
            break

    video_files = get_video_files(story_num, ep_name)
    print(f"[{project_name}] Running Whisper STT on {len(video_files)} scene videos...")
    
    caption_segments = []
    texts_materials = data.setdefault("materials", {}).setdefault("texts", [])
    tmp_wav = f"/tmp/whisper_temp_{project_name}.wav"
    tmp_out = f"/tmp/whisper_out_{project_name}"

    for i, mp4 in enumerate(video_files):
        # Extract 16kHz mono audio
        subprocess.run([FFMPEG_PATH, "-y", "-i", mp4, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp_wav],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        # Transcribe with whisper-cli
        subprocess.run([WHISPER_CLI_PATH, "-m", WHISPER_MODEL_PATH, "-f", tmp_wav, "-l", "th", "-oj", "-of", tmp_out, "-np"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        
        json_file = f"{tmp_out}.json"
        if os.path.exists(json_file):
            with open(json_file, "r", encoding="utf-8") as f_j:
                w_data = json.load(f_j)
            clip_speed = 1.4
            for sp in data.get("materials", {}).get("speeds", []):
                if sp.get("speed"):
                    clip_speed = float(sp["speed"])
                    break
            target_clip_dur_us = int(round(8000000 / clip_speed))

            for t in w_data.get("transcription", []):
                t_from = t.get("offsets", {}).get("from", 0)
                t_to = t.get("offsets", {}).get("to", 0)
                txt = t.get("text", "").strip()
                if not txt:
                    continue
                
                clip_start_us = i * target_clip_dur_us
                start_us = clip_start_us + int(round((t_from * 1000) / clip_speed))
                dur_us = int(round(((t_to - t_from) * 1000) / clip_speed))
                if dur_us <= 0:
                    continue
                    
                mat_id = str(uuid.uuid4()).upper()
                seg_id = str(uuid.uuid4()).upper()
                
                new_mat = dict(proto_mat)
                new_mat["id"] = mat_id
                new_mat["recognize_text"] = txt
                new_mat["font_size"] = 17.0
                new_mat["text_size"] = 17
                
                content_obj = {
                    "styles": [{
                        "fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]}}},
                        "font": {"id": "", "path": "/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf"},
                        "range": [0, len(txt)],
                        "size": 17,
                        "strokes": [{"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [0.0, 0.0, 0.0]}}, "width": 0.06}],
                        "useLetterColor": True
                    }],
                    "text": txt
                }
                new_mat["content"] = json.dumps(content_obj, ensure_ascii=False)
                new_mat["base_content"] = json.dumps(content_obj, ensure_ascii=False)
                new_mat["words"] = {"text": [txt]}
                texts_materials.append(new_mat)
                
                new_seg = dict(proto_seg) if proto_seg else {}
                new_seg["id"] = seg_id
                new_seg["material_id"] = mat_id
                new_seg["target_timerange"] = {"start": start_us, "duration": dur_us}
                new_seg["source_timerange"] = None
                new_seg["clip"] = {"transform": {"x": 0.0, "y": -0.56}, "scale": {"x": 1.0, "y": 1.0}}
                new_seg["uniform_scale"] = {"on": True, "value": 1.0}
                new_seg["extra_material_refs"] = []
                caption_segments.append(new_seg)

    # Clean up temp files
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)
    if os.path.exists(f"{tmp_out}.json"):
        os.remove(f"{tmp_out}.json")

    # Remove existing caption tracks if any
    data["tracks"] = [tr for tr in data.get("tracks", []) if tr.get("name") != "Auto Caption"]
    
    caption_track = {
        "id": str(uuid.uuid4()).upper(),
        "type": "text",
        "name": "Auto Caption",
        "flag": 0,
        "attribute": 0,
        "is_default_name": False,
        "segments": caption_segments
    }
    data["tracks"].append(caption_track)
    print(f"[{project_name}] Generated {len(caption_segments)} Whisper captions.")

    for p in [timeline_path, timeline_path + ".bak", root_draft_path, root_draft_path + ".bak"]:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    return True


def main():
    parser = argparse.ArgumentParser(description="CapCut Lakorn Project Builder & Refiner")
    parser.add_argument("--story", type=str, default="21", help="Story number (e.g. 21)")
    parser.add_argument("--ep", type=str, default=None, help="Episode name (e.g. EP01) or omit for all")
    parser.add_argument("--project", type=str, default=None, help="Target project name directly (e.g. 21-1)")
    parser.add_argument("--scenes", type=str, default=None, help="Scene range (e.g. 11-20)")
    parser.add_argument("--refine-captions", action="store_true", help="Run Phase 2 Caption-driven refinement instead of building")
    parser.add_argument("--whisper-captions", action="store_true", help="Auto-transcribe scenes with Whisper and refine timeline headlessly")
    args = parser.parse_args()

    if args.project:
        parts = args.project.split("-")
        story = args.story if args.story else parts[0]
        if args.ep:
            ep = args.ep
        else:
            ep = f"EP{int(parts[1]):02d}" if len(parts) > 1 and parts[1].isdigit() else "EP01"

        if args.whisper_captions:
            transcribe_and_inject_captions(args.project, story, ep)
            refine_project_captions(args.project)
        elif args.refine_captions:
            refine_project_captions(args.project)
        else:
            build_lakorn_project(story, ep, args.project, scene_range=args.scenes)
        return

    if args.ep:
        episodes = [args.ep]
    else:
        videos_base = os.path.join(BASE_CHANNEL_DIR, str(args.story), "7 - Videos")
        if os.path.isdir(videos_base):
            found_eps = sorted([d for d in os.listdir(videos_base) if d.upper().startswith("EP") and os.path.isdir(os.path.join(videos_base, d))])
            episodes = found_eps if found_eps else ["EP01", "EP02"]
        else:
            episodes = ["EP01", "EP02"]
    
    for ep in episodes:
        # Format target project name, e.g. '21-1' for Story 21 EP01
        ep_num = int(ep.upper().replace("EP", ""))
        proj_name = f"{args.story}-{ep_num}"
        try:
            if args.whisper_captions:
                transcribe_and_inject_captions(proj_name, args.story, ep)
                refine_project_captions(proj_name)
            elif args.refine_captions:
                refine_project_captions(proj_name)
            else:
                build_lakorn_project(args.story, ep, proj_name)
        except Exception as e:
            print(f"Error processing {proj_name}: {e}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
