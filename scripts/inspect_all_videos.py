import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from flow_video_generator import inspect_tab_js, DEFAULT_API_BASE

code = """(() => {
    const videoTiles = Array.from(document.querySelectorAll("flow-video-tile, [class*=\\"video-tile\\"]"));
    return videoTiles.map((vt, idx) => {
        const img = vt.querySelector("img.thumbnail, img");
        const footer = vt.querySelector(".footer-title");
        let mid = null;
        if (img && img.src) {
            const m = img.src.match(/\\/image\\/([0-9a-fA-F-]+)/);
            if (m) mid = m[1];
        }
        return {
            index: idx,
            media_id: mid,
            footer_title: footer ? footer.innerText.replace(/\\s+/g, " ").trim() : "",
        };
    });
})()"""

tiles = inspect_tab_js(DEFAULT_API_BASE, code)
print(f"Total video tiles found: {len(tiles)}")
for t in tiles:
    idx = t["index"]
    mid = t["media_id"]
    title = t["footer_title"]
    print(f"[{idx:02d}] id={mid} | title='{title}'")
