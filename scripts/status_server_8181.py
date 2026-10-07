"""Status Server on Port 8181 — Google Flow-Style Visual Tile Monitor for ผักกาดการละคร."""
import os
import sys
import re
import glob
import json
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] status_server: %(message)s")
logger = logging.getLogger("status_server_8181")

PORT = 8181
HOST = "0.0.0.0"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from app.env_config import get_channel_dir, get_repo_dir
    CHANNEL_ROOT = get_channel_dir()
    REPO_ROOT = str(get_repo_dir())
except Exception:
    CHANNEL_ROOT = os.environ.get("LAKORN_CHANNEL_DIR", os.path.expanduser("~/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย"))
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUDIT_LOG_PATH = os.path.join(REPO_ROOT, "flow_action_audit.log")
STATE_FILE = os.path.join(os.path.dirname(__file__), "generation_status.json")

app = FastAPI(title="Lakorn Flow-Style Status Monitor", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_state() -> Dict[str, Any]:
    """Load persistent state from JSON file or return default."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error reading state file: %s", e)
    return {
        "story": 31,
        "ep": "EP01",
        "mode": "video",
        "current_scene": None,
        "current_action": "พร้อมทำงาน",
        "current_status": "IDLE",  # IDLE, RUNNING, FIXING, COMPLETED, ERROR
        "fixing_scene": None,
        "fixing_scenes": {},
        "failed_scenes": [],
        "generating_scenes": [],
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_log": "ระบบพร้อมทำงานบน Port 8181",
    }


def save_state(state: Dict[str, Any]):
    """Save persistent state to JSON file."""
    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Error saving state file: %s", e)


def list_available_stories() -> List[Dict[str, Any]]:
    """Scan channel directory for all stories and their episodes."""
    if not os.path.isdir(CHANNEL_ROOT):
        return []
    result = []
    for item in sorted(os.listdir(CHANNEL_ROOT)):
        full_p = os.path.join(CHANNEL_ROOT, item)
        if os.path.isdir(full_p) and item.isdigit():
            story_num = int(item)
            eps = set()
            for sub in ["4 - Image Prompt", "6 - Storyboards", "7 - Videos"]:
                sub_p = os.path.join(full_p, sub)
                if os.path.isdir(sub_p):
                    for d in os.listdir(sub_p):
                        if d.upper().startswith("EP") and os.path.isdir(os.path.join(sub_p, d)):
                            eps.add(d.upper())
            sorted_eps = sorted(list(eps)) if eps else ["EP01"]
            result.append({"story": story_num, "episodes": sorted_eps})
    return sorted(result, key=lambda x: x["story"], reverse=True)


def get_story_scenes_info(story_num: int, ep_str: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Scan story directory to get detailed per-scene status for both storyboards and videos."""
    if state is None:
        state = load_state()

    story_dir = os.path.join(CHANNEL_ROOT, str(story_num))
    if not os.path.isdir(story_dir):
        return {"total_expected": 0, "scenes": []}

    prompt_dir = os.path.join(story_dir, "4 - Image Prompt", ep_str)
    storyboard_dir = os.path.join(story_dir, "6 - Storyboards", ep_str)
    video_dir = os.path.join(story_dir, "7 - Videos", ep_str)
    ces_dir = os.path.join(story_dir, "4 - Character Each Scene", ep_str)
    anim_dir = os.path.join(story_dir, "4 - Animation Prompt", ep_str)

    prompt_files = []
    if os.path.isdir(prompt_dir):
        prompt_files = sorted([f for f in os.listdir(prompt_dir) if f.endswith(".md") and not f.startswith(".")])

    # If no prompt files found, discover scenes from storyboards or videos
    scene_nums = set()
    for pf in prompt_files:
        parts = pf.split(" - ")
        if parts and parts[0].isdigit():
            scene_nums.add(int(parts[0]))

    if not scene_nums:
        # Check storyboards
        if os.path.isdir(storyboard_dir):
            for f in os.listdir(storyboard_dir):
                m = re.search(r"Scene\s*(\d+)", f, re.IGNORECASE)
                if m:
                    scene_nums.add(int(m.group(1)))
        # Check videos
        if os.path.isdir(video_dir):
            for f in os.listdir(video_dir):
                parts = f.split(" - ")
                if parts and parts[0].isdigit():
                    scene_nums.add(int(parts[0]))

    sorted_scene_nums = sorted(list(scene_nums)) if scene_nums else list(range(1, 21))

    current_sc = state.get("current_scene")
    is_active_story_ep = (
        int(state.get("story", 0)) == story_num and
        str(state.get("ep", "")).strip().upper() == ep_str.strip().upper()
    )

    failed_scenes = set()
    generating_scenes = set()

    if is_active_story_ep:
        raw_failed = state.get("failed_scenes", [])
        if isinstance(raw_failed, list):
            for item in raw_failed:
                if isinstance(item, dict):
                    sc_val = item.get("scene_num") or item.get("scene")
                    if sc_val is not None:
                        try:
                            failed_scenes.add(int(sc_val))
                        except (ValueError, TypeError):
                            pass
                elif isinstance(item, (int, str)) and str(item).isdigit():
                    failed_scenes.add(int(item))

        raw_generating = state.get("generating_scenes", [])
        if isinstance(raw_generating, list):
            for item in raw_generating:
                if isinstance(item, dict):
                    sc_val = item.get("scene_num") or item.get("scene")
                    if sc_val is not None:
                        try:
                            generating_scenes.add(int(sc_val))
                        except (ValueError, TypeError):
                            pass
                elif isinstance(item, (int, str)) and str(item).isdigit():
                    generating_scenes.add(int(item))

        if current_sc is not None:
            try:
                generating_scenes.add(int(current_sc))
            except (ValueError, TypeError):
                pass

    # Resolve fixing scenes for this specific story and episode
    story_ep_key = f"{story_num}_{ep_str}"
    raw_fixing = state.get("fixing_scenes", {})
    fixing_scenes_list = []
    if isinstance(raw_fixing, dict):
        fixing_scenes_list = raw_fixing.get(story_ep_key, [])
    elif isinstance(raw_fixing, list):
        fixing_scenes_list = raw_fixing

    fixing_scenes_set = set(int(x) for x in fixing_scenes_list if str(x).isdigit())
    if state.get("fixing_scene") is not None and int(state.get("story", 0)) == story_num and state.get("ep") == ep_str:
        try:
            fixing_scenes_set.add(int(state.get("fixing_scene")))
        except (ValueError, TypeError):
            pass

    scenes = []
    for sc_num in sorted_scene_nums:
        sc_str = f"{sc_num:02d}"
        
        # 1. Prompt and Dialog
        pf_name = f"{sc_str} - Scene {sc_str}.md"
        prompt_text = ""
        prompt_path = os.path.join(prompt_dir, pf_name)
        if os.path.isfile(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    prompt_text = f.read().strip()
            except Exception:
                pass

        dialogue_text = ""
        anim_path = os.path.join(anim_dir, pf_name)
        if os.path.isfile(anim_path):
            try:
                with open(anim_path, "r", encoding="utf-8") as f:
                    anim_content = f.read()
                    m = re.search(r"\(([^)]+)\)", anim_content)
                    if m:
                        dialogue_text = m.group(1).strip()
                    else:
                        dialogue_text = anim_content.strip()
            except Exception:
                pass

        # 2. Characters
        characters = []
        ces_file = os.path.join(ces_dir, pf_name)
        if os.path.isfile(ces_file):
            try:
                with open(ces_file, "r", encoding="utf-8") as f:
                    characters = [line.strip().replace(".png", "") for line in f.readlines() if line.strip()]
            except Exception:
                pass

        # 3. Storyboard Image
        img_candidates = [
            f"{ep_str} - Scene {sc_str}.jpg",
            f"{sc_str} - Scene {sc_str}.jpg",
            f"Scene {sc_str}.jpg",
            f"{ep_str} - Scene {sc_str}.png",
        ]
        has_image = False
        img_filename = None
        img_size_kb = 0
        img_mtime = ""
        if os.path.isdir(storyboard_dir):
            for cand in img_candidates:
                ipath = os.path.join(storyboard_dir, cand)
                if os.path.isfile(ipath):
                    has_image = True
                    img_filename = cand
                    st = os.stat(ipath)
                    img_size_kb = round(st.st_size / 1024, 1)
                    img_mtime = datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S")
                    break

        is_fixing = (sc_num in fixing_scenes_set)

        # Compute image_status
        if is_fixing:
            image_status = "FIXING"
        elif sc_num in failed_scenes:
            image_status = "FAILED"
        elif sc_num in generating_scenes and not has_image:
            image_status = "GENERATING"
        elif has_image and img_size_kb > 40:
            image_status = "DONE"
        elif sc_num in generating_scenes:
            image_status = "GENERATING"
        else:
            image_status = "PENDING"

        # 4. Video File
        vid_candidates = [
            f"{sc_str} - Scene {sc_str}.mp4",
            f"{ep_str} - Scene {sc_str}.mp4",
            f"Scene {sc_str}.mp4",
        ]
        has_video = False
        vid_filename = None
        vid_size_mb = 0
        vid_mtime = ""
        if os.path.isdir(video_dir):
            for cand in vid_candidates:
                vpath = os.path.join(video_dir, cand)
                if os.path.isfile(vpath):
                    has_video = True
                    vid_filename = cand
                    st = os.stat(vpath)
                    vid_size_mb = round(st.st_size / (1024 * 1024), 2)
                    vid_mtime = datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S")
                    break

        # Compute video_status
        if is_fixing:
            video_status = "FIXING"
        elif state.get("mode") in ["video", "videos"]:
            if sc_num in failed_scenes:
                video_status = "FAILED"
            elif sc_num in generating_scenes and not has_video:
                video_status = "GENERATING"
            elif has_video and vid_size_mb > 0.4:
                video_status = "DONE"
            elif sc_num in generating_scenes:
                video_status = "GENERATING"
            else:
                video_status = "PENDING"
        else:
            if has_video and vid_size_mb > 0.4:
                video_status = "DONE"
            else:
                video_status = "PENDING"

        scenes.append({
            "scene_num": sc_num,
            "scene_str": sc_str,
            "is_fixing": is_fixing,
            "prompt_preview": prompt_text[:140] + ("..." if len(prompt_text) > 140 else ""),
            "full_prompt": prompt_text,
            "dialogue": dialogue_text,
            "characters": characters,
            # Image details
            "has_image": has_image,
            "image_filename": img_filename,
            "image_size_kb": img_size_kb,
            "image_mtime": img_mtime,
            "image_status": image_status,
            "image_url": f"/api/storyboard-image/{story_num}/{ep_str}/{img_filename}" if has_image else None,
            # Video details
            "has_video": has_video,
            "video_filename": vid_filename,
            "video_size_mb": vid_size_mb,
            "video_mtime": vid_mtime,
            "video_status": video_status,
            "video_url": f"/api/video/{story_num}/{ep_str}/{vid_filename}" if has_video else None,
        })

    images_done = sum(1 for s in scenes if s["image_status"] == "DONE")
    videos_done = sum(1 for s in scenes if s["video_status"] == "DONE")
    total = len(scenes)

    return {
        "total_expected": total,
        "images_done": images_done,
        "videos_done": videos_done,
        "fixing_scenes": sorted(list(fixing_scenes_set)),
        "scenes": scenes,
    }


def get_recent_audit_logs(limit: int = 15) -> List[str]:
    """Read last N entries from flow_action_audit.log."""
    if not os.path.isfile(AUDIT_LOG_PATH):
        return []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            return lines[-limit:]
    except Exception:
        return []


@app.get("/health")
def health():
    return {"status": "ok", "port": PORT, "time": datetime.now().isoformat()}


@app.get("/api/stories")
def get_stories_api():
    """List all available stories and episodes."""
    return {"stories": list_available_stories()}


@app.get("/api/status")
def get_status_api(story: Optional[int] = None, ep: Optional[str] = None):
    """Detailed live status API."""
    state = load_state()
    active_story = story if story is not None else int(state.get("story", 31))
    active_ep = ep if ep is not None else state.get("ep", "EP01")

    story_info = get_story_scenes_info(active_story, active_ep, state)
    total_expected = story_info["total_expected"]

    recent_logs = get_recent_audit_logs(15)

    return {
        "story": active_story,
        "ep": active_ep,
        "mode": state.get("mode", "video"),
        "summary": {
            "total_expected": total_expected,
            "images_done": story_info["images_done"],
            "videos_done": story_info["videos_done"],
            "image_percent": round((story_info["images_done"] / total_expected * 100), 1) if total_expected > 0 else 0,
            "video_percent": round((story_info["videos_done"] / total_expected * 100), 1) if total_expected > 0 else 0,
            "current_status": state.get("current_status", "IDLE"),
            "current_action": state.get("current_action", "พร้อมทำงาน"),
            "current_scene": state.get("current_scene"),
            "fixing_scene": state.get("fixing_scene"),
            "fixing_scenes": story_info.get("fixing_scenes", []),
            "failed_scenes": state.get("failed_scenes", []),
            "last_updated": state.get("last_updated"),
        },
        "fixing_scenes": story_info.get("fixing_scenes", []),
        "scenes": story_info["scenes"],
        "recent_logs": recent_logs,
        "available_stories": list_available_stories(),
    }


@app.post("/api/status/update")
async def update_status_api(request: Request):
    """Update generator status dynamically from scripts or agents."""
    data = await request.json()
    state = load_state()

    for k in ["story", "ep", "mode", "current_scene", "current_action", "current_status", "fixing_scene", "fixing_scenes", "failed_scenes", "generating_scenes", "active_log"]:
        if k in data:
            state[k] = data[k]

    save_state(state)
    return {"success": True, "state": state}


@app.post("/api/fixing/add")
async def add_fixing_scenes_api(request: Request):
    """Add scenes to 'กำลังแก้ไข' (FIXING) list for a story and episode."""
    data = await request.json()
    story = data.get("story")
    ep = data.get("ep", "EP01")
    scenes = data.get("scenes", [])
    if not story or not scenes:
        return JSONResponse(status_code=400, content={"error": "story and scenes required"})
    
    state = load_state()
    if "fixing_scenes" not in state or not isinstance(state["fixing_scenes"], dict):
        state["fixing_scenes"] = {}
    
    key = f"{story}_{ep}"
    current_set = set(int(x) for x in state["fixing_scenes"].get(key, []) if str(x).isdigit())
    for s in scenes:
        try:
            current_set.add(int(s))
        except (ValueError, TypeError):
            pass
    state["fixing_scenes"][key] = sorted(list(current_set))
    save_state(state)
    return {"success": True, "fixing_scenes": state["fixing_scenes"][key]}


@app.post("/api/fixing/remove")
async def remove_fixing_scene_api(request: Request):
    """Remove a scene from 'กำลังแก้ไข' (mark as passed)."""
    data = await request.json()
    story = data.get("story")
    ep = data.get("ep", "EP01")
    scene = data.get("scene")
    if not story or scene is None:
        return JSONResponse(status_code=400, content={"error": "story and scene required"})
    
    state = load_state()
    if "fixing_scenes" not in state or not isinstance(state["fixing_scenes"], dict):
        state["fixing_scenes"] = {}
    
    key = f"{story}_{ep}"
    current_set = set(int(x) for x in state["fixing_scenes"].get(key, []) if str(x).isdigit())
    try:
        current_set.discard(int(scene))
    except (ValueError, TypeError):
        pass
    state["fixing_scenes"][key] = sorted(list(current_set))
    if state.get("fixing_scene") == int(scene):
        state["fixing_scene"] = None
    save_state(state)
    return {"success": True, "fixing_scenes": state["fixing_scenes"][key]}


@app.post("/api/fixing/clear")
async def clear_fixing_scenes_api(request: Request):
    """Clear all fixing scenes for a story and episode (Pass All)."""
    data = await request.json()
    story = data.get("story")
    ep = data.get("ep", "EP01")
    if not story:
        return JSONResponse(status_code=400, content={"error": "story required"})
    
    state = load_state()
    if "fixing_scenes" not in state or not isinstance(state["fixing_scenes"], dict):
        state["fixing_scenes"] = {}
    
    key = f"{story}_{ep}"
    state["fixing_scenes"][key] = []
    if int(state.get("story", 0)) == int(story) and state.get("ep") == ep:
        state["fixing_scene"] = None
    save_state(state)
    return {"success": True, "fixing_scenes": []}


@app.get("/api/storyboard-image/{story}/{ep}/{filename}")
def get_storyboard_image(story: int, ep: str, filename: str):
    """Serve storyboard image for live preview."""
    safe_file = os.path.basename(filename)
    path = os.path.join(CHANNEL_ROOT, str(story), "6 - Storyboards", ep, safe_file)
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": "Image not found"})


@app.get("/api/video/{story}/{ep}/{filename}")
def get_video_file(story: int, ep: str, filename: str):
    """Serve video MP4 file for live preview/playback."""
    safe_file = os.path.basename(filename)
    path = os.path.join(CHANNEL_ROOT, str(story), "7 - Videos", ep, safe_file)
    if os.path.isfile(path):
        return FileResponse(path, media_type="video/mp4")
    return JSONResponse(status_code=404, content={"error": "Video not found"})


@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    """Render high-fidelity real-time Google Flow-style tile dashboard."""
    html_content = """<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Google Flow Status Cockpit • ผักกาดการละคร (Port 8181)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Noto+Sans+Thai:wght@300;400;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Noto Sans Thai', 'Plus Jakarta Sans', sans-serif;
      background-color: #080b12;
      color: #f1f5f9;
    }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    .card-glass {
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .flow-tile {
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .flow-tile:hover {
      transform: translateY(-4px) scale(1.02);
      border-color: rgba(99, 102, 241, 0.6);
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.6), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
    }
    
    /* Central Status Badges as requested */
    .badge-center-done {
      background: rgba(16, 185, 129, 0.92);
      color: #ffffff;
      border: 1.5px solid #6ee7b7;
      box-shadow: 0 0 22px rgba(16, 185, 129, 0.6);
    }
    .badge-center-generating {
      background: rgba(37, 99, 235, 0.95);
      color: #ffffff;
      border: 1.5px solid #93c5fd;
      box-shadow: 0 0 22px rgba(59, 130, 246, 0.7);
      animation: pulse-badge 1.8s infinite;
    }
    .badge-center-failed {
      background: rgba(225, 29, 72, 0.95);
      color: #ffffff;
      border: 1.5px solid #fda4af;
      box-shadow: 0 0 22px rgba(244, 63, 94, 0.7);
    }
    .badge-center-fixing {
      background: rgba(245, 158, 11, 0.95);
      color: #0f172a;
      border: 1.5px solid #fde68a;
      box-shadow: 0 0 22px rgba(245, 158, 11, 0.7);
      animation: bounce-badge 1.5s infinite;
    }
    .badge-center-pending {
      background: rgba(30, 41, 59, 0.85);
      color: #94a3b8;
      border: 1px dashed rgba(148, 163, 184, 0.4);
    }

    /* Unified Filter Pill Buttons (Static & Consistent Resting State) */
    .filter-btn {
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      cursor: pointer;
    }
    .filter-btn-all {
      background: rgba(30, 41, 59, 0.7);
      color: #e2e8f0;
      border: 1px solid rgba(148, 163, 184, 0.3);
    }
    .filter-btn-done {
      background: rgba(6, 78, 59, 0.4);
      color: #6ee7b7;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .filter-btn-active {
      background: rgba(30, 58, 138, 0.4);
      color: #93c5fd;
      border: 1px solid rgba(59, 130, 246, 0.4);
    }
    .filter-btn-failed {
      background: rgba(136, 19, 55, 0.4);
      color: #fda4af;
      border: 1px solid rgba(244, 63, 94, 0.4);
    }
    .filter-btn-fixing {
      background: rgba(120, 53, 15, 0.4);
      color: #fde68a;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .filter-btn-pending {
      background: rgba(30, 41, 59, 0.4);
      color: #94a3b8;
      border: 1px dashed rgba(148, 163, 184, 0.4);
    }

    /* Active Highlight State when user selects a filter */
    .filter-btn.is-active {
      transform: scale(1.05);
      font-weight: 800;
      box-shadow: 0 0 16px rgba(255, 255, 255, 0.2);
    }
    .filter-btn-all.is-active {
      background: #334155;
      color: #ffffff;
      border-color: #f8fafc;
      box-shadow: 0 0 14px rgba(255, 255, 255, 0.3);
    }
    .filter-btn-done.is-active {
      background: #10b981;
      color: #ffffff;
      border-color: #a7f3d0;
      box-shadow: 0 0 16px rgba(16, 185, 129, 0.6);
    }
    .filter-btn-active.is-active {
      background: #2563eb;
      color: #ffffff;
      border-color: #bfdbfe;
      box-shadow: 0 0 16px rgba(37, 99, 235, 0.6);
    }
    .filter-btn-failed.is-active {
      background: #e11d48;
      color: #ffffff;
      border-color: #fecdd3;
      box-shadow: 0 0 16px rgba(225, 29, 72, 0.6);
    }
    .filter-btn-fixing.is-active {
      background: #d97706;
      color: #ffffff;
      border-color: #fde68a;
      box-shadow: 0 0 16px rgba(217, 119, 6, 0.6);
    }
    .filter-btn-pending.is-active {
      background: #475569;
      color: #ffffff;
      border-color: #cbd5e1;
      box-shadow: 0 0 14px rgba(148, 163, 184, 0.4);
    }

    @keyframes pulse-badge {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.82; transform: scale(1.05); }
    }
    @keyframes bounce-badge {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-4px); }
    }
    .shimmer-bg {
      background: linear-gradient(90deg, #0f172a 25%, #1e293b 50%, #0f172a 75%);
      background-size: 200% 100%;
      animation: shimmer 2s infinite;
    }
    @keyframes shimmer {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
  </style>
</head>
<body class="min-h-screen p-3 md:p-6 lg:p-8">
  <div class="max-w-[1600px] mx-auto space-y-6">

    <!-- Top Navigation Bar -->
    <header class="card-glass rounded-2xl p-4 md:p-5 shadow-2xl flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
      <div class="flex items-center gap-4">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-indigo-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
          <span class="text-xl">🎬</span>
        </div>
        <div>
          <div class="flex items-center gap-2.5">
            <h1 class="text-lg md:text-xl font-extrabold tracking-tight text-white">
              Google Flow Production Cockpit
            </h1>
            <span class="text-[11px] uppercase tracking-wider bg-emerald-500/20 text-emerald-300 font-bold px-2.5 py-0.5 rounded-full border border-emerald-500/40 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              PORT 8181
            </span>
          </div>
          <p class="text-xs text-slate-400">
            ผักกาดการละคร • ระบบตรวจจับ Tile Real-time • สถานะพาดกลางภาพ (เขียว/ฟ้า/แดง/เหลือง)
          </p>
        </div>
      </div>

      <!-- Controls: Story Selector & Refresh -->
      <div class="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-between lg:justify-end">
        <!-- Story / EP Selectors -->
        <div class="flex items-center gap-2 bg-slate-900/90 p-1.5 rounded-xl border border-slate-800 text-xs">
          <label class="text-slate-400 font-semibold px-2">เรื่อง:</label>
          <select id="storySelect" onchange="onStoryChange()" class="bg-slate-800 text-white rounded-lg px-2.5 py-1 font-bold border border-slate-700 outline-none">
            <option value="31">Story 31</option>
          </select>
          <label class="text-slate-400 font-semibold px-2">ตอน:</label>
          <select id="epSelect" onchange="onEpChange()" class="bg-slate-800 text-white rounded-lg px-2.5 py-1 font-bold border border-slate-700 outline-none">
            <option value="EP01">EP01</option>
          </select>
        </div>

        <!-- Refresh Button -->
        <button onclick="fetchStatus()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          รีเฟรช
        </button>
      </div>
    </header>

    <!-- KPI Summary Row (Clickable to switch between Storyboard and Video) -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
      <!-- KPI 1: Storyboard Clickable Box -->
      <div id="kpiBoxStoryboard" onclick="switchViewMode('STORYBOARD')" 
           class="card-glass rounded-2xl p-4 shadow-lg border-l-4 border-emerald-500 cursor-pointer hover:border-emerald-400 transition-all group select-none opacity-60">
        <div class="flex justify-between items-center text-slate-400 text-xs font-bold uppercase group-hover:text-emerald-300 transition">
          <span class="flex items-center gap-1.5">
            🖼️ สตอรี่บอร์ด (รูป)
            <span class="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded font-mono">กดกรอง</span>
          </span>
          <span class="text-base group-hover:scale-110 transition-transform">↗</span>
        </div>
        <div class="flex items-baseline gap-2 mt-1">
          <span id="kpiImgDone" class="text-2xl md:text-3xl font-extrabold text-white mono">0</span>
          <span class="text-xs text-slate-400">/ <span id="kpiTotalScenes">0</span> ฉาก</span>
        </div>
        <div class="w-full bg-slate-800 rounded-full h-1.5 mt-2 overflow-hidden">
          <div id="kpiImgBar" class="bg-emerald-400 h-1.5 rounded-full transition-all duration-500" style="width: 0%"></div>
        </div>
      </div>

      <!-- KPI 2: Video Clickable Box (Default Active) -->
      <div id="kpiBoxVideo" onclick="switchViewMode('VIDEO')" 
           class="card-glass rounded-2xl p-4 shadow-lg border-l-4 border-indigo-500 cursor-pointer hover:border-indigo-400 transition-all group select-none ring-2 ring-indigo-400 bg-indigo-950/30">
        <div class="flex justify-between items-center text-slate-400 text-xs font-bold uppercase group-hover:text-indigo-300 transition">
          <span class="flex items-center gap-1.5">
            🎬 วิดีโอ (คลิป MP4)
            <span class="text-[10px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded font-mono">กดกรอง</span>
          </span>
          <span class="text-base group-hover:scale-110 transition-transform">↗</span>
        </div>
        <div class="flex items-baseline gap-2 mt-1">
          <span id="kpiVidDone" class="text-2xl md:text-3xl font-extrabold text-white mono">0</span>
          <span class="text-xs text-slate-400">/ <span id="kpiTotalScenesVid">0</span> ฉาก</span>
        </div>
        <div class="w-full bg-slate-800 rounded-full h-1.5 mt-2 overflow-hidden">
          <div id="kpiVidBar" class="bg-indigo-400 h-1.5 rounded-full transition-all duration-500" style="width: 0%"></div>
        </div>
      </div>

      <!-- KPI 3: Status Action -->
      <div class="card-glass rounded-2xl p-4 shadow-lg border-l-4 border-amber-500 col-span-2 md:col-span-2">
        <div class="flex justify-between items-center text-slate-400 text-xs font-bold uppercase">
          <span>งานปัจจุบัน / สถานะระบบ</span>
          <span id="kpiStatusDot" class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
        </div>
        <div class="flex items-center gap-2 mt-1">
          <span id="kpiCurrentAction" class="text-sm md:text-base font-bold text-amber-300 truncate">พร้อมทำงาน</span>
        </div>
        <p class="text-xs text-slate-400 mt-1 flex items-center justify-between">
          <span>อัปเดตล่าสุด: <span id="kpiLastUpdated" class="mono text-slate-300">--:--:--</span></span>
          <span class="text-[11px] text-slate-500">คลิกที่ Tile เพื่อดูภาพ/เล่นวิดีโอ</span>
        </p>
      </div>
    </div>

    <!-- Active Status Legend as Clickable Filter Buttons -->
    <div class="flex flex-wrap items-center justify-between gap-3 bg-slate-900/70 p-3.5 rounded-2xl border border-slate-800 text-xs">
      <div class="flex flex-wrap items-center gap-2.5">
        <span class="text-slate-400 font-bold uppercase text-[11px] mr-1">กดสีเพื่อกรองสถานะ:</span>
        
        <button id="filterBtn_ALL" onclick="setTileFilter('ALL')" 
                class="filter-btn filter-btn-all px-3.5 py-1.5 rounded-full font-bold text-xs flex items-center gap-1.5 shadow">
          <span>📋</span> ทั้งหมด (<span id="filterCountAll">0</span>)
        </button>

        <button id="filterBtn_DONE" onclick="setTileFilter('DONE')" 
                class="filter-btn filter-btn-done px-3.5 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5 shadow">
          <span>✓</span> เสร็จแล้ว (<span id="filterCountDone">0</span>)
        </button>

        <button id="filterBtn_ACTIVE" onclick="setTileFilter('ACTIVE')" 
                class="filter-btn filter-btn-active px-3.5 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5 shadow">
          <span>⚡</span> กำลังทำ (<span id="filterCountActive">0</span>)
        </button>

        <button id="filterBtn_FAILED" onclick="setTileFilter('FAILED')" 
                class="filter-btn filter-btn-failed px-3.5 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5 shadow">
          <span>✕</span> ล้มเหลว (<span id="filterCountFailed">0</span>)
        </button>

        <button id="filterBtn_FIXING" onclick="setTileFilter('FIXING')" 
                class="filter-btn filter-btn-fixing px-3.5 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5 shadow">
          <span>⚙️</span> กำลังแก้ไข (<span id="filterCountFixing">0</span>)
        </button>

        <button id="filterBtn_PENDING" onclick="setTileFilter('PENDING')" 
                class="filter-btn filter-btn-pending px-3.5 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5 shadow">
          <span>⏳</span> ยังไม่ทำ (<span id="filterCountPending">0</span>)
        </button>
      </div>

      <div class="flex flex-wrap items-center gap-2.5">
        <!-- Selection & Copy Toolbar -->
        <div id="selectionBar" class="flex flex-wrap items-center gap-2 bg-slate-950/90 p-1.5 rounded-xl border border-slate-800 text-xs shadow-inner">
          <button id="btnSelectAll" onclick="toggleSelectAll()" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold transition flex items-center gap-1 cursor-pointer">
            <span>☑</span> <span id="btnSelectAllText">เลือกทั้งหมด</span>
          </button>
          <span class="text-slate-400 font-semibold px-1 text-[11px]">เลือก: <span id="selectionCount" class="text-indigo-400 font-mono font-bold">0</span> ฉาก</span>
          <button id="btnCopySelected" onclick="copySelectedScenes()" disabled
                  class="px-3 py-1 rounded-lg bg-slate-800 text-slate-500 font-bold transition flex items-center gap-1.5 cursor-not-allowed">
            <span>📋</span> <span id="btnCopyText">คัดลอกลำดับ</span>
          </button>
          <button id="btnPassSelected" onclick="passSelectedScenes()" style="display:none;"
                  class="px-2.5 py-1 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white font-bold transition flex items-center gap-1 cursor-pointer shadow">
            <span>✓</span> ผ่านที่เลือก (<span id="passSelectedCount">0</span>)
          </button>
          <button id="btnPassAll" onclick="passAllFixingScenes()" style="display:none;"
                  class="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition flex items-center gap-1 cursor-pointer shadow-lg shadow-emerald-600/30">
            <span>✓</span> ผ่านทั้งหมด (<span id="passAllCount">0</span>)
          </button>
          <button id="btnClearSelected" onclick="clearSelection()" style="display:none;"
                  class="px-2 py-1 rounded-lg text-slate-400 hover:text-rose-400 font-bold transition cursor-pointer" title="ล้างการเลือกทั้งหมด">
            ✕ ล้าง
          </button>
        </div>

        <!-- Tile Size Switcher -->
        <div class="flex items-center gap-1.5 bg-slate-950/90 p-1.5 rounded-xl border border-slate-800 text-xs">
          <span class="text-slate-400 font-semibold px-1 text-[11px]">ขนาดไทล์:</span>
          <button id="btnSizeNormal" onclick="setTileSize('NORMAL')" class="px-2.5 py-1 rounded-lg bg-indigo-600 text-white font-bold transition flex items-center gap-1 shadow">
            <span>⬛</span> ปกติ
          </button>
          <button id="btnSizeCompact" onclick="setTileSize('COMPACT')" class="px-2.5 py-1 rounded-lg text-slate-400 hover:text-white font-semibold transition flex items-center gap-1">
            <span>🗜️</span> เล็ก 50%
          </button>
        </div>
      </div>
    </div>

    <!-- MAIN: Google Flow 9:16 Tile Grid -->
    <div id="tileGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
      <!-- Dynamically generated Flow Tiles -->
      <div class="col-span-full py-16 text-center text-slate-500">
        กำลังโหลดข้อมูล Tile จากระบบ...
      </div>
    </div>

    <!-- Live Flow Audit Log Box -->
    <div class="card-glass rounded-2xl p-4 shadow-xl space-y-2">
      <div class="flex justify-between items-center pb-2 border-b border-slate-800">
        <h3 class="text-xs font-bold text-slate-300 flex items-center gap-2">
          📟 บันทึกเหตุการณ์สด (flow_action_audit.log)
        </h3>
        <span class="text-[11px] text-slate-500 mono">Auto-tailing live</span>
      </div>
      <div id="auditLogBox" class="bg-slate-950 p-3 rounded-xl border border-slate-900 mono text-xs text-slate-300 h-32 overflow-y-auto space-y-1">
        <div class="text-slate-500 italic">กำลังอ่านประวัติการทำงาน...</div>
      </div>
    </div>

    <footer class="text-center text-xs text-slate-500 py-2">
      ผักกาดการละคร Live Status Service • Running on Port 8181 • FlowKit Automation Architecture
    </footer>

  </div>

  <!-- Fullscreen Media Modal Lightbox -->
  <div id="mediaModal" class="hidden fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4" onclick="closeModal(event)">
    <div class="relative max-w-4xl w-full bg-slate-900 rounded-3xl overflow-hidden border border-slate-700 shadow-2xl flex flex-col md:flex-row max-h-[90vh]" onclick="event.stopPropagation()">
      <button onclick="closeModal()" class="absolute top-4 right-4 z-20 w-8 h-8 rounded-full bg-slate-800/80 text-white flex items-center justify-center hover:bg-slate-700 transition">✕</button>
      
      <!-- Media Player Area -->
      <div id="modalMediaArea" class="w-full md:w-1/2 bg-black flex items-center justify-center p-2 min-h-[360px]">
        <!-- Dynamic Image or Video -->
      </div>

      <!-- Info Area -->
      <div class="w-full md:w-1/2 p-6 flex flex-col justify-between overflow-y-auto space-y-4">
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span id="modalSceneTag" class="text-xs font-mono font-bold bg-indigo-500/20 text-indigo-300 px-3 py-1 rounded-full border border-indigo-500/30">Scene #01</span>
            <span id="modalStatusBadge" class="text-xs px-3 py-1 rounded-full font-bold">DONE</span>
          </div>
          
          <div>
            <h4 class="text-xs uppercase text-slate-400 font-bold">บทพูด / ไดอะล็อก:</h4>
            <p id="modalDialogue" class="text-sm font-semibold text-amber-300 mt-1 bg-amber-950/30 p-2.5 rounded-xl border border-amber-800/40">
              -
            </p>
          </div>

          <div>
            <h4 class="text-xs uppercase text-slate-400 font-bold">ตัวละครในฉาก:</h4>
            <div id="modalCharacters" class="flex flex-wrap gap-1 mt-1"></div>
          </div>

          <div>
            <h4 class="text-xs uppercase text-slate-400 font-bold">Prompt รายละเอียด:</h4>
            <p id="modalPrompt" class="text-xs text-slate-300 mt-1 leading-relaxed max-h-48 overflow-y-auto bg-slate-950 p-2.5 rounded-xl border border-slate-800 mono">
              -
            </p>
          </div>
        </div>

        <div class="pt-3 border-t border-slate-800 flex flex-wrap justify-between items-center gap-2 text-xs text-slate-400">
          <span id="modalFileSize">ขนาด: -</span>
          <div class="flex items-center gap-2">
            <button id="modalPassBtn" onclick="passModalScene()" style="display:none;" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold transition flex items-center gap-1 cursor-pointer shadow-md">
              <span>✓</span> ผ่านฉากนี้
            </button>
            <a id="modalDownloadLink" href="#" target="_blank" class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-semibold transition">
              เปิดดูไฟล์เต็ม ↗
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    // Read saved view mode from localStorage
    const savedMode = localStorage.getItem('flow_status_mode');
    let currentMode = (savedMode === 'STORYBOARD' || savedMode === 'VIDEO') ? savedMode : 'VIDEO';
    let currentFilter = 'ALL';
    let cachedScenes = [];

    // Read saved story and episode from localStorage
    const savedStory = localStorage.getItem('flow_status_story') || localStorage.getItem('selected_story');
    let activeStory = savedStory ? parseInt(savedStory, 10) : 31;
    const savedEp = localStorage.getItem('flow_status_ep') || localStorage.getItem('selected_ep');
    let activeEp = savedEp || 'EP01';

    // Set initial options immediately to prevent flickering
    const initStorySelect = document.getElementById('storySelect');
    if (initStorySelect && savedStory) {
      initStorySelect.innerHTML = `<option value="${activeStory}" selected>Story ${activeStory}</option>`;
    }
    const initEpSelect = document.getElementById('epSelect');
    if (initEpSelect && savedEp) {
      initEpSelect.innerHTML = `<option value="${activeEp}" selected>${activeEp}</option>`;
    }

    // Set initial mode styling immediately
    if (currentMode === 'STORYBOARD') {
      const boxImg = document.getElementById('kpiBoxStoryboard');
      const boxVid = document.getElementById('kpiBoxVideo');
      if (boxImg && boxVid) {
        boxImg.classList.add('ring-2', 'ring-emerald-400', 'bg-emerald-950/30');
        boxImg.classList.remove('opacity-60');
        boxVid.classList.remove('ring-2', 'ring-indigo-400', 'bg-indigo-950/30');
        boxVid.classList.add('opacity-60');
      }
    }

    let availableStoriesCache = [];

    async function fetchStatus() {
      try {
        const url = `/api/status?story=${activeStory}&ep=${activeEp}`;
        const res = await fetch(url);
        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.error('Error fetching status:', err);
      }
    }

    function switchViewMode(mode) {
      currentMode = mode;
      localStorage.setItem('flow_status_mode', mode);
      const boxImg = document.getElementById('kpiBoxStoryboard');
      const boxVid = document.getElementById('kpiBoxVideo');
      if (mode === 'STORYBOARD') {
        boxImg.classList.add('ring-2', 'ring-emerald-400', 'bg-emerald-950/30');
        boxImg.classList.remove('opacity-60');
        boxVid.classList.remove('ring-2', 'ring-indigo-400', 'bg-indigo-950/30');
        boxVid.classList.add('opacity-60');
      } else {
        boxVid.classList.add('ring-2', 'ring-indigo-400', 'bg-indigo-950/30');
        boxVid.classList.remove('opacity-60');
        boxImg.classList.remove('ring-2', 'ring-emerald-400', 'bg-emerald-950/30');
        boxImg.classList.add('opacity-60');
      }
      updateFilterCounts();
      renderTiles();
    }

    function setTileFilter(f) {
      if (currentFilter === f && f !== 'ALL') {
        currentFilter = 'ALL';
      } else {
        currentFilter = f;
      }
      updateFilterButtonsUI();
      renderTiles();
    }

    function updateFilterButtonsUI() {
      const keys = ['ALL', 'DONE', 'ACTIVE', 'FAILED', 'FIXING', 'PENDING'];
      keys.forEach(k => {
        const btn = document.getElementById('filterBtn_' + k);
        if (!btn) return;
        if (currentFilter === k) {
          btn.classList.add('is-active');
          btn.classList.remove('opacity-40');
        } else if (currentFilter === 'ALL') {
          btn.classList.remove('is-active', 'opacity-40');
        } else {
          btn.classList.remove('is-active');
          btn.classList.add('opacity-40');
        }
      });
    }

    function updateFilterCounts() {
      const isImg = (currentMode === 'STORYBOARD');
      const getSt = (s) => isImg ? s.image_status : s.video_status;
      
      const countAll = cachedScenes.length;
      const countDone = cachedScenes.filter(s => getSt(s) === 'DONE').length;
      const countActive = cachedScenes.filter(s => getSt(s) === 'GENERATING').length;
      const countFailed = cachedScenes.filter(s => getSt(s) === 'FAILED').length;
      const countFixing = cachedScenes.filter(s => getSt(s) === 'FIXING').length;
      const countPending = cachedScenes.filter(s => {
        const st = getSt(s);
        return !st || st === 'PENDING' || st === 'TODO' || (st !== 'DONE' && st !== 'GENERATING' && st !== 'FAILED' && st !== 'FIXING');
      }).length;

      const elAll = document.getElementById('filterCountAll');
      const elDone = document.getElementById('filterCountDone');
      const elActive = document.getElementById('filterCountActive');
      const elFailed = document.getElementById('filterCountFailed');
      const elFixing = document.getElementById('filterCountFixing');
      const elPending = document.getElementById('filterCountPending');

      if (elAll) elAll.innerText = countAll;
      if (elDone) elDone.innerText = countDone;
      if (elActive) elActive.innerText = countActive;
      if (elFailed) elFailed.innerText = countFailed;
      if (elFixing) elFixing.innerText = countFixing;
      if (elPending) elPending.innerText = countPending;
      updateFilterButtonsUI();
    }

    function updateEpDropdown() {
      const epSelect = document.getElementById('epSelect');
      if (!epSelect) return;
      const storyObj = availableStoriesCache.find(s => s.story === activeStory);
      const eps = (storyObj && storyObj.episodes && storyObj.episodes.length) ? storyObj.episodes : ['EP01'];
      if (!eps.includes(activeEp)) {
        activeEp = eps[0] || 'EP01';
        localStorage.setItem('flow_status_ep', activeEp);
      }
      epSelect.innerHTML = eps.map(e => 
        `<option value="${e}" ${e === activeEp ? 'selected' : ''}>${e}</option>`
      ).join('');
      epSelect.value = activeEp;
    }

    function onStoryChange() {
      activeStory = parseInt(document.getElementById('storySelect').value, 10);
      localStorage.setItem('flow_status_story', activeStory);
      selectedScenes = [];
      updateSelectionUI();
      updateEpDropdown();
      fetchStatus();
    }

    function onEpChange() {
      activeEp = document.getElementById('epSelect').value;
      localStorage.setItem('flow_status_ep', activeEp);
      selectedScenes = [];
      updateSelectionUI();
      fetchStatus();
    }

    function renderDashboard(data) {
      cachedScenes = data.scenes || [];
      const summary = data.summary || {};

      if (data.fixing_scenes && Array.isArray(data.fixing_scenes)) {
        saveLocalFixingScenes(data.fixing_scenes);
      }

      // Populate Story Selectors with persistence sync
      if (data.available_stories && data.available_stories.length) {
        availableStoriesCache = data.available_stories;
        const storySelect = document.getElementById('storySelect');
        const exists = availableStoriesCache.some(s => s.story === activeStory);
        if (!exists && !savedStory) {
          activeStory = availableStoriesCache[0].story;
          localStorage.setItem('flow_status_story', activeStory);
        }

        if (storySelect.options.length <= 1 || parseInt(storySelect.value, 10) !== activeStory) {
          storySelect.innerHTML = availableStoriesCache.map(s => 
            `<option value="${s.story}" ${s.story === activeStory ? 'selected' : ''}>Story ${s.story}</option>`
          ).join('');
          storySelect.value = activeStory;
        }

        updateEpDropdown();
      }

      // KPIs
      document.getElementById('kpiTotalScenes').innerText = summary.total_expected || cachedScenes.length;
      document.getElementById('kpiTotalScenesVid').innerText = summary.total_expected || cachedScenes.length;
      document.getElementById('kpiImgDone').innerText = summary.images_done || 0;
      document.getElementById('kpiVidDone').innerText = summary.videos_done || 0;

      document.getElementById('kpiImgBar').style.width = (summary.image_percent || 0) + '%';
      document.getElementById('kpiVidBar').style.width = (summary.video_percent || 0) + '%';

      document.getElementById('kpiCurrentAction').innerText = summary.current_action || 'พร้อมทำงาน';
      document.getElementById('kpiLastUpdated').innerText = summary.last_updated ? summary.last_updated.split(' ')[1] : '--:--:--';

      updateFilterCounts();
      renderTiles();
      renderLogs(data.recent_logs || []);
    }

    let currentTileSize = 'NORMAL'; // 'NORMAL' or 'COMPACT'

    function setTileSize(sz) {
      currentTileSize = sz;
      const btnNorm = document.getElementById('btnSizeNormal');
      const btnComp = document.getElementById('btnSizeCompact');
      const grid = document.getElementById('tileGrid');
      
      if (sz === 'COMPACT') {
        btnComp.className = 'px-2.5 py-1 rounded-lg bg-indigo-600 text-white font-bold transition flex items-center gap-1 shadow';
        btnNorm.className = 'px-2.5 py-1 rounded-lg text-slate-400 hover:text-white font-semibold transition flex items-center gap-1';
        grid.className = 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 2xl:grid-cols-12 gap-2';
      } else {
        btnNorm.className = 'px-2.5 py-1 rounded-lg bg-indigo-600 text-white font-bold transition flex items-center gap-1 shadow';
        btnComp.className = 'px-2.5 py-1 rounded-lg text-slate-400 hover:text-white font-semibold transition flex items-center gap-1';
        grid.className = 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-5 2xl:grid-cols-6 gap-4';
      }
      renderTiles();
    }

    let lastRenderStateKey = '';
    let selectedScenes = [];
    let currentModalSceneNum = null;

    function getLocalFixingKey() {
      return `flow_status_fixing_${activeStory}_${activeEp}`;
    }

    function getLocalFixingScenes() {
      try {
        const val = localStorage.getItem(getLocalFixingKey());
        return val ? JSON.parse(val) : [];
      } catch (e) {
        return [];
      }
    }

    function saveLocalFixingScenes(arr) {
      try {
        localStorage.setItem(getLocalFixingKey(), JSON.stringify(arr));
      } catch (e) {}
    }

    function toggleSelectScene(scNum, event) {
      if (event && event.target && event.target.closest('.modal-trigger-btn')) {
        return;
      }
      const idx = selectedScenes.indexOf(scNum);
      if (idx > -1) {
        selectedScenes.splice(idx, 1);
      } else {
        selectedScenes.push(scNum);
      }
      updateSelectionUI();
    }

    function clearSelection() {
      selectedScenes = [];
      updateSelectionUI();
    }

    function toggleSelectAll() {
      const isImg = (currentMode === 'STORYBOARD');
      const getSt = (s) => isImg ? s.image_status : s.video_status;
      const visibleScenes = cachedScenes.filter(s => {
        const st = getSt(s);
        if (currentFilter === 'DONE') return st === 'DONE';
        if (currentFilter === 'ACTIVE') return st === 'GENERATING';
        if (currentFilter === 'FAILED') return st === 'FAILED';
        if (currentFilter === 'FIXING') return st === 'FIXING';
        if (currentFilter === 'PENDING') return !st || st === 'PENDING' || st === 'TODO' || (st !== 'DONE' && st !== 'GENERATING' && st !== 'FAILED' && st !== 'FIXING');
        return true;
      }).map(s => s.scene_num);

      if (!visibleScenes.length) return;

      const allSelected = visibleScenes.every(num => selectedScenes.includes(num));
      if (allSelected) {
        selectedScenes = selectedScenes.filter(num => !visibleScenes.includes(num));
      } else {
        visibleScenes.forEach(num => {
          if (!selectedScenes.includes(num)) selectedScenes.push(num);
        });
      }
      updateSelectionUI();
    }

    async function copySelectedScenes() {
      if (!selectedScenes.length) return;
      const scenesToFix = [...selectedScenes];
      const text = scenesToFix.join(',');

      // 1. Copy to clipboard
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        console.warn('Clipboard write fallback', err);
      }

      // 2. Add to fixing_scenes in backend
      try {
        await fetch('/api/fixing/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            story: activeStory,
            ep: activeEp,
            scenes: scenesToFix
          })
        });
      } catch (err) {
        console.error('Error adding fixing scenes:', err);
      }

      // Sync local storage
      let localFixing = getLocalFixingScenes();
      scenesToFix.forEach(sc => {
        if (!localFixing.includes(sc)) localFixing.push(sc);
      });
      saveLocalFixingScenes(localFixing);

      // 3. Clear selections & automatically filter to FIXING tag
      selectedScenes = [];
      setTileFilter('FIXING');

      // 4. Update button feedback
      const btnText = document.getElementById('btnCopyText');
      if (btnText) {
        btnText.innerText = `✓ คัดลอก & ส่งไปแท็กแก้ไข (${text})`;
        setTimeout(() => {
          if (btnText) btnText.innerText = 'คัดลอกลำดับ';
        }, 2200);
      }

      // 5. Re-fetch status immediately
      await fetchStatus();
    }

    async function passScene(scNum) {
      try {
        await fetch('/api/fixing/remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            story: activeStory,
            ep: activeEp,
            scene: scNum
          })
        });
      } catch (err) {
        console.error('Error removing fixing scene:', err);
      }

      let localFixing = getLocalFixingScenes().filter(s => s !== scNum);
      saveLocalFixingScenes(localFixing);

      selectedScenes = selectedScenes.filter(s => s !== scNum);
      await fetchStatus();
    }

    async function passSelectedScenes() {
      if (!selectedScenes.length) return;
      const targets = [...selectedScenes];
      for (const scNum of targets) {
        try {
          await fetch('/api/fixing/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              story: activeStory,
              ep: activeEp,
              scene: scNum
            })
          });
        } catch (err) {}
      }

      let localFixing = getLocalFixingScenes().filter(s => !targets.includes(s));
      saveLocalFixingScenes(localFixing);

      selectedScenes = [];
      await fetchStatus();
    }

    async function passAllFixingScenes() {
      try {
        await fetch('/api/fixing/clear', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            story: activeStory,
            ep: activeEp
          })
        });
      } catch (err) {
        console.error('Error clearing fixing scenes:', err);
      }

      saveLocalFixingScenes([]);
      selectedScenes = [];
      await fetchStatus();
    }

    function passModalScene() {
      if (currentModalSceneNum !== null) {
        passScene(currentModalSceneNum);
        closeModal();
      }
    }

    function updateSelectionUI() {
      const countEl = document.getElementById('selectionCount');
      const btnCopy = document.getElementById('btnCopySelected');
      const btnText = document.getElementById('btnCopyText');
      const btnClear = document.getElementById('btnClearSelected');
      const btnSelectAll = document.getElementById('btnSelectAllText');
      const btnPassSel = document.getElementById('btnPassSelected');
      const passSelCount = document.getElementById('passSelectedCount');
      const btnPassAll = document.getElementById('btnPassAll');
      const passAllCount = document.getElementById('passAllCount');

      if (countEl) countEl.innerText = selectedScenes.length;

      // Check visible scenes for Select All button text
      const isImg = (currentMode === 'STORYBOARD');
      const getSt = (s) => isImg ? s.image_status : s.video_status;
      const visibleScenes = cachedScenes.filter(s => {
        const st = getSt(s);
        if (currentFilter === 'DONE') return st === 'DONE';
        if (currentFilter === 'ACTIVE') return st === 'GENERATING';
        if (currentFilter === 'FAILED') return st === 'FAILED';
        if (currentFilter === 'FIXING') return st === 'FIXING';
        if (currentFilter === 'PENDING') return !st || st === 'PENDING' || st === 'TODO' || (st !== 'DONE' && st !== 'GENERATING' && st !== 'FAILED' && st !== 'FIXING');
        return true;
      }).map(s => s.scene_num);

      if (btnSelectAll) {
        const allSelected = visibleScenes.length > 0 && visibleScenes.every(num => selectedScenes.includes(num));
        btnSelectAll.innerText = allSelected ? "ยกเลิกเลือก" : "เลือกทั้งหมด";
      }

      // Fixing scenes count
      const fixingScenes = cachedScenes.filter(s => getSt(s) === 'FIXING').map(s => s.scene_num);
      const fixingCount = fixingScenes.length;

      // Pass All button
      if (btnPassAll && passAllCount) {
        passAllCount.innerText = fixingCount;
        if (fixingCount > 0) {
          btnPassAll.style.display = "inline-flex";
        } else {
          btnPassAll.style.display = "none";
        }
      }

      // Pass Selected button
      const selectedFixingCount = selectedScenes.filter(num => fixingScenes.includes(num)).length;
      if (btnPassSel && passSelCount) {
        const countToShow = selectedFixingCount > 0 ? selectedFixingCount : selectedScenes.length;
        passSelCount.innerText = countToShow;
        if (selectedScenes.length > 0 && (selectedFixingCount > 0 || currentFilter === 'FIXING')) {
          btnPassSel.style.display = "inline-flex";
        } else {
          btnPassSel.style.display = "none";
        }
      }

      if (btnCopy && btnText) {
        if (selectedScenes.length > 0) {
          btnCopy.disabled = false;
          btnCopy.className = "px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition flex items-center gap-1.5 cursor-pointer shadow-lg shadow-emerald-600/30 scale-105";
          btnText.innerText = `คัดลอก: ${selectedScenes.join(',')}`;
          if (btnClear) btnClear.style.display = "inline-block";
        } else {
          btnCopy.disabled = true;
          btnCopy.className = "px-3 py-1 rounded-lg bg-slate-800 text-slate-500 font-bold transition flex items-center gap-1.5 cursor-not-allowed";
          btnText.innerText = "คัดลอกลำดับ";
          if (btnClear) btnClear.style.display = "none";
        }
      }

      document.querySelectorAll('.flow-tile').forEach(tile => {
        const scNum = parseInt(tile.dataset.sceneNum, 10);
        const selIdx = selectedScenes.indexOf(scNum);
        const badgeEl = tile.querySelector('.selection-order-badge');
        if (selIdx > -1) {
          tile.classList.add('ring-4', 'ring-indigo-500', 'border-indigo-400', 'shadow-indigo-500/40');
          if (badgeEl) {
            badgeEl.innerText = (selIdx + 1);
            badgeEl.classList.remove('hidden');
          }
        } else {
          tile.classList.remove('ring-4', 'ring-indigo-500', 'border-indigo-400', 'shadow-indigo-500/40');
          if (badgeEl) {
            badgeEl.classList.add('hidden');
          }
        }
      });
    }

    function handleTileHover(tile, isEnter) {
      const vid = tile.querySelector('video');
      if (!vid) return;
      if (isEnter) {
        vid.dataset.hovering = 'true';
        vid.loop = true;
        vid.playbackRate = 2.0; // 2x speed for quick preview
        const playPromise = vid.play();
        if (playPromise !== undefined) {
          playPromise.catch(() => {});
        }
      } else {
        delete vid.dataset.hovering;
        vid.pause();
        vid.currentTime = 0;
        vid.playbackRate = 1.0;
      }
    }

    function renderTiles() {
      const grid = document.getElementById('tileGrid');
      if (!cachedScenes || !cachedScenes.length) {
        grid.innerHTML = '<div class="col-span-full py-16 text-center text-slate-500">ไม่มีข้อมูลฉากในตอนนี้</div>';
        lastRenderStateKey = '';
        return;
      }

      const filtered = cachedScenes.filter(s => {
        const st = (currentMode === 'STORYBOARD') ? s.image_status : s.video_status;
        if (currentFilter === 'DONE') return st === 'DONE';
        if (currentFilter === 'ACTIVE') return st === 'GENERATING';
        if (currentFilter === 'FAILED') return st === 'FAILED';
        if (currentFilter === 'FIXING') return st === 'FIXING';
        if (currentFilter === 'PENDING') return !st || st === 'PENDING' || st === 'TODO' || (st !== 'DONE' && st !== 'GENERATING' && st !== 'FAILED' && st !== 'FIXING');
        return true;
      });

      if (!filtered.length) {
        grid.innerHTML = '<div class="col-span-full py-16 text-center text-slate-500">ไม่มีฉากในตัวกรองนี้</div>';
        lastRenderStateKey = '';
        return;
      }

      // Smart Cache Check: avoid re-rendering DOM every 2s if status hasn't changed so hover video doesn't reset
      const currentStateKey = `${activeStory}_${activeEp}_${currentMode}_${currentFilter}_${currentTileSize}_` +
        filtered.map(s => `${s.scene_num}:${s.image_status}:${s.video_status}:${s.is_fixing}:${s.has_image}:${s.has_video}:${s.image_size_kb}:${s.video_size_mb}`).join('|');

      if (currentStateKey === lastRenderStateKey) {
        return;
      }
      lastRenderStateKey = currentStateKey;

      // Preserve currently playing/hovered videos if data changed
      const activeHoverVideos = {};
      grid.querySelectorAll('video[data-hovering="true"]').forEach(v => {
        const sc = v.dataset.scene;
        if (sc) activeHoverVideos[sc] = { time: v.currentTime };
      });

      const isCompact = (currentTileSize === 'COMPACT');

      grid.innerHTML = filtered.map(s => {
        const isImg = (currentMode === 'STORYBOARD');
        const st = isImg ? s.image_status : s.video_status;
        const fallbackThumb = s.image_url;

        // Top Status Badge Style & Text (Placed at top header of tile)
        let badgeHtml = '';
        if (isCompact) {
          if (st === 'DONE') {
            badgeHtml = `<div class="px-1.5 py-0.2 rounded-full badge-center-done font-black text-[9px] tracking-tight shadow flex items-center gap-0.5"><span>✓</span> เสร็จแล้ว</div>`;
          } else if (st === 'GENERATING') {
            badgeHtml = `<div class="px-1.5 py-0.2 rounded-full badge-center-generating font-black text-[9px] tracking-tight shadow flex items-center gap-0.5"><svg class="animate-spin w-2 h-2 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span>กำลังทำ</span></div>`;
          } else if (st === 'FAILED') {
            badgeHtml = `<div class="px-1.5 py-0.2 rounded-full badge-center-failed font-black text-[9px] tracking-tight shadow flex items-center gap-0.5"><span>✕</span> ล้มเหลว</div>`;
          } else if (st === 'FIXING') {
            badgeHtml = `<div class="px-1.5 py-0.2 rounded-full badge-center-fixing font-black text-[9px] tracking-tight shadow flex items-center gap-0.5"><span>⚙️</span> กำลังแก้</div>`;
          } else {
            badgeHtml = `<div class="px-1.5 py-0.2 rounded-full badge-center-pending font-bold text-[8px] tracking-tight"><span>⏳ ยังไม่ทำ</span></div>`;
          }
        } else {
          if (st === 'DONE') {
            badgeHtml = `<div class="px-2.5 py-0.5 rounded-full badge-center-done font-black text-xs tracking-tight shadow-md flex items-center gap-1"><span>✓</span> เสร็จแล้ว</div>`;
          } else if (st === 'GENERATING') {
            badgeHtml = `<div class="px-2.5 py-0.5 rounded-full badge-center-generating font-black text-xs tracking-tight shadow-md flex items-center gap-1"><svg class="animate-spin w-3 h-3 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span>กำลังทำ</span></div>`;
          } else if (st === 'FAILED') {
            badgeHtml = `<div class="px-2.5 py-0.5 rounded-full badge-center-failed font-black text-xs tracking-tight shadow-md flex items-center gap-1"><span>✕</span> ล้มเหลว</div>`;
          } else if (st === 'FIXING') {
            badgeHtml = `<div class="px-2.5 py-0.5 rounded-full badge-center-fixing font-black text-xs tracking-tight shadow-md flex items-center gap-1"><span>⚙️</span> กำลังแก้ไข</div>`;
          } else {
            badgeHtml = `<div class="px-2 py-0.5 rounded-full badge-center-pending font-bold text-[10px] tracking-tight"><span>⏳ ยังไม่ทำ</span></div>`;
          }
        }

        // Top tag & size
        const sizeText = isImg ? (s.image_size_kb ? `${s.image_size_kb} KB` : '') : (s.video_size_mb ? `${s.video_size_mb} MB` : '');

        // Media visual in tile
        let visualHtml = '';
        if (isImg) {
          if (s.has_image) {
            visualHtml = `<img src="${s.image_url}" loading="lazy" class="w-full h-full object-cover">`;
          } else if (st === 'GENERATING') {
            visualHtml = `<div class="w-full h-full shimmer-bg flex items-center justify-center"></div>`;
          } else {
            visualHtml = `<div class="w-full h-full bg-slate-950 flex items-center justify-center text-slate-600 font-mono text-[10px]">No Img</div>`;
          }
        } else {
          if (s.has_video) {
            visualHtml = `<video data-scene="${s.scene_num}" src="${s.video_url}" ${fallbackThumb ? `poster="${fallbackThumb}"` : ''} muted loop playsinline preload="metadata" class="w-full h-full object-cover"></video>`;
          } else if (s.has_image) {
            visualHtml = `<img src="${s.image_url}" loading="lazy" class="w-full h-full object-cover opacity-60 filter brightness-75">`;
          } else if (st === 'GENERATING') {
            visualHtml = `<div class="w-full h-full shimmer-bg flex items-center justify-center"></div>`;
          } else {
            visualHtml = `<div class="w-full h-full bg-slate-950 flex items-center justify-center text-slate-600 font-mono text-[10px]">No Vid</div>`;
          }
        }

        const charHtml = isCompact ? '' : (s.characters || []).slice(0, 2).map(c => 
          `<span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-900/90 text-slate-300 border border-slate-700/60 truncate max-w-[90px]">${c}</span>`
        ).join('');

        const cardPadding = isCompact ? 'p-1.5' : 'p-2.5';
        const sceneTagClass = isCompact ? 'text-[10px] font-black font-mono bg-slate-900/80 text-white px-1.5 py-0.2 rounded border border-slate-700/60 backdrop-blur-md' : 'text-xs font-black font-mono bg-slate-900/80 text-white px-2 py-0.5 rounded-lg border border-slate-700/60 backdrop-blur-md';
        const sizeTagClass = isCompact ? 'text-[8px] font-mono font-bold bg-slate-900/80 text-slate-300 px-1 py-0.2 rounded border border-slate-700/60 backdrop-blur-md' : 'text-[10px] font-mono font-bold bg-slate-900/80 text-slate-300 px-2 py-0.5 rounded-lg border border-slate-700/60 backdrop-blur-md';

        return `
          <div class="flow-tile relative aspect-[9/16] rounded-xl md:rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-xl cursor-pointer group flex flex-col justify-between transition-all"
               data-scene-num="${s.scene_num}"
               onmouseenter="handleTileHover(this, true)"
               onmouseleave="handleTileHover(this, false)"
               onclick="toggleSelectScene(${s.scene_num}, event)"
               ondblclick="openModal(${s.scene_num})">
            
            <!-- Background Visual Media -->
            <div class="absolute inset-0 z-0">
              ${visualHtml}
              <!-- Gradient Overlay for Contrast -->
              <div class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-slate-950/60 pointer-events-none"></div>
            </div>

            <!-- Top Header on Tile: Scene Tag + Status Badge + Pass Button + File Size + Selection Order -->
            <div class="relative z-10 ${cardPadding} flex justify-between items-center gap-1 pointer-events-none">
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="${sceneTagClass}">
                  #${s.scene_str}
                </span>
                ${badgeHtml}
                ${(st === 'FIXING' || s.is_fixing) ? `
                  <button onclick="event.stopPropagation(); passScene(${s.scene_num})" 
                          class="pointer-events-auto px-2 py-0.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-black ${isCompact ? 'text-[9px]' : 'text-[11px]'} shadow-lg border border-emerald-400 flex items-center gap-0.5 transition-all transform hover:scale-105 active:scale-95 cursor-pointer" 
                          title="กดผ่านฉากนี้ (ปลดจากสถานะกำลังแก้ไข)">
                    <span>✓</span> ผ่าน
                  </button>
                ` : ''}
              </div>
              <div class="flex items-center gap-1">
                ${sizeText ? `
                  <span class="${sizeTagClass} shrink-0">
                    ${sizeText}
                  </span>` : ''}
                <span class="selection-order-badge hidden min-w-[20px] h-5 px-1.5 rounded-full bg-indigo-600 text-white font-black text-xs flex items-center justify-center border-2 border-white shadow-lg">
                </span>
              </div>
            </div>

            <!-- Bottom Footer on Tile -->
            <div class="relative z-10 ${cardPadding} space-y-0.5 bg-slate-950/80 backdrop-blur-md border-t border-slate-800/80 pointer-events-none">
              ${s.dialogue ? `
                <div class="${isCompact ? 'text-[9px]' : 'text-[11px]'} font-semibold text-amber-300 line-clamp-1" title="${s.dialogue}">
                  "${s.dialogue}"
                </div>` : `
                <div class="${isCompact ? 'text-[8px]' : 'text-[10px]'} text-slate-400 line-clamp-1" title="${s.prompt_preview}">
                  ${s.prompt_preview || 'ไม่มีข้อมูลบท'}
                </div>`}
              <div class="flex items-center justify-between pt-0.5">
                <div class="flex items-center gap-1 overflow-hidden pointer-events-none">
                  ${charHtml}
                </div>
                <span class="modal-trigger-btn pointer-events-auto text-[10px] text-indigo-400 hover:text-indigo-200 font-bold transition-all cursor-pointer"
                      onclick="event.stopPropagation(); openModal(${s.scene_num})">
                  ${isCompact ? '↗' : 'ดู ↗'}
                </span>
              </div>
            </div>

          </div>
        `;
      }).join('');

      // Restore video playback if it was playing before re-render
      Object.keys(activeHoverVideos).forEach(sc => {
        const v = grid.querySelector(`video[data-scene="${sc}"]`);
        if (v) {
          v.currentTime = activeHoverVideos[sc].time;
          v.dataset.hovering = 'true';
          v.loop = true;
          v.play().catch(() => {});
        }
      });

      // Restore active selections and order badges
      updateSelectionUI();
    }


    function openModal(scNum) {
      const s = cachedScenes.find(x => x.scene_num === scNum);
      if (!s) return;
      currentModalSceneNum = scNum;

      const modal = document.getElementById('mediaModal');
      const mediaArea = document.getElementById('modalMediaArea');
      const isImg = (currentMode === 'STORYBOARD');

      document.getElementById('modalSceneTag').innerText = `Scene #${s.scene_str}`;
      
      const st = isImg ? s.image_status : s.video_status;
      const statusBadge = document.getElementById('modalStatusBadge');
      let stBadgeText = st;
      let stBadgeClass = 'bg-slate-700/40 text-slate-300 border border-slate-600/40';
      if (st === 'DONE') {
        stBadgeText = '✓ เสร็จแล้ว';
        stBadgeClass = 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
      } else if (st === 'GENERATING') {
        stBadgeText = '⚡ กำลังทำ';
        stBadgeClass = 'bg-blue-500/20 text-blue-300 border border-blue-500/40';
      } else if (st === 'FAILED') {
        stBadgeText = '✕ ล้มเหลว';
        stBadgeClass = 'bg-rose-500/20 text-rose-300 border border-rose-500/40';
      } else if (st === 'FIXING') {
        stBadgeText = '⚙️ กำลังแก้ไข';
        stBadgeClass = 'bg-amber-500/20 text-amber-300 border border-amber-500/40';
      } else {
        stBadgeText = '⏳ ยังไม่ทำ';
        stBadgeClass = 'bg-slate-800 text-slate-400 border border-slate-700';
      }
      statusBadge.innerText = stBadgeText;
      statusBadge.className = `text-xs px-3 py-1 rounded-full font-bold ${stBadgeClass}`;

      const passBtn = document.getElementById('modalPassBtn');
      if (passBtn) {
        if (st === 'FIXING' || s.is_fixing) {
          passBtn.style.display = 'inline-flex';
        } else {
          passBtn.style.display = 'none';
        }
      }

      document.getElementById('modalDialogue').innerText = s.dialogue ? `"${s.dialogue}"` : '- ไม่มีบทพูด -';
      document.getElementById('modalPrompt').innerText = s.full_prompt || s.prompt_preview || 'ไม่มีข้อมูลพรอมต์';
      
      const charBox = document.getElementById('modalCharacters');
      charBox.innerHTML = (s.characters || []).map(c => 
        `<span class="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-200 border border-slate-700">${c}</span>`
      ).join('') || '<span class="text-xs text-slate-500">-</span>';

      const dLink = document.getElementById('modalDownloadLink');
      const sizeEl = document.getElementById('modalFileSize');

      if (!isImg && s.has_video) {
        mediaArea.innerHTML = `<video src="${s.video_url}" controls autoplay class="max-h-[80vh] w-auto max-w-full rounded-2xl shadow-2xl"></video>`;
        dLink.href = s.video_url;
        sizeEl.innerText = `ขนาดวิดีโอ: ${s.video_size_mb} MB`;
      } else if (s.has_image) {
        mediaArea.innerHTML = `<img src="${s.image_url}" class="max-h-[80vh] w-auto max-w-full object-contain rounded-2xl shadow-2xl">`;
        dLink.href = s.image_url;
        sizeEl.innerText = `ขนาดรูป: ${s.image_size_kb} KB`;
      } else {
        mediaArea.innerHTML = `<div class="text-slate-500 font-mono text-xs">ยังไม่มีไฟล์สื่อสำหรับฉากนี้</div>`;
        dLink.href = '#';
        sizeEl.innerText = 'ขนาด: -';
      }

      modal.classList.remove('hidden');
    }

    function closeModal(e) {
      const modal = document.getElementById('mediaModal');
      const mediaArea = document.getElementById('modalMediaArea');
      mediaArea.innerHTML = '';
      currentModalSceneNum = null;
      modal.classList.add('hidden');
    }

    function renderLogs(logs) {
      const box = document.getElementById('auditLogBox');
      if (!logs || !logs.length) {
        box.innerHTML = '<div class="text-slate-500 italic">ไม่มีบันทึกเหตุการณ์</div>';
        return;
      }
      box.innerHTML = logs.map(l => {
        let colorClass = 'text-slate-300';
        if (l.includes('[PASS]') || l.includes('[SUCCESS]') || l.includes('OK')) colorClass = 'text-emerald-400';
        else if (l.includes('[ERROR]') || l.includes('[FAIL]') || l.includes('failed')) colorClass = 'text-rose-400';
        else if (l.includes('[SUBMIT_START]') || l.includes('[BEGIN]')) colorClass = 'text-cyan-400';
        return `<div class="${colorClass}">${escapeHtml(l)}</div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    }

    function escapeHtml(str) {
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Auto-refresh every 2 seconds
    fetchStatus();
    setInterval(fetchStatus, 2000);
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


def main():
    logger.info("Starting Status Server 8181 at http://%s:%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
