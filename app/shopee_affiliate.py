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

def step_4_select_best_product_and_get_link(driver, target_file_path: str = "", folder_path: str = "") -> dict[str, Any]:
    """Step 4: Select product with highest commission (sales > 10 items, or fallback to lower sales),
    click 'เอาลิงก์', copy affiliate short link, and save it to the product's .md file and Caption.md."""
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

    # 3. Find and click the orange "เอา ลิงก์" button on the product details page
    log("[Shopee Step 4] 🟠 กำลังกดปุ่มสีส้ม 'เอา ลิงก์' บนหน้ารายละเอียดสินค้า...")
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
        log("[Shopee Step 4] ⚠️ ไม่พบปุ่มสีส้ม 'เอา ลิงก์' บนหน้ารายละเอียดสินค้า")

    # 4. Wait for modal & extract affiliate short link
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
        log("[Shopee Step 4] ⚠️ ไม่สามารถดึงลิงก์ Affiliate จาก Modal ได้")

    log(f"[Shopee Step 4] 🔗 คัดลอก Affiliate Link สำเร็จ: {affiliate_link or '-'}")

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
                log(f"[Shopee Step 4] 💾 บันทึก Affiliate Link.md เรียบร้อย: {aff_path}")
                saved_files.append(aff_path)
            except Exception as e:
                log(f"[Shopee Step 4] ⚠️ บันทึก Affiliate Link.md ไม่สำเร็จ: {e}")

        # B) Save 'Product Link.md'
        if product_link:
            prod_path = os.path.join(target_dir, "Product Link.md")
            try:
                with open(prod_path, "w", encoding="utf-8") as f:
                    f.write(product_link + "\n")
                log(f"[Shopee Step 4] 💾 บันทึก Product Link.md เรียบร้อย: {prod_path}")
                saved_files.append(prod_path)
            except Exception as e:
                log(f"[Shopee Step 4] ⚠️ บันทึก Product Link.md ไม่สำเร็จ: {e}")

    # 3.5 Extract fallback image hash from current affiliate page before opening product page
    fallback_image_hash = driver.execute_script(r"""
        const img = document.querySelector('img.offer-img, img[src*="susercontent"]');
        if (!img) return '';
        const src = img.src || '';
        const m = src.match(/susercontent\.com\/(?:file\/)?([a-zA-Z0-9_-]+)/);
        return m ? m[1].replace(/\.[^.]+$/, '').replace(/_tn$/, '').split('@')[0] : '';
    """) or ""

    # 4. Open real product page via "ดูสินค้า" and download all main images as .jpg
    downloaded_images = []
    if target_dir and os.path.exists(target_dir):
        downloaded_images = step_5_open_product_and_download_images(driver, target_dir=target_dir, fallback_hash=fallback_image_hash)
        saved_files.extend(downloaded_images)

    return {
        "success": True,
        "chosen": chosen_info,
        "affiliate_link": affiliate_link,
        "product_link": product_link,
        "saved_files": saved_files,
        "downloaded_images": downloaded_images
    }

def step_5_open_product_and_download_images(driver, target_dir: str = "", fallback_hash: str = "") -> list[str]:
    """Step 5: Click 'ดูสินค้า' to open the real Shopee product page in a new tab, download all main product images as .jpg,
    and fallback to affiliate image if verify/traffic error occurs."""
    check_stop()
    log("[Shopee Step 5] 🔍 กำลังค้นหาปุ่ม 'ดูสินค้า' เพื่อเปิดหน้าสินค้าจริง...")
    
    main_window = driver.current_window_handle
    init_handles = set(driver.window_handles)

    # 1. Click "ดูสินค้า" using native element click so referrer is preserved and opens in new tab
    clicked_view = False
    try:
        view_btn = driver.find_element(By.CSS_SELECTOR, "a.view-product, [href*='shopee.co.th/product/']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", view_btn)
        interruptible_sleep(0.3)
        view_btn.click()
        clicked_view = True
    except Exception:
        # Fallback to JS click
        clicked_view = driver.execute_script("""
            const viewProdBtn = Array.from(document.querySelectorAll('a, button, div[role="button"]')).find(el => 
                el.classList.contains('view-product') || 
                (el.innerText || '').trim() === 'ดูสินค้า' || 
                (el.innerText || '').includes('ดูสินค้า')
            );
            if (viewProdBtn) {
                viewProdBtn.scrollIntoView({block: 'center'});
                viewProdBtn.click();
                return true;
            }
            return false;
        """)

    opened_new_tab = False
    new_tab_handle = None
    if clicked_view:
        for _ in range(15):
            check_stop()
            interruptible_sleep(0.3)
            current_handles = set(driver.window_handles)
            new_handles = current_handles - init_handles
            if new_handles:
                opened_new_tab = True
                new_tab_handle = list(new_handles)[0]
                break

    image_hashes = []
    if opened_new_tab and new_tab_handle:
        driver.switch_to.window(new_tab_handle)
        human_delay(1.8, 3.0)
        current_product_url = driver.current_url or ""
        log(f"[Shopee Step 5] 🌐 เปิดแท็บหน้าสินค้าจริงสำเร็จ: {current_product_url}")

        if is_shopee_captcha_url(current_product_url):
            log(f"[Shopee Step 5] 🛑 ตรวจพบระบบกันบอท Shopee (verify/captcha/traffic) -> หยุดการทำงานทันที!")
            raise ShopeeCaptchaBlockedException(
                "ตรวจพบระบบกันบอท Shopee (CAPTCHA / Traffic Verification) ขณะเปิดดูหน้าสินค้าจริง",
                captcha_url=current_product_url
            )

        # Micro-scroll down naturally to mimic human reading and trigger lazy-loaded product media
        try:
            driver.execute_script("""
                window.scrollBy({ top: Math.floor(Math.random() * 250 + 200), behavior: 'smooth' });
            """)
        except Exception:
            pass
        human_delay(1.5, 2.6)

        try:
            driver.execute_script("""
                window.scrollBy({ top: -Math.floor(Math.random() * 80 + 50), behavior: 'smooth' });
            """)
        except Exception:
            pass
        human_delay(0.6, 1.2)

        # 2. Extract all main gallery image hashes from the real product page
        image_hashes = driver.execute_script(r"""
            function extractHash(url) {
                if (!url) return null;
                const m = url.match(/susercontent\.com\/file\/([a-zA-Z0-9_-]+)/);
                if (m) {
                    return m[1].replace(/_tn$/, '').split('@')[0];
                }
                return null;
            }

            // On Shopee desktop, main gallery is inside the left media column
            const mainImg = Array.from(document.querySelectorAll('img')).find(i => {
                const r = i.getBoundingClientRect();
                return r.width >= 300 && r.height >= 300 && r.x < 650 && r.y < 850;
            });
            const wrapper = mainImg ? (mainImg.closest('.flex.flex-column') || mainImg.closest('.C21rQm') || mainImg.parentElement.parentElement) : document.body;

            // Select all images in the wrapper, excluding tiny variation icons (width <= 40)
            const galleryEls = Array.from(wrapper.querySelectorAll('img, picture source')).filter(el => {
                const r = el.getBoundingClientRect ? el.getBoundingClientRect() : (el.parentElement ? el.parentElement.getBoundingClientRect() : {});
                return (!r.width || r.width > 40);
            });

            const hashes = [];
            galleryEls.forEach(el => {
                const src = el.src || el.getAttribute('srcset') || el.srcset || '';
                const h = extractHash(src);
                if (h && !src.includes('.svg') && !hashes.includes(h)) {
                    hashes.push(h);
                }
            });

            return hashes;
        """) or []

        # Close product tab and switch back to affiliate main window
        try:
            driver.close()
        except Exception:
            pass
        driver.switch_to.window(main_window)
        human_delay(1.0, 2.0)
    else:
        log("[Shopee Step 5] ⚠️ ไม่สามารถเปิดแท็บหน้าสินค้าจริงได้")

    # If no hashes extracted from product page, use fallback_hash
    if not image_hashes and fallback_hash:
        log(f"[Shopee Step 5] ℹ️ ใช้รูปภาพจากหน้า Affiliate (Fallback Hash: {fallback_hash})")
        image_hashes = [fallback_hash]

    log(f"[Shopee Step 5] 📸 ได้รับรายการรูปภาพสำหรับดาวน์โหลดทั้งหมด {len(image_hashes)} รูป")
    if not image_hashes:
        log("[Shopee Step 5] ⚠️ ไม่พบ URL รูปภาพสำหรับดาวน์โหลด")
        return []

    if not target_dir or not os.path.exists(target_dir):
        log(f"[Shopee Step 5] ⚠️ โฟลเดอร์เป้าหมายไม่ถูกต้อง: {target_dir}")
        return []

    # 3. Create 'main_images' directory and save .jpg images
    main_images_dir = os.path.join(target_dir, "main_images")
    os.makedirs(main_images_dir, exist_ok=True)

    downloaded_files = []
    import urllib.request
    import io
    from PIL import Image

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for idx, h in enumerate(image_hashes, 1):
        check_stop()
        img_url = f"https://down-th.img.susercontent.com/file/{h}"
        dest_filename = f"{idx}.jpg"
        dest_path = os.path.join(main_images_dir, dest_filename)

        try:
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()

            check_stop()
            with Image.open(io.BytesIO(data)) as pil_img:
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                pil_img.save(dest_path, "JPEG", quality=95)

            log(f"[Shopee Step 5] 💾 ดาวน์โหลดรูปหลัก #{idx}: {dest_filename} สำเร็จ")
            downloaded_files.append(dest_path)

            # Also save first image as product.jpg in target_dir root
            if idx == 1:
                product_jpg_path = os.path.join(target_dir, "product.jpg")
                try:
                    with Image.open(io.BytesIO(data)) as pil_img:
                        if pil_img.mode in ("RGBA", "P"):
                            pil_img = pil_img.convert("RGB")
                        pil_img.save(product_jpg_path, "JPEG", quality=95)
                    downloaded_files.append(product_jpg_path)
                    log(f"[Shopee Step 5] 💾 บันทึก product.jpg ในโฟลเดอร์หลักเรียบร้อย")
                except Exception as ep:
                    log(f"[Shopee Step 5] ⚠️ บันทึก product.jpg ไม่สำเร็จ: {ep}")

        except ForceStopException:
            raise
        except Exception as e:
            log(f"[Shopee Step 5] ⚠️ ดาวน์โหลดรูป #{idx} ({img_url}) ล้มเหลว: {e}")

    log(f"[Shopee Step 5] ✅ ดาวน์โหลดและบันทึกรูปหลักทั้งหมด {len(downloaded_files)} ไฟล์เรียบร้อยแล้ว")
    return downloaded_files

def post_single_shopee_item(
    driver,
    item: dict[str, Any],
    page_url: str,
    item_idx: int = 1,
    total_items: int = 1,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
) -> bool:
    """Process a single Shopee Affiliate item: search keyword without number, sort, select best item, and save Affiliate Link.md & Product Link.md."""
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

    # Step 4: Select best product (highest commission with sales > 10), get link and save to Affiliate Link.md & Product Link.md
    res = step_4_select_best_product_and_get_link(driver, target_file_path=target_file, folder_path=folder_path)
    check_stop()
    if res.get("skipped"):
        log(f"[Shopee Affiliate] ⏭️ ข้ามรายการที่ {item_idx}/{total_items}: {name} (เหตุผล: ไม่พบข้อมูลสินค้าใน Shopee)")
        item["skipped"] = True
        item["skip_reason"] = res.get("reason", "no_data")
        return True

    if res.get("affiliate_link"):
        item["affiliate_link"] = res["affiliate_link"]
    if res.get("product_link"):
        item["product_link"] = res["product_link"]
    if res.get("downloaded_images"):
        item["downloaded_images"] = res["downloaded_images"]

    log(f"[Shopee Affiliate] ✅ สำเร็จการค้นหาและดึงลิงก์รายการที่ {item_idx}/{total_items}: {name} (Affiliate: {res.get('affiliate_link', '-')}, Product: {res.get('product_link', '-')}, รูปหลัก: {len(res.get('downloaded_images', []))} รูป)")
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
