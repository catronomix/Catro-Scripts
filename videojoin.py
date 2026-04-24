# Video concatenation and processing utility using FFmpeg
"""
			VIDEO JOINER (PRO)
			==================
This utility concatenates multiple video files using FFmpeg directly. 
It uses 'decord' for fast metadata analysis and constructs advanced 
FFmpeg filter chains for resizing and trimming.

Features:
	- Join any number of video files.
	- Skip the last frame of each video (loop optimization).
	- Interactive codec selection.
	- Advanced resizing: Crop, Fit (Letterbox), Stretch, or Limit.
	- Auto-detects audio and handles silent/video-only files gracefully.
	- Join all videos in the current directory with --all.

Usage:
	python videojoin.py [filenames] [options]

Options:
	-a, --all        Join all video files in the working directory (alphanumerical).
	-s, --skipframe  Skip the last frame of each clip.
	-c, --codec      Manually choose output codec.
	-r, --resize     Configure output dimensions and method.
	-o, --output     Set custom output filename.

Requirements:
	- decord (for metadata)
	- ffmpeg (system dependency)
"""

import os
import sys
import argparse
import platform
import subprocess
import re

def init_ansi():
	if platform.system().lower() == "windows":
		os.system('color')

try:
	import decord
	from decord import VideoReader
except ImportError:
	init_ansi()
	print("\033[0;31mError: 'decord' library is not installed.\033[0m")
	print(f"Please install it using: {sys.executable} -m pip install decord")
	sys.exit(1)

# ANSI Color constants
PURPLE = '\033[38;2;170;0;255m'
CYAN = '\033[0;36m'
YELLOW = '\033[0;33m'
GREEN = '\033[0;32m'
RED = '\033[0;31m'
BOLD = '\033[1m'
RESET = '\033[0m'

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
FFPROBE_BIN = get_bin_path("ffprobe")

def check_ffmpeg():
	try:
		subprocess.run([FFMPEG_BIN, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		return True
	except FileNotFoundError:
		return False

def has_audio(filename):
	"""Checks if a file has an audio stream using ffprobe."""
	cmd = [
		FFPROBE_BIN, "-v", "error", "-select_streams", "a", 
		"-show_entries", "stream=index", "-of", "csv=p=0", filename
	]
	try:
		result = subprocess.run(cmd, capture_output=True, text=True)
		return len(result.stdout.strip()) > 0
	except:
		return False

def get_unique_filename(filename):
	if not os.path.exists(filename):
		return filename
	base, ext = os.path.splitext(filename)
	counter = 1
	while True:
		new_name = f"{base} ({counter}){ext}"
		if not os.path.exists(new_name):
			return new_name
		counter += 1

def get_codec_choice():
	codecs = [
		("libx264", "H.264 (Default/High Compatibility)"),
		("libx265", "H.265 (HEVC - High Efficiency)"),
		("libvpx-vp9", "VP9 (WebM High Quality)"),
		("mpeg4", "MPEG-4 (Legacy)"),
	]
	print(f"\n{PURPLE}{BOLD}--- Select Output Codec ---{RESET}")
	for i, (cmd, desc) in enumerate(codecs, 1):
		print(f"{CYAN}{i}.{RESET} {BOLD}{cmd:<12}{RESET} - {desc}")
	while True:
		choice = input(f"\nChoose (1-{len(codecs)}) [1]: ").strip()
		if not choice: return codecs[0][0]
		if choice.isdigit() and 1 <= int(choice) <= len(codecs):
			return codecs[int(choice)-1][0]
		print(f"{RED}Invalid choice.{RESET}")

def get_resize_config():
	print(f"\n{PURPLE}{BOLD}--- Resize Configuration ---{RESET}")
	try:
		w = int(input(f"{CYAN}Target Width (px):{RESET} ").strip())
		h = int(input(f"{CYAN}Target Height (px):{RESET} ").strip())
	except ValueError:
		return None
	methods = [
		("fit", "Letterbox (Keep ratio, add black bars)"),
		("crop", "Fill (Keep ratio, crop edges)"),
		("stretch", "Stretch (Ignore ratio)"),
		("limit", "Downscale Only (Don't upscale if smaller)")
	]
	print(f"\n{YELLOW}Select Resize Method:{RESET}")
	for i, (cmd, desc) in enumerate(methods, 1):
		print(f"{CYAN}{i}.{RESET} {BOLD}{cmd:<8}{RESET} - {desc}")
	while True:
		choice = input(f"\nChoose (1-{len(methods)}) [1]: ").strip()
		if not choice: return {"width": w, "height": h, "method": "fit"}
		if choice.isdigit() and 1 <= int(choice) <= len(methods):
			return {"width": w, "height": h, "method": methods[int(choice)-1][0]}

def run_ffmpeg_join(files, skip_frame, codec, resize, output_name):
	if not check_ffmpeg():
		print(f"{RED}Error: FFmpeg not found in PATH or program directory.{RESET}")
		return

	input_args = []
	filter_complex = ""
	any_audio = False
	file_data = []
	
	print(f"\n{GREEN}Analyzing {len(files)} files...{RESET}")
	
	try:
		for i, f in enumerate(files):
			vr = VideoReader(f)
			fps = vr.get_avg_fps()
			total_frames = len(vr)
			audio_present = has_audio(f)
			if audio_present: any_audio = True
			
			file_data.append({
				'index': i,
				'fps': fps,
				'frames': total_frames,
				'has_audio': audio_present,
				'duration': total_frames / fps
			})
			input_args.extend(["-i", f])
			
			v_label = f"v{i}"
			a_label = f"a{i}"
			
			# 1. Trimming
			v_trim = ""
			a_trim = ""
			if skip_frame:
				v_trim = f"trim=end_frame={total_frames-1},setpts=PTS-STARTPTS,"
				a_trim = f"atrim=end={(total_frames-1)/fps},asetpts=PTS-STARTPTS,"
			
			# 2. Resizing
			res_filter = ""
			if resize:
				tw, th = resize["width"], resize["height"]
				m = resize["method"]
				if m == "stretch":
					res_filter = f"scale={tw}:{th},"
				elif m == "fit":
					res_filter = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,"
				elif m == "crop":
					res_filter = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},"
				elif m == "limit":
					res_filter = f"scale='min({tw},iw)':'min({th},ih)':force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,"

			# Final Video Chain
			v_chain = v_trim + res_filter
			if not v_chain: v_chain = "copy"
			filter_complex += f"[{i}:v]{v_chain.rstrip(',')}[{v_label}];"
			
			# Final Audio Chain (with silence fallback if we need audio output)
			if any_audio:
				if audio_present:
					a_chain = a_trim if a_trim else "acopy"
					filter_complex += f"[{i}:a]{a_chain.rstrip(',')}[{a_label}];"
				else:
					# Generate silence of the correct duration for this specific segment
					dur = (total_frames - 1) / fps if skip_frame else total_frames / fps
					filter_complex += f"aevalsrc=0:d={dur}[{a_label}];"

		# Interleave: [v0][a0][v1][a1]... for concat
		concat_inputs = ""
		for i in range(len(files)):
			concat_inputs += f"[v{i}]"
			if any_audio:
				concat_inputs += f"[a{i}]"
		
		audio_opt = ":a=1" if any_audio else ""
		filter_complex += f"{concat_inputs}concat=n={len(files)}:v=1{audio_opt}[outv]"
		if any_audio:
			filter_complex += "[outa]"

		cmd = [
			FFMPEG_BIN, "-y",
			*input_args,
			"-filter_complex", filter_complex,
			"-map", "[outv]"
		]
		
		if any_audio:
			cmd.extend(["-map", "[outa]", "-c:a", "aac"])
		else:
			cmd.append("-an")
		
		cmd.extend(["-c:v", codec, "-preset", "medium", output_name])

		print(f"\n{YELLOW}Executing FFmpeg...{RESET}")
		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0:
			print(f"{RED}FFmpeg Error Output:{RESET}\n{result.stderr}")
			raise subprocess.CalledProcessError(result.returncode, cmd)
			
		print(f"\n{GREEN}{BOLD}[Success] Joined video saved as {output_name}{RESET}")

	except Exception as e:
		print(f"\n{RED}An error occurred: {e}{RESET}")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Concatenate video files using FFmpeg and Decord.")
	parser.add_argument("filenames", nargs="*", help="Video files to join")
	parser.add_argument("-a", "--all", action="store_true", help="Join all video files in working directory")
	parser.add_argument("-s", "--skipframe", action="store_true", help="Skip the last frame of each clip")
	parser.add_argument("-c", "--codec", action="store_true", help="Manually choose output codec")
	parser.add_argument("-r", "--resize", action="store_true", help="Configure output dimensions")
	parser.add_argument("-o", "--output", help="Output filename")

	args = parser.parse_args()
	
	target_files = args.filenames

	if args.all:
		video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.mpeg', '.mpg')
		found = [f for f in os.listdir('.') if f.lower().endswith(video_exts) and os.path.isfile(f)]
		if not found:
			print(f"{RED}Error: No video files found in the current directory.{RESET}")
			sys.exit(1)
		target_files = sorted(found)
		print(f"{GREEN}Found {len(target_files)} video files in directory.{RESET}")
	
	if not target_files:
		print(f"{RED}No files provided. Provide filenames or use -a.{RESET}")
		parser.print_help()
		return

	output_file = get_unique_filename(args.output if args.output else "joined_video.mp4")
	if not output_file.lower().endswith((".mp4", ".mkv", ".webm")):
		output_file += ".mp4"

	selected_codec = get_codec_choice() if args.codec else "libx264"
	resize_config = get_resize_config() if args.resize else None

	run_ffmpeg_join(target_files, args.skipframe, selected_codec, resize_config, output_file)

if __name__ == "__main__":
	main()