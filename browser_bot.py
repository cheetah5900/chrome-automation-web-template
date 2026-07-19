from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

_cached_driver_path = None

class BrowserBot:
    def __init__(self):
        self.driver = None
        self.wait = None

    def start_browser(self, attach=False, port=9222):
        """Starts the Chrome browser or connects to an existing one."""
        if self.driver is not None:
            return  # Already started

        options = webdriver.ChromeOptions()
        
        if attach:
            # Connect to existing Chrome opened with --remote-debugging-port
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            print(f"Attempting to attach to existing Chrome on port {port}...")
        else:
            # Opens a new Chrome window
            options.add_argument("--start-maximized")
            options.add_experimental_option("detach", True)

        try:
            import os
            import json
            import re
            import urllib.request
            import zipfile
            import platform
            import subprocess
            from pathlib import Path
            
            # 1. Determine active browser type
            browser_type = "chrome"
            base_dir = Path(__file__).resolve().parent
            defaults_file = base_dir / "runtime" / "defaults.json"
            profiles_file = base_dir / "runtime" / "profiles.json"
            try:
                if defaults_file.exists() and profiles_file.exists():
                    defaults = json.loads(defaults_file.read_text())
                    selected_name = defaults.get("selected_profile", "")
                    if selected_name:
                        profiles_data = json.loads(profiles_file.read_text())
                        profiles = profiles_data.get("profiles", [])
                        profile = next((p for p in profiles if p.get("name") == selected_name), None)
                        if profile:
                            browser_type = profile.get("browser_type", "chrome")
            except Exception:
                pass

            # 2. Get milestone of the selected browser dynamically on macOS
            milestone = None
            binary = None
            sys_name = platform.system()
            
            if sys_name == "Darwin":
                paths = {
                    "canary": "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
                    "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                    "edge": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
                }
                binary = paths.get(browser_type)

            if binary and Path(binary).exists():
                try:
                    res = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5)
                    out = res.stdout.strip()
                    m = re.search(r"(\d+)\.\d+", out)
                    if m:
                        milestone = int(m.group(1))
                except Exception:
                    pass
                    
                if milestone is None and sys_name == "Darwin":
                    try:
                        plist_path = binary.split("/Contents/MacOS/")[0] + "/Contents/Info.plist"
                        if Path(plist_path).exists():
                            res = subprocess.run(["defaults", "read", plist_path, "CFBundleShortVersionString"], capture_output=True, text=True, timeout=5)
                            out = res.stdout.strip()
                            m = re.search(r"^(\d+)", out)
                            if m:
                                milestone = int(m.group(1))
                    except Exception:
                        pass

            # 3. Resolve driver path using Google CFT per milestone (macOS only)
            driver_path = None
            if milestone and sys_name == "Darwin":
                print(f"Detected macOS browser milestone version: {milestone}")
                drivers_dir = base_dir / "runtime" / "matched_drivers"
                drivers_dir.mkdir(parents=True, exist_ok=True)
                
                # Fetch matching CFT version
                version = None
                try:
                    url = "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone.json"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode('utf-8'))
                        milestone_data = data.get("milestones", {}).get(str(milestone))
                        if milestone_data:
                            version = milestone_data.get("version")
                except Exception as e:
                    print(f"Error fetching milestone version: {e}")
                    
                if version:
                    # Detect Apple Silicon (M1/M2/M3/M4) vs Intel dynamically
                    is_arm = platform.machine() == 'arm64' or platform.processor() == 'arm'
                    platform_name = "mac-arm64" if is_arm else "mac-x64"
                    driver_exe = "chromedriver"
                    
                    driver_bin_path = drivers_dir / f"chromedriver-{version}" / f"chromedriver-{platform_name}" / driver_exe
                    if driver_bin_path.exists():
                        try:
                            os.chmod(driver_bin_path, 0o755)
                            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(driver_bin_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except Exception:
                            pass
                        driver_path = str(driver_bin_path)
                        print(f"Using matched ChromeDriver for macOS: {driver_path}")
                    else:
                        zip_url = f"https://storage.googleapis.com/chrome-for-testing-public/{version}/{platform_name}/chromedriver-{platform_name}.zip"
                        zip_file_path = drivers_dir / f"chromedriver-{version}.zip"
                        
                        print(f"Downloading matched ChromeDriver version {version} ({platform_name}) from CFT...")
                        try:
                            urllib.request.urlretrieve(zip_url, zip_file_path)
                            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                                zip_ref.extractall(drivers_dir / f"chromedriver-{version}")
                                
                            if driver_bin_path.exists():
                                subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(driver_bin_path)], check=False)
                                os.chmod(driver_bin_path, 0o755)
                                driver_path = str(driver_bin_path)
                                print(f"Successfully installed matched ChromeDriver for macOS: {driver_path}")
                                
                            if zip_file_path.exists():
                                zip_file_path.unlink()
                        except Exception as download_err:
                            print(f"Failed to download matched ChromeDriver: {download_err}")
                            if zip_file_path.exists():
                                zip_file_path.unlink()

            # 4. Fallback to Selenium Manager if no custom driver resolved
            service = None
            if driver_path:
                service = Service(driver_path, args=["--disable-build-check"])
                print(f"Starting Chrome with Service pointing to custom driver: {driver_path}")
            else:
                print("No custom macOS driver path resolved. Falling back to Selenium Manager (built-in)...")

            # Add retry logic for connection (optimized timeout)
            for attempt in range(2):
                try:
                    if service:
                        self.driver = webdriver.Chrome(service=service, options=options)
                    else:
                        self.driver = webdriver.Chrome(options=options)
                    self.wait = WebDriverWait(self.driver, 5) # 5 seconds timeout
                    print("Browser connected/started successfully.")
                    return True
                except Exception as conn_err:
                    print(f"Connection attempt {attempt+1} failed: {conn_err}")
                    time.sleep(0.5) # Wait before retry
            
            print("All connection attempts failed.")
            return False

        except Exception as e:
            print(f"Critical error in driver setup: {e}")
            import traceback
            traceback.print_exc()
            return False

    def open_url(self, url):
        """Navigates to a specific URL."""
        if self.driver:
            self.driver.get(url)
            print(f"Opened {url}")

    def click_element(self, xpath, timeout=10):
        """Clicks an element specified by its XPath."""
        if not self.driver:
            print("Error: Browser not started.")
            return False

        try:
            element = WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            element.click()
            print(f"Clicked element at: {xpath}")
            return True
        except Exception as e:
            print(f"Error clicking {xpath}: {e}")
            return False

    def input_text(self, xpath, text, timeout=10):
        """Inputs text into an element specified by its XPath."""
        if not self.driver:
            print("Error: Browser not started.")
            return False

        try:
            element = WebDriverWait(self.driver, timeout).until(EC.visibility_of_element_located((By.XPATH, xpath)))
            element.clear()
            element.send_keys(text)
            print(f"Inputted '{text}' at: {xpath}")
            return True
        except Exception as e:
            print(f"Error inputting text at {xpath}: {e}")
            return False

    def get_current_url(self):
        """Returns the current URL."""
        if self.driver:
            return self.driver.current_url
        return ""

    def switch_to_tab_containing(self, url_part):
        """Switches to a tab that contains the given string in its URL."""
        if not self.driver:
            return False
            
        print(f"Switching to tab containing '{url_part}'...")
        
        try:
            # Optimization: Check current tab first!
            # If we are already there, don't flicker.
            if url_part in self.driver.current_url:
                print(f"Already on tab: {self.driver.current_url}")
                return True
        except Exception:
            pass # Handle might be stale/closed, proceed to search loop

        try:
            # Get all window handles
            handles = self.driver.window_handles
            
            # Iterate through all handles to find the match
            for handle in handles:
                try:
                    self.driver.switch_to.window(handle)
                    if url_part in self.driver.current_url:
                        print(f"Found tab: {self.driver.title} ({self.driver.current_url})")
                        return True
                except Exception as e:
                    print(f"Error accessing tab {handle}: {e}")
                    continue

        except Exception as e:
            print(f"Critical error during tab switch: {e}")
            if "invalid session id" in str(e).lower():
                raise
            return False
            
        print(f"Tab containing '{url_part}' NOT found.")
        return False

    def execute_script(self, script, element=None):
         if self.driver:
            if element:
                return self.driver.execute_script(script, element)
            return self.driver.execute_script(script)

    def close_browser(self):
        """Closes the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            print("Browser closed.")
