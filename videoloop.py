# Video seamless looping utility using FFmpeg
"""
			VIDEO LOOPER
			==================
This utility creates a seamless, crossfaded loop from a single video file. 
Instead of a simple repetition, it fades the end of the clip into the 
beginning, creating a smooth transition.

Features:
	- Seamless crossfade looping.
	- Timeline Shift: Set the starting position of the final loop (0.0 - 1.0).
	- Interactive codec and fade curve selection.
	- Automatic handling of silent or audio-heavy files.
	- Fallback logic for older FFmpeg versions.

Usage:
	python videolooper.py <filename> [options]

Options:
	-f, --fade           Crossfade duration in seconds (default: 1.0).
	-s, --shift          Start position offset (0.0 to 1.0, default: 0.0).
	-c, --codec          Choose output codec interactively.
	-n, --interpolation  Choose fade curve interactively (FFmpeg 4.3+).
	-o, --output         Set custom output filename.

Requirements:
	- decord (for duration/metadata)
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
	try:
		result = subprocess.run([FFMPEG_BIN, "-version"], capture_output=True, text=True)
		match = re.search(r'version (\d+)\.(\d+)', result.stdout.split('\n')[0])
		if match:
			return int(match.group(1)), int(match.group(2))
	except: pass
	return 0, 0

def has_audio(filename):
	cmd = [
		FFPROBE_BIN, "-v", "error", "-select_streams", "a", 
		"-show_entries", "stream=index", "-of", "csv=p=0", filename
	]
	try:
		result = subprocess.run(cmd, capture_output=True, text=True)
		return len(result.stdout.strip()) > 0
	except: return False

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
		("esin", "Exponential Sine (Ease-In-Out)"),
		("tri", "Linear (Standard)"),
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

def process_loop(file_path, fade_dur, shift_offset, codec, curve, output_name, supports_curve):
	if not check_ffmpeg():
		print(f"{RED}Error: FFmpeg not found.{RESET}")
		return

	try:
		vr = VideoReader(file_path)
		fps = vr.get_avg_fps()
		total_frames = len(vr)
		duration = total_frames / fps
		audio_present = has_audio(file_path)

		if fade_dur >= duration / 2:
			print(f"{YELLOW}Warning: Fade duration is very long. Reducing to {duration/4:.2f}s.{RESET}")
			fade_dur = duration / 4

		# Loop duration is original minus fade overlap
		loop_duration = duration - fade_dur
		# Calculate actual shift in seconds
		shift_time = (shift_offset % 1.0) * loop_duration

		print(f"{GREEN}Analyzing: {os.path.basename(file_path)} ({duration:.2f}s)...{RESET}")
		
		# Build Filter Chain
		v_curve = f":curve={curve}" if (supports_curve and curve != "tri") else ""
		
		v_filter = (
			f"[0:v]trim=start={fade_dur}:end={duration-fade_dur},setpts=PTS-STARTPTS[body];"
			f"[0:v]trim=start={duration-fade_dur}:end={duration},setpts=PTS-STARTPTS[tail];"
			f"[0:v]trim=start=0:end={fade_dur},setpts=PTS-STARTPTS[head];"
			f"[head]format=yuva420p,fade=t=in:st=0:d={fade_dur}:alpha=1{v_curve}[h_f];"
			f"[tail][h_f]overlay=eof_action=repeat[trans];"
			f"[body][trans]concat=n=2:v=1[loopv]"
		)
		
		if shift_time > 0:
			v_filter += (
				f";[loopv]split[s1][s2];"
				f"[s1]trim=start={shift_time}:end={loop_duration},setpts=PTS-STARTPTS[p1];"
				f"[s2]trim=start=0:end={shift_time},setpts=PTS-STARTPTS[p2];"
				f"[p1][p2]concat=n=2:v=1[outv]"
			)
		else:
			v_filter += ";[loopv]copy[outv]"

		a_filter = ""
		if audio_present:
			a_curve = f":curve={curve}" if (supports_curve and curve != "tri") else ""
			a_filter = (
				f"[0:a]atrim=start={fade_dur}:end={duration-fade_dur},asetpts=PTS-STARTPTS[abody];"
				f"[0:a]atrim=start={duration-fade_dur}:end={duration},asetpts=PTS-STARTPTS[atail];"
				f"[0:a]atrim=start=0:end={fade_dur},asetpts=PTS-STARTPTS[ahead];"
				f"[atail]afade=t=out:st=0:d={fade_dur}{a_curve}[at_f];"
				f"[ahead]afade=t=in:st=0:d={fade_dur}{a_curve}[ah_f];"
				f"[at_f][ah_f]amix=inputs=2:duration=first:dropout_transition={fade_dur}[atrans];"
				f"[abody][atrans]concat=n=2:v=0:a=1[loopa]"
			)
			if shift_time > 0:
				a_filter += (
					f";[loopa]asplit[as1][as2];"
					f"[as1]atrim=start={shift_time}:end={loop_duration},asetpts=PTS-STARTPTS[ap1];"
					f"[as2]atrim=start=0:end={shift_time},asetpts=PTS-STARTPTS[ap2];"
					f"[ap1][ap2]concat=n=2:v=0:a=1[outa]"
				)
			else:
				a_filter += ";[loopa]acopy[outa]"

		cmd = [FFMPEG_BIN, "-y", "-i", file_path]
		
		if audio_present:
			cmd.extend([
				"-filter_complex", f"{v_filter};{a_filter}",
				"-map", "[outv]", "-map", "[outa]", "-c:a", "aac"
			])
		else:
			cmd.extend([
				"-filter_complex", v_filter,
				"-map", "[outv]", "-an"
			])

		cmd.extend(["-c:v", codec, "-preset", "medium", output_name])

		print(f"{YELLOW}Creating seamless loop...{RESET}")
		result = subprocess.run(cmd, capture_output=True, text=True)
		
		if result.returncode != 0:
			if "Option 'curve' not found" in result.stderr or "Error applying option 'curve'" in result.stderr:
				print(f"{YELLOW}Curve '{curve}' not supported by this FFmpeg build. Retrying with linear fade...{RESET}")
				return process_loop(file_path, fade_dur, shift_offset, codec, "tri", output_name, False)
			print(f"{RED}FFmpeg Error Output:{RESET}\n{result.stderr}")
		else:
			print(f"{GREEN}[Success] Loop saved as {output_name}{RESET}")

	except Exception as e:
		print(f"{RED}Error: {e}{RESET}")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Create a seamless crossfade loop.")
	parser.add_argument("filename", help="Video file to loop")
	parser.add_argument("-f", "--fade", type=float, default=1.0, help="Crossfade duration (sec)")
	parser.add_argument("-s", "--shift", type=float, default=0.0, help="Timeline offset (0.0-1.0)")
	parser.add_argument("-c", "--codec", action="store_true", help="Choose codec interactively")
	parser.add_argument("-n", "--interpolation", action="store_true", help="Choose curve interactively")
	parser.add_argument("-o", "--output", help="Output filename")

	args = parser.parse_args()
	
	if not os.path.exists(args.filename):
		print(f"{RED}Error: File not found.{RESET}")
		return

	v_major, v_minor = get_ffmpeg_version()
	supports_curve = (v_major > 4) or (v_major == 4 and v_minor >= 3)
	
	selected_codec = get_codec_choice() if args.codec else "libx264"
	selected_curve = get_curve_choice() if args.interpolation else "esin"

	output = args.output or f"{os.path.splitext(args.filename)[0]}_seamless.mp4"

	print(f"\n{PURPLE}{BOLD}--- LOOP SETTINGS ---{RESET}")
	print(f"Fade Time: {args.fade}s")
	print(f"Shift:     {args.shift*100:.0f}%")
	print(f"Curve:     {selected_curve}\n")

	process_loop(args.filename, args.fade, args.shift, selected_codec, selected_curve, output, supports_curve)

if __name__ == "__main__":
	main()