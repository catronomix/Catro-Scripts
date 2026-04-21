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
import piexif

def copy_exif(source_path, target_path):
	"""
	Copies EXIF metadata from source_path to target_path.
	
	Args:
		source_path (str): Path to the image containing the metadata.
		target_path (str): Path to the image where metadata will be written.
	"""
	# Convert to absolute paths so the output is clear regardless of where the script is called from
	abs_source = os.path.abspath(source_path)
	abs_target = os.path.abspath(target_path)

	if not os.path.exists(abs_source):
		print(f"Error: Source file '{abs_source}' does not exist.")
		return

	if not os.path.exists(abs_target):
		print(f"Error: Target file '{abs_target}' does not exist.")
		return

	try:
		# Load EXIF data from the source image
		exif_dict = piexif.load(abs_source)
		
		# Convert the dictionary back into bytes for insertion
		exif_bytes = piexif.dump(exif_dict)
		
		# Insert the metadata into the target image
		piexif.insert(exif_bytes, abs_target)
		
		print(f"Successfully copied EXIF data from:\n  {abs_source}\nto:\n  {abs_target}")
		
	except Exception as e:
		print(f"An error occurred: {e}")

if __name__ == "__main__":
	# Ensure exactly two arguments are provided (excluding the script name)
	if len(sys.argv) != 3:
		print("Usage: python exif_cloner.py <source_image_path> <target_image_path>")
		sys.exit(1)

	source_img = sys.argv[1]
	target_img = sys.argv[2]

	copy_exif(source_img, target_img)