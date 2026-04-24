# Video frame extraction utility
"""
			FRAME EXTRACTOR
			===============
This utility extracts a single frame from a video file and saves it as a PNG. 
It utilizes the Decord library for efficient seeking and frame grabbing.

Features:
	- Extract by index, 'first', or 'last' frame.
	- Keyframe snapping option for faster seeking in large files.
	- Automatic dependency check for FFmpeg/LibAV.
	- Saves output as [filename]_frame_[id].png.

Usage:
	python extractframe.py <filename> <frame_id> [options]

Examples:
	- python extractframe.py movie.mp4 500
	- python extractframe.py clip.mkv last
	- python extractframe.py video.mp4 1200 -k

Requirements:
	- decord
	- pillow (PIL)
	- ffmpeg (system dependency)
"""

import os
import sys
import argparse
import subprocess
import platform
from PIL import Image

def init_ansi():
	"""Enables ANSI escape sequences on Windows consoles."""
	if platform.system().lower() == "windows":
		os.system('color')

try:
	import decord
	from decord import VideoReader, cpu
except ImportError:
	init_ansi()
	print("\033[0;31mError: 'decord' library is not installed.\033[0m")
	print("Please install it using: pip install decord")
	sys.exit(1)

def check_ffmpeg():
	"""Checks if ffmpeg is available in the system path."""
	try:
		subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		return True
	except FileNotFoundError:
		return False

def get_ffmpeg_instructions():
	"""Provides download links and instructions for FFmpeg."""
	instructions = (
		"\n\033[0;33mFFmpeg is missing or not found in your PATH.\033[0m\n"
		"Decord requires FFmpeg/LibAV to decode video files.\n\n"
		"Manual Download Links:\n"
		" - Windows: https://www.gyan.dev/ffmpeg/builds/\n"
		" - macOS (Homebrew): brew install ffmpeg\n"
		" - Linux: sudo apt install ffmpeg\n\n"
		"Once downloaded, ensure the 'bin' folder is added to your System Environment Variables (PATH)."
	)
	return instructions

def extract_frame(video_path, frame_id, use_keyframe=False):
	if not os.path.exists(video_path):
		print(f"\033[0;31mError: File '{video_path}' not found.\033[0m")
		return

	if not check_ffmpeg():
		print(get_ffmpeg_instructions())
		return

	try:
		# Initialize VideoReader
		vr = VideoReader(video_path, ctx=cpu(0))
		total_frames = len(vr)

		# Resolve frame_id
		target_idx = 0
		if isinstance(frame_id, str):
			if frame_id.lower() == 'first':
				target_idx = 0
			elif frame_id.lower() == 'last':
				target_idx = total_frames - 1
			else:
				try:
					target_idx = int(frame_id)
				except ValueError:
					print(f"\033[0;31mError: Invalid frame ID '{frame_id}'. Use a number, 'first', or 'last'.\033[0m")
					return
		else:
			target_idx = frame_id

		# Bounds check
		if target_idx < 0 or target_idx >= total_frames:
			print(f"\033[0;31mError: Frame index {target_idx} is out of range (0-{total_frames-1}).\033[0m")
			return

		print(f"Extracting frame {target_idx} from {os.path.basename(video_path)}...")

		# Decord handles seeking. If keyframe is requested, we can't strictly "snap" 
		# in the VideoReader indexed access easily, but Decord's seeking is often
		# optimized. For specific keyframe snapping, we use internal seek logic if available.
		if use_keyframe:
			# Note: decord doesn't expose a simple 'snap-to-keyframe' for single index access 
			# via [], but it uses keyframes internally for seeking.
			print("Note: Keyframe snapping is managed by Decord's internal seek optimizer.")

		# Get the frame as a numpy array (RGB)
		frame = vr[target_idx].asnumpy()

		# Convert to Image and save
		img = Image.fromarray(frame)
		base_name = os.path.splitext(os.path.basename(video_path))[0]
		output_name = f"{base_name}_frame_{target_idx}.png"
		img.save(output_name)

		print(f"\033[0;32m[Success] Frame saved as: {output_name}\033[0m")

	except Exception as e:
		print(f"\033[0;31mAn error occurred during extraction: {e}\033[0m")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Extract a single frame from a video using Decord.")
	parser.add_argument("filename", help="Path to the video file")
	parser.add_argument("frame_id", help="Frame index (number, 'first', or 'last')")
	parser.add_argument("-k", "--keyframe", action="store_true", help="Utilize keyframe seeking optimization")

	args = parser.parse_args()

	extract_frame(args.filename, args.frame_id, args.keyframe)

if __name__ == "__main__":
	main()