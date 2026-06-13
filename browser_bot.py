from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

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
            driver_path = ChromeDriverManager().install()
            # Automatically codesign the chromedriver on macOS to prevent SIGKILL (status code -9) crashes
            import subprocess
            try:
                subprocess.run(["codesign", "--force", "--deep", "--sign", "-", driver_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            service = Service(driver_path)
            
            # Add retry logic for connection
            for attempt in range(3):
                try:
                    self.driver = webdriver.Chrome(service=service, options=options)
                    self.wait = WebDriverWait(self.driver, 10) # 10 seconds timeout
                    print("Browser connected/started successfully.")
                    return True
                except Exception as conn_err:
                    print(f"Connection attempt {attempt+1} failed: {conn_err}")
                    time.sleep(2) # Wait before retry
            
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
