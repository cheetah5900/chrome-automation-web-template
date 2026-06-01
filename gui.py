import customtkinter as ctk
import threading
import time
import os
import zipfile
import shutil
import json
import math
import re
import sys
from send2trash import send2trash
from browser_bot import BrowserBot
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image # For image resolution check

# --- Configuration ---
CONFIG_FILE = "config_win.json" if os.name == 'nt' else "config_mac.json"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("DDCM WorkFlow - Sequential Guide")
        self.minsize(1100, 800)
        self.after(0, self._maximize_window)
        
        self.bot = BrowserBot()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self.label = ctk.CTkLabel(self, text="DDCM WorkFlow - Sequential Guide", font=("Arial", 24, "bold"), text_color="white")
        self.label.grid(row=0, column=0, padx=20, pady=20)

        self.main_container = ctk.CTkScrollableFrame(self)
        # Smooth scrolling: override default mousewheel behavior
        try:
            self.main_container._parent_canvas.configure(yscrollincrement=10)
        except Exception:
            pass
        def _on_mousewheel(event):
            try:
                c = self.main_container._parent_canvas
            except Exception:
                return
            if sys.platform == "darwin":
                delta = event.delta
                step = -10 if delta > 0 else 10
            else:
                delta = event.delta
                step = -10 if delta > 0 else 10
            c.yview_scroll(step, "units")
            return "break"
        def _on_mousewheel_linux(event):
            try:
                c = self.main_container._parent_canvas
            except Exception:
                return
            step = -10 if event.num == 4 else 10
            c.yview_scroll(step, "units")
            return "break"
        try:
            self.main_container._parent_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            self.main_container._parent_canvas.bind_all("<Button-4>", _on_mousewheel_linux)
            self.main_container._parent_canvas.bind_all("<Button-5>", _on_mousewheel_linux)
        except Exception:
            pass
        self.main_container.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self._steps_container = self.main_container
        self._steps_container.grid_columnconfigure(0, weight=1, uniform="steps")
        self._steps_container.grid_columnconfigure(1, weight=1, uniform="steps")
        self._steps_container.grid_rowconfigure(0, weight=0)
        self._steps_container.grid_rowconfigure(1, weight=0)
        self._steps_container.grid_rowconfigure(2, weight=1)
        self._step_index = 0

        group_bg = "#2a2a2a"
        group_border = "#333333"
        self._group_1 = ctk.CTkFrame(self._steps_container, fg_color=group_bg, corner_radius=14, border_width=1, border_color=group_border)
        self._group_1.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=12, pady=(10, 6))
        self._group_1.grid_columnconfigure(0, weight=1, uniform="steps")
        self._group_1.grid_columnconfigure(1, weight=1, uniform="steps")
        self._g1_left = ctk.CTkFrame(self._group_1, fg_color="transparent")
        self._g1_right = ctk.CTkFrame(self._group_1, fg_color="transparent")
        self._g1_left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)
        self._g1_right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)

        self._group_2 = ctk.CTkFrame(self._steps_container, fg_color=group_bg, corner_radius=14, border_width=1, border_color=group_border)
        self._group_2.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(6, 6))
        self._group_2.grid_columnconfigure(0, weight=1, uniform="steps")
        self._group_2.grid_columnconfigure(1, weight=1, uniform="steps")
        self._g2_left = ctk.CTkFrame(self._group_2, fg_color="transparent")
        self._g2_right = ctk.CTkFrame(self._group_2, fg_color="transparent")
        self._g2_left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)
        self._g2_right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)

        # Remaining steps (9+) continue below grouped sections
        self._left_col = ctk.CTkFrame(self._steps_container, fg_color="transparent")
        self._right_col = ctk.CTkFrame(self._steps_container, fg_color="transparent")
        self._left_col.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        self._right_col.grid(row=2, column=1, sticky="nsew", padx=(6, 0))

        # 1. Basic Info
        self.frame_step1 = self.create_step_frame("1. กรอกข้อมูลพื้นฐาน (Basic Info)")
        def add_input_row(parent, label_text, key, default_val=""):
            self.add_label(parent, label_text)
            row_frame = ctk.CTkFrame(parent, fg_color="transparent"); row_frame.pack(fill="x", pady=(0, 10))
            entry = ctk.CTkEntry(row_frame, placeholder_text=label_text)
            if default_val: entry.insert(0, default_val)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ctk.CTkButton(row_frame, text="Set Default", width=100, fg_color="#5D6D7E", 
                                command=lambda: self.action_save_single_default(key, entry.get().strip())).pack(side="right")
            return entry
        self.entry_folder_name = add_input_row(self.frame_step1, "Folder Name (ชื่อโฟลเดอร์งาน)", "folder_name")
        self.entry_element_name = add_input_row(self.frame_step1, "Element Name (ชื่อโฟลเดอร์ของตกแต่ง)", "element_name", "Songkran")
        self.entry_element_path = add_input_row(self.frame_step1, "Element Path (ที่เก็บของตกแต่ง)", "element_path")
        self.entry_local_path = add_input_row(self.frame_step1, "Local Path (ที่เก็บงานในเครื่อง)", "local_path")
        self.entry_remote_path = add_input_row(self.frame_step1, "Remote Path (ที่เก็บงานบน Drive)", "remote_path")
        self.entry_watermark_path = add_input_row(self.frame_step1, "Watermark Path (ที่เก็บไฟล์ลายน้ำ)", "watermark_path")

        # 2. Folders
        self.frame_step2 = self.create_step_frame("2. เตรียมโฟลเดอร์งาน")
        self.add_desc(self.frame_step2, "สร้างโฟลเดอร์งานที่ Local และ Remote พร้อมโฟลเดอร์ย่อยที่จำเป็น")
        self.btn_create_folders = self.add_button(self.frame_step2, "Create Folders", self.action_create_folders, "#27AE60")

        # 3. Gemini Automation
        self.frame_step3 = self.create_step_frame("3. Gemini Automation (สร้างรูปภาพ)")
        self.add_desc(self.frame_step3, "ดึงข้อมูลจาก DDCM ไปสร้างภาพใน Gemini")
        inner_gemini = ctk.CTkFrame(self.frame_step3, fg_color="transparent"); inner_gemini.pack(fill="x")
        self.entry_single_count = ctk.CTkEntry(inner_gemini, width=60); self.entry_single_count.insert(0, "12"); self.entry_single_count.grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkButton(inner_gemini, text="Gen Single", width=140, command=self.action_gemini_single, fg_color="#8E44AD").grid(row=0, column=1, padx=5, pady=5)
        self.entry_companion_count = ctk.CTkEntry(inner_gemini, width=60); self.entry_companion_count.insert(0, "12"); self.entry_companion_count.grid(row=1, column=0, padx=5, pady=5)
        ctk.CTkButton(inner_gemini, text="Gen Companion", width=140, command=self.action_gemini_companion, fg_color="#8E44AD").grid(row=1, column=1, padx=5, pady=5)
        self.entry_elements_count = ctk.CTkEntry(inner_gemini, width=60); self.entry_elements_count.insert(0, "5"); self.entry_elements_count.grid(row=2, column=0, padx=5, pady=5)
        ctk.CTkButton(inner_gemini, text="Gen Elements", width=140, command=self.action_gemini_elements, fg_color="#8E44AD").grid(row=2, column=1, padx=5, pady=5)

        # 4. Download Images
        self.frame_step4 = self.create_step_frame("4. จัดเก็บรูปภาพจาก Gemini")
        self.add_desc(self.frame_step4, "โหลดรูปภาพทั้งหมดและย้ายไปไว้ที่โฟลเดอร์ images ใน Downloads")
        self.btn_download_imgs = self.add_button(self.frame_step4, "Download images", self.action_download_images, "#2E86C1")

        # 5. Remove Background
        self.frame_step5 = self.create_step_frame("5. ตัดพื้นหลัง (Remove Background)")
        self.add_desc(self.frame_step5, "นำรูปใน Downloads/images เข้า Photoshop เพื่อตัดพื้นหลังให้ใส")

        # 6. Classify Resolution (NEW)
        self.frame_step6 = self.create_step_frame("6. แยกกลุ่มตามขนาดภาพ (Classify Resolution)")
        self.add_desc(self.frame_step6, "ตรวจสอบขนาดรูปภาพใน Downloads/images และแยกใส่โฟลเดอร์ตามความละเอียด (เช่น 1024x1024)")
        self.btn_classify = self.add_button(self.frame_step6, "Classify resolution", self.action_classify_resolution, "#16A085")

        # 7. Upscale Instruction
        self.frame_step7 = self.create_step_frame("7. การขยายภาพ (Upscale)")
        self.add_desc(self.frame_step7, "นำรูปที่แยกกลุ่มแล้วไปขยายขนาดด้วยโปรแกรม Upscayl โดยบันทึกไว้ในโฟลเดอร์ 'upscale' ของแต่ละกลุ่ม")

        # 8. Upscale to Local
        self.frame_step8 = self.create_step_frame("8. ย้ายไฟล์ Upscale เข้าเครื่อง (รูปหลัก)")
        self.add_desc(self.frame_step8, "ย้ายรูปในโฟลเดอร์ images ไปที่ Local โฟลเดอร์ 4000x4000 พร้อมเปลี่ยนชื่อเริ่มที่เลข (1)")
        self.btn_copy_upscale = self.add_button(self.frame_step8, "Downloads/images to Local", self.action_copy_upscale, "#8E44AD")

        # 9. Element to Local
        self.frame_step9 = self.create_step_frame("9. ย้ายไฟล์ Elements เข้าคลัง (ของตกแต่ง)")
        self.add_desc(self.frame_step9, "ย้ายไฟล์ของตกแต่งจาก elements/upscale ไปไว้ที่ Element Path และเริ่มที่เลข (1)")
        self.btn_element_local = self.add_button(self.frame_step9, "Element to Local", self.action_element_to_local, "#D35400")

        # 10. Canva Instruction
        self.frame_step10 = self.create_step_frame("10. ออกแบบปกใน Canva")
        self.add_desc(self.frame_step10, "จัดวางหน้าปกและ Preview ใน Canva ให้เรียบร้อย")
        self.btn_create_preview = self.add_button(self.frame_step10, "Create Preview Sheet", self.action_create_preview, "#E67E22")

        # 11. Canva Automation (ส่งออกไฟล์)
        self.frame_step11 = self.create_step_frame("11. Canva Automation (ส่งออกไฟล์)")
        f_canva = ctk.CTkFrame(self.frame_step11, fg_color="transparent"); f_canva.pack(fill="x")

        def add_export_row(label, default_pages, btn_text, command, color):
            row = ctk.CTkFrame(f_canva, fg_color="transparent"); row.pack(fill="x", pady=(0, 10))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=label, font=("Arial", 13), text_color="white").grid(row=0, column=0, padx=(0, 10), sticky="w")
            entry = ctk.CTkEntry(row, width=120)
            entry.insert(0, default_pages)
            entry.grid(row=0, column=1, sticky="w")
            btn = ctk.CTkButton(row, text=btn_text, command=command, fg_color=color, height=36, font=("Arial", 13, "bold"), width=160)
            btn.grid(row=0, column=2, padx=(10, 0), sticky="e")
            return entry, btn

        self.entry_png_pages, self.btn_export_png = add_export_row("PNG Pages", "1-4", "Export PNG", self.action_export_png, "#00C4CC")
        self.entry_jpg_pages, self.btn_export_jpg = add_export_row("JPG Pages", "6-9", "Export JPG", self.action_export_jpg, "#00C4CC")
        self.entry_pdf_pages, self.btn_export_pdf = add_export_row("PDF Pages", "10", "Export PDF", self.action_export_pdf, "#E04F5F")
        self.btn_export_all = self.add_button(self.frame_step11, "Export ALL", self.action_export_all, "#005F99")

        # 12. Unzip
        self.frame_step12 = self.create_step_frame("12. แตกไฟล์ Zip งาน")
        self.add_desc(self.frame_step12, "แตกไฟล์ .zip ที่ดาวน์โหลดจาก Canva ในโฟลเดอร์ Downloads")
        self.btn_unzip = self.add_button(self.frame_step12, "Unzip Downloads", self.action_unzip_downloads, "#FFA500")

        # 13. Download to Local
        self.frame_step13 = self.create_step_frame("13. รวบรวมไฟล์เข้าโฟลเดอร์งาน")
        self.add_desc(self.frame_step13, "รวบรวมไฟล์งานจาก Downloads เข้าสู่โฟลเดอร์งานใน Local (เช่น Preview, Download file)")
        self.btn_download_local = self.add_button(self.frame_step13, "Download to Local", self.action_download_to_local, "#F39C12")

        # 14. Local to Remote
        self.frame_step14 = self.create_step_frame("14. สำรองไฟล์ขึ้น Cloud (Drive)")
        self.add_desc(self.frame_step14, "อัปโหลด/คัดลอกไฟล์จาก Local ไปยัง Remote (Google Drive)")
        self.btn_local_remote = self.add_button(self.frame_step14, "Local to Remote", self.action_local_remote, "#3498DB")

        # 15. Etsy
        self.frame_step15 = self.create_step_frame("15. ลงสินค้าใน Etsy")
        self.add_desc(self.frame_step15, "สร้าง Listing บน Etsy จากข้อมูลที่เลือก (สีหลัก/สีรอง) และขั้นตอนที่เตรียมไว้")
        self.etsy_colors = ["Beige", "Black", "Blue", "Bronze", "Brown", "Clear", "Copper", "Gold", "Gray", "Green", "Orange", "Pink", "Purple", "Rainbow", "Red", "Rose gold", "Silver", "White", "Yellow"]
        dd_row = ctk.CTkFrame(self.frame_step15, fg_color="transparent"); dd_row.pack(fill="x", pady=(6, 10))
        dd_row.grid_columnconfigure(0, weight=1, uniform="etsy")
        dd_row.grid_columnconfigure(1, weight=1, uniform="etsy")

        left = ctk.CTkFrame(dd_row, fg_color="transparent"); left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ctk.CTkFrame(dd_row, fg_color="transparent"); right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(left, text="Primary Color", font=("Arial", 13), text_color="white").pack(anchor="w")
        self.dropdown_primary = ctk.CTkOptionMenu(left, values=self.etsy_colors, width=220)
        self.dropdown_primary.set("Red")
        self.dropdown_primary.pack(fill="x", anchor="w", pady=(2, 0))

        ctk.CTkLabel(right, text="Secondary Color", font=("Arial", 13), text_color="white").pack(anchor="w")
        self.dropdown_secondary = ctk.CTkOptionMenu(right, values=self.etsy_colors, width=220)
        self.dropdown_secondary.set("Gray")
        self.dropdown_secondary.pack(fill="x", anchor="w", pady=(2, 0))
        self.btn_etsy = self.add_button(self.frame_step15, "Create Listing", self.action_etsy_listing, "#F1641E")

        self.status_label = ctk.CTkLabel(self, text="Connecting...", text_color="orange", font=("Arial", 15, "bold"))
        self.status_label.grid(row=2, column=0, pady=10)
        self.load_defaults(); self.start_browser_thread()

    # --- UI Helpers ---
    def create_step_frame(self, title):
        idx = self._step_index
        self._step_index += 1

        # Steps 1-4 in Group 1
        if idx == 0:
            parent = self._g1_left
        elif idx in (1, 2, 3):
            parent = self._g1_right
        # Steps 5-9 in Group 2
        elif idx in (4, 5, 6):
            parent = self._g2_left
        elif idx in (7, 8):
            parent = self._g2_right
        elif idx in (9, 10, 11):
            # Steps 10-12 in left column
            parent = self._left_col
        elif idx in (12, 13, 14):
            # Steps 13-15 in right column
            parent = self._right_col
        else:
            parent = self._left_col if (idx % 2 == 0) else self._right_col

        frame = ctk.CTkFrame(parent, corner_radius=12, border_width=1, border_color="#2b2b2b")
        frame.pack(fill="x", padx=12, pady=10)
        lbl = ctk.CTkLabel(frame, text=title, font=("Arial", 18, "bold"), text_color="white")
        lbl.pack(pady=(12, 8), padx=16, anchor="w")
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        inner.grid_columnconfigure(0, weight=1)
        return inner
    def add_label(self, parent, text, text_color="white"):
        lbl = ctk.CTkLabel(parent, text=text, font=("Arial", 13), text_color=text_color)
        lbl.pack(pady=(6, 2), fill="x", anchor="w")
        return lbl
    def add_entry(self, parent, placeholder, default_val="", width=400):
        e = ctk.CTkEntry(parent, placeholder_text=placeholder, width=width); e.pack(pady=(0, 10), anchor="w")
        if default_val: e.insert(0, default_val)
        return e
    def add_button(self, parent, text, command, color):
        btn = ctk.CTkButton(parent, text=text, command=command, fg_color=color, height=40, font=("Arial", 14, "bold"))
        btn.pack(pady=(6, 10), fill="x", anchor="w")
        return btn
    def add_desc(self, parent, text, color="white", font_size=13):
        lbl = ctk.CTkLabel(parent, text=text, font=("Arial", font_size), wraplength=900, justify="left", text_color=color)
        lbl.pack(pady=(0, 8), fill="x", anchor="w")
        return lbl

    # --- Logic ---
    def action_classify_resolution(self):
        self.log("Classifying resolutions...")
        dp = os.path.join(os.path.expanduser("~"), "Downloads")
        img_d = os.path.join(dp, "images")
        if not os.path.exists(img_d): self.log("Error: No 'images' in Downloads", error=True); return
        
        counts = {}
        try:
            for f in os.listdir(img_d):
                fp = os.path.join(img_d, f)
                if os.path.isfile(fp) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    try:
                        with Image.open(fp) as img:
                            w, h = img.size
                            res_folder = f"{w}x{h}"
                            target_d = os.path.join(img_d, res_folder)
                            os.makedirs(target_d, exist_ok=True)
                            shutil.move(fp, os.path.join(target_d, f))
                            counts[res_folder] = counts.get(res_folder, 0) + 1
                    except Exception as ie: print(f"Skipping {f}: {ie}")
            self.log(f"Classified: {', '.join([f'{k}({v})' for k,v in counts.items()])}")
        except Exception as e: self.log(f"Error classifying: {e}", error=True)

    def action_save_single_default(self, key, value):
        c = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f: c = json.load(f)
            except: pass
        c[key] = value
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(c, f, indent=4)
            self.log(f"Saved default for {key}!")
        except Exception as e: self.log(f"Error: {e}", error=True)

    def load_defaults(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    self.entry_folder_name.insert(0, c.get("folder_name", ""))
                    self.entry_element_name.delete(0, 'end'); self.entry_element_name.insert(0, c.get("element_name", "Songkran"))
                    self.entry_element_path.insert(0, c.get("element_path", ""))
                    self.entry_local_path.insert(0, c.get("local_path", ""))
                    self.entry_remote_path.insert(0, c.get("remote_path", ""))
                    self.entry_watermark_path.insert(0, c.get("watermark_path", ""))
                return
            except: pass
        if os.name == 'nt':
            self.entry_element_path.insert(0, r"C:\Files\Project\local DDCM\Elements")
            self.entry_local_path.insert(0, r"C:\Files\Project\local DDCM")
            self.entry_remote_path.insert(0, r"G:\My Drive\Projects\DDCM\Cliparts DDCM")
            self.entry_watermark_path.insert(0, r"C:\Files\Project\local DDCM\Watermark.png")
        else:
            h = os.path.expanduser("~")
            self.entry_element_path.insert(0, os.path.join(h, "Documents/DDCM/Elements"))
            self.entry_local_path.insert(0, os.path.join(h, "Documents/DDCM"))
            self.entry_remote_path.insert(0, "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Projects/DDCM/Cliparts DDCM")
            self.entry_watermark_path.insert(0, os.path.join(h, "Documents/DDCM/Watermark.png"))

    def log(self, m, error=False):
        c = "red" if error else "white"
        self.status_label.configure(text=m, text_color=c); print(m)

    def _maximize_window(self):
        try:
            if os.name == 'nt':
                # Windows: maximize window
                self.state('zoomed')
            else:
                # macOS/Linux: best-effort maximize
                try:
                    self.attributes('-zoomed', True)
                except Exception:
                    sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                    self.geometry(f"{sw}x{sh}+0+0")
        except Exception as e:
            self.log(f"Maximize failed: {e}", error=True)

    def _trash(self, path: str):
        if not path or not os.path.exists(path):
            return
        try:
            send2trash(path)
        except Exception as e:
            self.log(f"Error moving to Trash: {path} ({e})", error=True)

    def start_browser_thread(self): threading.Thread(target=self._start_browser_task).start()
    def _start_browser_task(self):
        if self.bot.start_browser(attach=True): self.log("Connected to Browser."); self.status_label.configure(text_color="#27AE60")
        else: self.log("Failed: Close ALL Chrome & Restart App", error=True)

    def action_gemini_single(self): threading.Thread(target=self._run_gemini_gen, args=("single",)).start()
    def action_gemini_companion(self): threading.Thread(target=self._run_gemini_gen, args=("companion",)).start()
    def action_gemini_elements(self): threading.Thread(target=self._run_gemini_gen, args=("elements",)).start()
    def action_download_images(self): threading.Thread(target=self._run_download_images).start()

    def _run_download_images(self):
        try:
            self.log("Starting Image Download...")
            if not self.bot.switch_to_tab_containing("gemini.google.com/app"): self.log("Error: Gemini tab not found!", error=True); return
            time.sleep(1); self.bot.driver.execute_script("window.scrollTo(0, 0);")
            scs = self.bot.driver.find_elements(By.CSS_SELECTOR, ".infinite-scroller, .conversation-container, main")
            for s in scs: self.bot.driver.execute_script("arguments[0].scrollTop = 0;", s)
            time.sleep(2); btns = self.bot.driver.find_elements(By.CSS_SELECTOR, "download-generated-image-button > button")
            if not btns:
                self.bot.driver.execute_script("window.scrollTo(0, 1000);"); time.sleep(1)
                btns = self.bot.driver.find_elements(By.CSS_SELECTOR, "download-generated-image-button > button")
            if not btns: self.log("Error: No download buttons found.", error=True); return
            cnt = len(btns); self.log(f"Found {cnt} images.")
            for i in range(cnt):
                self.log(f"Downloading {i+1}/{cnt}...")
                try:
                    curr_btns = self.bot.driver.find_elements(By.CSS_SELECTOR, "download-generated-image-button > button")
                    if i >= len(curr_btns): break
                    btn = curr_btns[i]; self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(1); ohtml = btn.get_attribute("innerHTML")
                    try: btn.click()
                    except: self.bot.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1); wt = 0
                    while wt < 20:
                        try:
                            c_btn = self.bot.driver.find_elements(By.CSS_SELECTOR, "download-generated-image-button > button")[i]
                            if c_btn.get_attribute("innerHTML") == ohtml: break
                        except: pass
                        time.sleep(1); wt += 1
                    time.sleep(1)
                except Exception as e: self.log(f"Error clicking btn {i+1}: {e}", error=True)
            self.log("Moving files...")
            try:
                dp = os.path.join(os.path.expanduser("~"), "Downloads"); ip = os.path.join(dp, "images")
                os.makedirs(ip, exist_ok=True); mc = 0
                for f in os.listdir(dp):
                    if f.lower().endswith(".png"):
                        src, dst = os.path.join(dp, f), os.path.join(ip, f)
                        if os.path.exists(dst): self._trash(dst)
                        shutil.move(src, dst); mc += 1
                self.log(f"Moved {mc} PNG files to 'Downloads/images'.")
            except Exception as me: self.log(f"Error moving images: {me}", error=True)
        except Exception as e: self.log(f"Error: {e}", error=True)

    def _run_gemini_gen(self, mode="single"):
        try:
            self.log(f"Starting Gemini Gen ({mode})...")
            if not self.bot.switch_to_tab_containing("ddcm.litarandfriends.uk"): self.log("Error: DDCM tab not found!", error=True); return
            time.sleep(1); containers = []
            if mode == "single": containers = [("Set 1", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(1) > div:nth-child(2)")]
            elif mode == "companion": containers = [("Set 2", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(2) > div:nth-child(2)")]
            elif mode == "elements": containers = [("Elements", "body > main > div.modal-overlay > div > div:nth-child(2) > div:nth-child(13) > div > div > div > div:nth-child(3) > div:nth-child(2)")]
            all_p = []
            for n, sel in containers:
                try:
                    cont = WebDriverWait(self.bot.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cont); time.sleep(0.5)
                    bs = cont.find_elements(By.TAG_NAME, "button")
                    if not bs: bs = cont.find_elements(By.XPATH, ".//button")
                    for i, b in enumerate(bs):
                        try:
                            self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b); time.sleep(0.5)
                            try: b.click()
                            except: self.bot.driver.execute_script("arguments[0].click();", b)
                            time.sleep(1.0); text = self.clipboard_get()
                            if text: all_p.append(text)
                        except: pass
                except Exception as e: self.log(f"Error {n}: {e}", error=True)
            if not all_p: self.log("No prompts collected."); return
            try:
                if mode == "single": cl = int(self.entry_single_count.get().strip())
                elif mode == "companion": cl = int(self.entry_companion_count.get().strip())
                else: cl = int(self.entry_elements_count.get().strip())
            except: cl = 5
            all_p = all_p[:cl]
            self.log(f"Processing {len(all_p)} prompts. Switching to Gemini...")
            if not self.bot.switch_to_tab_containing("gemini.google.com/app"): self.log("Error: Gemini tab not found!", error=True); return
            time.sleep(1); strats = ["//div[contains(@class, 'ql-editor') and @contenteditable='true']", "//rich-textarea//div[@contenteditable='true']", "//div[@contenteditable='true' and @role='textbox']"]
            for i, p in enumerate(all_p):
                self.log(f"Processing Gemini {i+1}/{len(all_p)}...")
                try:
                    box = None
                    for s in strats:
                        try:
                            tmp = WebDriverWait(self.bot.driver, 5).until(EC.presence_of_element_located((By.XPATH, s)))
                            if tmp.is_displayed(): box = tmp; break
                        except: continue
                    if not box: self.log("Error: No Input Box", error=True); return
                    try: box.click()
                    except: self.bot.driver.execute_script("arguments[0].click();", box)
                    time.sleep(0.5); self.bot.driver.execute_script("if(arguments[0].textContent !== undefined) { arguments[0].textContent = ''; } else { arguments[0].innerText = ''; }", box)
                    time.sleep(0.5); box.send_keys(p); time.sleep(1); box.send_keys(Keys.ENTER)
                    self.log(f"  -> Sent {i+1}. Waiting..."); time.sleep(3)
                    st_xp = "//mat-icon[contains(@data-mat-icon-name, 'stop') or @fonticon='stop']"
                    mw, el = 120, 0
                    while el < mw:
                        try: self.bot.driver.find_element(By.XPATH, st_xp); time.sleep(2); el += 2
                        except: self.log("  -> Finished."); break
                    time.sleep(3)
                except Exception as e: self.log(f"Error: {e}", error=True); return
            self.log("Gemini Automation Complete!")
        except Exception as e: self.log(f"Critical Error: {e}", error=True)

    def action_export_png(self):
        self.log("Running Export PNG...")
        if not self.bot.switch_to_tab_containing("canva.com"): self.log("Error: Canva not found."); return
        ps = self.entry_png_pages.get().strip() or "1-4"
        steps = [("Rename Design to 'png'", "//input[@aria-label='Design title']", "png"), ("Click Share", "//button[.//span[text()='Share']]"), ("Click Download", "//button[@aria-label='Download']"), ("Click File Type", "//button[@aria-label='File type']"), ("Select PNG", "//*[@role='option']//div[text()='PNG']"), ("Set Size to 1", "//input[@role='spinbutton']", "1"), ("Click Transparent", "//label[.//p[contains(text(), 'Transparent background')]]"), (f"Set Pages to {ps}", "//input[@placeholder='Select pages']", ps), ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]")]
        self._execute_steps(steps)

    def action_export_jpg(self):
        self.log("Running Export JPG...")
        if not self.bot.switch_to_tab_containing("canva.com"): self.log("Error: Canva not found."); return
        ps = self.entry_jpg_pages.get().strip() or "6-9"
        steps = [("Rename Design to 'jpg'", "//input[@aria-label='Design title']", "jpg"), ("Click Share", "//button[.//span[text()='Share']]"), ("Click Download", "//button[@aria-label='Download']"), ("Click File Type", "//button[@aria-label='File type']"), ("Select JPG", "//*[@role='option']//div[text()='JPG']"), ("Set Size to 0.5", "//input[@role='spinbutton']", "0.5"), (f"Set Pages to {ps}", "//input[@placeholder='Select pages']", ps), ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]")]
        self._execute_steps(steps)

    def action_export_pdf(self):
        self.log("Running Export PDF...")
        if not self.bot.switch_to_tab_containing("canva.com"): self.log("Error: Canva not found."); return
        ps = self.entry_pdf_pages.get().strip() or "10"
        steps = [("Rename Design to 'pdf_for_downloading'", "//input[@aria-label='Design title']", "pdf_for_downloading"), ("Click Share", "//button[.//span[text()='Share']]"), ("Click Download", "//button[@aria-label='Download']"), ("Click File Type", "//button[@aria-label='File type']"), ("Select PDF Standard", "//*[@role='option']//div[text()='PDF Standard']"), (f"Set Pages to {ps}", "//input[@placeholder='Select pages']", ps), ("Final Download", "//button[@type='submit'][.//span[contains(text(), 'Download')]]")]
        self._execute_steps(steps)

    def action_export_all(self):
        self.log("Starting ALL Exports..."); self.action_export_png(); time.sleep(8); self.action_export_jpg(); time.sleep(8); self.action_export_pdf()

    def action_create_folders(self):
        fn = self.entry_folder_name.get().strip()
        if not fn: self.log("Error: Folder Name required.", error=True); return
        configs = [{"path": self.entry_local_path.get().strip(), "folder": fn, "subfolders": ["4000x4000", "Download file", "Original", "Preview", "Sticker Set"]}, {"path": self.entry_remote_path.get().strip(), "folder": fn, "subfolders": ["4000x4000", "Sticker Set"]}]
        for i, c in enumerate(configs):
            base, name, subs = c["path"], c["folder"], c["subfolders"]
            if not base or not name: continue
            f = os.path.join(base, name); os.makedirs(f, exist_ok=True); cr = 0
            for sub in subs:
                sp = os.path.join(f, sub)
                if not os.path.exists(sp): os.makedirs(sp, exist_ok=True); cr += 1
            self.log(f"Path {i+1}: {'Done' if cr > 0 else 'Exist'}")

    def action_copy_upscale(self):
        fn, lp = self.entry_folder_name.get().strip(), self.entry_local_path.get().strip()
        if not fn or not lp: self.log("Error: Paths required.", error=True); return
        clean_name = fn.split(" - ", 1)[1] if " - " in fn else fn
        base, dp = os.path.join(lp, fn), os.path.join(os.path.expanduser("~"), "Downloads")
        img_d = os.path.join(dp, "images")
        if not os.path.exists(img_d): self.log("Error: No 'images' folder", error=True); return

        d4000 = os.path.join(base, "4000x4000"); os.makedirs(d4000, exist_ok=True)
        img_files = []
        for root, dirs, files in os.walk(img_d):
            for f in files:
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    img_files.append(os.path.join(root, f))

        if not img_files:
            self.log("No images found in Downloads/images.")
            return

        for i, fp in enumerate(sorted(img_files)):
            shutil.copy2(fp, os.path.join(d4000, f"{clean_name} ({i+1}){os.path.splitext(fp)[1]}"))

        self._trash(img_d); self.log("Moved & Renamed images to Local.")

    def action_create_preview(self): threading.Thread(target=self._run_create_preview).start()

    def _run_create_preview(self):
        try:
            fn, lp = self.entry_folder_name.get().strip(), self.entry_local_path.get().strip()
            if not fn or not lp: self.log("Error: Paths required.", error=True); return
            
            base = os.path.join(lp, fn)
            src_dir = os.path.join(base, "4000x4000")
            target_dir = os.path.join(base, "Sticker Set")
            
            if not os.path.exists(src_dir):
                self.log(f"Error: Folder NOT FOUND: 4000x4000", error=True); return
            
            os.makedirs(target_dir, exist_ok=True)
            img_files = sorted([f for f in os.listdir(src_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
            if not img_files:
                self.log("Error: No images in 4000x4000", error=True); return
            
            self.log(f"Creating sheets for {len(img_files)} images...")
            cw, ch, max_p = 4000, 4000, 16
            pages = [img_files[i:i + max_p] for i in range(0, len(img_files), max_p)]
            
            # Find the starting index for numbering to avoid overwriting
            max_num = 0
            for f in os.listdir(target_dir):
                match = re.search(r"Sticker Set \((\d+)\)\.png", f)
                if match:
                    num = int(match.group(1))
                    if num > max_num: max_num = num
            start_idx = max_num + 1

            for p_idx, page_imgs in enumerate(pages):
                n = len(page_imgs)
                cols = math.ceil(math.sqrt(n))
                rows = math.ceil(n / cols)
                
                # Create a transparent canvas (RGBA with alpha 0)
                canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                cell_w, cell_h = cw // cols, ch // rows
                
                for i, img_file in enumerate(page_imgs):
                    c, r = i % cols, i // cols
                    with Image.open(os.path.join(src_dir, img_file)) as img:
                        # Ensure image is RGBA to maintain its own transparency
                        img = img.convert("RGBA")
                        img_ratio = img.width / img.height
                        cell_ratio = cell_w / cell_h
                        if img_ratio > cell_ratio:
                            nw = cell_w
                            nh = int(nw / img_ratio)
                        else:
                            nh = cell_h
                            nw = int(nh * img_ratio)
                        
                        img_res = img.resize((nw, nh), Image.LANCZOS)
                        x = c * cell_w + (cell_w - nw) // 2
                        y = r * cell_h + (cell_h - nh) // 2
                        # Paste using the image itself as a mask to preserve transparency
                        canvas.paste(img_res, (x, y), img_res)
                
                file_name = f"Sticker Set ({start_idx + p_idx}).png"
                canvas.save(os.path.join(target_dir, file_name), "PNG")
                self.log(f"Saved {file_name}")
            
            # --- New: Synchronize to Preview folder with Watermark ---
            preview_dir = os.path.join(base, "Preview")
            os.makedirs(preview_dir, exist_ok=True)
            wm_path = self.entry_watermark_path.get().strip()
            
            self.log("Applying watermarks and converting to JPG in Preview folder...")
            for f in os.listdir(target_dir):
                if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')): continue
                
                src_path = os.path.join(target_dir, f)
                # Determine target filename in Preview folder with .jpg extension
                if f.startswith("Sticker Set"):
                    target_name = f.replace("Sticker Set", "Preview")
                else:
                    target_name = f
                
                # Force .jpg extension
                target_name = os.path.splitext(target_name)[0] + ".jpg"
                
                dst_path = os.path.join(preview_dir, target_name)
                self._apply_watermark(src_path, dst_path, wm_path, convert_to_jpg=True)
            
            self.log(f"Step 10: Created {len(pages)} transparent sheets and updated Preview with JPG watermarks.")
        except Exception as e: self.log(f"Preview Error: {e}", error=True)

    def _apply_watermark(self, src, dst, wm_path, convert_to_jpg=False):
        try:
            with Image.open(src) as img:
                img = img.convert("RGBA")
                if wm_path and os.path.exists(wm_path):
                    with Image.open(wm_path) as wm:
                        wm = wm.convert("RGBA")
                        wm.thumbnail(img.size, Image.LANCZOS)
                        x = (img.width - wm.width) // 2
                        y = (img.height - wm.height) // 2
                        img.alpha_composite(wm, (x, y))
                
                if convert_to_jpg:
                    # Create white background for JPG conversion
                    final_img = Image.new("RGB", img.size, (255, 255, 255))
                    final_img.paste(img, mask=img.split()[3]) # Use alpha as mask
                    final_img.save(dst, "JPEG", quality=95)
                else:
                    img.save(dst, "PNG")
        except Exception as e:
            print(f"Error watermarking {src}: {e}")

    def action_element_to_local(self):
        en, ep = self.entry_element_name.get().strip(), self.entry_element_path.get().strip()
        if not en or not ep: self.log("Error: Element Name & Path required.", error=True); return
        dp = os.path.join(os.path.expanduser("~"), "Downloads"); el_d = os.path.join(dp, "elements")
        if not os.path.exists(el_d): self.log("Error: No 'elements' in Downloads", error=True); return
        target_dir = os.path.join(ep, en); os.makedirs(target_dir, exist_ok=True)
        found_any = False
        for root, dirs, files in os.walk(el_d):
            if "upscayl" in root.lower():
                img_files = sorted([f for f in files if os.path.isfile(os.path.join(root, f))])
                for i, it in enumerate(img_files):
                    shutil.copy2(os.path.join(root, it), os.path.join(target_dir, f"{en} ({i+1}){os.path.splitext(it)[1]}"))
                found_any = True
        self._trash(el_d); self.log("Elements moved & cleaned.")

    def action_unzip_downloads(self):
        self.log("Starting Unzip...")
        try:
            dp = os.path.join(os.path.expanduser("~"), "Downloads")
            for zfn in [f for f in os.listdir(dp) if f.lower().endswith('.zip')]:
                zp, ep = os.path.join(dp, zfn), os.path.join(dp, os.path.splitext(zfn)[0])
                with zipfile.ZipFile(zp, 'r') as zr: os.makedirs(ep, exist_ok=True); zr.extractall(ep)
            self.log("Unzip Complete!")
        except Exception as e: self.log(f"Unzip Error: {e}", error=True)

    def action_download_to_local(self):
        folder_name, local_path = self.entry_folder_name.get().strip(), self.entry_local_path.get().strip()
        if not folder_name or not local_path: self.log("Error: Paths required.", error=True); return
        base, downloads_path = os.path.join(local_path, folder_name), os.path.join(os.path.expanduser("~"), "Downloads")
        for search_key, target_sub in [("png", "Sticker Set"), ("jpg", "Preview")]:
            target_dir = os.path.join(base, target_sub)
            if not os.path.exists(target_dir): continue
            matched_folders = [f for f in os.listdir(downloads_path) if os.path.isdir(os.path.join(downloads_path, f)) and f.lower().startswith(search_key)]
            for folder in matched_folders:
                src = os.path.join(downloads_path, folder)
                try:
                    for it in os.listdir(src):
                        if os.path.isfile(os.path.join(src, it)): shutil.copy2(os.path.join(src, it), os.path.join(target_dir, it))
                    self._trash(src)
                except Exception as e: self.log(f"Error folder {folder}: {e}", error=True)
            matched_zips = [f for f in os.listdir(downloads_path) if os.path.isfile(os.path.join(downloads_path, f)) and f.lower().startswith(search_key) and f.lower().endswith(".zip")]
            for zip_file in matched_zips:
                try: self._trash(os.path.join(downloads_path, zip_file))
                except: pass
        pdfs = [f for f in os.listdir(downloads_path) if f.lower().endswith('.pdf')]
        if pdfs:
            pdf_target_dir = os.path.join(base, "Download file")
            if os.path.exists(pdf_target_dir):
                target_pdf = next((p for p in pdfs if "pdf_for_downloading" in p.lower()), pdfs[0])
                try:
                    shutil.copy2(os.path.join(downloads_path, target_pdf), os.path.join(pdf_target_dir, target_pdf))
                    self._trash(os.path.join(downloads_path, target_pdf))
                except: pass
        self.log("Step 13: Finished Copy & Cleanup.")

    def action_local_remote(self): threading.Thread(target=self._run_local_remote).start()

    def _run_local_remote(self):
        try:
            fn, lp, rp = self.entry_folder_name.get().strip(), self.entry_local_path.get().strip(), self.entry_remote_path.get().strip()
            en, ep = self.entry_element_name.get().strip(), self.entry_element_path.get().strip()
            
            if not all([fn, lp, rp, en, ep]): 
                self.log("Error: All fields required.", error=True); return
            
            es = os.path.join(ep, en)
            if not os.path.exists(es): 
                self.log(f"CRITICAL: Elements folder NOT FOUND: {en}", error=True); return

            clean_name = fn.split(" - ", 1)[1] if " - " in fn else fn
            
            self.log("Starting Local to Remote...")
            total_copied = 0
            
            # 1. Copy 4000x4000 and Sticker Set from Local Project to Remote
            for sub in ["4000x4000", "Sticker Set"]:
                s, d = os.path.join(lp, fn, sub), os.path.join(rp, fn, sub)
                if not os.path.exists(s): continue
                os.makedirs(d, exist_ok=True)
                files = sorted([f for f in os.listdir(s) if os.path.isfile(os.path.join(s, f))])
                for i, it in enumerate(files):
                    self.log(f"Copying {sub}: {i+1}/{len(files)}...")
                    ext = os.path.splitext(it)[1]
                    # Always start numbering at (1) on Remote.
                    shutil.copy2(os.path.join(s, it), os.path.join(d, f"{clean_name} ({i+1}){ext}"))
                    total_copied += 1
            
            # 2. Copy Elements from Library to Remote 4000x4000
            rd = os.path.join(rp, fn, "4000x4000")
            os.makedirs(rd, exist_ok=True)
            el_files = sorted([f for f in os.listdir(es) if os.path.isfile(os.path.join(es, f))])
            el_copied = 0
            for i, it in enumerate(el_files):
                self.log(f"Copying Elements: {i+1}/{len(el_files)}...")
                # Keep element filenames as-is.
                shutil.copy2(os.path.join(es, it), os.path.join(rd, it))
                el_copied += 1
                total_copied += 1
            
            self.log(f"Step 14: Done! Copied {total_copied} files total ({el_copied} elements).")
        except Exception as e:
            self.log(f"Error in Local to Remote: {e}", error=True)

    def action_etsy_listing(self):
        self.log("Starting Etsy..."); up, us = self.dropdown_primary.get(), self.dropdown_secondary.get()
        if not self.bot.switch_to_tab_containing("ddcm.litarandfriends.uk"): self.log("Error: No DDCM", error=True); return
        ddcm_fields = [("name", "//div[span[contains(., 'Clipart Name')]]//div[last()]"), ("tag", "//div[span[contains(., 'Tags')]]//div[last()]"), ("description", "//div[span[contains(., 'Description')]]//div[last()]"), ("theme", "//div[span[contains(., 'Theme')]]//div[last()]"), ("price", "//div[span[contains(., 'Price')]]//div[last()]")]
        data = {}
        for fn, xp in ddcm_fields:
            try:
                element = WebDriverWait(self.bot.driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
                data[fn] = element.text.strip(); self.log(f"Extracted {fn}: {data[fn][:30]}...")
            except: self.log(f"Error: ไม่พบข้อมูลช่อง {fn}", error=True); return
        self.bot.driver.switch_to.new_window('tab'); self.bot.driver.get("https://www.etsy.com/your/shops/me/listing-editor/create")
        try: WebDriverWait(self.bot.driver, 20).until(lambda d: "etsy.com" in d.current_url); time.sleep(2)
        except: self.log("Error: Etsy timeout", error=True); return
        setup = [("Category", "//div[contains(@class, 'le-category-action-item') and .//h2[contains(text(), 'Clip Art')]]"), ("Digital", "//label[contains(., 'Digital')]"), ("I did", "//label[contains(., 'I did')]"), ("Supply", "//label[contains(., 'A supply')]"), ("Year", "//select[@id='when-made-select']", "2020_2026"), ("AI", "//label[contains(., 'AI')] | //input[contains(@value, 'ai_gen')] | //label[contains(., 'Yes, I used AI')]")]
        for n, x, *v in setup:
            try:
                el = WebDriverWait(self.bot.driver, 5).until(EC.presence_of_element_located((By.XPATH, x)))
                self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el); time.sleep(0.5)
                if v: from selenium.webdriver.support.ui import Select; Select(el).select_by_value(v[0])
                else: self.bot.driver.execute_script("arguments[0].click();", el)
                time.sleep(0.8)
            except: self.log(f"Etsy Warning at {n}: Proceeding...", error=False); continue
        self.log("Setup finished. Starting data entry...")
        steps = [("INPUT", "//textarea[@id='listing-title-input']", data.get('name', '')), ("INPUT", "//textarea[@id='listing-description-textarea' or @name='description']", data.get('description', '')), ("INPUT", "//input[@id='listing-tags-input']", data.get('tag', '')), ("CLICK", "//button[@id='listing-tags-button']"), ("LOG", "Craft"), ("DELAY", "1"), ("INPUT_BY_LABEL", "Craft type", "Scrapbooking"), ("WAIT", "//label[contains(., 'Scrapbooking')]"), ("SELECT_CHECKBOX", "Scrapbooking"), ("SPECIAL_ESC", ""), ("DELAY", "1"), ("LOG", "Primary"), ("INPUT_BY_LABEL", "Primary color", up), ("WAIT", "//button[@role='menuitemradio']//p[text()='" + up + "']"), ("CLICK", "//button[@role='menuitemradio']//p[text()='" + up + "']"), ("SPECIAL_ESC", ""), ("LOG", "Secondary"), ("INPUT_BY_LABEL", "Secondary color", us), ("WAIT", "//button[@role='menuitemradio']//p[text()='" + us + "']"), ("CLICK", "//button[@role='menuitemradio']//p[text()='" + us + "']"), ("SPECIAL_ESC", ""), ("LOG", "Price"), ("INPUT", "//input[@id='listing-price-input']", data.get('price', '5.99')), ("LOG", "Quantity"), ("INPUT", "//input[@id='listing-quantity-input']", "999"), ("LOG", "Ads Off"), ("OFF_CHECKBOX", "//*[@id='listing-is-promoted-checkbox']"), ("LOG", "Finalizing"), ("SELECT_DROPDOWN", "//select[@id='shop-section-select']", data.get('theme', 'General'))]
        for s in steps:
            cmd, xp = s[0], s[1]
            try:
                if cmd == "LOG": self.log(xp); continue
                if cmd == "DELAY": time.sleep(float(xp)); continue
                if cmd == "SPECIAL_ESC":
                    try: self.bot.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE); self.bot.driver.execute_script("if(document.activeElement) document.activeElement.blur(); document.body.click();")
                    except: pass
                    time.sleep(1); continue
                if cmd == "WAIT": WebDriverWait(self.bot.driver, 15).until(EC.presence_of_element_located((By.XPATH, xp))); continue
                if cmd == "INPUT_BY_LABEL":
                    ln, tt = xp, str(s[2]); ss = [f"//div[.//label[contains(., '{ln}')]]//input", f"//label[contains(., '{ln}')]/following::input[1]", "//input[@placeholder='Type to search…']"]
                    el = None
                    for st in ss:
                        try:
                            tmp = self.bot.driver.find_element(By.XPATH, st)
                            if tmp.is_displayed(): el = tmp; break
                        except: continue
                    if not el: self.log(f"Error: {ln}", error=True); return
                    self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el); time.sleep(0.5); el.click()
                    self.bot.driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", el, tt)
                    el.send_keys(Keys.SPACE); time.sleep(0.1); el.send_keys(Keys.BACKSPACE); continue
                if cmd == "SELECT_CHECKBOX":
                    lt = xp; lb = WebDriverWait(self.bot.driver, 15).until(EC.presence_of_element_located((By.XPATH, f"//label[contains(., '{lt}')]")))
                    cid = lb.get_attribute("for"); cb = self.bot.driver.find_element(By.ID, cid)
                    if not (cb.is_selected() or self.bot.driver.execute_script("return arguments[0].checked;", cb)): self.bot.driver.execute_script("arguments[0].click();", lb)
                    time.sleep(0.5); continue
                if cmd == "OFF_CHECKBOX":
                    cb = WebDriverWait(self.bot.driver, 15).until(EC.presence_of_element_located((By.XPATH, xp)))
                    if cb.is_selected() or self.bot.driver.execute_script("return arguments[0].checked;", cb):
                        try: cb.click()
                        except: self.bot.driver.execute_script("arguments[0].click();", cb)
                    time.sleep(0.5); continue
                if cmd == "SELECT_DROPDOWN":
                    tv = s[2]; el = WebDriverWait(self.bot.driver, 15).until(EC.presence_of_element_located((By.XPATH, xp)))
                    from selenium.webdriver.support.ui import Select; Select(el).select_by_visible_text(tv); time.sleep(0.5); continue
                el = WebDriverWait(self.bot.driver, 15).until(EC.presence_of_element_located((By.XPATH, xp))); self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el); time.sleep(0.5)
                if cmd == "INPUT":
                    tv = str(s[2]); el.click(); time.sleep(0.3)
                    self.bot.driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", el, tv)
                elif cmd == "CLICK":
                    try: el.click()
                    except: self.bot.driver.execute_script("arguments[0].click();", el)
                time.sleep(0.5)
            except Exception as e: self.log(f"Error: {cmd}", error=True); return
        self.log("Etsy Listing populated!")

    def _execute_steps(self, steps):
        for n, xp, *v in steps:
            try:
                el = WebDriverWait(self.bot.driver, 20).until(EC.presence_of_element_located((By.XPATH, xp)))
                self.bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el); time.sleep(0.5)
                if v:
                    val = v[0]
                    if any(k in xp for k in ["Select pages", "spinbutton", "Design title"]):
                        try: el.click()
                        except: self.bot.driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5); self.bot.driver.execute_script("arguments[0].value = '';", el)
                        for _ in range(15): el.send_keys(Keys.BACKSPACE)
                        el.send_keys(val); time.sleep(0.5)
                        if "Design title" in xp or "spinbutton" in xp: el.send_keys(Keys.ENTER)
                        else: el.send_keys(Keys.TAB)
                    else: self.bot.input_text(xp, val)
                else:
                    try: el.click()
                    except: self.bot.driver.execute_script("arguments[0].click();", el)
                self.log(f"Success: {n}"); time.sleep(0.5)
            except Exception as e: self.log(f"Error [{n}]: {str(e)[:50]}", error=True); return False
        return True

    def clipboard_get(self):
        try: return self.selection_get(selection='CLIPBOARD')
        except: return ""

if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    app = App()
    app.mainloop()
