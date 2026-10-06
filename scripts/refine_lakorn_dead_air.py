#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lakorn Dead Air Cutter & Music Sync
Channel: ผักกาดการละคร - ละครไทย
"""

import os
import sys
import glob
import json
import uuid
import time
import subprocess
from pythainlp import word_tokenize

DRAFT_ROOT = "/Users/litarcopperkaikem/Movies/CapCut/User Data/Projects/com.lveditor.draft"
PROJ_NAME = "31-1"
BASE_CHANNEL_DIR = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย"
EP_VIDEO_DIR = os.path.join(BASE_CHANNEL_DIR, "31", "7 - Videos", "EP01")


def format_thai_caption(text: str, max_words_per_line: int = 5) -> str:
    """Formats subtitle text into balanced lines using PyThaiNLP."""
    words = word_tokenize(text, engine="newmm")
    if len(words) <= max_words_per_line:
        return text
    
    lines = []
    curr_line = []
    for w in words:
        curr_line.append(w)
        if len(curr_line) >= max_words_per_line:
            lines.append("".join(curr_line))
            curr_line = []
    if curr_line:
        lines.append("".join(curr_line))
    return "\n".join(lines)


def run_dead_air_cutter(project_name: str = "31-1"):
    proj_dir = os.path.join(DRAFT_ROOT, project_name)
    if not os.path.isdir(proj_dir):
        raise FileNotFoundError(f"Project '{project_name}' not found at: {proj_dir}")

    timeline_matches = glob.glob(os.path.join(proj_dir, "Timelines", "*", "draft_info.json"))
    if not timeline_matches:
        raise FileNotFoundError("Timeline draft_info.json not found")
    timeline_path = timeline_matches[0]
    root_draft_path = os.path.join(proj_dir, "draft_info.json")
    draft_meta_path = os.path.join(proj_dir, "draft_meta_info.json")
    root_meta_path = os.path.join(DRAFT_ROOT, "root_meta_info.json")

    with open(timeline_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Identify Existing Materials and Tracks
    spy_audio_id = None
    mafia_audio_id = None
    for a in data.get("materials", {}).get("audios", []):
        p_lower = a.get("path", "").lower()
        if "สายลับ" in p_lower:
            spy_audio_id = a.get("id")
        elif "มาเฟีย" in p_lower:
            mafia_audio_id = a.get("id")

    if not spy_audio_id or not mafia_audio_id:
        print("⚠️ Warning: Could not find user spy/mafia audio materials!")

    # Find existing audio tracks
    spy_audio_track = None
    mafia_audio_track = None
    for tr in data.get("tracks", []):
        if tr.get("type") == "audio":
            for s in tr.get("segments", []):
                if s.get("material_id") == spy_audio_id:
                    spy_audio_track = tr
                elif s.get("material_id") == mafia_audio_id:
                    mafia_audio_track = tr

    # Identify Logo, Outro, Filter, Video tracks
    main_video_track = None
    filter_track = None
    logo_track = None
    outro_track = None
    logo_material_id = None
    outro_material_id = None
    fade_anim_id = None

    for m in data.get("materials", {}).get("material_animations", []):
        for an in m.get("animations", []):
            if an.get("name") == "Fade In" and an.get("type") == "in":
                fade_anim_id = m.get("id")
                break

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

    for tr in data.get("tracks", []):
        t_type = tr.get("type")
        if t_type == "video" and not main_video_track:
            main_video_track = tr
        elif t_type == "filter" and not filter_track:
            filter_track = tr
        elif t_type == "text":
            for s in tr.get("segments", []):
                if s.get("material_id") == logo_material_id:
                    logo_track = tr
                elif s.get("material_id") == outro_material_id:
                    outro_track = tr

    # 2. Get Video Files
    all_mp4s = sorted(glob.glob(os.path.join(EP_VIDEO_DIR, "*.mp4")))
    primary_files = [f for f in all_mp4s if not (f.endswith("_v2.mp4") or f.endswith("_v1.mp4"))]
    primary_files.sort(key=lambda p: int(os.path.basename(p).split(" - ")[0]))
    total_scenes = len(primary_files)
    print(f"Loaded {total_scenes} video files from {EP_VIDEO_DIR}")

    # Prototype objects
    proto_mat_text = data.get("materials", {}).get("texts", [])[0] if data.get("materials", {}).get("texts") else {}
    proto_seg_text = None
    for tr in data.get("tracks", []):
        if tr.get("type") == "text" and tr.get("segments"):
            proto_seg_text = tr["segments"][0]
            break

    clip_speed = 1.4
    buffer_s = 0.20  # 0.2s buffer after speech

    # 3. Process Scenes: Cut Dead Air > 0.5s & Calculate Timeline
    new_video_segments = []
    caption_segments = []
    texts_materials = data.setdefault("materials", {}).setdefault("texts", [])
    data["materials"]["transitions"] = []
    transitions = data["materials"]["transitions"]

    # Clear old materials
    data["materials"]["videos"] = []
    video_materials = data["materials"]["videos"]
    speeds = data.setdefault("materials", {}).setdefault("speeds", [])
    placeholders = data.setdefault("materials", {}).setdefault("placeholder_infos", [])
    canvases = data.setdefault("materials", {}).setdefault("canvases", [])
    sound_channel_mappings = data.setdefault("materials", {}).setdefault("sound_channel_mappings", [])
    material_colors = data.setdefault("materials", {}).setdefault("material_colors", [])
    vocal_separations = data.setdefault("materials", {}).setdefault("vocal_separations", [])

    scene_starts = {}
    curr_time_us = 0

    for idx, vpath in enumerate(primary_files):
        sc_num = int(os.path.basename(vpath).split(" - ")[0])
        scene_starts[sc_num] = curr_time_us

        # Get real duration via ffprobe
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", vpath]
        real_dur_s = float(subprocess.check_output(cmd).decode().strip())
        real_dur_us = int(round(real_dur_s * 1000000))

        # Check Whisper transcription
        jf = f"/tmp/sc_{sc_num:02d}.json"
        trans = []
        if os.path.exists(jf):
            with open(jf, "r", encoding="utf-8") as f_j:
                trans = json.load(f_j).get("transcription", [])
        trans = [t for t in trans if t.get("text", "").strip() not in ["[เสียงดนตรี]", ""]]

        # Determine source duration after cutting dead air > 0.5s
        if not trans:
            # Action scene: keep full motion, zero freeze
            src_dur_us = real_dur_us
            print(f"Scene {sc_num:02d}: Action Scene (Full {real_dur_s:.2f}s, no dead air)")
        else:
            last_speech_end_s = trans[-1]["offsets"]["to"] / 1000.0
            tail_gap_s = real_dur_s - last_speech_end_s
            if tail_gap_s > 0.5:
                # Cut dead air exceeding 0.5s (keep buffer)
                src_dur_s = min(real_dur_s, last_speech_end_s + buffer_s)
                src_dur_us = int(round(src_dur_s * 1000000))
                print(f"Scene {sc_num:02d}: Speech ends {last_speech_end_s:.2f}s | Cut {tail_gap_s - buffer_s:.2f}s dead air -> src {src_dur_s:.2f}s")
            else:
                src_dur_us = real_dur_us
                print(f"Scene {sc_num:02d}: Speech ends {last_speech_end_s:.2f}s | Tail gap {tail_gap_s:.2f}s <= 0.5s -> keep {real_dur_s:.2f}s")

        # Timeline target duration at 1.4x
        target_dur_us = int(round(src_dur_us / clip_speed))

        # Register video material
        v_mat_id = str(uuid.uuid4()).upper()
        v_file_name = os.path.basename(vpath)
        video_materials.append({
            "id": v_mat_id,
            "unique_id": str(uuid.uuid4()).upper(),
            "type": "video",
            "duration": real_dur_us,
            "path": vpath,
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
            "material_name": v_file_name,
            "material_url": "",
            "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
            "audio_fade": None
        })

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

        # Zero-Fade / Direct Hard Cut standard (No transition between clips)
        extra_refs = [speed_id, ph_id, canvas_id, scm_id, mc_id, vs_id]

        seg_id = str(uuid.uuid4()).upper()
        seg = {
            "id": seg_id,
            "material_id": v_mat_id,
            "target_timerange": {"start": curr_time_us, "duration": target_dur_us},
            "source_timerange": {"start": 0, "duration": src_dur_us},
            "speed": clip_speed,
            "volume": 1.0,
            "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}, "rotation": 0.0, "flip": {"horizontal": False, "vertical": False}, "alpha": 1.0},
            "visible": True,
            "state": 0,
            "render_index": 10000 + idx,
            "track_render_index": 0,
            "extra_material_refs": extra_refs
        }
        new_video_segments.append(seg)

        # Build captions for dialogue
        for t in trans:
            txt = t.get("text", "").strip()
            if not txt:
                continue
            f_ms = t["offsets"]["from"]
            t_ms = t["offsets"]["to"]
            c_start_us = curr_time_us + int(round((f_ms * 1000) / clip_speed))
            c_dur_us = int(round(((t_ms - f_ms) * 1000) / clip_speed))
            if c_dur_us <= 0:
                continue

            formatted_txt = format_thai_caption(txt)
            c_mat_id = str(uuid.uuid4()).upper()
            c_seg_id = str(uuid.uuid4()).upper()

            c_content_obj = {
                "styles": [{
                    "fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]}}},
                    "font": {"id": "", "path": "/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf"},
                    "range": [0, len(formatted_txt)],
                    "size": 17,
                    "strokes": [{"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [0.0, 0.0, 0.0]}}, "width": 0.06}],
                    "useLetterColor": True
                }],
                "text": formatted_txt
            }

            new_c_mat = dict(proto_mat_text) if proto_mat_text else {}
            new_c_mat["id"] = c_mat_id
            new_c_mat["recognize_text"] = formatted_txt
            new_c_mat["font_size"] = 17.0
            new_c_mat["text_size"] = 17
            new_c_mat["content"] = json.dumps(c_content_obj, ensure_ascii=False)
            new_c_mat["base_content"] = json.dumps(c_content_obj, ensure_ascii=False)
            new_c_mat["words"] = {"text": [formatted_txt]}
            texts_materials.append(new_c_mat)

            new_c_seg = dict(proto_seg_text) if proto_seg_text else {}
            new_c_seg["id"] = c_seg_id
            new_c_seg["material_id"] = c_mat_id
            new_c_seg["target_timerange"] = {"start": c_start_us, "duration": c_dur_us}
            new_c_seg["source_timerange"] = None
            new_c_seg["clip"] = {"transform": {"x": 0.0, "y": -0.56}, "scale": {"x": 1.0, "y": 1.0}}
            new_c_seg["uniform_scale"] = {"on": True, "value": 1.0}
            new_c_seg["extra_material_refs"] = []
            caption_segments.append(new_c_seg)

        curr_time_us += target_dur_us

    total_video_dur = curr_time_us
    print(f"\n=======================================================")
    print(f"Total Video Duration (post dead-air cut): {total_video_dur / 1000000:.2f}s ({total_video_dur} us)")
    print(f"Total Captions Generated: {len(caption_segments)}")

    # Update Main Video Track
    main_video_track["segments"] = new_video_segments

    # 4. Align Background Music Tracks (Preserve User Music!)
    scene_18_start = scene_starts.get(18, 0)
    print(f"Scene 18 start time: {scene_18_start / 1000000:.2f}s ({scene_18_start} us)")

    # Prepare Audio Fade materials
    bgm_volume = 0.3162277638912201  # -10 dB as set by user
    crossfade_us = 2000000  # 2.0s crossfade

    fade_spy_id = str(uuid.uuid4()).upper()
    fade_mafia_id = str(uuid.uuid4()).upper()
    data.setdefault("materials", {}).setdefault("audio_fades", []).extend([
        {
            "id": fade_spy_id,
            "type": "audio_fade",
            "fade_type": 0,
            "fade_in_duration": 0,
            "fade_out_duration": crossfade_us
        },
        {
            "id": fade_mafia_id,
            "type": "audio_fade",
            "fade_type": 0,
            "fade_in_duration": crossfade_us,
            "fade_out_duration": crossfade_us
        }
    ])

    spy_dur_us = scene_18_start + crossfade_us
    mafia_dur_us = total_video_dur - scene_18_start

    # Configure Track 1: สายลับเท่ๆ.m4a
    spy_seg_id = str(uuid.uuid4()).upper()
    spy_seg = {
        "id": spy_seg_id,
        "material_id": spy_audio_id,
        "target_timerange": {"start": 0, "duration": spy_dur_us},
        "source_timerange": {"start": 0, "duration": spy_dur_us},
        "volume": bgm_volume,
        "last_nonzero_volume": bgm_volume,
        "speed": 1.0,
        "state": 0,
        "visible": True,
        "render_index": 0,
        "track_render_index": 0,
        "extra_material_refs": [fade_spy_id]
    }
    if not spy_audio_track:
        spy_audio_track = {"id": str(uuid.uuid4()).upper(), "type": "audio", "name": "BG Music 1", "flag": 0, "attribute": 4, "segments": []}
    spy_audio_track["flag"] = 0
    spy_audio_track["attribute"] = (spy_audio_track.get("attribute", 0) & 3) | 4
    spy_audio_track["name"] = "BG Music 1 (สายลับ)"
    spy_audio_track["segments"] = [spy_seg]
    print(f"Configured Track 'BG Music 1 (สายลับ)': 0s -> {spy_dur_us / 1000000:.2f}s (Fade Out 2s)")

    # Configure Track 2: แนะนำตัวมาเฟีย 1.mp3
    mafia_seg_id = str(uuid.uuid4()).upper()
    mafia_seg = {
        "id": mafia_seg_id,
        "material_id": mafia_audio_id,
        "target_timerange": {"start": scene_18_start, "duration": mafia_dur_us},
        "source_timerange": {"start": 0, "duration": mafia_dur_us},
        "volume": bgm_volume,
        "last_nonzero_volume": bgm_volume,
        "speed": 1.0,
        "state": 0,
        "visible": True,
        "render_index": 0,
        "track_render_index": 0,
        "extra_material_refs": [fade_mafia_id]
    }
    if not mafia_audio_track:
        mafia_audio_track = {"id": str(uuid.uuid4()).upper(), "type": "audio", "name": "BG Music 2", "flag": 0, "attribute": 4, "segments": []}
    mafia_audio_track["flag"] = 0
    mafia_audio_track["attribute"] = (mafia_audio_track.get("attribute", 0) & 3) | 4
    mafia_audio_track["name"] = "BG Music 2 (มาเฟีย)"
    mafia_audio_track["segments"] = [mafia_seg]
    print(f"Configured Track 'BG Music 2 (มาเฟีย)': {scene_18_start / 1000000:.2f}s -> {total_video_dur / 1000000:.2f}s (Fade In 2s, Fade Out 2s)")

    # 5. Stretch Logo & Filter, Re-align Outro Text
    if logo_track:
        logo_track["flag"] = 0
        logo_track["attribute"] = (logo_track.get("attribute", 0) & 3) | 4
        for seg in logo_track.get("segments", []):
            seg["target_timerange"]["start"] = 0
            seg["target_timerange"]["duration"] = total_video_dur
        print(f"Stretched & Locked Logo Track to {total_video_dur / 1000000:.2f}s")

    if filter_track:
        filter_track["flag"] = 0
        filter_track["attribute"] = (filter_track.get("attribute", 0) & 3) | 4
        for seg in filter_track.get("segments", []):
            seg["target_timerange"]["start"] = 0
            seg["target_timerange"]["duration"] = total_video_dur
        print(f"Stretched & Locked Filter Track to {total_video_dur / 1000000:.2f}s")

    if outro_track:
        outro_dur = 2616667
        for seg in outro_track.get("segments", []):
            seg["target_timerange"]["start"] = max(0, total_video_dur - outro_dur)
            seg["target_timerange"]["duration"] = outro_dur
            if fade_anim_id and fade_anim_id not in seg.get("extra_material_refs", []):
                seg.setdefault("extra_material_refs", []).append(fade_anim_id)
        print(f"Positioned Outro Text at tail: {max(0, total_video_dur - outro_dur) / 1000000:.2f}s")

    # 6. Rebuild Tracks List
    caption_track = {
        "id": str(uuid.uuid4()).upper(),
        "type": "text",
        "name": "Auto Caption",
        "flag": 0,
        "attribute": 0,
        "is_default_name": False,
        "segments": caption_segments
    }

    final_tracks = [main_video_track]
    if outro_track:
        final_tracks.append(outro_track)
    if logo_track:
        final_tracks.append(logo_track)
    if caption_segments:
        final_tracks.append(caption_track)
    if filter_track:
        final_tracks.append(filter_track)
    final_tracks.append(spy_audio_track)
    final_tracks.append(mafia_audio_track)

    data["tracks"] = final_tracks
    data["duration"] = total_video_dur

    # 7. Dual-Sync Saving across all 4 CapCut paths
    paths_to_write = [
        timeline_path,
        timeline_path + ".bak",
        root_draft_path,
        root_draft_path + ".bak"
    ]
    for p in paths_to_write:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    if os.path.exists(draft_meta_path):
        with open(draft_meta_path, "r", encoding="utf-8") as f:
            meta_info = json.load(f)
        meta_info["tm_duration"] = total_video_dur
        meta_info["tm_draft_modified"] = int(time.time() * 1000000)
        with open(draft_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, ensure_ascii=False, indent=2)

    if os.path.exists(root_meta_path):
        with open(root_meta_path, "r", encoding="utf-8") as f:
            root_meta = json.load(f)
        for d in root_meta.get("all_draft_store", []):
            if d.get("draft_name") == project_name:
                d["tm_duration"] = total_video_dur
                d["tm_draft_modified"] = int(time.time() * 1000000)
        with open(root_meta_path, "w", encoding="utf-8") as f:
            json.dump(root_meta, f, ensure_ascii=False)

    print(f"\n✅ Project '{project_name}' successfully refined and saved!")
    print(f"   - New Duration: {total_video_dur / 1000000:.2f}s (was 228.57s)")
    print(f"   - Dead air cut: ~{228.57 - (total_video_dur / 1000000):.2f}s eliminated")
    print(f"   - Preserved Music: 'สายลับเท่ๆ.m4a' (0s-{scene_18_start/1000000:.1f}s) & 'แนะนำตัวมาเฟีย 1.mp3' ({scene_18_start/1000000:.1f}s-{total_video_dur/1000000:.1f}s)")
    print(f"   - Captions: {len(caption_segments)} segments in Auto Caption track\n")


if __name__ == "__main__":
    run_dead_air_cutter("31-1")
