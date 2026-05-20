# Video frame extraction utility
"""
			VIDEOFRAMES: EXTRACT FRAMES FROM VIDEO
			===============
This utility extracts frames from a video file and saves them as PNG images. 
It utilizes the Decord library for efficient seeking and frame grabbing.

Features:
	- Extract a single frame by index, 'first', or 'last'.
	- Extract multiple frames with a specified frame interval (-i / --interval).
	- Extract a specific number of evenly spread frames (-t / --total).
	- Keyframe snapping and optimization (-k / --keyframe) for fast seek operations.
	- Automatic dependency check for FFmpeg/LibAV.
	- Saves outputs as [filename]_frame_[id].png.

Usage:
	python videoframes.py <filename> [<frame_id>] [flags]

Arguments:
	filename             Path to the input video file.
	frame_id             (Optional) The frame index to extract. Accepts an integer (e.g., 500),
	                     'first' for the initial frame, or 'last' for the final frame.
	                     Mutually exclusive with -i and -t.

Flags:
	-k, --keyframe       Enables keyframe optimization. 
	                     - With <frame_id>: snaps to the nearest keyframe.
	                     - With -i or -t: limits the extraction pool to keyframes only,
	                       which can drastically reduce and accelerate extraction.
	-i, --interval N     Extract all frames (or keyframes if -k is active) with a specified
	                     interval of N frames. Mutually exclusive with <frame_id> and -t.
	-t, --total N        Extract exactly N frames (or keyframes if -k is active) evenly spread
	                     across the video, including the first and last.
	                     Mutually exclusive with <frame_id> and -i.

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

def extract_frames(video_path, frame_id=None, use_keyframe=False, interval=None, total=None):
	if not os.path.exists(video_path):
		print(f"\033[0;31mError: File '{video_path}' not found.\033[0m")
		return

	if not check_ffmpeg():
		print(get_ffmpeg_instructions())
		return

	try:
		vr = VideoReader(video_path, ctx=cpu(0))
		total_frames = len(vr)
		base_name = os.path.splitext(os.path.basename(video_path))[0]

		# Determine the candidate pool of frames
		if use_keyframe:
			# Get indices of keyframes (I-frames) only
			pool = vr.get_key_indices()
			if not pool:
				print("\033[0;31mError: Could not retrieve keyframes from this video.\033[0m")
				return
		else:
			pool = list(range(total_frames))

		# Case 1: Single frame_id extraction
		if frame_id is not None:
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

			# If -k is on, snap target_idx to nearest keyframe
			if use_keyframe:
				nearest_idx = min(pool, key=lambda x: abs(x - target_idx))
				if nearest_idx != target_idx:
					print(f"Snapping frame {target_idx} to nearest keyframe {nearest_idx}...")
					target_idx = nearest_idx

			print(f"Extracting frame {target_idx} from {os.path.basename(video_path)}...")
			frame = vr[target_idx].asnumpy()
			img = Image.fromarray(frame)
			output_name = f"{base_name}_frame_{target_idx}.png"
			img.save(output_name)
			print(f"\033[0;32m[Success] Frame saved as: {output_name}\033[0m")

		# Case 2: Interval-based extraction
		elif interval is not None:
			target_indices = [pool[i] for i in range(0, len(pool), interval)]
			print(f"Extracting {len(target_indices)} frames with interval={interval}...")
			
			for idx in target_indices:
				frame = vr[idx].asnumpy()
				img = Image.fromarray(frame)
				output_name = f"{base_name}_frame_{idx}.png"
				img.save(output_name)
				print(f"Saved: {output_name}")
			
			print(f"\033[0;32m[Success] Successfully extracted {len(target_indices)} frames.\033[0m")

		# Case 3: Total evenly spread extraction
		elif total is not None:
			pool_len = len(pool)
			if total > pool_len:
				print(f"\033[0;33mWarning: Requested {total} frames, but only {pool_len} are available in the pool. Extracting all {pool_len}.\033[0m")
				total = pool_len

			if total == 1:
				selected_pool_indices = [0]
			else:
				selected_pool_indices = [int(round(i * (pool_len - 1) / (total - 1))) for i in range(total)]

			target_indices = [pool[idx] for idx in selected_pool_indices]
			print(f"Extracting {len(target_indices)} evenly spread frames...")

			for idx in target_indices:
				frame = vr[idx].asnumpy()
				img = Image.fromarray(frame)
				output_name = f"{base_name}_frame_{idx}.png"
				img.save(output_name)
				print(f"Saved: {output_name}")

			print(f"\033[0;32m[Success] Successfully extracted {len(target_indices)} frames.\033[0m")

	except Exception as e:
		print(f"\033[0;31mAn error occurred during extraction: {e}\033[0m")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Extract video frames using Decord.")
	parser.add_argument("filename", help="Path to the video file")
	parser.add_argument("frame_id", nargs="?", help="Frame index (number, 'first', or 'last')")
	parser.add_argument("-k", "--keyframe", action="store_true", help="Optimize/limit selection to keyframes")
	
	group = parser.add_mutually_exclusive_group()
	group.add_argument("-i", "--interval", type=int, help="Extract frames at a specified step interval")
	group.add_argument("-t", "--total", type=int, help="Extract N evenly spaced frames spanning the video")

	args = parser.parse_args()

	# Manual mutual exclusion validation between positional and optional arguments
	if args.frame_id is not None and (args.interval is not None or args.total is not None):
		parser.error("positional argument 'frame_id' cannot be used with -i/--interval or -t/--total")
	if args.frame_id is None and args.interval is None and args.total is None:
		parser.error("must specify either 'frame_id', -i/--interval, or -t/--total")

	if args.interval is not None and args.interval <= 0:
		parser.error("interval must be a positive integer greater than 0")
	if args.total is not None and args.total <= 0:
		parser.error("total count must be a positive integer greater than 0")

	extract_frames(args.filename, frame_id=args.frame_id, use_keyframe=args.keyframe, interval=args.interval, total=args.total)

if __name__ == "__main__":
	main()