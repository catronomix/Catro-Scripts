# Video seamless looping utility using FFmpeg
"""
			VIDEO LOOPER
			==================
This utility creates a seamless, crossfaded loop from a single video file or 
an entire directory. Instead of a simple repetition, it fades the end of 
the clip into the beginning, creating a smooth transition.

Features:
	- Seamless crossfade looping.
	- Timeline Shift: Set the starting position of the final loop (0.0 - 1.0).
	- Interactive codec and fade curve selection.
	- Batch processing for folders.
	- Automatic handling of silent or audio-heavy files.
	- Fallback logic for older FFmpeg versions.
	- Advanced resizing: Crop, Fit (Letterbox), Stretch, or Limit.
	- Filter by specific extension with --ext.

Usage:
	python videoloop.py [path] [options]

Options:
	-f, --fade           Crossfade duration in seconds (default: 1.0).
	-s, --shift          Start position offset (0.0 to 1.0, default: 0.0).
	-c, --codec          Choose output codec interactively.
	-n, --interpolation  Choose fade curve interactively (FFmpeg 4.3+).
	-r, --resize         Configure output dimensions and method.
	-e, --ext            Filter files by specific extension (e.g., mp4, webp).
	-x, --suffix         Suffix for output files (default: _seamless).

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

DEFAULT_VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.webm', '.avi', '.webp')

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

def get_resize_config():
	print(f"\n{PURPLE}{BOLD}--- Resize Configuration ---{RESET}")
	try:
		w = int(input(f"{CYAN}Target Width (px):{RESET} ").strip())
		if w % 2 != 0: w += 1 
		
		h_in = input(f"{CYAN}Target Height (px) [Enter for Auto]:{RESET} ").strip()
		if not h_in:
			h = -2
		else:
			h = int(h_in)
			if h != -2 and h % 2 != 0: h += 1
	except ValueError:
		return None

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

def process_loop(file_path, fade_dur, shift_offset, codec, curve, suffix, supports_curve, resize_config):
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

		if fade_dur >= duration / 2:
			print(f"{YELLOW}Warning: Fade duration is very long for {os.path.basename(file_path)}. Reducing overlap.{RESET}")
			fade_dur = duration / 4

		loop_duration = duration - fade_dur
		shift_time = (shift_offset % 1.0) * loop_duration

		print(f"{YELLOW}Processing: {os.path.basename(file_path)}...{RESET}")
		
		# Build Resizing Filter
		res_filter = ""
		if resize_config:
			tw, th = resize_config["width"], resize_config["height"]
			m = resize_config["method"]
			if m == "stretch" or th == -2:
				res_filter = f"scale={tw}:{th},"
			elif m == "fit":
				res_filter = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,"
			elif m == "crop":
				res_filter = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},"
			elif m == "limit":
				q = resize_config["quant"]
				if q > 1:
					res_filter = (f"scale='trunc(min({tw},iw*min({tw}/iw,{th}/ih))/{q})*{q}':"
								  f"'trunc(min({th},ih*min({tw}/iw,{th}/ih))/{q})*{q}',")
				else:
					res_filter = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"

		v_curve = f":curve={curve}" if (supports_curve and curve != "tri") else ""
		
		v_filter = (
			f"[0:v]{res_filter}split=3[vhead][vbody][vtail];"
			f"[vbody]trim=start={fade_dur}:end={duration-fade_dur},setpts=PTS-STARTPTS[body];"
			f"[vtail]trim=start={duration-fade_dur}:end={duration},setpts=PTS-STARTPTS[tail];"
			f"[vhead]trim=start=0:end={fade_dur},setpts=PTS-STARTPTS[head];"
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
				f"[0:a]asplit=3[ahead_raw][abody_raw][atail_raw];"
				f"[abody_raw]atrim=start={fade_dur}:end={duration-fade_dur},asetpts=PTS-STARTPTS[abody];"
				f"[atail_raw]atrim=start={duration-fade_dur}:end={duration},asetpts=PTS-STARTPTS[atail];"
				f"[ahead_raw]atrim=start=0:end={fade_dur},asetpts=PTS-STARTPTS[ahead];"
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
			cmd.extend(["-filter_complex", f"{v_filter};{a_filter}", "-map", "[outv]", "-map", "[outa]", "-c:a", "aac"])
		else:
			cmd.extend(["-filter_complex", v_filter, "-map", "[outv]", "-an"])

		cmd.extend(["-c:v", codec, "-preset", "medium", "-pix_fmt", "yuv420p", output_name])

		result = subprocess.run(cmd, capture_output=True, text=True)
		
		if result.returncode != 0:
			if "Option 'curve' not found" in result.stderr or "Error applying option 'curve'" in result.stderr:
				print(f"{YELLOW}Curve '{curve}' not supported. Retrying with linear...{RESET}")
				return process_loop(file_path, fade_dur, shift_offset, codec, "tri", suffix, False, resize_config)
			print(f"{RED}FFmpeg Error Output:{RESET}\n{result.stderr}")
		else:
			print(f"{GREEN}[Success] Loop saved as {output_name}{RESET}")

	except Exception as e:
		print(f"{RED}Error processing {file_path}: {e}{RESET}")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Create a seamless crossfade loop.")
	parser.add_argument("path", nargs="?", help="Video file or directory")
	parser.add_argument("-f", "--fade", type=float, default=1.0, help="Crossfade duration (sec)")
	parser.add_argument("-s", "--shift", type=float, default=0.0, help="Timeline offset (0.0-1.0)")
	parser.add_argument("-c", "--codec", action="store_true", help="Choose codec interactively")
	parser.add_argument("-n", "--interpolation", action="store_true", help="Choose curve interactively")
	parser.add_argument("-r", "--resize", action="store_true", help="Configure output dimensions")
	parser.add_argument("-e", "--ext", help="Filter files by specific extension (e.g., mp4)")
	parser.add_argument("-x", "--suffix", default="_seamless", help="Suffix for output files")

	args = parser.parse_args()
	
	target = args.path if args.path else "."
	
	if args.ext:
		ext_filter = args.ext if args.ext.startswith('.') else f".{args.ext}"
		filter_criteria = (ext_filter.lower(),)
	else:
		filter_criteria = DEFAULT_VIDEO_EXTS

	files = []
	if os.path.isfile(target):
		files = [target]
	elif os.path.isdir(target):
		files = [os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith(filter_criteria)]
	
	if not files:
		print(f"{RED}No video files found matching criteria.{RESET}")
		return

	v_major, v_minor = get_ffmpeg_version()
	supports_curve = (v_major > 4) or (v_major == 4 and v_minor >= 3)
	
	selected_codec = get_codec_choice() if args.codec else "libx264"
	selected_curve = get_curve_choice() if args.interpolation else "esin"
	resize_config = get_resize_config() if args.resize else None

	print(f"\n{PURPLE}{BOLD}--- LOOP SETTINGS ---{RESET}")
	print(f"Fade Time: {args.fade}s")
	print(f"Shift:     {args.shift*100:.0f}%")
	print(f"Curve:     {selected_curve}\n")

	for f in sorted(files):
		process_loop(f, args.fade, args.shift, selected_codec, selected_curve, args.suffix, supports_curve, resize_config)

if __name__ == "__main__":
	main()