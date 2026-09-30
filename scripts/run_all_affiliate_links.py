import sys
import os
import re
import time
import random
import glob

# Add template repo to path
sys.path.insert(0, "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template")
from app.browser import browser_manager
from app.shopee_affiliate import (
    reset_shopee_stop, apply_stealth_cdp, post_single_shopee_item, is_shopee_stopped
)

BASE_DIR = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย"

STORIES_CONFIG = [
    ("21", [1, 2, 3]),
    ("22", [1, 2, 3]),
    ("23", [1, 2, 3]),
    ("24", [1, 2, 3]),
    ("25", [1, 2, 3]),
    ("26", [1, 2, 3]),
    ("27", [1, 2, 3]),
    ("28", [1, 2, 3]),
    ("29", [1, 2, 3]),
]

def get_tasks():
    tasks = []
    for story_id, eps in STORIES_CONFIG:
        aff_dir = os.path.join(BASE_DIR, story_id, "8 - Affiliate")
        for ep in eps:
            target_link_file = os.path.join(aff_dir, f"ep{ep} - affiliate link.md")
            
            # Check if already done
            already_done = False
            existing_link = ""
            if os.path.exists(target_link_file):
                with open(target_link_file, "r", encoding="utf-8") as f:
                    c = f.read().strip()
                if c.startswith("http"):
                    already_done = True
                    existing_link = c
            
            # Find product keyword
            prod_files = [f for f in glob.glob(os.path.join(aff_dir, f"ep{ep} - *.md")) if "affiliate link" not in f]
            keyword = ""
            if prod_files:
                basename = os.path.basename(prod_files[0])
                kw_match = re.search(r"ep\d+\s*-\s*(.+)\.md", basename)
                if kw_match:
                    keyword = kw_match.group(1).strip()
            
            tasks.append({
                "story": story_id,
                "ep": ep,
                "keyword": keyword,
                "target_file": target_link_file,
                "folder_path": aff_dir,
                "already_done": already_done,
                "existing_link": existing_link
            })
    return tasks

def main():
    tasks = get_tasks()
    todo_tasks = [t for t in tasks if not t["already_done"]]
    print(f"Total tasks: {len(tasks)}, Already completed: {len(tasks) - len(todo_tasks)}, Remaining to do: {len(todo_tasks)}")
    
    if not todo_tasks:
        print("All affiliate links are already generated!")
        return

    print("Connecting to Chrome on port 9222...")
    reset_shopee_stop()
    bot = browser_manager.get(target_port=9222)
    driver = bot.driver
    apply_stealth_cdp(driver)

    success_count = 0
    errors = []

    for idx, t in enumerate(todo_tasks, 1):
        if is_shopee_stopped():
            print("Stop requested. Aborting.")
            break

        story = t["story"]
        ep = t["ep"]
        kw = t["keyword"]
        target_file = t["target_file"]
        folder_path = t["folder_path"]

        print(f"\n=======================================================")
        print(f"[{idx}/{len(todo_tasks)}] Story {story} EP{ep}: '{kw}'")
        print(f"=======================================================")

        item = {
            "keyword": kw,
            "file_path": target_file,
            "folder_path": folder_path,
            "number": ep
        }

        try:
            ok = post_single_shopee_item(
                driver=driver,
                item=item,
                page_url="https://affiliate.shopee.co.th/offer/product_offer",
                item_idx=idx,
                total_items=len(todo_tasks)
            )

            aff_link = item.get("affiliate_link", "")
            prod_link = item.get("product_link", "")

            if aff_link:
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(aff_link + "\n")
                print(f"✅ [SUCCESS] Story {story} EP{ep}: Saved '{aff_link}' into {target_file}")
                success_count += 1
            else:
                print(f"⚠️ [WARNING] No affiliate link returned for Story {story} EP{ep} ('{kw}')")
                errors.append(f"Story {story} EP{ep} ('{kw}'): No affiliate link")

            # Human-like delay between items (4.0s - 7.0s)
            if idx < len(todo_tasks):
                delay = round(random.uniform(4.0, 7.0), 1)
                print(f"⏳ Waiting {delay}s before next item...")
                time.sleep(delay)

        except Exception as e:
            print(f"❌ [ERROR] Story {story} EP{ep} ('{kw}'): {e}")
            errors.append(f"Story {story} EP{ep} ('{kw}'): {str(e)}")

    print(f"\n=======================================================")
    print(f"BATCH FINISHED: Successfully generated {success_count}/{len(todo_tasks)} links!")
    if errors:
        print(f"Errors encountered ({len(errors)}):")
        for err in errors:
            print(f" - {err}")
    print(f"=======================================================")

if __name__ == "__main__":
    main()
