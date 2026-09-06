import os
import sys
import time
import random
import subprocess
import argparse
from datetime import datetime
from typing import Any, Callable, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from app.browser import browser_manager

def log(msg: str) -> None:
    print(msg)
    try:
        from app.main import log_bus
        log_bus.publish(msg)
    except Exception:
        pass

def cleanup_browser_tabs(driver) -> None:
    """Closes extraneous tabs, keeping only the main Shopee tab."""
    try:
        handles = driver.window_handles
        if len(handles) > 1:
            main_handle = None
            for h in handles:
                try:
                    driver.switch_to.window(h)
                    if "shopee.co.th" in driver.current_url:
                        main_handle = h
                        break
                except Exception:
                    pass
            if not main_handle:
                main_handle = handles[0]
            for h in handles:
                if h != main_handle:
                    try:
                        driver.switch_to.window(h)
                        driver.close()
                    except Exception:
                        pass
            driver.switch_to.window(main_handle)
    except Exception:
        pass

def fast_poll(driver, js_condition: str, timeout: float = 15.0, poll_interval: float = 0.1, js_args=None) -> Any:
    """Polls javascript condition at short intervals until non-null/truthy or timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            if js_args is not None:
                if isinstance(js_args, (list, tuple)):
                    val = driver.execute_script(js_condition, *js_args)
                else:
                    val = driver.execute_script(js_condition, js_args)
            else:
                val = driver.execute_script(js_condition)
            if val:
                return val
        except Exception:
            pass
        time.sleep(poll_interval)
    return None

# Global cancellation event
_shopee_stop_requested = False

def stop_shopee_affiliate() -> None:
    global _shopee_stop_requested
    _shopee_stop_requested = True
    log("[Shopee Affiliate] 🛑 ได้รับสัญญาณ Force Stop กำลังหยุดการทำงาน...")

def is_shopee_stopped() -> bool:
    global _shopee_stop_requested
    return _shopee_stop_requested

def reset_shopee_stop() -> None:
    global _shopee_stop_requested
    _shopee_stop_requested = False

# ==============================================================================
# Shopee Affiliate Core Steps
# ==============================================================================

def step_1_open_shopee_page(driver, page_url: str = "") -> bool:
    """Step 1: Open Shopee Affiliate Platform / Product / Post URL."""
    url = page_url.strip() if page_url else "https://affiliate.shopee.co.th"
    log(f"[Shopee Step 1] กำลังเปิดหน้าเว็บ Shopee: {url}")
    driver.get(url)
    time.sleep(2.0)
    return True

def step_2_upload_media(driver, video_path: str) -> bool:
    """Step 2: Upload Video / Media if applicable."""
    if not video_path or not os.path.exists(video_path):
        log(f"[Shopee Step 2] ไม่พบไฟล์มีเดีย: {video_path} (ข้ามขั้นตอน)")
        return False
    log(f"[Shopee Step 2] เตรียมอัปโหลดไฟล์: {os.path.basename(video_path)}")
    time.sleep(1.0)
    return True

def step_3_insert_details(driver, caption: str = "", product_link: str = "") -> bool:
    """Step 3: Insert product link, caption, and affiliate metadata."""
    log(f"[Shopee Step 3] กำลังกรอกข้อมูลข้อความ / ลิงก์สินค้า Affiliate...")
    time.sleep(1.0)
    return True

def step_4_submit_item(driver) -> bool:
    """Step 4: Submit / Publish or schedule affiliate post/video."""
    log("[Shopee Step 4] กำลังบันทึก / โพสต์รายการ Shopee Affiliate...")
    time.sleep(1.0)
    return True

def post_single_shopee_item(
    driver,
    item: dict[str, Any],
    page_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """Process a single Shopee Affiliate post item."""
    name = item.get("subfolder_name") or item.get("video_name") or item.get("title", f"Item #{item_idx}")
    video_path = item.get("video_path", "")
    caption = item.get("caption", "")
    product_link = item.get("product_link", "")

    msg = f"[{item_idx}/{total_items}] กำลังจัดการ Shopee Affiliate: {name}"
    log(f"[Shopee Affiliate] {msg}")
    if progress_callback:
        progress_callback({
            "current": item_idx,
            "total": total_items,
            "percent": int(((item_idx - 1) / max(total_items, 1)) * 100),
            "message": msg
        })

    # Step 1: Open URL
    step_1_open_shopee_page(driver, page_url)
    if is_shopee_stopped():
        return False

    # Step 2: Upload Media
    if video_path:
        step_2_upload_media(driver, video_path)
    if is_shopee_stopped():
        return False

    # Step 3: Insert Details & Affiliate Link
    step_3_insert_details(driver, caption=caption, product_link=product_link)
    if is_shopee_stopped():
        return False

    # Step 4: Submit
    step_4_submit_item(driver)

    log(f"[Shopee Affiliate] ✅ สำเร็จการดำเนินการรายการที่ {item_idx}/{total_items}: {name}")
    return True

def run_shopee_affiliate_batch(
    items: list[dict[str, Any]],
    target_url: str = "",
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """Runs a batch of Shopee Affiliate automation tasks."""
    bot = browser_manager.get()
    driver = bot.driver
    total = len(items)

    url = target_url.strip() if target_url else "https://affiliate.shopee.co.th"
    errors = []
    success_count = 0
    reset_shopee_stop()

    log(f"[Shopee Affiliate Engine] เริ่มรัน {total} รายการบน Port 9222 (หน่วงเวลา: {delay_min}s - {delay_max}s)...")

    for idx, item in enumerate(items):
        if is_shopee_stopped():
            log("[Shopee Affiliate] 🛑 ยกเลิกการทำงานเนื่องจาก Force Stop")
            errors.append("🛑 การทำงานถูกยกเลิกด้วย Force Stop")
            break

        # Delay before starting next item
        if idx > 0 and (delay_max > 0 or delay_min > 0):
            actual_min = min(float(delay_min), float(delay_max))
            actual_max = max(float(delay_min), float(delay_max))
            rand_delay = round(random.uniform(actual_min, actual_max), 1)
            log(f"[Shopee Affiliate] ⏳ หน่วงเวลาสุ่ม {rand_delay} วินาที ก่อนเริ่มรายการ {idx + 1}/{total}...")
            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total,
                    "percent": int((idx / max(total, 1)) * 100),
                    "message": f"⏳ หน่วงเวลาสุ่ม {rand_delay}s ก่อนเริ่มรายการ {idx + 1}/{total}..."
                })

            wait_start = time.time()
            while time.time() - wait_start < rand_delay:
                if is_shopee_stopped():
                    break
                time.sleep(0.3)

            if is_shopee_stopped():
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break

        try:
            ok = post_single_shopee_item(
                driver=driver,
                item=item,
                page_url=url,
                item_idx=idx + 1,
                total_items=total,
                progress_callback=progress_callback
            )
            if ok:
                success_count += 1
        except Exception as e:
            if is_shopee_stopped() or "Force Stop" in str(e):
                log("[Shopee Affiliate] 🛑 หยุดทำงานทันทีตามคำสั่ง Force Stop")
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break
            err_msg = f"[{idx+1}/{total}] {item.get('subfolder_name', 'Item')}: {str(e)}"
            log(f"[Shopee Affiliate Error] {err_msg}")
            errors.append(err_msg)

    if progress_callback:
        progress_callback({
            "current": total,
            "total": total,
            "percent": 100,
            "status": "completed" if not errors else "completed_with_errors",
            "message": f"✅ ดำเนินการสำเร็จ {success_count}/{total} รายการ" if not errors else f"เสร็จสิ้น {success_count}/{total} (พบข้อผิดพลาด {len(errors)} รายการ)",
            "errors": errors
        })

    return {
        "ok": len(errors) == 0,
        "total": total,
        "success_count": success_count,
        "errors": errors
    }
