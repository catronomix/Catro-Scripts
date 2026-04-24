# Video fade-in and fade-out utility
"""
			VIDEO FADER
			=================
This utility adds smooth fade-in and fade-out effects to video clips. It 
supports interactive configuration for timings, interpolation curves, and 
a special "Append Mode" that freezes the edges of the video for the duration 
of the fade.

Features:
	- Customizable fade-in and fade-out durations.
	- Interpolation curves (Linear, Sine, Ease-in-out, etc.).
	- Append Mode: Freezes first/last frames to pad the video duration.
	- Batch processing for entire folders or single files.
	- High-performance FFmpeg backend.

Usage:
	python videofade.py [filename] [options]

Options:
	-i, --fadein         Fade-in duration in seconds (default: 1.0).
	-o, --fadeout        Fade-out duration in seconds (default: 1.0).
	-a, --append         Freeze first/last frames for fade duration.
	-s, --suffix         Filename suffix (default: _faded).
	-c, --codec          Interactively choose output codec.
	-n, --interpolation  Interactively choose fade interpolation curve.

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

def get_ffmpeg_version():
	"""Returns the FFmpeg version as a tuple of ints (major, minor)."""
	try:
		result = subprocess.run([FFMPEG_BIN, "-version"], capture_output=True, text=True)
		first_line = result.stdout.split('\n')[0]
		match = re.search(r'version (\d+)\.(\d+)', first_line)
		if match:
			return int(match.group(1)), int(match.group(2))
	except:
		pass
	return 0, 0

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

def get_curve_choice():
	curves = [
		("tri", "Linear (Standard Compatibility)"),
		("esin", "Exponential Sine (Ease-In-Out)"),
		("qsin", "Quarter Sine"),
		("hsin", "Half Sine"),
		("exp", "Exponential"),
		("log", "Logarithmic"),
	]
	print(f"\n{PURPLE}{BOLD}--- Select Fade Interpolation ---{RESET}")
	for i, (cmd, desc) in enumerate(curves, 1):
		print(f"{CYAN}{i}.{RESET} {BOLD}{cmd:<8}{RESET} - {desc}")
	while True:
		choice = input(f"\nChoose (1-{len(curves)}) [1]: ").strip()
		if not choice: return curves[0][0]
		if choice.isdigit() and 1 <= int(choice) <= len(curves):
			return curves[int(choice)-1][0]
		print(f"{RED}Invalid choice.{RESET}")

def process_video(file_path, fade_in, fade_out, append_mode, codec, curve, suffix, supports_curve=True):
	if not check_ffmpeg():
		print(f"{RED}Error: FFmpeg not found.{RESET}")
		return

	base, ext = os.path.splitext(file_path)
	output_name = f"{base}{suffix}{ext}"
	
	try:
		vr = VideoReader(file_path)
		fps = vr.get_avg_fps()
		total_frames = len(vr)
		duration = total_frames / fps
		audio_present = has_audio(file_path)

		v_filter = ""
		a_filter = ""
		
		actual_duration = duration + (fade_in + fade_out if append_mode else 0)
		start_fade_out = round(actual_duration - fade_out, 3)

		if append_mode:
			v_filter += f"tpad=start_duration={fade_in}:start_mode=clone:end_duration={fade_out}:end_mode=clone,"
			if audio_present:
				ms_in = int(fade_in * 1000)
				a_filter += f"adelay={ms_in}|{ms_in},apad=add={fade_out},"
		
		curve_opt = f":curve={curve}" if (supports_curve and curve != "tri") else ""
		
		v_filter += f"fade=t=in:st=0:d={fade_in}{curve_opt},"
		v_filter += f"fade=t=out:st={start_fade_out}:d={fade_out}{curve_opt}"
		
		if audio_present:
			a_filter += f"afade=t=in:st=0:d={fade_in}{curve_opt},"
			a_filter += f"afade=t=out:st={start_fade_out}:d={fade_out}{curve_opt}"

		v_filter = v_filter.rstrip(',')
		a_filter = a_filter.rstrip(',')

		cmd = [FFMPEG_BIN, "-y", "-i", file_path]
		
		if audio_present:
			cmd.extend([
				"-filter_complex", f"[0:v]{v_filter}[v];[0:a]{a_filter}[a]",
				"-map", "[v]", "-map", "[a]",
				"-c:a", "aac"
			])
		else:
			cmd.extend(["-vf", v_filter, "-an"])

		cmd.extend(["-c:v", codec, "-preset", "medium", output_name])

		print(f"{YELLOW}Processing: {os.path.basename(file_path)}...{RESET}")
		result = subprocess.run(cmd, capture_output=True, text=True)
		
		if result.returncode != 0:
			if "Option 'curve' not found" in result.stderr or "Error applying option 'curve'" in result.stderr:
				print(f"{YELLOW}Curve '{curve}' not supported by this FFmpeg build. Retrying with linear fade...{RESET}")
				return process_video(file_path, fade_in, fade_out, append_mode, codec, "tri", suffix, False)
			
			print(f"{RED}FFmpeg Error Output:{RESET}\n{result.stderr}")
			return
			
		print(f"{GREEN}[Success] Saved as {output_name}{RESET}")

	except Exception as e:
		print(f"{RED}Error processing {file_path}: {e}{RESET}")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Add fades to video files.")
	parser.add_argument("path", nargs="?", help="Video file or directory")
	parser.add_argument("-i", "--fadein", type=float, default=1.0, help="Fade-in duration (sec)")
	parser.add_argument("-o", "--fadeout", type=float, default=1.0, help="Fade-out duration (sec)")
	parser.add_argument("-a", "--append", action="store_true", help="Freeze edges")
	parser.add_argument("-s", "--suffix", default="_faded", help="Suffix for output")
	parser.add_argument("-c", "--codec", action="store_true", help="Choose codec interactively")
	parser.add_argument("-n", "--interpolation", action="store_true", help="Choose curve interactively")

	args = parser.parse_args()

	v_major, v_minor = get_ffmpeg_version()
	supports_curve = (v_major > 4) or (v_major == 4 and v_minor >= 3)
	
	target = args.path if args.path else "."
	files = []
	if os.path.isfile(target):
		files = [target]
	elif os.path.isdir(target):
		video_exts = ('.mp4', '.mkv', '.mov', '.webm', '.avi')
		files = [os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith(video_exts)]
	
	if not files:
		print(f"{RED}No video files found.{RESET}")
		return

	selected_codec = get_codec_choice() if args.codec else "libx264"
	selected_curve = get_curve_choice() if args.interpolation else "esin"

	print(f"\n{PURPLE}{BOLD}--- FADE SETTINGS ---{RESET}")
	print(f"Fade In:  {args.fadein}s")
	print(f"Fade Out: {args.fadeout}s")
	print(f"Mode:     {'Append' if args.append else 'Standard'}")
	print(f"Curve:    {selected_curve}\n")

	for f in sorted(files):
		process_video(f, args.fadein, args.fadeout, args.append, selected_codec, selected_curve, args.suffix, supports_curve)

if __name__ == "__main__":
	main()