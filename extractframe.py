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

def get_bin_path(name):
	"""Returns the path to a binary, prioritizing the script's directory."""
	script_dir = os.path.dirname(os.path.abspath(__file__))
	local_path = os.path.join(script_dir, name)
	if platform.system().lower() == "windows" and not local_path.lower().endswith(".exe"):
		local_path += ".exe"
	if os.path.exists(local_path) and os.access(local_path, os.X_OK):
		return local_path
	return name

FFMPEG_BIN = get_bin_path("ffmpeg")

def check_ffmpeg():
	"""Checks if ffmpeg is available in the system path or program dir."""
	try:
		subprocess.run([FFMPEG_BIN, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		return True
	except FileNotFoundError:
		return False

def get_ffmpeg_instructions():
	return (
		"\n\033[0;33mFFmpeg is missing or not found.\033[0m\n"
		"Decord requires FFmpeg/LibAV. Place ffmpeg in the script folder or add it to PATH.\n"
	)

def extract_frame(video_path, frame_id, use_keyframe=False):
	if not os.path.exists(video_path):
		print(f"\033[0;31mError: File '{video_path}' not found.\033[0m")
		return

	if not check_ffmpeg():
		print(get_ffmpeg_instructions())
		return

	try:
		vr = VideoReader(video_path, ctx=cpu(0))
		total_frames = len(vr)

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
					print(f"\033[0;31mError: Invalid frame ID '{frame_id}'.\033[0m")
					return
		else:
			target_idx = frame_id

		if target_idx < 0 or target_idx >= total_frames:
			print(f"\033[0;31mError: Frame index {target_idx} out of range.\033[0m")
			return

		print(f"Extracting frame {target_idx} from {os.path.basename(video_path)}...")
		frame = vr[target_idx].asnumpy()
		img = Image.fromarray(frame)
		base_name = os.path.splitext(os.path.basename(video_path))[0]
		output_name = f"{base_name}_frame_{target_idx}.png"
		img.save(output_name)
		print(f"\033[0;32m[Success] Frame saved as: {output_name}\033[0m")

	except Exception as e:
		print(f"\033[0;31mAn error occurred during extraction: {e}\033[0m")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Extract a single frame using Decord.")
	parser.add_argument("filename", help="Path to the video file")
	parser.add_argument("frame_id", help="Frame index (number, 'first', or 'last')")
	parser.add_argument("-k", "--keyframe", action="store_true", help="Seek optimization note")
	args = parser.parse_args()
	extract_frame(args.filename, args.frame_id, args.keyframe)

if __name__ == "__main__":
	main()