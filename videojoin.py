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
	- Loop segments: Repeat each clip X times (e.g., a-a-b-b).
	- Interactive codec selection.
	- Advanced resizing: Crop, Fit (Letterbox), Stretch, or Limit.
	- Auto-detects audio and handles silent/video-only files gracefully.
	- Auto-matches resolution of the first clip if no resize is specified.
	- Retains metadata (e.g., ComfyUI workflows) from the first clip.
	- Join all videos in the current directory with --all.
	- Batch process all subdirectories with --dir.
	- Filter by specific extension with --ext.

Usage:
	python videojoin.py [filenames] [options]

Options:
	-a, --all        Join all video files in the working directory (alphanumerical).
	-e, --ext        Join all videos with a specific extension (e.g., mp4, webp).
	-d, --dir        Process all subdirectories in the working directory.
	-l, --loop       Number of times to repeat each video (default: 1).
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

DEFAULT_VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.mpeg', '.mpg', '.webp')

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

def get_unique_filename(filename, directory="."):
	full_path = os.path.join(directory, filename)
	if not os.path.exists(full_path):
		return filename
	base, ext = os.path.splitext(filename)
	counter = 1
	while True:
		new_name = f"{base} ({counter}){ext}"
		if not os.path.exists(os.path.join(directory, new_name)):
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
		if w % 2 != 0: w += 1 # Force divisible by 2
		
		h_in = input(f"{CYAN}Target Height (px) [Enter for Auto]:{RESET} ").strip()
		if not h_in:
			h = -2
		else:
			h = int(h_in)
			if h != -2 and h % 2 != 0: h += 1 # Force divisible by 2
	except ValueError:
		return None

	# If height is auto, we only need basic scaling
	if h == -2:
		return {"width": w, "height": h, "method": "stretch"}

	methods = [
		("fit", "Letterbox (Keep ratio, add black bars)"),
		("crop", "Fill (Keep ratio, crop edges)"),
		("stretch", "Stretch (Ignore ratio)"),
		("limit", "Limit (Scale proportional within bounds)")
	]
	print(f"\n{YELLOW}Select Resize Method:{RESET}")
	for i, (cmd, desc) in enumerate(methods, 1):
		print(f"{CYAN}{i}.{RESET} {BOLD}{cmd:<8}{RESET} - {desc}")
	
	while True:
		choice = input(f"\nChoose (1-{len(methods)}) [1]: ").strip()
		if not choice: 
			method = "fit"
			break
		if choice.isdigit() and 1 <= int(choice) <= len(methods):
			method = methods[int(choice)-1][0]
			break
		print(f"{RED}Invalid choice.{RESET}")

	quant = 2
	if method == "limit":
		q_opts = [0, 2, 4, 8, 16, 32, 64]
		print(f"\n{YELLOW}Select Edge Quantization (pixels):{RESET}")
		print(f"{CYAN}Options:{RESET} {', '.join(map(str, q_opts))}")
		while True:
			q_in = input(f"Choose quantization [2]: ").strip()
			if not q_in:
				quant = 2
				break
			if q_in.isdigit() and int(q_in) in q_opts:
				quant = int(q_in)
				break
			print(f"{RED}Invalid choice.{RESET}")

	return {"width": w, "height": h, "method": method, "quant": quant}

def run_ffmpeg_join(files, skip_frame, codec, resize, output_name, working_dir="."):
	if not check_ffmpeg():
		print(f"{RED}Error: FFmpeg not found in PATH or program directory.{RESET}")
		return

	# Auto-detect resolution from the first file if no resize provided
	# This ensures the concat filter doesn't fail due to mixed dimensions.
	if not resize and files:
		try:
			first_vr = VideoReader(os.path.join(working_dir, files[0]))
			fh, fw = first_vr[0].shape[:2]
			# Ensure even dimensions for compatibility
			fw = fw if fw % 2 == 0 else fw + 1
			fh = fh if fh % 2 == 0 else fh + 1
			resize = {"width": fw, "height": fh, "method": "fit", "quant": 2}
			print(f"{CYAN}Auto-matching resolution to first clip: {fw}x{fh}{RESET}")
		except Exception as e:
			print(f"{YELLOW}Warning: Could not detect dimensions of first file. FFmpeg might fail if dimensions differ.{RESET}")

	input_args = []
	filter_complex = ""
	any_audio = False
	
	print(f"\n{GREEN}Analyzing {len(files)} inputs in '{working_dir}'...{RESET}")
	
	try:
		for i, f in enumerate(files):
			full_path = os.path.join(working_dir, f)
			vr = VideoReader(full_path)
			fps = vr.get_avg_fps()
			total_frames = len(vr)
			audio_present = has_audio(full_path)
			if audio_present: any_audio = True
			
			input_args.extend(["-i", full_path])
			
			v_label = f"v{i}"
			a_label = f"a{i}"
			
			# 1. Trimming
			v_trim = ""
			a_trim = ""
			if skip_frame:
				v_trim = f"trim=end_frame={total_frames-1},setpts=PTS-STARTPTS,"
				a_trim = f"atrim=end={(total_frames-1)/fps},asetpts=PTS-STARTPTS,"
			
			# 2. Resizing (Mandatory if dimensions differ)
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
					q = resize["quant"]
					if q > 1:
						res_filter = (f"scale='trunc(min({tw},iw*min({tw}/iw,{th}/ih))/{q})*{q}':"
									  f"'trunc(min({th},ih*min({tw}/iw,{th}/ih))/{q})*{q}',")
					else:
						res_filter = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"

			# Final Video Chain
			v_chain = v_trim + res_filter
			if not v_chain: v_chain = "copy"
			filter_complex += f"[{i}:v]{v_chain.rstrip(',')}[{v_label}];"
			
			# Final Audio Chain
			if any_audio:
				if audio_present:
					a_chain = a_trim if a_trim else "acopy"
					filter_complex += f"[{i}:a]{a_chain.rstrip(',')}[{a_label}];"
				else:
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

		output_path = os.path.join(working_dir, output_name)
		cmd = [
			FFMPEG_BIN, "-y",
			*input_args,
			"-filter_complex", filter_complex,
			"-map", "[outv]",
			"-map_metadata", "0"
		]
		
		if any_audio:
			cmd.extend(["-map", "[outa]", "-c:a", "aac"])
		else:
			cmd.append("-an")
		
		cmd.extend(["-c:v", codec, "-preset", "medium", "-pix_fmt", "yuv420p", output_path])

		print(f"\n{YELLOW}Executing FFmpeg for {output_name}...{RESET}")
		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0:
			print(f"{RED}FFmpeg Error Output:{RESET}\n{result.stderr}")
			return False
			
		print(f"\n{GREEN}{BOLD}[Success] Joined video saved as {output_path}{RESET}")
		return True

	except Exception as e:
		print(f"\n{RED}An error occurred processing {working_dir}: {e}{RESET}")
		return False

def apply_loop_to_list(file_list, loop_count):
	"""Repeats each item in the list loop_count times."""
	if loop_count <= 1:
		return file_list
	looped = []
	for f in file_list:
		for _ in range(loop_count):
			looped.append(f)
	return looped

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Concatenate video files using FFmpeg and Decord.")
	parser.add_argument("filenames", nargs="*", help="Video files to join")
	
	group = parser.add_mutually_exclusive_group()
	group.add_argument("-a", "--all", action="store_true", help="Join all video files in working directory")
	group.add_argument("-e", "--ext", help="Filter files by specific extension (e.g., mp4)")

	parser.add_argument("-d", "--dir", action="store_true", help="Process all subdirectories in working directory")
	parser.add_argument("-l", "--loop", type=int, default=1, help="Number of times to repeat each video")
	parser.add_argument("-s", "--skipframe", action="store_true", help="Skip the last frame of each clip")
	parser.add_argument("-c", "--codec", action="store_true", help="Manually choose output codec")
	parser.add_argument("-r", "--resize", action="store_true", help="Configure output dimensions")
	parser.add_argument("-o", "--output", help="Output filename")

	args = parser.parse_args()
	
	if args.ext:
		ext_filter = args.ext if args.ext.startswith('.') else f".{args.ext}"
		filter_criteria = (ext_filter.lower(),)
	else:
		filter_criteria = DEFAULT_VIDEO_EXTS

	selected_codec = get_codec_choice() if args.codec else "libx264"
	resize_config = get_resize_config() if args.resize else None
	base_output_name = args.output

	# Mode 1: Directory Batch Processing
	if args.dir:
		subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
		if not subdirs:
			print(f"{RED}Error: No subdirectories found in current directory.{RESET}")
			return

		print(f"{PURPLE}{BOLD}Batch processing {len(subdirs)} directories...{RESET}")
		for d in subdirs:
			found = [f for f in os.listdir(d) if f.lower().endswith(filter_criteria) and os.path.isfile(os.path.join(d, f))]
			if not found:
				continue
			
			target_files = apply_loop_to_list(sorted(found), args.loop)
			
			if base_output_name:
				current_out = base_output_name
			else:
				current_out = f"{os.path.basename(os.path.abspath(d))}_joined.mp4"
			
			if not current_out.lower().endswith((".mp4", ".mkv", ".webm", ".webp")):
				current_out += ".mp4"

			output_file = get_unique_filename(current_out, directory=d)
			run_ffmpeg_join(target_files, args.skipframe, selected_codec, resize_config, output_file, working_dir=d)
		return

	# Mode 2: Single Directory
	target_files = args.filenames
	if args.all or args.ext:
		found = [f for f in os.listdir('.') if f.lower().endswith(filter_criteria) and os.path.isfile(f)]
		if not found:
			print(f"{RED}Error: No video files found in the current directory matching criteria.{RESET}")
			sys.exit(1)
		target_files = sorted(found)
	
	if not target_files:
		print(f"{RED}No files provided. Provide filenames or use -a, -e, or -d.{RESET}")
		parser.print_help()
		return

	# Apply loop logic to final file list
	target_files = apply_loop_to_list(target_files, args.loop)
	print(f"{GREEN}Processing {len(target_files)} segments (including loops).{RESET}")

	final_output = base_output_name if base_output_name else "joined_video.mp4"
	if not final_output.lower().endswith((".mp4", ".mkv", ".webm", ".webp")):
		final_output += ".mp4"

	output_file = get_unique_filename(final_output)
	run_ffmpeg_join(target_files, args.skipframe, selected_codec, resize_config, output_file)

if __name__ == "__main__":
	main()