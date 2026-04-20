# Timestamped, color-coded image generator.
"""
IMAGE GENERATOR SCRIPT
----------------------
This script generates a batch of images with a solid background color and a 
centralized 'chunky' noise square. It organizes these files into a 
timestamped directory and artificially distributes their 'Modified' 
timestamps across a specific time window (10:00 - 17:00).

USAGE:
1. Run the script: python image_generator.py
2. Provide a 6-digit Hex color code (e.g., FF5733).
3. Specify the number of images to generate.
4. Set a naming prefix for the files.
5. Enter a date in YYYY-MM-DD format.

REQUIREMENTS:
- Pillow library (PIL) (pip install pillow)

DISCLAIMER:
This script was generated with Gemini 3.
"""

import os
import random
from datetime import datetime, timedelta
from PIL import Image

def generate_colored_images():
    # User Inputs
    hex_input = input("Enter RGB hex color (e.g., 3498db): ").strip().lstrip('#')
    
    try:
        rgb = tuple(int(hex_input[i:i+2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        print("Error: Invalid hex color format. Please use 6 characters (e.g., FF5733).")
        return

    try:
        count_input = input("Enter number of images (X): ").strip()
        count = int(count_input)
        if count <= 0:
            print("Error: Amount must be greater than 0.")
            return
    except ValueError:
        print("Error: Amount must be an integer.")
        return

    name_prefix = input("Enter image name prefix (e.g., texture): ").strip()
    if not name_prefix:
        name_prefix = "image"

    date_str = input("Enter date (YYYY-MM-DD): ").strip()
    
    try:
        # Define the time window for image timestamps
        start_time = datetime.strptime(f"{date_str} 10:00:00", "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(f"{date_str} 17:00:00", "%Y-%m-%d %H:%M:%S")
        
        # Create folder name: YYYYMMDD + random HHMM
        folder_date_part = start_time.strftime("%Y%m%d")
        random_hour = random.randint(0, 23)
        random_minute = random.randint(0, 59)
        folder_name = f"{folder_date_part}{random_hour:02d}{random_minute:02d}"
        
    except ValueError:
        print("Error: Invalid date format. Use YYYY-MM-DD.")
        return

    # Create the directory
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        print(f"Created directory: {folder_name}")

    # Image constants
    res = 512
    noise_display_size = int(res * 0.75)
    noise_grid_res = 16 
    start_pos = (res - noise_display_size) // 2

    # Calculate time intervals
    total_seconds = (end_time - start_time).total_seconds()
    interval = total_seconds / (count - 1) if count > 1 else 0

    print(f"Generating {count} images in {folder_name}...")

    for i in range(count):
        file_name = f"{name_prefix}_{i+1:03d}.png"
        file_path = os.path.join(folder_name, file_name)
        
        # 1. Create the base colored image
        img = Image.new('RGB', (res, res), color=rgb)
        
        # 2. Create the noise square
        tiny_noise = Image.new('RGB', (noise_grid_res, noise_grid_res))
        noise_pixels = [
            (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for _ in range(noise_grid_res * noise_grid_res)
        ]
        tiny_noise.putdata(noise_pixels)
        
        chunky_noise = tiny_noise.resize((noise_display_size, noise_display_size), resample=Image.NEAREST)
        img.paste(chunky_noise, (start_pos, start_pos))
        
        # 3. Add a black border
        pixels = img.load()
        border_thickness = 2
        for x in range(start_pos - border_thickness, start_pos + noise_display_size + border_thickness):
            for y in range(start_pos - border_thickness, start_pos + noise_display_size + border_thickness):
                if (x < start_pos or x >= start_pos + noise_display_size or 
                    y < start_pos or y >= start_pos + noise_display_size):
                    if 0 <= x < res and 0 <= y < res:
                        pixels[x, y] = (0, 0, 0)

        img.save(file_path)

        # 4. Calculate target timestamp
        target_dt = start_time + timedelta(seconds=interval * i)
        target_timestamp = target_dt.timestamp()

        # 5. Modify timestamps
        os.utime(file_path, (target_timestamp, target_timestamp))

        print(f"Created {file_path} | Timestamp: {target_dt.strftime('%H:%M:%S')}")

    print(f"\nProcess complete. Files are in: {os.path.abspath(folder_name)}")

if __name__ == "__main__":
    generate_colored_images()