# Clone exif data from images
"""
		EXIF Data Cloner
		================
A utility to copy EXIF metadata (camera settings, GPS, timestamps, etc.) 
from a source image to a target image.

Usage:
	python exif_cloner.py <source_path> <target_path>

Requirements:
	- piexif library (pip install piexif)
	- Source and target files must be in a supported format (e.g., JPEG, WebP).

Disclaimer: This script was generated with Gemini 3
"""

import sys
import os

import tui

# Optional dependency: piexif is imported on demand inside copy_exif() so the
# usage path still works on machines where it is not installed.


def copy_exif(source_path, target_path, cap=None):
	"""
	Copies EXIF metadata from source_path to target_path.

	The caller resolves `cap` once per run; a direct call still gets a probe.

	Args:
		source_path (str): Path to the image containing the metadata.
		target_path (str): Path to the image where metadata will be written.
		cap (Capabilities): Capability record for this run.
	"""
	cap = cap or tui.detect()

	# piexif is only needed for an actual copy, so the dependency is checked
	# here (first use) instead of at import time.
	try:
		import piexif
	except ImportError:
		print(tui.status("error", "Error: 'piexif' library is not installed.",
						 cap=cap))
		print(f"Please install it using: {sys.executable} -m pip install piexif")
		sys.exit(1)

	# Convert to absolute paths so the output is clear regardless of where the script is called from
	abs_source = os.path.abspath(source_path)
	abs_target = os.path.abspath(target_path)

	if not os.path.exists(abs_source):
		print(tui.status("error", f"Error: Source file '{abs_source}' does not exist.",
						 cap=cap))
		sys.exit(1)

	if not os.path.exists(abs_target):
		print(tui.status("error", f"Error: Target file '{abs_target}' does not exist.",
						 cap=cap))
		sys.exit(1)

	try:
		# Load EXIF data from the source image
		exif_dict = piexif.load(abs_source)

		# Convert the dictionary back into bytes for insertion
		exif_bytes = piexif.dump(exif_dict)

		# Insert the metadata into the target image
		piexif.insert(exif_bytes, abs_target)

		print(tui.section("Successfully copied EXIF data:", cap=cap))
		print(tui.key_values(None, [("from", abs_source), ("to", abs_target)],
							 cap=cap))

	except Exception as e:
		print(tui.status("error", f"An error occurred: {e}", cap=cap),
			  file=sys.stderr)
		sys.exit(1)


def main():
	tui.init_ansi()
	cap = tui.detect()

	# Ensure exactly two arguments are provided (excluding the script name)
	if len(sys.argv) != 3:
		print("Usage: python exif_cloner.py <source_image_path> <target_image_path>")
		sys.exit(1)

	source_img = sys.argv[1]
	target_img = sys.argv[2]

	copy_exif(source_img, target_img, cap=cap)


if __name__ == "__main__":
	main()
