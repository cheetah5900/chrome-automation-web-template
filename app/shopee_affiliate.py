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

class ForceStopException(Exception):
    """Raised immediately when a Force Stop signal is received."""
    pass

def stop_shopee_affiliate() -> None:
    global _shopee_stop_requested
    _shopee_stop_requested = True
    log("[Shopee Affiliate] 🛑 ได้รับสัญญาณ Force Stop กำลังหยุดการทำงาน...")

def is_shopee_stopped() -> bool:
    global _shopee_stop_requested
    return _shopee_stop_requested

def check_stop() -> None:
    """Raise ForceStopException immediately if stop was requested."""
    if is_shopee_stopped():
        raise ForceStopException("🛑 บังคับหยุดทำงาน (Force Stop)")

def interruptible_sleep(duration: float, step: float = 0.1) -> None:
    """Sleeps for duration seconds in small increments, raising ForceStopException if stopped."""
    check_stop()
    start_time = time.time()
    while time.time() - start_time < duration:
        check_stop()
        time.sleep(min(step, max(0.01, duration - (time.time() - start_time))))
    check_stop()

def reset_shopee_stop() -> None:
    global _shopee_stop_requested
    _shopee_stop_requested = False

def human_delay(min_sec: float = 1.5, max_sec: float = 3.5) -> None:
    """Sleep for a randomized duration between min_sec and max_sec while respecting stop requests."""
    import random
    duration = random.uniform(min_sec, max_sec)
    interruptible_sleep(duration)

def apply_stealth_cdp(driver) -> None:
    """Inject CDP stealth script to mask navigator.webdriver and common automation signatures."""
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                try {
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                } catch (e) {}
                try {
                    window.chrome = window.chrome || {};
                    window.chrome.runtime = window.chrome.runtime || {};
                    window.chrome.loadTimes = window.chrome.loadTimes || function() {};
                    window.chrome.csi = window.chrome.csi || function() {};
                    window.chrome.app = window.chrome.app || {};
                } catch (e) {}
                try {
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['th-TH', 'th', 'en-US', 'en']
                    });
                } catch (e) {}
                try {
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                } catch (e) {}
            """
        })
    except Exception:
        pass

class ShopeeCaptchaBlockedException(Exception):
    """Raised immediately when Shopee Anti-bot / CAPTCHA verification page is detected."""
    def __init__(self, message: str = "ตรวจพบระบบกันบอท Shopee (CAPTCHA / Traffic Verification)", captcha_url: str = ""):
        super().__init__(message)
        self.captcha_url = captcha_url

def is_shopee_captcha_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return (
        "verify/captcha" in u or
        "verify/traffic" in u or
        "anti_bot_tracking_id" in u or
        ("shopee.co.th/verify" in u)
    )

def check_shopee_captcha(driver) -> None:
    """Checks if the current active tab or any window is stuck on Shopee CAPTCHA / Traffic verification."""
    check_stop()
    try:
        current_url = getattr(driver, "current_url", "") or ""
        if is_shopee_captcha_url(current_url):
            log(f"[Shopee Anti-Bot] 🛑 ตรวจพบหน้า CAPTCHA/Traffic Verification: {current_url[:120]}...")
            raise ShopeeCaptchaBlockedException(
                "ตรวจพบระบบกันบอท Shopee (CAPTCHA / Traffic Verification) ระบบหยุดทำงานอัตโนมัติ",
                captcha_url=current_url
            )

        title = (getattr(driver, "title", "") or "").lower()
        if "verify" in title and ("captcha" in title or "traffic" in title or "security" in title):
            raise ShopeeCaptchaBlockedException(
                "ตรวจพบระบบกันบอท Shopee (CAPTCHA) จาก Title หน้าเว็บ",
                captcha_url=current_url
            )
    except ShopeeCaptchaBlockedException:
        raise
    except Exception:
        pass

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
    check_stop()
    apply_stealth_cdp(driver)
    check_shopee_captcha(driver)
    url = page_url.strip() if page_url else "https://affiliate.shopee.co.th/offer/product_offer"
    if "offer/product_offer" not in url and url.endswith("shopee.co.th"):
        url = "https://affiliate.shopee.co.th/offer/product_offer"
    
    current = driver.current_url or ""
    current_base = current.split("?")[0].rstrip("/")
    target_base = url.split("?")[0].rstrip("/")
    if current_base == target_base:
        log("[Shopee Step 1] อยู่ที่หน้าข้อเสนอผลิตภัณฑ์ Shopee Affiliate อยู่แล้ว")
        check_shopee_captcha(driver)
        return True

    log(f"[Shopee Step 1] กำลังเปิดหน้าเว็บ Shopee: {url}")
    driver.get(url)
    human_delay(2.2, 3.8)
    check_shopee_captcha(driver)
    return True

def step_2_search_product(driver, keyword: str) -> bool:
    """Step 2: Enter clean keyword into search box and submit with human-like typing simulation."""
    check_stop()
    check_shopee_captcha(driver)
    clean_kw = clean_search_keyword(keyword)
    if not clean_kw:
        log("[Shopee Step 2] ⚠️ ไม่พบคีย์เวิร์ดสำหรับค้นหา (ข้ามขั้นตอน)")
        return False

    log(f"[Shopee Step 2] 🔍 กำลังพิมพ์ค้นหาสินค้า: '{clean_kw}'...")
    
    # 1. Click search input to focus and clear old value
    driver.execute_script("""
        const inputs = Array.from(document.querySelectorAll('input'));
        const searchInput = inputs.find(i => 
            (i.placeholder && (i.placeholder.includes('ค้นหาสินค้า') || i.placeholder.includes('ค้นหา'))) ||
            i.classList.contains('ant-input-lg')
        );
        if (searchInput) {
            searchInput.focus();
            searchInput.click();
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeSetter.call(searchInput, '');
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
    """)
    human_delay(0.4, 0.8)

    # 2. Enter keyword simulating input event
    res = driver.execute_script("""
        const kw = arguments[0];
        const inputs = Array.from(document.querySelectorAll('input'));
        const searchInput = inputs.find(i => 
            (i.placeholder && (i.placeholder.includes('ค้นหาสินค้า') || i.placeholder.includes('ค้นหา'))) ||
            i.classList.contains('ant-input-lg')
        );
        if (!searchInput) return { success: false, reason: "Search input not found" };
        
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        nativeSetter.call(searchInput, kw);
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
        return { success: true };
    """, clean_kw)
    
    human_delay(0.6, 1.2)

    # 3. Click search button or trigger enter key
    driver.execute_script("""
        const inputs = Array.from(document.querySelectorAll('input'));
        const searchInput = inputs.find(i => 
            (i.placeholder && (i.placeholder.includes('ค้นหาสินค้า') || i.placeholder.includes('ค้นหา'))) ||
            i.classList.contains('ant-input-lg')
        );
        const allDivs = Array.from(document.querySelectorAll('div, button, span'));
        const searchBtn = allDivs.find(el => 
            el.children.length === 0 && 
            el.textContent.trim() === 'ค้นหา' && 
            el.getBoundingClientRect().width > 0
        );
        if (searchBtn) {
            searchBtn.click();
        } else if (searchInput) {
            searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            searchInput.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            searchInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        }
    """)
            
    human_delay(2.5, 4.0)
    check_shopee_captcha(driver)
    log(f"[Shopee Step 2] ✅ ค้นหาคำว่า '{clean_kw}' เรียบร้อยแล้ว")
    return True

def check_shopee_no_data(driver) -> bool:
    """Check if the search result page shows 'ไม่มีข้อมูล' or has zero product cards."""
    check_stop()
    check_shopee_captcha(driver)
    try:
        res = driver.execute_script("""
            const hasEmptyEl = !!document.querySelector('.empty, .ant-empty, [class*="empty"], [class*="nodata"]');
            const hasEmptyText = document.body && document.body.innerText ? document.body.innerText.includes('ไม่มีข้อมูล') : false;
            const cards = document.querySelectorAll('.product-offer-item, .AffiliateItemCard');
            return {
                noData: (hasEmptyEl || hasEmptyText) && cards.length === 0,
                cardsCount: cards.length
            };
        """)
        if res and res.get("noData"):
            return True
    except Exception:
        pass
    return False

def step_3_sort_best_sellers(driver) -> bool:
    """Step 3: Click 'ขายดี' (Best Seller) tab with natural scroll and human delay."""
    check_stop()
    check_shopee_captcha(driver)
    # Check if page has no data first
    if check_shopee_no_data(driver):
        log("[Shopee Step 3] ⚠️ ตรวจพบ 'ไม่มีข้อมูล' บนหน้าเว็บ ข้ามขั้นตอนการจัดเรียง")
        return False

    # Simulate slight natural human scroll before sorting
    try:
        driver.execute_script("window.scrollBy({ top: Math.floor(Math.random() * 120 + 80), behavior: 'smooth' });")
    except Exception:
        pass
    human_delay(1.0, 1.8)

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
    human_delay(2.5, 4.0)
    if res and res.get("success"):
        log("[Shopee Step 3] ✅ คลิกแท็บ 'ขายดี' สำเร็จ")
        return True
    log("[Shopee Step 3] ⚠️ ไม่พบปุ่ม 'ขายดี' (อาจอยู่ในหน้านี้แล้วหรือโหลดไม่ทัน)")
    return False

def step_4_select_and_open_product(driver) -> dict[str, Any]:
    """Step 4: Analyze and select product with highest commission (sales > 10), highlight it, and click to enter product details page."""
    # Check if page has no data first
    if check_shopee_no_data(driver):
        log("[Shopee Step 4] ⚠️ ตรวจพบ 'ไม่มีข้อมูล' (ไม่พบสินค้าที่ค้นหา) -> ข้ามรายการนี้ทันที")
        return {"success": False, "skipped": True, "reason": "no_data"}

    log("[Shopee Step 4] 🎯 กำลังวิเคราะห์เลือกสินค้าที่ค่าคอมมิชชั่นสูงสุด (เงื่อนไขยอดขาย > 10 ชิ้น)...")
    
    # 1. Analyze and pick best card
    selection = driver.execute_script("""
        const hasEmptyEl = !!document.querySelector('.empty, .ant-empty, [class*="empty"], [class*="nodata"]');
        const hasEmptyText = document.body && document.body.innerText ? document.body.innerText.includes('ไม่มีข้อมูล') : false;
        const list = document.querySelector('.product-offer-list');
        const cards = list ? Array.from(list.querySelectorAll('.product-offer-item')) : [];
        if ((hasEmptyEl || hasEmptyText) && cards.length === 0) {
            return { success: false, noData: true, reason: "No data found" };
        }
        if (!list) return { success: false, reason: "Container .product-offer-list not found" };
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

        // Extract Product Link directly from chosen card's anchor tag
        const aTag = card.querySelector('a[href*="offer/product_offer"]') || card.querySelector('a');
        const productLink = aTag ? aTag.href : '';

        // Navigate directly into product details page by clicking the anchor
        let clicked = false;
        if (aTag) {
            aTag.removeAttribute('target');
            aTag.click();
            clicked = true;
        }

        return {
            success: true,
            clicked: clicked,
            productLink: productLink,
            chosen: {
                idx: chosen.idx,
                title: chosen.title,
                salesText: chosen.salesText,
                salesCount: chosen.salesCount,
                commRate: chosen.commRate,
                pool: chosen.pool,
                productLink: productLink
            }
        };
    """)

    if not selection or not selection.get("success"):
        log(f"[Shopee Step 4] ❌ ไม่สามารถเลือกรายการสินค้าได้: {selection}")
        return {"success": False, "error": "selection_failed"}

    chosen_info = selection.get("chosen", {})
    product_link = selection.get("productLink") or chosen_info.get("productLink") or ""
    log(f"[Shopee Step 4] ⭐ เลือกสินค้า: '{chosen_info.get('title')}' | ค่าคอม: {chosen_info.get('commRate')}% | {chosen_info.get('salesText')} ({chosen_info.get('pool')})")
    
    # 2. Navigate to product detail page if not already navigating
    interruptible_sleep(1.5)
    if product_link:
        current_url = driver.current_url or ""
        # If still on the search page, force navigate using driver.get(product_link)
        if current_url.split("?")[0].rstrip("/").endswith("product_offer"):
            log(f"[Shopee Step 4] 🌐 กำลังเปิดหน้าลิงก์สินค้า: {product_link}")
            driver.get(product_link)
            interruptible_sleep(2.0)
        else:
            log(f"[Shopee Step 4] 🌐 นำทางเข้าสู่หน้ารายละเอียดสินค้าสำเร็จ: {driver.current_url}")

    return {
        "success": True,
        "chosen": chosen_info,
        "product_link": product_link or driver.current_url
    }

def step_5_get_affiliate_link(driver, target_file_path: str = "", folder_path: str = "", product_link: str = "") -> dict[str, Any]:
    """Step 5: Click orange 'เอา ลิงก์' button, copy affiliate short link, and save markdown files. (Does NOT click view product)."""
    check_stop()
    check_shopee_captcha(driver)

    if not product_link:
        product_link = driver.current_url or ""

    # 1. Find and click the orange "เอา ลิงก์" button on the product details page
    log("[Shopee Step 5] 🟠 กำลังกดปุ่มสีส้ม 'เอา ลิงก์' บนหน้ารายละเอียดสินค้า...")
    clicked_orange = False
    for _ in range(12):
        check_stop()
        clicked_orange = driver.execute_script("""
            const btns = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
            const orangeBtn = btns.find(b => {
                const txt = (b.innerText || '').trim().replace(/\\s+/g, '');
                return (txt === 'เอาลิงก์' || b.classList.contains('get-link-btn')) && !b.disabled;
            });
            if (orangeBtn) {
                orangeBtn.scrollIntoView({ block: 'center' });
                orangeBtn.click();
                return true;
            }
            return false;
        """)
        if clicked_orange:
            break
        interruptible_sleep(0.4)

    if not clicked_orange:
        log("[Shopee Step 5] ⚠️ ไม่พบปุ่มสีส้ม 'เอา ลิงก์' บนหน้ารายละเอียดสินค้า")

    # 2. Wait for modal & extract affiliate short link
    interruptible_sleep(1.2)
    affiliate_link = ""
    for _ in range(15):
        check_stop()
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
        interruptible_sleep(0.4)

    # Click copy button inside modal
    check_stop()
    driver.execute_script("""
        const copyBtn = document.querySelector('.ant-modal button.ant-btn-primary');
        if (copyBtn && !copyBtn.disabled) copyBtn.click();
    """)
    interruptible_sleep(0.3)

    # Dismiss any browser alert (e.g. Copy to clipboard)
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except Exception:
        pass

    # Close modal
    driver.execute_script("document.querySelector('.ant-modal-close, .ant-modal-close-x')?.click();")

    if not affiliate_link:
        log("[Shopee Step 5] ⚠️ ไม่สามารถดึงลิงก์ Affiliate จาก Modal ได้")

    log(f"[Shopee Step 5] 🔗 คัดลอก Affiliate Link สำเร็จ: {affiliate_link or '-'}")

    # 3. Determine target directory for saving files
    target_dir = folder_path
    if not target_dir and target_file_path:
        target_dir = os.path.dirname(target_file_path)

    saved_files = []
    if target_dir and os.path.exists(target_dir):
        # A) Save 'Affiliate Link.md'
        if affiliate_link:
            aff_path = os.path.join(target_dir, "Affiliate Link.md")
            try:
                with open(aff_path, "w", encoding="utf-8") as f:
                    f.write(affiliate_link + "\n")
                log(f"[Shopee Step 5] 💾 บันทึก Affiliate Link.md เรียบร้อย: {aff_path}")
                saved_files.append(aff_path)
            except Exception as e:
                log(f"[Shopee Step 5] ⚠️ บันทึก Affiliate Link.md ไม่สำเร็จ: {e}")

        # B) Save 'Product Link.md'
        if product_link:
            prod_path = os.path.join(target_dir, "Product Link.md")
            try:
                with open(prod_path, "w", encoding="utf-8") as f:
                    f.write(product_link + "\n")
                log(f"[Shopee Step 5] 💾 บันทึก Product Link.md เรียบร้อย: {prod_path}")
                saved_files.append(prod_path)
            except Exception as e:
                log(f"[Shopee Step 5] ⚠️ บันทึก Product Link.md ไม่สำเร็จ: {e}")

    return {
        "success": True,
        "affiliate_link": affiliate_link,
        "product_link": product_link,
        "saved_files": saved_files
    }

def step_4_select_best_product_and_get_link(driver, target_file_path: str = "", folder_path: str = "") -> dict[str, Any]:
    """Legacy wrapper: Runs Step 4 (select and open product) then Step 5 (get affiliate link)."""
    sel_res = step_4_select_and_open_product(driver)
    if sel_res.get("skipped") or not sel_res.get("success"):
        return sel_res
    prod_link = sel_res.get("product_link", "")
    link_res = step_5_get_affiliate_link(driver, target_file_path=target_file_path, folder_path=folder_path, product_link=prod_link)
    return {
        "success": True,
        "chosen": sel_res.get("chosen", {}),
        "affiliate_link": link_res.get("affiliate_link", ""),
        "product_link": prod_link,
        "saved_files": link_res.get("saved_files", []),
        "downloaded_images": []
    }

def step_6_open_product_tab(driver, target_dir: str = "", fallback_hash: str = "") -> list[str]:
    """Step 6: Click 'ดูสินค้า' to open the real Shopee product page in a new tab via CDP Trusted Click,
    keep the product tab open for the user to download images with their extension."""
    check_stop()
    log("[Shopee Step 6] 🔍 กำลังค้นหาปุ่ม 'ดูสินค้า' เพื่อเปิดหน้าสินค้าจริง...")
    
    init_handles = set(driver.window_handles)

    # 1. Click "ดูสินค้า" using CDP trusted mouse click
    clicked = False
    try:
        view_btn = driver.find_element(By.CSS_SELECTOR, "a.view-product, [href*='shopee.co.th/product/']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", view_btn)
        interruptible_sleep(0.4)
        rect = driver.execute_script("""
            const r = arguments[0].getBoundingClientRect();
            return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
        """, view_btn)
        if rect:
            cx, cy = rect['x'], rect['y']
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': cx - 20, 'y': cy - 15})
            interruptible_sleep(0.08)
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': cx, 'y': cy})
            interruptible_sleep(0.08)
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'button': 'left', 'x': cx, 'y': cy, 'clickCount': 1})
            interruptible_sleep(0.08)
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'button': 'left', 'x': cx, 'y': cy, 'clickCount': 1})
            clicked = True
            log("[Shopee Step 6] ✅ กดปุ่ม 'ดูสินค้า' (Trusted Click) สำเร็จแล้ว (ไม่สลับแท็บ)")
    except Exception as e:
        log(f"[Shopee Step 6] ⚠️ CDP click ไม่สำเร็จ ({e}) -> สลับใช้ native click")

    if not clicked:
        try:
            view_btn = driver.find_element(By.CSS_SELECTOR, "a.view-product, [href*='shopee.co.th/product/']")
            view_btn.click()
            clicked = True
            log("[Shopee Step 6] ✅ กดปุ่ม 'ดูสินค้า' (Native Click) สำเร็จแล้ว (ไม่สลับแท็บ)")
        except Exception as e:
            log(f"[Shopee Step 6] ⚠️ ไม่สามารถกดปุ่มดูสินค้าได้: {e}")

    # # 2. Confirm new tab opened in background WITHOUT switching to it
    # new_tab_found = False
    # for _ in range(10):
    #     check_stop()
    #     interruptible_sleep(0.3)
    #     current_handles = set(driver.window_handles)
    #     new_handles = current_handles - init_handles
    #     if new_handles:
    #         new_tab_found = True
    #         log(f"[Shopee Step 6] 🌐 ตรวจพบแท็บสินค้าใหม่เปิดขึ้นมาแล้ว ({len(new_handles)} แท็บใหม่) โดยไม่สลับแท็บ")
    #         break
    # 
    # if not new_tab_found:
    #     log("[Shopee Step 6] ℹ️ กดปุ่ม 'ดูสินค้า' เรียบร้อยแล้ว (ไม่สลับแท็บ)")

    return []

# Alias for backward compatibility
step_5_open_product_and_download_images = step_6_open_product_tab

def post_single_shopee_item(
    driver,
    item: dict[str, Any],
    page_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """Process a single Shopee Affiliate item: search keyword, sort best sellers, click product, get link, and open product tab."""
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
    check_stop()
    step_1_open_shopee_page(driver, page_url)
    check_stop()

    # Step 2: Search keyword (clean without numbers)
    step_2_search_product(driver, keyword)
    check_stop()

    # Step 3: Sort by 'ขายดี'
    step_3_sort_best_sellers(driver)
    check_stop()

    # Step 4: Select product with highest commission (sales > 10) and click into details
    sel_res = step_4_select_and_open_product(driver)
    check_stop()
    if sel_res.get("skipped"):
        log(f"[Shopee Affiliate] ⏭️ ข้ามรายการที่ {item_idx}/{total_items}: {name} (เหตุผล: ไม่พบข้อมูลสินค้าใน Shopee)")
        item["skipped"] = True
        item["skip_reason"] = sel_res.get("reason", "no_data")
        return True

    prod_link = sel_res.get("product_link") or sel_res.get("chosen", {}).get("productLink") or ""
    if prod_link:
        item["product_link"] = prod_link

    # Step 5: Click 'เอาลิงก์' and save markdown files (WITHOUT clicking view product)
    link_res = step_5_get_affiliate_link(driver, target_file_path=target_file, folder_path=folder_path, product_link=prod_link)
    check_stop()
    if link_res.get("affiliate_link"):
        item["affiliate_link"] = link_res["affiliate_link"]

    # Step 6: Click 'ดูสินค้า' to open real Shopee product page in a new tab
    step_6_open_product_tab(driver, target_dir=folder_path)

    log(f"[Shopee Affiliate] ✅ สำเร็จการค้นหาและดึงลิงก์รายการที่ {item_idx}/{total_items}: {name} (Affiliate: {item.get('affiliate_link', '-')}, Product: {item.get('product_link', '-')})")
    return True

def run_shopee_affiliate_batch(
    items: list[dict[str, Any]],
    target_url: str = "",
    delay_min: float = 5.0,
    delay_max: float = 15.0,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> dict[str, Any]:
    """Runs a batch of Shopee Affiliate automation tasks."""
    reset_shopee_stop()
    bot = browser_manager.get(target_port=9222)
    driver = bot.driver
    apply_stealth_cdp(driver)
    total = len(items)

    url = target_url.strip() if target_url else "https://affiliate.shopee.co.th"
    errors = []
    skipped_items = []
    success_count = 0

    log(f"[Shopee Affiliate Engine] เริ่มรัน {total} รายการบน Port 9222 (หน่วงเวลา: {delay_min}s - {delay_max}s)...")

    stopped_by_user = False
    for idx, item in enumerate(items):
        if is_shopee_stopped():
            stopped_by_user = True
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
                    "message": f"⏳ หน่วงเวลาสุ่ม {rand_delay}s ก่อนเริ่มรายการ {idx + 1}/{total}...",
                    "skipped_items": skipped_items
                })

            try:
                interruptible_sleep(rand_delay)
            except ForceStopException:
                stopped_by_user = True
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break

        try:
            check_stop()
            ok = post_single_shopee_item(
                driver=driver,
                item=item,
                page_url=url,
                item_idx=idx + 1,
                total_items=total,
                progress_callback=progress_callback
            )
            if item.get("skipped"):
                folder_desc = item.get("subfolder_name") or item.get("keyword") or f"Item #{idx+1}"
                skipped_items.append({
                    "folder": folder_desc,
                    "keyword": item.get("keyword", ""),
                    "reason": item.get("skip_reason", "no_data")
                })
            elif ok:
                success_count += 1
        except ShopeeCaptchaBlockedException as ce:
            stopped_by_user = True
            folder_desc = item.get("subfolder_name") or item.get("keyword") or f"Item #{idx+1}"
            log(f"[Shopee Affiliate] 🛑 หยุดทำงานทันทีเนื่องจากติดระบบกันบอท Shopee (CAPTCHA): {ce}")
            errors.append(f"🛑 ติดระบบกันบอท Shopee (CAPTCHA) ที่โฟลเดอร์: {folder_desc}")
            return {
                "ok": False,
                "stopped": True,
                "captcha_blocked": True,
                "captcha_url": ce.captcha_url or getattr(driver, "current_url", "") or "",
                "blocked_folder": folder_desc,
                "success_count": success_count,
                "skipped_items": skipped_items,
                "errors": errors
            }
        except ForceStopException:
            stopped_by_user = True
            log("[Shopee Affiliate] 🛑 หยุดทำงานทันทีตามคำสั่ง Force Stop")
            errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
            break
        except Exception as e:
            if is_shopee_stopped() or "Force Stop" in str(e):
                stopped_by_user = True
                log("[Shopee Affiliate] 🛑 หยุดทำงานทันทีตามคำสั่ง Force Stop")
                errors.append("🛑 บังคับหยุดทำงาน (Force Stop)")
                break
            err_msg = f"[{idx+1}/{total}] {item.get('subfolder_name', 'Item')}: {str(e)}"
            log(f"[Shopee Affiliate Error] {err_msg}")
            errors.append(err_msg)

    if progress_callback:
        final_status = "stopped" if stopped_by_user else ("completed" if not errors else "completed_with_errors")
        final_msg = "🛑 บังคับหยุดการทำงานแล้ว (Force Stopped)" if stopped_by_user else (
            f"✅ ดำเนินการสำเร็จ {success_count}/{total} รายการ" if not errors else f"เสร็จสิ้น {success_count}/{total} (พบข้อผิดพลาด {len(errors)} รายการ)"
        )
        progress_callback({
            "current": total if not stopped_by_user else max(0, success_count),
            "total": total,
            "percent": 100 if not stopped_by_user else int((success_count / max(total, 1)) * 100),
            "status": final_status,
            "message": final_msg,
            "errors": errors,
            "skipped_items": skipped_items
        })

    return {
        "ok": len(errors) == 0 and not stopped_by_user,
        "stopped": stopped_by_user,
        "total": total,
        "success_count": success_count,
        "errors": errors,
        "skipped_items": skipped_items
    }
