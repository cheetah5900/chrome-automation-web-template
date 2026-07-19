import os
import sys
import json
import subprocess
import shutil
from fastapi import HTTPException

# Set working directory to project root so we can import app
sys.path.append(os.getcwd())

from app.main import make_video_cover

def run_test():
    print("Testing view_channel logic (divisibility validation and chunk looping)...")
    
    # 1. Prepare test files in /tmp
    # We need /tmp/test_vid.mp4 (10s) and /tmp/test_audio.mp3 (5s).
    if not os.path.exists("/tmp/test_vid.mp4"):
        print("Creating /tmp/test_vid.mp4...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:d=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "/tmp/test_vid.mp4"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not os.path.exists("/tmp/test_audio.mp3"):
        print("Creating /tmp/test_audio.mp3...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=5",
            "-c:a", "mp3", "/tmp/test_audio.mp3"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    test_folder = "/tmp/test_view_channel_folder"
    if os.path.exists(test_folder):
        shutil.rmtree(test_folder)
    os.makedirs(test_folder, exist_ok=True)

    # TEST A: Divisibility by 5 validation (should error with 4 videos)
    print("\n--- Test A: Divisibility validation ---")
    for i in range(1, 5):
        os.system(f"cp /tmp/test_vid.mp4 {test_folder}/{i}.mp4")
        
    try:
        print("Calling make_video_cover with 4 videos...")
        make_video_cover(
            folders_json=json.dumps([test_folder]),
            mode="combine",
            sub_mode="view_channel",
            amount="5",
            durations_json=json.dumps(["2", "2", "2", "2", "2"]),
            audio_path="/tmp/test_audio.mp3",
            output_path="/tmp/test_view_channel_output.mp4",
            video=None, image=None, video_path=None, image_path=None, prefix=None,
            no=None, suffix=None, folder_range=None, audio_boost=None, overwrite=None, job_id=None
        )
        print("FAILED: Did not raise error for 4 videos!")
        sys.exit(1)
    except HTTPException as e:
        print(f"PASSED: Correctly caught HTTPException: {e.status_code} - {e.detail}")
        if "หารด้วย 5 ลงตัว" not in e.detail:
            print("FAILED: Error message doesn't explain divisibility requirement.")
            sys.exit(1)

    # TEST B: Single chunk of 5 videos (should output folderName_combined.mp4)
    print("\n--- Test B: Single chunk (5 videos) ---")
    os.system(f"cp /tmp/test_vid.mp4 {test_folder}/5.mp4") # add the 5th video
    
    output_path = "/tmp/test_view_channel_output.mp4"
    actual_output_path = f"{test_folder}/test_view_channel_folder_combined.mp4"
    if os.path.exists(actual_output_path):
        os.remove(actual_output_path)
        
    try:
        print("Calling make_video_cover with 5 videos...")
        make_video_cover(
            folders_json=json.dumps([test_folder]),
            mode="combine",
            sub_mode="view_channel",
            amount="5",
            durations_json=json.dumps(["2", "2", "2", "2", "2"]),
            audio_path="/tmp/test_audio.mp3",
            output_path=output_path,
            video=None, image=None, video_path=None, image_path=None, prefix=None,
            no=None, suffix=None, folder_range=None, audio_boost=None, overwrite=None, job_id=None
        )
        
        if os.path.exists(actual_output_path):
            print(f"PASSED: File generated at {actual_output_path}")
        else:
            print(f"FAILED: Expected file not found at {actual_output_path}")
            sys.exit(1)
    except Exception as e:
        print(f"FAILED with exception: {e}")
        sys.exit(1)

    # TEST C: Multiple chunks (10 videos -> should output _1.mp4 and _2.mp4)
    print("\n--- Test C: Multiple chunks (10 videos) ---")
    for i in range(6, 11):
        os.system(f"cp /tmp/test_vid.mp4 {test_folder}/{i}.mp4")
        
    actual_output_1 = f"{test_folder}/test_view_channel_folder_combined_1.mp4"
    actual_output_2 = f"{test_folder}/test_view_channel_folder_combined_2.mp4"
    if os.path.exists(actual_output_1): os.remove(actual_output_1)
    if os.path.exists(actual_output_2): os.remove(actual_output_2)
    
    try:
        print("Calling make_video_cover with 10 videos...")
        make_video_cover(
            folders_json=json.dumps([test_folder]),
            mode="combine",
            sub_mode="view_channel",
            amount="5",
            durations_json=json.dumps(["2", "2", "2", "2", "2"]),
            audio_path="/tmp/test_audio.mp3",
            output_path=output_path,
            video=None, image=None, video_path=None, image_path=None, prefix=None,
            no=None, suffix=None, folder_range=None, audio_boost=None, overwrite=None, job_id=None
        )
        
        if os.path.exists(actual_output_1) and os.path.exists(actual_output_2):
            print(f"PASSED: Both files generated successfully:\n - {actual_output_1}\n - {actual_output_2}")
        else:
            print(f"FAILED: Output files not found. Exist status: _1: {os.path.exists(actual_output_1)}, _2: {os.path.exists(actual_output_2)}")
            sys.exit(1)
    except Exception as e:
        print(f"FAILED with exception: {e}")
        sys.exit(1)

    print("\nALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_test()
