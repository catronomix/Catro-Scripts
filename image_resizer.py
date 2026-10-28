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
"""

import os
import sys
import argparse
from datetime import datetime

import tui

# Optional dependency, imported on demand inside main() so that --help works
# without pillow installed.
Image = None

# Choices offered by the interactive prompts. The order is the numbering the
# user sees, so it must not be sorted.
FIT_OPTIONS = ('resize', 'crop', 'pad', 'limit')
INTERPOLATION_OPTIONS = ('nearest', 'bilinear', 'bicubic', 'lanczos')

# Sanity bound for the pixel size prompts: anything larger is a typo, not a
# target resolution.
MAX_DIMENSION = 32768

# --- Image Resizing Logic ---
def resize_and_fit_image(image_path, output_path, target_width, target_height, fit_option, interpolation_method, cap=None):
	try:
		with Image.open(image_path) as img:
			original_width, original_height = img.size

			if fit_option == 'resize':
				resized_img = img.resize((target_width, target_height), Image.LANCZOS)
			elif fit_option == 'crop':
				ratio_w = target_width / original_width
				ratio_h = target_height / original_height
				
				if ratio_w > ratio_h:
					new_width = target_width
					new_height = int(original_height * ratio_w)
					img = img.resize((new_width, new_height), interpolation_method)
					left = 0
					top = (new_height - target_height) // 2
					right = new_width
					bottom = top + target_height
					resized_img = img.crop((left, top, right, bottom))
				else:
					new_width = int(original_width * ratio_h)
					new_height = target_height
					img = img.resize((new_width, new_height), interpolation_method)
					left = (new_width - target_width) // 2
					top = 0
					right = left + target_width
					bottom = new_height
					resized_img = img.crop((left, top, right, bottom))
			elif fit_option == 'pad':
				ratio = min(target_width / original_width, target_height / original_height)
				new_width = int(original_width * ratio)
				new_height = int(original_height * ratio)
				img = img.resize((new_width, new_height), interpolation_method)
				resized_img = Image.new('RGB', (target_width, target_height), (0, 0, 0))
				paste_x = (target_width - new_width) // 2
				paste_y = (target_height - new_height) // 2
				resized_img.paste(img, (paste_x, paste_y))
			elif fit_option == 'limit':
				if original_width <= target_width and original_height <= target_height:
					resized_img = img.copy()
				else:
					ratio_w = target_width / original_width
					ratio_h = target_height / original_height
					scale_ratio = min(ratio_w, ratio_h)
					new_width = int(original_width * scale_ratio)
					new_height = int(original_height * scale_ratio)
					resized_img = img.resize((new_width, new_height), interpolation_method)
			else:
				return False

			resized_img.save(output_path)
			return True
	except Exception as e:
		print(tui.status("error",
						 f"Error processing {os.path.basename(image_path)}: {e}",
						 cap=cap))
		return False

# --- Main Script Logic ---
def resize_images_in_folder(cap):
	print()
	# Masthead + rule come from the shared page chrome, so the selected theme
	# paints this page exactly like every other script's.
	print(tui.header("Image Resizer", "Resize every image in this folder", cap=cap))

	# Supported image extensions
	image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff')
	current_dir = os.getcwd()
	
	# Check for images BEFORE asking for parameters or creating folders
	image_files = [f for f in os.listdir(current_dir) if f.lower().endswith(image_extensions) and os.path.isfile(os.path.join(current_dir, f))]
	
	if not image_files:
		print(tui.status("warn",
						 "No supported image files found in the current directory.",
						 cap=cap))
		return

	# Prompts come from tui.prompts, so validation, cancellation and styling
	# are shared with the rest of the suite instead of a local input loop.
	target_width = tui.ask_int("Enter target width (pixels)", 1, MAX_DIMENSION)
	if target_width is None:
		return
	target_height = tui.ask_int("Enter target height (pixels)", 1, MAX_DIMENSION)
	if target_height is None:
		return

	fit_index = tui.ask_choice("Choose fitting option", FIT_OPTIONS)
	if fit_index is None:
		return
	fit_option = FIT_OPTIONS[fit_index]
	
	interpolation_choices_map = {
		'nearest': Image.NEAREST,
		'bilinear': Image.BILINEAR,
		'bicubic': Image.BICUBIC,
		'lanczos': Image.LANCZOS
	}
	method_index = tui.ask_choice("Choose interpolation method",
								  INTERPOLATION_OPTIONS)
	if method_index is None:
		return
	interpolation_method_str = INTERPOLATION_OPTIONS[method_index]

	output_folder_name = f"Resized_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
	output_path = os.path.join(current_dir, output_folder_name)

	# Create output directory only now that we are ready to process
	os.makedirs(output_path, exist_ok=True)
	print(tui.status("ok", f"Output directory created: {output_path}", cap=cap))

	total_images = len(image_files)
	print(tui.field("Found", f"{total_images} images to process", cap=cap))

	interpolation_method = interpolation_choices_map[interpolation_method_str]

	# tui.ProgressBar owns the bar layout, the colours and the non-tty
	# degradation (one final line, never a carriage-return animation).
	progress = tui.ProgressBar(total_images, cap=cap, label="Resizing")
	for i, filename in enumerate(image_files):
		input_filepath = os.path.join(current_dir, filename)
		output_filepath = os.path.join(output_path, filename)

		progress.update(i + 1, label=f"Processing: {filename}")
		resize_and_fit_image(input_filepath, output_filepath, target_width, target_height, fit_option, interpolation_method, cap=cap)
	progress.finish()

	print()
	print(tui.panel(None, [tui.status(
		"ok",
		f"Resizing complete. Resized images are in: "
		f"{os.path.abspath(output_path)}",
		cap=cap)], cap=cap))

def main():
	# parse_args() first so --help works without pillow or a terminal.
	parser = argparse.ArgumentParser(
		description="Batch resize every image in the working folder."
	)
	parser.parse_args()

	# Refuse a non-terminal before anything else: the dependency check below
	# would otherwise print to a pipe and hide the real problem.
	tui.require_tty("image_resizer")

	# Capabilities are resolved once: the whole run uses one colour level,
	# Unicode decision and plain/tty mode.
	tui.init_ansi()
	cap = tui.detect()

	# Pillow is only needed for an actual run.
	global Image
	try:
		from PIL import Image
	except ImportError:
		print(tui.status("error", "Error: 'pillow' library is not installed.",
						 cap=cap))
		print("Please install it using: pip install pillow")
		sys.exit(1)

	resize_images_in_folder(cap)

if __name__ == "__main__":
	main()
