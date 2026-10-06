import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from flow_video_generator import generate_video_flow, DEFAULT_API_BASE, DEFAULT_PROJECT_ID

sb_dir = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย/32/6 - Storyboards/EP01"
ots_img = os.path.join(sb_dir, "EP01_Scene_32_ots.jpg")
out_video = "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย/32/7 - Videos/EP01/32 - Scene 32.mp4"

prompt = "Over-the-shoulder medium two-shot as the dignified chairman looks past the manager with wide eyes in sudden astonishment, showroom cars in background. (ท่านประธาน มองข้ามไหล่ผู้จัดการด้วยความตกตะลึง)"

print("Starting generation of Scene 32 with OTS image...")
res = generate_video_flow(
    image_path=ots_img,
    prompt=prompt,
    output_path=out_video,
    api_base=DEFAULT_API_BASE,
    project_id=DEFAULT_PROJECT_ID,
    aspect_ratio="9:16",
    skip_upload=False
)
print("Result:", res)
