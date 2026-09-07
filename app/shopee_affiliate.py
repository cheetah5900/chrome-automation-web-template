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

def step_4_select_best_product_and_get_link(driver, target_file_path: str = "", folder_path: str = "") -> dict[str, Any]:
    """Step 4: Select product with highest commission (sales > 10 items, or fallback to lower sales),
    click 'เอาลิงก์', copy affiliate short link, and save it to the product's .md file and Caption.md."""
    log("[Shopee Step 4] 🎯 กำลังวิเคราะห์เลือกสินค้าที่ค่าคอมมิชชั่นสูงสุด (เงื่อนไขยอดขาย > 10 ชิ้น)...")
    
    # 1. Analyze and pick best card
    selection = driver.execute_script("""
        const list = document.querySelector('.product-offer-list');
        if (!list) return { success: false, reason: "Container .product-offer-list not found" };
        const cards = Array.from(list.querySelectorAll('.product-offer-item'));
        if (cards.length === 0) return { success: false, reason: "No product cards found" };

        function parseSales(salesText) {
            if (!salesText) return 0;
            const m = salesText.match(/ขายได้\\s*([0-9]+(?:\\.[0-9]+)?)\\s*(พัน|หมื่น|แสน|ล้าน)?/);
            if (!m) {
                const m2 = salesText.match(/([0-9]+(?:\\.[0-9]+)?)/);
                return m2 ? parseFloat(m2[1]) : 0;
            }
            let val = parseFloat(m[1]);
            const unit = m[2];
            if (unit === "พัน") val *= 1000;
            else if (unit === "หมื่น") val *= 10000;
            else if (unit === "แสน") val *= 100000;
            else if (unit === "ล้าน") val *= 1000000;
            return val;
        }

        function parseComm(lines) {
            let commLine = lines.find(l => l.includes('คอมมิชชัน') || l.includes('คอมมิชชั่น'));
            if (commLine) {
                const m = commLine.match(/([0-9]+(?:\\.[0-9]+)?)\\s*%/);
                if (m) return { rate: parseFloat(m[1]), text: commLine };
            }
            for (const l of lines) {
                if (l.includes('%') && !l.includes('ลด')) {
                    const m = l.match(/([0-9]+(?:\\.[0-9]+)?)\\s*%/);
                    if (m) return { rate: parseFloat(m[1]), text: l };
                }
            }
            return { rate: 0, text: "" };
        }

        const parsed = cards.map((card, idx) => {
            const text = card.innerText || '';
            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
            const salesLine = lines.find(l => l.includes('ขายได้')) || '';
            const commInfo = parseComm(lines);
            const titleLine = lines.find(l => l.length > 15 && !l.includes('฿') && !l.includes('คอมมิชชัน') && !l.includes('ขายได้') && !l.includes('%')) || lines[0] || '';
            const salesCount = parseSales(salesLine);

            return {
                idx: idx,
                card: card,
                title: titleLine,
                salesText: salesLine,
                salesCount: salesCount,
                commText: commInfo.text,
                commRate: commInfo.rate,
                meetsSalesCondition: salesCount > 10
            };
        });

        const qualified = parsed.filter(p => p.meetsSalesCondition);
        let chosen = null;
        if (qualified.length > 0) {
            qualified.sort((a, b) => b.commRate - a.commRate);
            chosen = { ...qualified[0], pool: "qualified (sales > 10)" };
        } else {
            parsed.sort((a, b) => b.commRate - a.commRate);
            chosen = { ...parsed[0], pool: "fallback (highest comm available)" };
        }

        // Highlight chosen card visually on screen
        document.querySelectorAll('.top-commission-badge').forEach(b => b.remove());
        const card = chosen.card;
        card.style.position = 'relative';
        card.style.border = '3px solid #10b981';
        card.style.boxShadow = '0 8px 24px rgba(16, 185, 129, 0.5)';
        card.style.borderRadius = '14px';
        card.style.zIndex = '10';

        const badge = document.createElement('div');
        badge.className = 'top-commission-badge';
        badge.style.position = 'absolute';
        badge.style.top = '-12px';
        badge.style.left = '12px';
        badge.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        badge.style.color = '#fff';
        badge.style.fontSize = '12px';
        badge.style.fontWeight = 'bold';
        badge.style.padding = '4px 12px';
        badge.style.borderRadius = '20px';
        badge.style.zIndex = '20';
        badge.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
        badge.innerText = `⭐ เลือกรายการนี้ (คอม ${chosen.commRate}% | ยอดขาย ${chosen.salesText})`;
        card.appendChild(badge);

        // Click "เอา ลิงก์" button on this chosen card
        const btn = card.querySelector('button.AffiliateItemCard__getlinkBtn, button');
        let clicked = false;
        if (btn) {
            btn.click();
            clicked = true;
        } else {
            const btns = Array.from(card.querySelectorAll('button, a, span, div')).filter(el => 
                (el.innerText || '').replace(/\\s+/g, '') === 'เอาลิงก์'
            );
            if (btns.length > 0) {
                btns[0].click();
                clicked = true;
            }
        }

        return {
            success: true,
            clicked: clicked,
            chosen: {
                idx: chosen.idx,
                title: chosen.title,
                salesText: chosen.salesText,
                salesCount: chosen.salesCount,
                commRate: chosen.commRate,
                pool: chosen.pool
            }
        };
    """)

    if not selection or not selection.get("success"):
        log(f"[Shopee Step 4] ❌ ไม่สามารถเลือกรายการสินค้าได้: {selection}")
        return {"success": False, "error": "selection_failed"}

    chosen_info = selection.get("chosen", {})
    log(f"[Shopee Step 4] ⭐ เลือกสินค้า: '{chosen_info.get('title')}' | ค่าคอม: {chosen_info.get('commRate')}% | {chosen_info.get('salesText')} ({chosen_info.get('pool')})")

    # 2. Wait for modal & extract affiliate short link
    time.sleep(1.5)
    affiliate_link = ""
    for _ in range(12):
        affiliate_link = driver.execute_script("""
            const els = Array.from(document.querySelectorAll('.ant-modal textarea, .ant-modal input, textarea, input'));
            for (const el of els) {
                if (el.value && (el.value.includes('https://s.shopee.co.th') || el.value.includes('shopee.co.th'))) {
                    return el.value.trim();
                }
            }
            return "";
        """)
        if affiliate_link:
            break
        time.sleep(0.4)

    # Click copy button inside modal
    driver.execute_script("""
        const copyBtn = document.querySelector('.ant-modal button.ant-btn-primary');
        if (copyBtn && !copyBtn.disabled) copyBtn.click();
    """)
    time.sleep(0.3)

    # Dismiss any browser alert (e.g. Copy to clipboard)
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except Exception:
        pass

    # Close modal
    driver.execute_script("document.querySelector('.ant-modal-close, .ant-modal-close-x')?.click();")

    if not affiliate_link:
        log("[Shopee Step 4] ⚠️ ไม่สามารถดึงลิงก์จาก Modal ได้")
        return {"success": False, "error": "link_not_found", "chosen": chosen_info}

    log(f"[Shopee Step 4] 🔗 คัดลอกลิงก์สำเร็จ: {affiliate_link}")

    # 3. Save affiliate link to target .md file
    saved_files = []
    if target_file_path and os.path.exists(os.path.dirname(target_file_path)):
        try:
            with open(target_file_path, "w", encoding="utf-8") as f:
                f.write(affiliate_link + "\n")
            log(f"[Shopee Step 4] 💾 บันทึกลิงก์ลงไฟล์เป้าหมายเรียบร้อย: {os.path.basename(target_file_path)}")
            saved_files.append(target_file_path)
        except Exception as e:
            log(f"[Shopee Step 4] ⚠️ บันทึกลง {target_file_path} ไม่สำเร็จ: {e}")

    # Also update Caption.md if it exists in the folder
    target_dir = folder_path or (os.path.dirname(target_file_path) if target_file_path else "")
    if target_dir and os.path.exists(target_dir):
        caption_path = os.path.join(target_dir, "Caption.md")
        if os.path.exists(caption_path):
            try:
                with open(caption_path, "r", encoding="utf-8") as cf:
                    c_content = cf.read()
                # Replace placeholder or append
                if "waiting_for_real_affiliate_link" in c_content:
                    c_content = c_content.replace("waiting_for_real_affiliate_link", affiliate_link)
                elif affiliate_link not in c_content:
                    c_content = f"{affiliate_link}\n\n{c_content}"
                with open(caption_path, "w", encoding="utf-8") as cf:
                    cf.write(c_content)
                log("[Shopee Step 4] 💾 อัปเดตลิงก์ใน Caption.md เรียบร้อยแล้ว")
                saved_files.append(caption_path)
            except Exception as e:
                log(f"[Shopee Step 4] ⚠️ อัปเดต Caption.md ไม่สำเร็จ: {e}")

    return {
        "success": True,
        "chosen": chosen_info,
        "affiliate_link": affiliate_link,
        "saved_files": saved_files
    }

def post_single_shopee_item(
    driver,
    item: dict[str, Any],
    page_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """Process a single Shopee Affiliate item: search keyword without number, sort, select best item, and save affiliate link."""
    raw_keyword = item.get("keyword") or item.get("file_name") or item.get("subfolder_name") or ""
    keyword = clean_search_keyword(raw_keyword)
    target_file = item.get("file_path", "")
    folder_path = item.get("folder_path", "")
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

    # Step 4: Select best product (highest commission with sales > 10), get link and save to .md
    res = step_4_select_best_product_and_get_link(driver, target_file_path=target_file, folder_path=folder_path)
    if res.get("affiliate_link"):
        item["product_link"] = res["affiliate_link"]

    log(f"[Shopee Affiliate] ✅ สำเร็จการค้นหาและดึงลิงก์รายการที่ {item_idx}/{total_items}: {name} (ลิงก์: {res.get('affiliate_link', '-')})")
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
