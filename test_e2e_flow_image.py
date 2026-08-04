import os
import sys
import time
import shutil
import tempfile
import subprocess
import httpx
import json

def wait_for_server(port, timeout=15):
    import urllib.request
    start = time.time()
    url = f"http://127.0.0.1:{port}/docs"
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
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    episode_dir = os.path.join(temp_dir, "ton_1_ep_1")
    images_dir = os.path.join(episode_dir, "Images")
    prompts_dir = os.path.join(episode_dir, "Prompts")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(prompts_dir, exist_ok=True)
    
    # Create dummy reference image
    ref_image_path = os.path.join(images_dir, "ref_image.png")
    with open(ref_image_path, "wb") as f:
        f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc` \x05\x00\x00\x0b\x00\x01\x02\x1f\x15\x00\x00\x00\x00IEND\xaeB`\x82')
        
    print(f"Temporary workspace created at: {temp_dir}")
    
    # Start backend server with MOCK_FLOW_CLIENT=1
    print(f"Starting backend server on port {port}...")
    log_file = open("test_server_flow_image.log", "w", encoding="utf-8")
    env = os.environ.copy()
    env["MOCK_FLOW_CLIENT"] = "1"
    env["PORT"] = str(port)
    env["FLOW_AGENT_DB_NAME"] = "flow_agent_test.db"
    
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env
    )
    
    try:
        wait_for_server(port)
        
        # Call generate-image-batch
        print("Calling /api/flow/generate-image-batch endpoint...")
        with httpx.Client(timeout=40.0) as client:
            payload = {
                "prompt": "Create a premium realistic scene of a Thai traditional house",
                "project_id": "mock-project-id-12345",
                "aspect_ratio": "IMAGE_ASPECT_RATIO_PORTRAIT",
                "user_paygate_tier": "PAYGATE_TIER_TWO",
                "reference_images": ["ref_image.png"],
                "model_name": "GEM_PIX_2",
                "quantity": 1,
                "local_path": temp_dir,
                "folder_name": "ton_1_ep_1",
                "round_num": 1,
                "prompt_index": 1
            }
            res = client.post(f"http://127.0.0.1:{port}/api/flow/generate-image-batch", json=payload)
            print("Generate Image Batch status code:", res.status_code)
            print("Response:", res.text)
            
            assert res.status_code == 200
            res_data = res.json()
            assert res_data["success"] is True
            assert len(res_data["media"]) == 1
            media_item = res_data["media"][0]
            assert media_item["filename"] == "01.png"
            assert media_item["media_id"] == "a2948942-2616-4731-a395-d1afac6a87a7"
            
            # Verify 01.png is downloaded
            saved_img_path = os.path.join(images_dir, "01.png")
            assert os.path.isfile(saved_img_path)
            print("PASSED: Verified 01.png has been downloaded locally!")
            
            # Verify flow_media_ids.json is created and correct
            meta_path = os.path.join(images_dir, "flow_media_ids.json")
            assert os.path.isfile(meta_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                assert meta["01.png"] == "a2948942-2616-4731-a395-d1afac6a87a7"
                assert "ref_image.png" not in meta
            # Call generate-image-batch for Round 2 referencing the generated 01.png
            print("Calling /api/flow/generate-image-batch for Round 2 referencing the generated 01.png...")
            payload_r2 = {
                "prompt": "Create another similar Thai house scene",
                "project_id": "mock-project-id-12345",
                "aspect_ratio": "IMAGE_ASPECT_RATIO_PORTRAIT",
                "user_paygate_tier": "PAYGATE_TIER_TWO",
                "reference_images": ["01.png"],
                "model_name": "GEM_PIX_2",
                "quantity": 1,
                "local_path": temp_dir,
                "folder_name": "ton_1_ep_1",
                "round_num": 2,
                "prompt_index": 1
            }
            res_r2 = client.post(f"http://127.0.0.1:{port}/api/flow/generate-image-batch", json=payload_r2)
            print("Generate Image Batch Round 2 status code:", res_r2.status_code)
            print("Round 2 Response:", res_r2.text)
            assert res_r2.status_code == 200
            res_r2_data = res_r2.json()
            assert res_r2_data["success"] is True
            # Verify that the mock client received the correct character_media_ids which contains the media ID of 01.png
            mock_received_ids = res_r2_data.get("_mock_received_character_media_ids")
            assert mock_received_ids == ["a2948942-2616-4731-a395-d1afac6a87a7"]
            print("PASSED: Verified Round 2 successfully reused the cached media ID for 01.png and passed it to Flow client!")

            # Call generate-image-batch with empty/blank reference image paths
            print("Calling /api/flow/generate-image-batch with empty reference strings...")
            payload_empty = {
                "prompt": "Plain landscape scene",
                "project_id": "mock-project-id-12345",
                "aspect_ratio": "IMAGE_ASPECT_RATIO_PORTRAIT",
                "user_paygate_tier": "PAYGATE_TIER_TWO",
                "reference_images": ["", "   "],
                "model_name": "GEM_PIX_2",
                "quantity": 1,
                "local_path": temp_dir,
                "folder_name": "ton_1_ep_1",
                "round_num": 3,
                "prompt_index": 1
            }
            res_empty = client.post(f"http://127.0.0.1:{port}/api/flow/generate-image-batch", json=payload_empty)
            print("Generate Image Batch empty refs status code:", res_empty.status_code)
            assert res_empty.status_code == 200
            res_empty_data = res_empty.json()
            assert res_empty_data["success"] is True
            # Verify no character media IDs were passed to the flow client
            assert res_empty_data.get("_mock_received_character_media_ids") is None
            print("PASSED: Verified empty reference image strings are successfully ignored!")

            # Call /api/batch-uploader/process to verify it reuses the cached media ID
            print("Calling /api/batch-uploader/process to test media ID reuse...")
            process_payload = {
                "project_id": "mock-project-id-12345",
                "orientation": "VERTICAL",
                "pairs": [
                    {
                        "image_path": saved_img_path,
                        "prompt_content": "A high-angle scene of the traditional Thai house."
                    }
                ],
                "video_model": "veo_3_1_i2v_lite_low_priority",
                "upscale_resolution": "NONE"
            }
            res_process = client.post(f"http://127.0.0.1:{port}/api/batch-uploader/process", json=process_payload)
            print("Batch Uploader Process status code:", res_process.status_code)
            print("Process Response:", res_process.text)
            assert res_process.status_code == 200
            print("PASSED: Batch uploader successfully processed the scene and reused cached media ID!")
            
    except Exception as e:
        print(f"E2E test failed: {e}")
        log_file.close()
        with open("test_server_flow_image.log", "r", encoding="utf-8") as f:
            print("--- SERVER LOGS ---")
            print(f.read())
        raise e
    finally:
        log_file.close()
        print("Stopping uvicorn server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("Cleaned up temporary workspace.")
        
        # Clean up test database files
        for suffix in ("", "-wal", "-shm"):
            db_file = os.path.join(os.path.dirname(__file__), f"flow_agent_test.db{suffix}")
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                except Exception:
                    pass
        print("Cleaned up test database files.")

if __name__ == "__main__":
    run_e2e_test()
