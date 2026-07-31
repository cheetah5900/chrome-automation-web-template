import os
import sys
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def wait_for_server(port, timeout=15):
    import urllib.request
    start = time.time()
    url = f"http://127.0.0.1:{port}/"
    while time.time() - start < timeout:
        try:
            res = urllib.request.urlopen(url)
            if res.status == 200:
                print("Server is ready!")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server did not start within {timeout} seconds")

def run_e2e_test():
    port = 9098
    print(f"Starting backend server on port {port}...")
    log_file = open("test_server_lakorn13.log", "w", encoding="utf-8")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file,
        stderr=log_file
    )
    
    driver = None
    try:
        wait_for_server(port)
        
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        print("Launching Selenium headless Chrome...")
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_window_size(1920, 1080)
        
        url = f"http://127.0.0.1:{port}/"
        print(f"Navigating to {url}...")
        driver.get(url)
        
        # Unlock navigation buttons via script injection so we can test other tabs
        print("Injecting script to unlock sidebar navigation tabs...")
        driver.execute_script("""
            document.querySelectorAll('.sidebar-nav-btn').forEach(btn => {
                btn.classList.remove('locked');
                btn.removeAttribute('disabled');
            });
        """)
        
        # Click on Video Gen tab
        print("Switching to Video Gen tab...")
        video_tab_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "tabVideoGenBtn"))
        )
        driver.execute_script("arguments[0].click();", video_tab_btn)
        time.sleep(1.5)
        
        # Select "ละคร" preset from dropdown
        print("Selecting 'ละคร' preset...")
        preset_select = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "flowVideoPresetSelect"))
        )
        # Find option and select it
        for option in preset_select.find_elements(By.TAG_NAME, "option"):
            if option.text == "ละคร":
                option.click()
                break
        time.sleep(1.5)
        
        # Click Scan button
        print("Clicking Scan folder button...")
        scan_btn = driver.find_element(By.ID, "btnScanFlowKit")
        driver.execute_script("arguments[0].click();", scan_btn)
        
        # Wait for scenes to be scanned and rendered in the grid
        print("Waiting for scanned scenes container to load cells...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#scannedPairsContainer img"))
        )
        time.sleep(1)
        
        # Find all filenames rendered under images
        cells = driver.find_elements(By.CSS_SELECTOR, "#scannedPairsContainer > div > div")
        print(f"Found {len(cells)} scene cells.")
        
        # Inspect first cell's filename
        first_cell_text = cells[0].find_elements(By.TAG_NAME, "div")[-1].text
        print(f"First scene filename: '{first_cell_text}'")
        
        # Assert that the first scene is 01.png or starts with 01
        assert "01" in first_cell_text, f"Expected scene 01, but got: {first_cell_text}"
        print("PASSED: Verified '01.png' is sorted first in the list!")
        
        # Print ordering of the first few cells for visual confirmation
        print("First 5 cells order:")
        for idx, cell in enumerate(cells[:5]):
            txt = cell.find_elements(By.TAG_NAME, "div")[-1].text
            print(f" - Cell {idx+1}: {txt}")
            
    except Exception as e:
        print(f"Exception encountered: {e}")
        if driver:
            try:
                logs = driver.get_log("browser")
                print("--- BROWSER CONSOLE LOGS ---")
                for log_entry in logs:
                     print(log_entry)
            except Exception:
                pass
        raise e
    finally:
        if driver:
            driver.quit()
        log_file.close()
        print("Stopping uvicorn server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

if __name__ == "__main__":
    run_e2e_test()
