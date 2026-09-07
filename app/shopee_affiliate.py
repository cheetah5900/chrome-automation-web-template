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

def clean_search_keyword(raw_text: str) -> str:
    """Extract clean product search keyword by removing file extensions, numbers and dashes."""
    import re
    s = (raw_text or "").strip()
    s = re.sub(r"\.[^.]+$", "", s)
    s = re.sub(r"^\d+\s*[-_–.]*\s*", "", s).strip()
    return s

def step_1_open_shopee_page(driver, page_url: str = "") -> bool:
    """Step 1: Open Shopee Affiliate Platform / Product Offer URL."""
    url = page_url.strip() if page_url else "https://affiliate.shopee.co.th/offer/product_offer"
    if "offer/product_offer" not in url and url.endswith("shopee.co.th"):
        url = "https://affiliate.shopee.co.th/offer/product_offer"
    
    current = driver.current_url or ""
    if "offer/product_offer" in current:
        log("[Shopee Step 1] อยู่ที่หน้าข้อเสนอผลิตภัณฑ์ Shopee Affiliate อยู่แล้ว")
        return True

    log(f"[Shopee Step 1] กำลังเปิดหน้าเว็บ Shopee: {url}")
    driver.get(url)
    time.sleep(2.0)
    return True

def step_2_search_product(driver, keyword: str) -> bool:
    """Step 2: Enter clean keyword into search box and submit."""
    clean_kw = clean_search_keyword(keyword)
    if not clean_kw:
        log("[Shopee Step 2] ⚠️ ไม่พบคีย์เวิร์ดสำหรับค้นหา (ข้ามขั้นตอน)")
        return False

    log(f"[Shopee Step 2] 🔍 กำลังค้นหาสินค้าด้วยคำค้น: '{clean_kw}'...")
    
    res = driver.execute_script("""
        const kw = arguments[0];
        const inputs = Array.from(document.querySelectorAll('input'));
        const searchInput = inputs.find(i => 
            (i.placeholder && (i.placeholder.includes('ค้นหาสินค้า') || i.placeholder.includes('ค้นหา'))) ||
            i.classList.contains('ant-input-lg')
        );
        if (!searchInput) return { success: false, reason: "Search input not found" };
        
        searchInput.focus();
        searchInput.click();
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        nativeSetter.call(searchInput, kw);
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
        
        const allDivs = Array.from(document.querySelectorAll('div, button, span'));
        const searchBtn = allDivs.find(el => 
            el.children.length === 0 && 
            el.textContent.trim() === 'ค้นหา' && 
            el.getBoundingClientRect().width > 0
        );
        if (searchBtn) {
            searchBtn.click();
            return { success: true, method: "search_btn", value: kw };
        } else {
            searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            searchInput.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            searchInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            return { success: true, method: "enter_key", value: kw };
        }
    """, clean_kw)
    
    if not res or not res.get("success"):
        try:
            input_el = driver.find_element(By.CSS_SELECTOR, "input.ant-input-lg, input[placeholder*='ค้นหา']")
            input_el.send_keys(Keys.ENTER)
        except Exception:
            pass
            
    time.sleep(2.5)
    log(f"[Shopee Step 2] ✅ ค้นหาคำว่า '{clean_kw}' เรียบร้อยแล้ว")
    return True

def step_3_sort_best_sellers(driver) -> bool:
    """Step 3: Click 'ขายดี' (Best Seller) tab."""
    log("[Shopee Step 3] 📈 กำลังเลือกจัดเรียงตาม 'ขายดี'...")
    res = driver.execute_script("""
        const spans = Array.from(document.querySelectorAll('span, div, button, a'));
        const target = spans.find(el => 
            el.children.length === 0 && 
            el.textContent.trim() === 'ขายดี' && 
            el.getBoundingClientRect().width > 0
        );
        if (target) {
            target.click();
            if (target.parentElement) target.parentElement.click();
            return { success: true, text: target.textContent.trim() };
        }
        return { success: false, reason: "Element 'ขายดี' not found" };
    """)
    time.sleep(3.0)
    if res and res.get("success"):
        log("[Shopee Step 3] ✅ คลิกแท็บ 'ขายดี' สำเร็จ")
        return True
    log("[Shopee Step 3] ⚠️ ไม่พบปุ่ม 'ขายดี' (อาจอยู่ในหน้านี้แล้วหรือโหลดไม่ทัน)")
    return False

def step_4_highlight_and_reorder_top3(driver) -> dict[str, Any]:
    """Step 4: Highlight top 3 commission items among first 10 cards and move to slots 1-3."""
    log("[Shopee Step 4] 🏆 ไฮไลต์และจัดลำดับสินค้าค่าคอมสูงสุด 3 อันดับแรก...")
    res = driver.execute_script("""
        document.querySelectorAll('.top-commission-badge').forEach(b => b.remove());
        document.querySelectorAll('.product-offer-item').forEach(card => {
            card.style.border = '';
            card.style.boxShadow = '';
            card.style.transform = '';
            card.style.zIndex = '';
            card.style.position = '';
        });
        
        const list = document.querySelector('.product-offer-list');
        if (!list) return { success: false, reason: "Container .product-offer-list not found" };
        
        const allCards = Array.from(list.querySelectorAll('.product-offer-item'));
        if (allCards.length === 0) return { success: false, reason: "No product cards found" };
        
        const first10 = allCards.slice(0, 10);
        const parsed = first10.map((card, idx) => {
            const text = card.innerText || '';
            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
            let commRate = 0;
            for (const line of lines) {
                if (line.includes('คอมมิชชัน') || line.includes('คอมมิชชั่น') || line.includes('%')) {
                    const match = line.match(/([0-9]+(?:\\.[0-9]+)?)\\s*%/);
                    if (match) {
                        const val = parseFloat(match[1]);
                        if (line.includes('คอมมิชชัน') || line.includes('คอมมิชชั่น') || val > commRate) {
                            commRate = val;
                        }
                    }
                }
            }
            return { card, commRate, idx };
        });
        
        parsed.sort((a, b) => b.commRate - a.commRate);
        const top3 = parsed.slice(0, 3);
        
        const colors = [
            { border: '#f59e0b', shadow: 'rgba(245, 158, 11, 0.5)', badge: 'linear-gradient(135deg, #f59e0b, #ef4444)' },
            { border: '#ec4899', shadow: 'rgba(236, 72, 153, 0.5)', badge: 'linear-gradient(135deg, #ec4899, #8b5cf6)' },
            { border: '#3b82f6', shadow: 'rgba(59, 130, 246, 0.5)', badge: 'linear-gradient(135deg, #3b82f6, #06b6d4)' }
        ];
        
        top3.forEach((item, rIdx) => {
            const rank = rIdx + 1;
            const card = item.card;
            const c = colors[rIdx] || colors[0];
            
            card.style.position = 'relative';
            card.style.border = `2.5px solid ${c.border}`;
            card.style.boxShadow = `0 8px 24px ${c.shadow}`;
            card.style.borderRadius = '14px';
            card.style.zIndex = '10';
            
            const badge = document.createElement('div');
            badge.className = 'top-commission-badge';
            badge.style.position = 'absolute';
            badge.style.top = '-12px';
            badge.style.left = '12px';
            badge.style.background = c.badge;
            badge.style.color = '#fff';
            badge.style.fontSize = '12px';
            badge.style.fontWeight = 'bold';
            badge.style.padding = '4px 12px';
            badge.style.borderRadius = '20px';
            badge.style.zIndex = '20';
            badge.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
            badge.innerText = `🔥 ค่าคอมอันดับ ${rank} (${item.commRate}%)`;
            card.appendChild(badge);
        });
        
        if (top3.length >= 3) list.prepend(top3[2].card);
        if (top3.length >= 2) list.prepend(top3[1].card);
        if (top3.length >= 1) list.prepend(top3[0].card);
        
        list.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return { success: true, count: top3.length, topRates: top3.map(t => t.commRate) };
    """)
    if res and res.get("success"):
        log(f"[Shopee Step 4] ✅ จัดเรียงและไฮไลต์สำเร็จ (Top Rates: {res.get('topRates')}%)")
    else:
        log(f"[Shopee Step 4] ⚠️ ไม่สามารถไฮไลต์การ์ดสินค้าได้: {res}")
    return res or {}

def post_single_shopee_item(
    driver,
    item: dict[str, Any],
    page_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """Process a single Shopee Affiliate item: search keyword without number, sort, and highlight top 3."""
    raw_keyword = item.get("keyword") or item.get("file_name") or item.get("subfolder_name") or ""
    keyword = clean_search_keyword(raw_keyword)
    name = f"#{item.get('number', item_idx)} {keyword}"

    msg = f"[{item_idx}/{total_items}] กำลังค้นหาสินค้า Shopee: {name}"
    log(f"[Shopee Affiliate] {msg}")
    if progress_callback:
        progress_callback({
            "current": item_idx,
            "total": total_items,
            "percent": int(((item_idx - 1) / max(total_items, 1)) * 100),
            "message": msg
        })

    # Step 1: Open Shopee Product Offer Page
    step_1_open_shopee_page(driver, page_url)
    if is_shopee_stopped():
        return False

    # Step 2: Search keyword (clean without numbers)
    step_2_search_product(driver, keyword)
    if is_shopee_stopped():
        return False

    # Step 3: Sort by 'ขายดี'
    step_3_sort_best_sellers(driver)
    if is_shopee_stopped():
        return False

    # Step 4: Highlight top 3 commission and move to slots 1-3
    step_4_highlight_and_reorder_top3(driver)

    log(f"[Shopee Affiliate] ✅ สำเร็จการค้นหาและจัดลำดับรายการที่ {item_idx}/{total_items}: {name}")
    return True

def run_shopee_affiliate_batch(
    items: list[dict[str, Any]],
    target_url: str = "",
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """Runs a batch of Shopee Affiliate automation tasks."""
    bot = browser_manager.get(target_port=9222)
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
