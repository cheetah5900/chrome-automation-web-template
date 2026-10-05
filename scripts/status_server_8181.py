"""Status Server on Port 8181 — Detailed Generation & Fix Tracker for ผักกาดการละคร."""
import os
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

CHANNEL_ROOT = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย"
REPO_ROOT = "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"
AUDIT_LOG_PATH = os.path.join(REPO_ROOT, "flow_action_audit.log")
STATE_FILE = os.path.join(os.path.dirname(__file__), "generation_status.json")

app = FastAPI(title="Lakorn Generation Status Monitor", version="1.0.0")

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
        "story": 26,
        "ep": "EP02",
        "current_scene": None,
        "current_action": "พร้อมทำงาน (EP02 25/25 ฉากสมบูรณ์ 100%)",
        "current_status": "IDLE",  # IDLE, RUNNING, FIXING, COMPLETED, ERROR
        "fixing_scene": None,
        "failed_scenes": [],
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_log": "ภาพสตอรี่บอร์ดครบถ้วน 25 ฉาก",
    }


def save_state(state: Dict[str, Any]):
    """Save persistent state to JSON file."""
    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Error saving state file: %s", e)


def get_story_scenes_info(story_num: int, ep_str: str) -> Dict[str, Any]:
    """Scan story directory to get detailed per-scene status."""
    story_dir = os.path.join(CHANNEL_ROOT, str(story_num))
    if not os.path.isdir(story_dir):
        return {"total_expected": 0, "scenes": []}

    prompt_dir = os.path.join(story_dir, "4 - Image Prompt", ep_str)
    storyboard_dir = os.path.join(story_dir, "6 - Storyboards", ep_str)
    ces_dir = os.path.join(story_dir, "4 - Character Each Scene", ep_str)

    scenes = []
    if os.path.isdir(prompt_dir):
        prompt_files = sorted([f for f in os.listdir(prompt_dir) if f.endswith(".md") and not f.startswith(".")])
    else:
        prompt_files = []

    for pf in prompt_files:
        # Expected format: "01 - Scene 01.md"
        base_name = os.path.splitext(pf)[0]
        parts = base_name.split(" - ")
        sc_num_str = parts[0]
        try:
            sc_num = int(sc_num_str)
        except ValueError:
            continue

        # Check prompt text
        prompt_path = os.path.join(prompt_dir, pf)
        prompt_preview = ""
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_text = f.read()
                # Find scene description
                if f"Scene {sc_num:02d}:" in prompt_text:
                    prompt_preview = prompt_text.split(f"Scene {sc_num:02d}:")[1].split("..")[0].strip()
                elif f"Scene {sc_num}:" in prompt_text:
                    prompt_preview = prompt_text.split(f"Scene {sc_num}:")[1].split("..")[0].strip()
                else:
                    prompt_preview = prompt_text[:100].strip()
        except Exception:
            pass

        # Check character assignments
        characters = []
        ces_file = os.path.join(ces_dir, pf)
        if os.path.isfile(ces_file):
            try:
                with open(ces_file, "r", encoding="utf-8") as f:
                    characters = [line.strip() for line in f.readlines() if line.strip()]
            except Exception:
                pass

        # Check generated image
        img_name = f"{ep_str} - Scene {sc_num:02d}.jpg"
        img_path = os.path.join(storyboard_dir, img_name)
        exists = os.path.isfile(img_path)
        size_kb = 0
        mtime_str = ""
        if exists:
            stat = os.stat(img_path)
            size_kb = round(stat.st_size / 1024, 1)
            mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M:%S")

        status = "DONE" if (exists and size_kb > 50) else "MISSING"

        scenes.append({
            "scene_num": sc_num,
            "scene_str": f"{sc_num:02d}",
            "filename": img_name,
            "status": status,
            "size_kb": size_kb,
            "mtime": mtime_str,
            "characters": characters,
            "prompt_preview": prompt_preview,
            "has_image": exists,
            "image_url": f"/api/storyboard-image/{story_num}/{ep_str}/{img_name}" if exists else None,
        })

    return {
        "total_expected": len(scenes),
        "total_created": sum(1 for s in scenes if s["status"] == "DONE"),
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


@app.get("/api/status")
def get_status_api(story: Optional[int] = None, ep: Optional[str] = None):
    """Detailed live status API."""
    state = load_state()
    active_story = story if story is not None else state.get("story", 26)
    active_ep = ep if ep is not None else state.get("ep", "EP02")

    story_info = get_story_scenes_info(active_story, active_ep)
    total_expected = story_info["total_expected"]
    total_created = story_info["total_created"]

    # Calculate stuck / failed count
    failed_scenes = state.get("failed_scenes", [])
    # Also detect any missing scenes that were expected
    missing_scenes = [s["scene_num"] for s in story_info["scenes"] if s["status"] == "MISSING"]

    stuck_count = len(failed_scenes) if failed_scenes else len(missing_scenes)

    # Current fixing / active scene
    fixing_scene = state.get("fixing_scene")
    current_scene = state.get("current_scene")

    recent_logs = get_recent_audit_logs(15)

    return {
        "story": active_story,
        "ep": active_ep,
        "summary": {
            "total_created": total_created,
            "total_expected": total_expected,
            "percent_completed": round((total_created / total_expected * 100), 1) if total_expected > 0 else 0,
            "stuck_count": stuck_count,
            "is_all_done": (total_created == total_expected and total_expected > 0),
            "current_status": state.get("current_status", "IDLE"),
            "current_action": state.get("current_action", "พร้อมทำงาน"),
            "current_scene": current_scene,
            "fixing_scene": fixing_scene,
            "last_updated": state.get("last_updated"),
        },
        "failed_scenes": failed_scenes,
        "missing_scenes": missing_scenes,
        "scenes": story_info["scenes"],
        "recent_logs": recent_logs,
    }


@app.post("/api/status/update")
async def update_status_api(request: Request):
    """Update generator status dynamically from scripts or agents."""
    data = await request.json()
    state = load_state()

    if "story" in data:
        state["story"] = data["story"]
    if "ep" in data:
        state["ep"] = data["ep"]
    if "current_scene" in data:
        state["current_scene"] = data["current_scene"]
    if "current_action" in data:
        state["current_action"] = data["current_action"]
    if "current_status" in data:
        state["current_status"] = data["current_status"]
    if "fixing_scene" in data:
        state["fixing_scene"] = data["fixing_scene"]
    if "failed_scenes" in data:
        state["failed_scenes"] = data["failed_scenes"]
    if "active_log" in data:
        state["active_log"] = data["active_log"]

    save_state(state)
    return {"success": True, "state": state}


@app.get("/api/storyboard-image/{story}/{ep}/{filename}")
def get_storyboard_image(story: int, ep: str, filename: str):
    """Serve storyboard image for live thumbnail preview."""
    safe_file = os.path.basename(filename)
    path = os.path.join(CHANNEL_ROOT, str(story), "6 - Storyboards", ep, safe_file)
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": "Image not found"})


@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    """Render high-fidelity real-time monitor dashboard."""
    html_content = """<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>สถานะสร้างสตอรี่บอร์ด & แก้ไขภาพ (Port 8181)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@300;400;600;700&family=Noto+Sans+Thai:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Noto Sans Thai', 'Chakra Petch', sans-serif;
      background-color: #0b0f19;
      color: #e2e8f0;
    }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    .card-glass {
      background: rgba(17, 24, 39, 0.85);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .badge-done { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-fixing { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); animation: pulse 2s infinite; }
    .badge-stuck { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-missing { background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3); }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }
  </style>
</head>
<body class="min-h-screen p-4 md:p-6 lg:p-8">
  <div class="max-w-7xl mx-auto space-y-6">

    <!-- Header Section -->
    <header class="card-glass rounded-2xl p-5 shadow-2xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div class="space-y-1">
        <div class="flex items-center gap-3">
          <div class="w-3.5 h-3.5 rounded-full bg-emerald-400 animate-ping"></div>
          <h1 class="text-xl md:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            🎬 ศูนย์รายงานสถานะการสร้างสตอรี่บอร์ด
            <span class="text-xs uppercase bg-emerald-500/20 text-emerald-300 font-semibold px-2.5 py-0.5 rounded-full border border-emerald-500/40">PORT 8181 LIVE</span>
          </h1>
        </div>
        <p class="text-xs md:text-sm text-slate-400">
          ช่องผักกาดการละคร • ตรวจจับความคืบหน้าแบบ Real-time • ล็อกตัวละคร Character Sheet 100%
        </p>
      </div>

      <!-- Controls & Refresh Indicator -->
      <div class="flex items-center gap-3 self-end md:self-auto">
        <span id="lastUpdated" class="text-xs text-slate-400 mono">อัปเดต: --:--:--</span>
        <button onclick="fetchStatus()" class="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 transition flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          รีเฟรชสด
        </button>
      </div>
    </header>

    <!-- KPI Metric Cards Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- KPI 1: สร้างรูปทั้งหมดเท่าไร -->
      <div class="card-glass rounded-2xl p-5 shadow-lg border-l-4 border-emerald-500 space-y-2">
        <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
          <span>สร้างรูปทั้งหมด</span>
          <span class="text-emerald-400 text-base">🖼️</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="metricCreated" class="text-3xl font-extrabold text-white mono">0</span>
          <span class="text-sm font-medium text-slate-400">/ <span id="metricExpected">0</span> ฉาก</span>
        </div>
        <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div id="metricProgressBar" class="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 rounded-full transition-all duration-500" style="width: 0%"></div>
        </div>
        <div class="flex justify-between text-xs text-slate-400">
          <span id="metricPercent">0% สำเร็จ</span>
          <span id="metricDoneText" class="text-emerald-400 font-medium">รอข้อมูล</span>
        </div>
      </div>

      <!-- KPI 2: ติดกี่อัน -->
      <div class="card-glass rounded-2xl p-5 shadow-lg border-l-4 border-rose-500 space-y-2">
        <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
          <span>ติดกี่อัน (Stuck / Failed)</span>
          <span class="text-rose-400 text-base">⚠️</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="metricStuck" class="text-3xl font-extrabold text-white mono">0</span>
          <span class="text-sm font-medium text-slate-400">ฉากที่มีปัญหา</span>
        </div>
        <p id="metricStuckDesc" class="text-xs text-emerald-400 font-medium pt-1">
          ✅ ไม่มีฉากติดขัด ทุกภาพสมบูรณ์
        </p>
      </div>

      <!-- KPI 3: กำลังแก้อันไหน -->
      <div class="card-glass rounded-2xl p-5 shadow-lg border-l-4 border-amber-500 space-y-2">
        <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
          <span>กำลังแก้อันไหน / งานปัจจุบัน</span>
          <span class="text-amber-400 text-base">🔧</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="metricFixing" class="text-lg md:text-xl font-bold text-amber-300 truncate">ไม่มี (ว่าง)</span>
        </div>
        <p id="metricAction" class="text-xs text-slate-400 truncate pt-1">
          สถานะ: สแตนด์บาย
        </p>
      </div>

      <!-- KPI 4: ตอน & สเตจการผลิต -->
      <div class="card-glass rounded-2xl p-5 shadow-lg border-l-4 border-cyan-500 space-y-2">
        <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
          <span>เรื่อง & ตอนที่กำลังรัน</span>
          <span class="text-cyan-400 text-base">📌</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="metricStory" class="text-2xl font-bold text-white mono">Story 26</span>
          <span id="metricEp" class="text-sm font-semibold text-cyan-300 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-700/50">EP02</span>
        </div>
        <p class="text-xs text-slate-400 pt-1">
          Aspect Ratio: <span class="text-slate-200 font-medium mono">9:16 Vertical</span>
        </p>
      </div>
    </div>

    <!-- Active Task Alert Banner (Appears if fixing or generating) -->
    <div id="activeBanner" class="hidden p-4 rounded-xl card-glass border border-amber-500/30 flex items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-3 h-3 rounded-full bg-amber-400 animate-ping"></div>
        <div>
          <span class="text-xs font-bold text-amber-400 uppercase tracking-wider">กำลังดำเนินการ:</span>
          <p id="bannerText" class="text-sm font-medium text-slate-200">กำลังทำงาน...</p>
        </div>
      </div>
      <span class="text-xs text-amber-400/80 font-mono bg-amber-950/40 px-2.5 py-1 rounded border border-amber-800/40">In Progress</span>
    </div>

    <!-- Main Content: Scene Table & Gallery -->
    <div class="card-glass rounded-2xl p-5 shadow-xl space-y-4">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pb-3 border-b border-slate-800">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            📋 รายละเอียดสถานะสตอรี่บอร์ดรายฉาก
            <span id="tableCountBadge" class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 mono">25 ฉาก</span>
          </h2>
          <p class="text-xs text-slate-400">ตรวจสอบขนาดไฟล์ภาพ รูปพรีวิว และตัวละครที่แนบในแต่ละฉาก</p>
        </div>

        <!-- View Filter Buttons -->
        <div class="flex items-center gap-1.5 text-xs bg-slate-900/80 p-1 rounded-lg border border-slate-800">
          <button id="filterAll" onclick="filterScenes('ALL')" class="px-3 py-1 rounded-md bg-slate-800 text-white font-semibold">ทั้งหมด</button>
          <button id="filterDone" onclick="filterScenes('DONE')" class="px-3 py-1 rounded-md text-slate-400 hover:text-white">สำเร็จ (<span id="countDone">0</span>)</button>
          <button id="filterStuck" onclick="filterScenes('STUCK')" class="px-3 py-1 rounded-md text-slate-400 hover:text-rose-400">ติดขัด (<span id="countStuck">0</span>)</button>
        </div>
      </div>

      <!-- Scenes Table -->
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="text-slate-400 uppercase border-b border-slate-800 font-semibold tracking-wider">
              <th class="py-3 px-3">ฉาก</th>
              <th class="py-3 px-3">พรีวิวรูปภาพ</th>
              <th class="py-3 px-3">สถานะ</th>
              <th class="py-3 px-3">ตัวละครที่แนบ (CES)</th>
              <th class="py-3 px-3">ขนาดไฟล์</th>
              <th class="py-3 px-3">รายละเอียดบท / พรอมต์</th>
            </tr>
          </thead>
          <tbody id="scenesTableBody" class="divide-y divide-slate-800/60">
            <tr>
              <td colspan="6" class="text-center py-8 text-slate-500">กำลังโหลดข้อมูลสถานะ...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Live Flow Action Audit Log Box -->
    <div class="card-glass rounded-2xl p-5 shadow-xl space-y-3">
      <div class="flex justify-between items-center pb-2 border-b border-slate-800">
        <h3 class="text-sm font-bold text-slate-300 flex items-center gap-2">
          📟 บันทึกการทำงานสดจาก FlowKit (flow_action_audit.log)
        </h3>
        <span class="text-xs text-slate-500 mono">Auto-tailing 15 entries</span>
      </div>
      <div id="auditLogBox" class="bg-slate-950 p-3 rounded-xl border border-slate-900 mono text-xs text-slate-300 h-44 overflow-y-auto space-y-1">
        <div class="text-slate-500 italic">กำลังอ่านประวัติการทำงาน...</div>
      </div>
    </div>

    <!-- Footer -->
    <footer class="text-center text-xs text-slate-500 py-3">
      ผักกาดการละคร Automated Orchestrator • Status Monitor Service running on Port 8181
    </footer>

  </div>

  <script>
    let currentFilter = 'ALL';
    let cachedScenes = [];

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.error('Error fetching status:', err);
      }
    }

    function renderDashboard(data) {
      const summary = data.summary || {};
      cachedScenes = data.scenes || [];

      // Update Header
      document.getElementById('lastUpdated').innerText = 'อัปเดต: ' + (summary.last_updated ? summary.last_updated.split(' ')[1] : '--:--:--');

      // Update KPI 1
      const created = summary.total_created || 0;
      const expected = summary.total_expected || 0;
      const percent = summary.percent_completed || 0;
      document.getElementById('metricCreated').innerText = created;
      document.getElementById('metricExpected').innerText = expected;
      document.getElementById('metricPercent').innerText = percent + '% สำเร็จ';
      document.getElementById('metricProgressBar').style.width = percent + '%';
      document.getElementById('metricDoneText').innerText = summary.is_all_done ? '🎉 ครบ 100%' : 'กำลังดำเนินการ';

      // Update KPI 2 (ติดกี่อัน)
      const stuck = summary.stuck_count || 0;
      document.getElementById('metricStuck').innerText = stuck;
      const stuckDesc = document.getElementById('metricStuckDesc');
      if (stuck === 0) {
        stuckDesc.innerText = '✅ ไม่มีฉากติดขัด ทุกภาพสมบูรณ์ 100%';
        stuckDesc.className = 'text-xs text-emerald-400 font-medium pt-1';
      } else {
        stuckDesc.innerText = `⚠️ มี ${stuck} ฉากที่ต้องการการแก้ไข`;
        stuckDesc.className = 'text-xs text-rose-400 font-semibold pt-1';
      }

      // Update KPI 3 (กำลังแก้อันไหน)
      const fixing = summary.fixing_scene;
      const currentSc = summary.current_scene;
      const fixingEl = document.getElementById('metricFixing');
      const actionEl = document.getElementById('metricAction');

      if (fixing) {
        fixingEl.innerText = `ฉาก ${String(fixing).padStart(2, '0')}`;
        fixingEl.className = 'text-lg md:text-xl font-bold text-amber-300';
      } else if (currentSc) {
        fixingEl.innerText = `ฉาก ${String(currentSc).padStart(2, '0')}`;
        fixingEl.className = 'text-lg md:text-xl font-bold text-cyan-300';
      } else {
        fixingEl.innerText = summary.is_all_done ? 'ครบแล้ว (สแตนด์บาย)' : 'ไม่มีค้าง';
        fixingEl.className = 'text-lg md:text-xl font-bold text-slate-300';
      }
      actionEl.innerText = summary.current_action || 'พร้อมทำงาน';

      // Update KPI 4
      document.getElementById('metricStory').innerText = 'Story ' + (data.story || 26);
      document.getElementById('metricEp').innerText = data.ep || 'EP02';

      // Update Active Banner
      const banner = document.getElementById('activeBanner');
      if (summary.current_status === 'RUNNING' || summary.current_status === 'FIXING') {
        banner.classList.remove('hidden');
        document.getElementById('bannerText').innerText = summary.current_action;
      } else {
        banner.classList.add('hidden');
      }

      // Update Counts for Filter
      const doneCount = cachedScenes.filter(s => s.status === 'DONE').length;
      const stuckCount = cachedScenes.filter(s => s.status !== 'DONE').length;
      document.getElementById('countDone').innerText = doneCount;
      document.getElementById('countStuck').innerText = stuckCount;
      document.getElementById('tableCountBadge').innerText = `${cachedScenes.length} ฉาก`;

      // Render Scene Table
      renderTable();

      // Render Audit Log
      renderLogs(data.recent_logs || []);
    }

    function filterScenes(f) {
      currentFilter = f;
      document.getElementById('filterAll').className = f === 'ALL' ? 'px-3 py-1 rounded-md bg-slate-800 text-white font-semibold' : 'px-3 py-1 rounded-md text-slate-400 hover:text-white';
      document.getElementById('filterDone').className = f === 'DONE' ? 'px-3 py-1 rounded-md bg-slate-800 text-emerald-400 font-semibold' : 'px-3 py-1 rounded-md text-slate-400 hover:text-white';
      document.getElementById('filterStuck').className = f === 'STUCK' ? 'px-3 py-1 rounded-md bg-slate-800 text-rose-400 font-semibold' : 'px-3 py-1 rounded-md text-slate-400 hover:text-rose-400';
      renderTable();
    }

    function renderTable() {
      const tbody = document.getElementById('scenesTableBody');
      const filtered = cachedScenes.filter(s => {
        if (currentFilter === 'DONE') return s.status === 'DONE';
        if (currentFilter === 'STUCK') return s.status !== 'DONE';
        return true;
      });

      if (!filtered.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-500">ไม่มีฉากในหมวดนี้</td></tr>`;
        return;
      }

      tbody.innerHTML = filtered.map(s => {
        const isDone = s.status === 'DONE';
        const badgeClass = isDone ? 'badge-done' : 'badge-stuck';
        const badgeText = isDone ? '✅ สำเร็จ' : '⚠️ ยังไม่มีรูป';

        const charBadges = (s.characters || []).map(c => 
          `<span class="inline-block px-2 py-0.5 text-[11px] rounded bg-slate-800 text-slate-300 border border-slate-700 mr-1 mb-1">${c.replace('.png', '')}</span>`
        ).join('') || '<span class="text-slate-600">-</span>';

        const imgThumb = s.has_image ? 
          `<a href="${s.image_url}" target="_blank" class="block w-14 h-24 rounded-lg overflow-hidden border border-slate-700 bg-slate-900 hover:scale-105 transition-transform shadow">
            <img src="${s.image_url}" loading="lazy" class="w-full h-full object-cover">
          </a>` : 
          `<div class="w-14 h-24 rounded-lg border border-dashed border-slate-800 bg-slate-950 flex items-center justify-center text-slate-600 text-[10px]">No Pic</div>`;

        return `
          <tr class="hover:bg-slate-900/40 transition">
            <td class="py-3 px-3 font-bold mono text-sm text-slate-200">
              #${s.scene_str}
            </td>
            <td class="py-3 px-3">
              ${imgThumb}
            </td>
            <td class="py-3 px-3">
              <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${badgeClass}">
                ${badgeText}
              </span>
              ${s.mtime ? `<div class="text-[11px] text-slate-500 mono mt-1">${s.mtime}</div>` : ''}
            </td>
            <td class="py-3 px-3 max-w-xs">
              ${charBadges}
            </td>
            <td class="py-3 px-3 mono text-slate-300">
              ${s.size_kb > 0 ? `${s.size_kb} KB` : '<span class="text-slate-600">-</span>'}
            </td>
            <td class="py-3 px-3 text-slate-400 max-w-md text-xs leading-relaxed">
              <div class="line-clamp-2" title="${s.prompt_preview}">
                ${s.prompt_preview || 'ไม่มีข้อมูลบท'}
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }

    function renderLogs(logs) {
      const box = document.getElementById('auditLogBox');
      if (!logs || !logs.length) {
        box.innerHTML = '<div class="text-slate-500 italic">ไม่มีบันทึกเหตุการณ์</div>';
        return;
      }
      box.innerHTML = logs.map(l => {
        let colorClass = 'text-slate-300';
        if (l.includes('[PASS]') || l.includes('[SUCCESS]')) colorClass = 'text-emerald-400';
        else if (l.includes('[ERROR]') || l.includes('[FAIL]') || l.includes('failed')) colorClass = 'text-rose-400';
        else if (l.includes('[SUBMIT_START]') || l.includes('[BEGIN]')) colorClass = 'text-cyan-400';
        return `<div class="${colorClass}">${escapeHtml(l)}</div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    }

    function escapeHtml(str) {
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Auto-refresh every 2.5 seconds
    fetchStatus();
    setInterval(fetchStatus, 2500);
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
