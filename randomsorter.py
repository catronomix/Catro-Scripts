"""
RANDOM IMAGE SORTER
-------------------
This script renames and distributes images within the current working directory. 
It identifies common image files, renames them to unique random 6-digit 
identifiers to anonymize/shuffle them, and then moves them into subfolders 
(reeks1, reeks2, etc.) based on user-defined quantities.

SUPPORTED TYPES:
.jpg, .jpeg, .png, .webp, .gif, .bmp, .tiff

USAGE:
1. Open a terminal/command prompt in the folder containing your images.
2. Run the script followed by the number of images you want in each subfolder.
   Example: python randomsorter.py 10 5 20
   
3. To filter by a specific extension only:
   Example: python randomsorter.py 10 5 --ext .png

DISCLAIMER:
This script was generated with Gemini 3.
"""

import os
import random
import argparse

# List of most common image extensions
DEFAULT_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff')

def rename_images_in_folder(folder_path, allowed_extensions):
    """
    Renames all supported image types in the specified folder to a random 6-digit number.
    """
    used_names = set()
    # List directory first to avoid issues with renaming while iterating
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(allowed_extensions)]
    
    if not files:
        print(f"No images found with extensions {allowed_extensions} to rename.")
        return

    for filename in files:
        extension = os.path.splitext(filename)[1]
        new_name = f"{random.randint(100000, 999999)}{extension}"
        
        # Ensure the new name is unique within the folder and current session
        while new_name in used_names or os.path.exists(os.path.join(folder_path, new_name)):
            new_name = f"{random.randint(100000, 999999)}{extension}"
        
        used_names.add(new_name)
        old_path = os.path.join(folder_path, filename)
        new_path = os.path.join(folder_path, new_name)
        os.rename(old_path, new_path)
        print(f"Renamed: {filename} -> {new_name}")

def distribute_images(folder_path, counts, allowed_extensions):
    """
    Shuffles images and distributes them into subfolders (reeks1, reeks2, etc.) 
    based on the provided count arguments.
    """
    # First, perform the random renaming to ensure everything is shuffled and unique
    rename_images_in_folder(folder_path, allowed_extensions)
    
    # Get the newly renamed list of images
    images = [f for f in os.listdir(folder_path) if f.lower().endswith(allowed_extensions)]
    random.shuffle(images)

    if not images:
        print("No images available to distribute.")
        return

    for i, count in enumerate(counts):
        subfolder_name = f"reeks{i + 1}"
        subfolder_path = os.path.join(folder_path, subfolder_name)
        os.makedirs(subfolder_path, exist_ok=True)

        print(f"\nPopulating {subfolder_name} with {count} images...")
        for _ in range(count):
            if images:
                image = images.pop()
                old_path = os.path.join(folder_path, image)
                new_path = os.path.join(subfolder_path, image)
                os.rename(old_path, new_path)
                print(f"Moved: {image} -> {subfolder_name}")
            else:
                print("Warning: No more images left to distribute.")
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename and distribute images into subfolders.")
    parser.add_argument("counts", metavar="N", type=int, nargs="+", help="List of integers specifying the number of images per subfolder.")
    parser.add_argument("-e", "--ext", type=str, help="Filter for a specific extension only (e.g., .jpg or .png)")
    args = parser.parse_args()

    # Determine which extensions to look for
    if args.ext:
        # Ensure the extension starts with a dot
        target_ext = args.ext if args.ext.startswith('.') else f".{args.ext}"
        allowed = (target_ext.lower(),)
    else:
        allowed = DEFAULT_EXTENSIONS

    current_folder = os.getcwd()
    distribute_images(current_folder, args.counts, allowed)
    print("\nProcessing complete.")