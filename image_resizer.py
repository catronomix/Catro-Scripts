# Batch image resizer
"""
IMAGE RESIZE SCRIPT
----------------------
This script resizes generates all the images in the working folder
saved into a subfolder named Resized{datetime}

USAGE:
Run the script, it will ask for a width and height and fitting options interactively.

REQUIREMENTS:
- Pillow library (PIL) (pip install pillow)

DISCLAIMER:
This script was generated with Gemini 2.5
"""

import os
from PIL import Image
from datetime import datetime
import sys

# --- ANSI Color Codes for Progress Bar ---
class Colors:
    RESET = '\033[0m'
    # Background colors for the progress bar
    BG_GREEN = '\033[48;2;0;128;0m' # Dark Green
    BG_YELLOW = '\033[48;2;255;165;0m' # Orange
    BG_RED = '\033[48;2;255;0;0m' # Red
    BG_BLUE = '\033[48;2;0;0;255m' # Blue (not used in current logic, but good to have)
    BG_GRAY = '\033[48;2;100;100;100m' # Gray for empty part
    TEXT_WHITE = '\033[38;2;255;255;255m' # White text

# --- Helper Functions for User Input ---
def get_integer_input(prompt, min_val=1):
    while True:
        try:
            value = int(input(prompt).strip())
            if value >= min_val:
                return value
            else:
                print(f"Error: Please enter a number greater than or equal to {min_val}.")
        except ValueError:
            print("Error: Invalid input. Please enter an integer.")

def get_choice_input(prompt, choices_list):
    """
    Prompts the user to select from a numbered list of choices.
    """
    while True:
        print(f"\n{prompt}:")
        for i, choice in enumerate(choices_list, 1):
            print(f"  {i}. {choice.capitalize()}")
        
        user_input_raw = input("Enter choice number: ").strip()
        try:
            user_input_num = int(user_input_raw)
            if 1 <= user_input_num <= len(choices_list):
                return choices_list[user_input_num - 1]
            else:
                print("Error: Invalid number. Please choose from the options above.")
        except ValueError:
            print("Error: Invalid input. Please enter a number.")

# --- Image Resizing Logic ---
def resize_and_fit_image(image_path, output_path, target_width, target_height, fit_option, interpolation_method):
    try:
        with Image.open(image_path) as img:
            original_width, original_height = img.size

            if fit_option == 'resize':
                # Simple resize, may change aspect ratio
                resized_img = img.resize((target_width, target_height), Image.LANCZOS)
            elif fit_option == 'crop': # Use the provided interpolation method
                # Resize to fill, then crop
                ratio_w = target_width / original_width
                ratio_h = target_height / original_height
                
                if ratio_w > ratio_h: # Original image is relatively taller than target
                    # Resize based on width, then crop height
                    new_width = target_width
                    new_height = int(original_height * ratio_w)
                    img = img.resize((new_width, new_height), interpolation_method)
                    
                    # Calculate crop box
                    left = 0
                    top = (new_height - target_height) // 2
                    right = new_width
                    bottom = top + target_height
                    resized_img = img.crop((left, top, right, bottom))
                else: # Original image is relatively wider than target
                    # Resize based on height, then crop width
                    new_width = int(original_width * ratio_h)
                    new_height = target_height
                    img = img.resize((new_width, new_height), interpolation_method)
                    
                    # Calculate crop box
                    left = (new_width - target_width) // 2
                    top = 0
                    right = left + target_width
                    bottom = new_height
                    resized_img = img.crop((left, top, right, bottom))
            elif fit_option == 'pad':
                # Resize to fit within, then pad with black
                ratio = min(target_width / original_width, target_height / original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                img = img.resize((new_width, new_height), interpolation_method)
                
                # Create a new blank image with target dimensions and black background
                resized_img = Image.new('RGB', (target_width, target_height), (0, 0, 0))
                
                # Paste the resized image onto the center of the new canvas
                paste_x = (target_width - new_width) // 2
                paste_y = (target_height - new_height) // 2
                resized_img.paste(img, (paste_x, paste_y))
            elif fit_option == 'limit':
                # Keeps aspect ratio, scales down if either dimension exceeds target,
                # but does not scale up if image is smaller than target.
                
                # Check if resizing is actually needed (only scale down if larger)
                if original_width <= target_width and original_height <= target_height:
                    # Image is already smaller than or equal to target, no scaling up.
                    resized_img = img.copy() # Just return a copy of the original
                else:
                    # Calculate ratios to fit within target dimensions
                    ratio_w = target_width / original_width
                    ratio_h = target_height / original_height
                    
                    # Use the smaller ratio to ensure both dimensions fit
                    scale_ratio = min(ratio_w, ratio_h)
                    
                    new_width = int(original_width * scale_ratio)
                    new_height = int(original_height * scale_ratio)
                    
                    resized_img = img.resize((new_width, new_height), interpolation_method)
            else:
                print(f"Warning: Unknown fit option '{fit_option}'. Skipping {os.path.basename(image_path)}.")
                return

            # Save the image, preserving original format if possible, or defaulting to PNG
            # Pillow's save method infers format from extension, but some formats don't support all features (e.g., transparency)
            # For simplicity, we'll just save with the original extension.
            resized_img.save(output_path)
            return True
    except Exception as e:
        print(f"Error processing {os.path.basename(image_path)}: {e}")
        return False

# --- Progress Bar Function ---
def print_progress_bar(iteration, total, filename, length=50):
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    
    # Choose background color based on progress
    if iteration / total < 0.33:
        bg_color = Colors.BG_RED
    elif iteration / total < 0.66:
        bg_color = Colors.BG_YELLOW
    else:
        bg_color = Colors.BG_GREEN
        
    bar = bg_color + Colors.TEXT_WHITE + ' ' * filled_length + Colors.BG_GRAY + ' ' * (length - filled_length) + Colors.RESET
    
    # Clear line before printing to ensure it's always fresh
    # Clear a wider area than the bar itself to handle varying filename lengths
    sys.stdout.write('\r' + ' ' * (length + 100)) 
    sys.stdout.flush()

    sys.stdout.write(f'\r{bar} {percent}% | Processing: {filename[:60]}{"..." if len(filename) > 60 else ""}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n') # New line at the end

# --- Main Script Logic ---
def resize_images_in_folder():
    # Initialize Windows console for ANSI escape sequences
    if os.name == 'nt':
        os.system('')

    print("\n--- Image Resizer Script ---")

    target_width = get_integer_input("Enter target width (pixels): ")
    target_height = get_integer_input("Enter target height (pixels): ")
    fit_option = get_choice_input("Choose fitting option", ['resize', 'crop', 'pad', 'limit'])
    
    interpolation_choices_map = {
        'nearest': Image.NEAREST,
        'bilinear': Image.BILINEAR,
        'bicubic': Image.BICUBIC,
        'lanczos': Image.LANCZOS
    } # The keys are the strings we want to display as choices
    interpolation_method_str = get_choice_input("Choose interpolation method", list(interpolation_choices_map.keys()))

    current_dir = os.getcwd()
    output_folder_name = f"Resized_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = os.path.join(current_dir, output_folder_name)

    os.makedirs(output_path, exist_ok=True)
    print(f"Output directory created: {output_path}")

    # Supported image extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff')
    
    # Find all image files in the current directory
    image_files = [f for f in os.listdir(current_dir) if f.lower().endswith(image_extensions) and os.path.isfile(os.path.join(current_dir, f))]
    
    if not image_files:
        print("No supported image files found in the current directory.")
        return

    total_images = len(image_files)
    print(f"Found {total_images} images to process.")

    interpolation_method = interpolation_choices_map[interpolation_method_str]
    for i, filename in enumerate(image_files):
        input_filepath = os.path.join(current_dir, filename)
        output_filename = filename # Keep original name for now
        output_filepath = os.path.join(output_path, output_filename)

        print_progress_bar(i + 1, total_images, filename)
        resize_and_fit_image(input_filepath, output_filepath, target_width, target_height, fit_option, interpolation_method)

    print(f"\n\nResizing complete. Resized images are in: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    resize_images_in_folder()
