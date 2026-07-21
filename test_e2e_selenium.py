import os
import sys
import json
import time
import subprocess
import socket
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
    port = 9099
    
    # 1. Start FastAPI server on port 9099
    print(f"Starting backend server on port {port}...")
    log_file = open("test_server.log", "w", encoding="utf-8")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file,
        stderr=log_file
    )
    
    driver = None
    try:
        # Wait for uvicorn to boot up
        wait_for_server(port)
        
        # 2. Setup Headless Chrome Options
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

        # Verify ChatGPT download button and starting index input are present
        download_btn = driver.find_element(By.ID, "btn_chatgpt_download")
        start_num_input = driver.find_element(By.ID, "chatgpt_download_start_num")
        assert download_btn is not None, "ChatGPT download button not found"
        assert start_num_input is not None, "ChatGPT starting number input not found"
        default_start_num = start_num_input.get_attribute("value")
        print(f"Verified ChatGPT download starting number default value is: {default_start_num}")
        assert default_start_num == "1", f"Expected default starting number 1, got {default_start_num}"

        # Switch to Video Helper tab
        print("Switching to Video Helper tab...")
        tab_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "tabVideoHelperBtn"))
        )
        driver.execute_script("arguments[0].click();", tab_btn)
        time.sleep(1)
        
        # Wait for page elements to load
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "videoSpeedText"))
        )
        
        # Verify default speed input is 1.0
        speed_input = driver.find_element(By.ID, "videoSpeedText")
        default_val = speed_input.get_attribute("value")
        print(f"Verified default speed value is: {default_val}")
        assert default_val == "1.0", f"Expected default speed 1.0, got {default_val}"
        
        # Verify preset dropdown starts hidden (default Cover mode)
        presets_group = driver.find_element(By.ID, "videoPresetsGroup")
        assert "hidden" in presets_group.get_attribute("class"), "Presets group should be hidden initially"
        print("Verified Presets group is hidden by default in Cover Mode.")
        
        # Select "Combine" mode radio
        combine_radio = driver.find_element(By.XPATH, "//input[@name='videoHelperMode' and @value='combine']")
        driver.execute_script("arguments[0].click();", combine_radio)
        time.sleep(1) # wait for DOM updates
        
        # Verify preset dropdown is unhidden
        assert "hidden" not in presets_group.get_attribute("class"), "Presets group should be unhidden in Combine Mode"
        print("Verified Presets group is shown in Combine Mode.")
        
        # Type speed factor 2.5
        print("Changing speed factor to 2.5...")
        speed_input.clear()
        speed_input.send_keys("2.5")
        time.sleep(0.5)
        
        # Verify dynamic tooltip contains (เร่งความเร็ว 2.5 เท่า)
        tooltip = driver.find_element(By.ID, "tooltip_runVideoHelperBtn")
        tooltip_text = tooltip.get_attribute("textContent")
        print(f"Tooltip text: {tooltip_text}")
        assert "(เร่งความเร็ว 2.5 เท่า)" in tooltip_text, "Tooltip did not dynamically update with speed factor!"
        print("Verified dynamic tooltip updates correctly!")
        
        # Save as Default speed
        print("Clicking Set Default speed button...")
        set_default_btn = driver.find_element(By.ID, "setVideoSpeedDefaultBtn")
        driver.execute_script("arguments[0].click();", set_default_btn)
        
        # Verify console log message is written
        print("Waiting for console log output...")
        WebDriverWait(driver, 5).until(
            lambda d: "Video speed default saved: 2.5" in d.find_element(By.ID, "videoConsole").get_attribute("textContent")
        )
        print("Verified default speed saved message in UI console box!")
        
        print("\nALL E2E SELENIUM TESTS PASSED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"Exception encountered during E2E test: {e}")
        if driver:
            try:
                logs = driver.get_log("browser")
                print("--- BROWSER CONSOLE LOGS ---")
                for log_entry in logs:
                    print(log_entry)
            except Exception as le:
                print(f"Could not retrieve browser logs: {le}")
        
        # Read server output
        try:
            log_file.close()
            with open("test_server.log", "r", encoding="utf-8") as lf:
                print("--- SERVER LOGS ---")
                print(lf.read())
        except Exception as se:
            print(f"Could not retrieve server output: {se}")
        raise e
    finally:
        if driver:
            driver.quit()
        try:
            log_file.close()
        except Exception:
            pass
        print("Stopping uvicorn server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

if __name__ == "__main__":
    run_e2e_test()
