# Video tweaking utility using FFmpeg
"""
			VIDEO TWEAKER (PRO)
			==================
This utility applies advanced temporal and spatial effects to video files 
using FFmpeg. It uses 'decord' for fast metadata analysis and constructs 
dynamic filter chains for processing individual files or entire directories.

Features:
	- Reverse: High-quality backward playback for video and audio.
	- Lower FPS: Drop frames to achieve a "choppy" look while maintaining duration.
	- Change FPS: Adjust playback speed/framerate (affects duration).
	- Bounce: Concatenate forward and reverse playback for a seamless back-and-forth loop.
	- Time Stretch: Fit video to a specific duration (e.g., 1m15s) with 
	  optional motion-compensated frame interpolation.
	- Passthrough: No temporal changes, but allows for resizing, transcoding, and renaming.
	- Interactive Codec Selection: Dynamically queries FFmpeg for available encoders.
	- Smart Resizing: Aspect-ratio aware scaling (Fit, Crop, Stretch, Limit) with even-dimension enforcement.

Usage:
	python videotweak.py [path] [options]

Options:
	path             Path to a video file or a directory of videos.
	-d, --directory  Output results into a specific subdirectory.
	-s, --suffix     Apply a custom suffix to the output filename.
	-c, --codec      Enable interactive menu to select output encoder.
	-r, --resize     Enable interactive menu to select output resolution and method.

Requirements:
	- decord (for metadata and frame analysis)
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

def get_available_encoders():
	"""Queries ffmpeg -encoders and returns a list of supported video encoders."""
	try:
		result = subprocess.run([FFMPEG_BIN, "-encoders"], capture_output=True, text=True)
		encoders = []
		# Regex to find video encoders: V..... name description
		# Updated to match any capability flags (F, S, X, B, D) instead of just dots
		pattern = re.compile(r' V.{5} ([^ ]+) +(.*)')
		for line in result.stdout.split('\n'):
			match = pattern.match(line)
			if match:
				encoders.append((match.group(1), match.group(2)))
		return encoders
	except:
		return []

def has_audio(filename):
	"""Check if the video file contains an audio stream."""
	cmd = [
		FFPROBE_BIN, "-v", "error", "-select_streams", "a", 
		"-show_entries", "stream=index", "-of", "csv=p=0", filename
	]
	try:
		result = subprocess.run(cmd, capture_output=True, text=True)
		return len(result.stdout.strip()) > 0
	except: return False

def parse_duration(dur_str):
	"""Parses strings like 1m30s, 2m, 45s into total seconds."""
	total_seconds = 0
	pattern = re.compile(r'(?:(\d+)m)?(?:(\d+)s)?')
	match = pattern.match(dur_str.strip().lower())
	if match:
		minutes = int(match.group(1)) if match.group(1) else 0
		seconds = int(match.group(2)) if match.group(2) else 0
		total_seconds = (minutes * 60) + seconds
	
	if total_seconds == 0:
		try:
			total_seconds = float(dur_str)
		except ValueError:
			return None
	return total_seconds

def get_codec_choice():
	# Standard favorites
	preferred = {
		"libx264": "H.264 (Default/High Compatibility)",
		"libx265": "H.265 (HEVC - High Efficiency)",
		"libsvtav1": "AV1 (Next-gen / SVT-AV1)",
		"libaom-av1": "AV1 (Next-gen / AOM-AV1)",
		"mpeg4": "MPEG-4 (Legacy)",
		"rawvideo": "Uncompressed (Raw YUV)",
		"prores_ks": "Apple ProRes (Editing)",
		"h264_nvenc": "H.264 (NVIDIA Hardware Accel)",
		"h264_videotoolbox": "H.264 (Apple Hardware Accel)",
		"h264_amf": "H.264 (AMD Hardware Accel)",
		"h264_qsv": "H.264 (Intel QuickSync Accel)"
	}
	
	system_encoders = {name: desc for name, desc in get_available_encoders()}
	
	# Filter preferred list based on what is actually available
	available_options = []
	for cmd, desc in preferred.items():
		if cmd in system_encoders:
			available_options.append((cmd, desc))
	
	# Add an option to see all
	available_options.append(("SHOW_ALL", "[Show All Available System Encoders]"))

	print(f"\n{PURPLE}{BOLD}--- Select Output Codec ---{RESET}")
	for i, (cmd, desc) in enumerate(available_options, 1):
		if cmd == "SHOW_ALL":
			print(f"{CYAN}{i}.{RESET} {YELLOW}{desc}{RESET}")
		else:
			print(f"{CYAN}{i}.{RESET} {BOLD}{cmd:<18}{RESET} - {desc}")
	
	while True:
		choice = input(f"\nChoose (1-{len(available_options)}) [1]: ").strip()
		if not choice: return available_options[0][0]
		if choice.isdigit() and 1 <= int(choice) <= len(available_options):
			selected_cmd = available_options[int(choice)-1][0]
			
			if selected_cmd == "SHOW_ALL":
				all_enc = sorted(system_encoders.items())
				print(f"\n{PURPLE}--- All Available Video Encoders ---{RESET}")
				for j, (name, desc) in enumerate(all_enc, 1):
					print(f"{CYAN}{j:3}.{RESET} {BOLD}{name:<20}{RESET} {desc[:60]}")
				
				sub_choice = input(f"\nSelect by number: ").strip()
				if sub_choice.isdigit() and 1 <= int(sub_choice) <= len(all_enc):
					return all_enc[int(sub_choice)-1][0]
				continue
				
			return selected_cmd
		print(f"{RED}Invalid choice.{RESET}")

def get_resize_choice():
	res_options = [
		("original", "Keep original resolution"),
		("1920x1080", "1080p (1920x1080)"),
		("1280x720", "720p (1280x720)"),
		("custom", "Enter custom dimensions"),
	]
	print(f"\n{PURPLE}{BOLD}--- Select Output Resolution ---{RESET}")
	for i, (val, desc) in enumerate(res_options, 1):
		print(f"{CYAN}{i}.{RESET} {desc}")
	
	w, h = None, None
	while True:
		choice = input(f"\nChoose (1-{len(res_options)}) [1]: ").strip()
		if not choice or choice == "1": return None
		if choice == "2":
			w, h = 1920, 1080
			break
		if choice == "3":
			w, h = 1280, 720
			break
		if choice == "4":
			try:
				w = int(input(f"{CYAN}Target Width (px):{RESET} ").strip())
				if w % 2 != 0: w += 1
				h_in = input(f"{CYAN}Target Height (px) [Enter for Auto]:{RESET} ").strip()
				h = int(h_in) if h_in else -2
				if h != -2 and h % 2 != 0: h += 1
				break
			except ValueError:
				print(f"{RED}Invalid dimensions.{RESET}")
				continue
		print(f"{RED}Invalid choice.{RESET}")

	if h == -2:
		return {"width": w, "height": h, "method": "stretch"}

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
		print(f"{RED}Invalid choice.{RESET}")

def get_effect_choice():
	print(f"\n{PURPLE}{BOLD}--- Select Tweak Effect ---{RESET}")
	print(f"{CYAN}1.{RESET} Reverse")
	print(f"{CYAN}2.{RESET} Lower FPS (Drop frames, keep duration)")
	print(f"{CYAN}3.{RESET} Change FPS (Change speed/length)")
	print(f"{CYAN}4.{RESET} Bounce (Forward + Reverse)")
	print(f"{CYAN}5.{RESET} Time Stretch (Exact Duration)")
	print(f"{CYAN}6.{RESET} Passthrough (Transcode/Resize only)")
	
	while True:
		choice = input(f"\nChoose (1-6): ").strip()
		if choice in ['1', '2', '3', '4', '5', '6']:
			return int(choice)
		print(f"{RED}Invalid choice.{RESET}")

def process_video(file_path, effect_id, out_dir, custom_suffix, codec, resize_config):
	base_name = os.path.basename(file_path)
	name_no_ext, ext = os.path.splitext(base_name)
	
	effect_suffixes = {1: "_reversed", 2: "_lowfps", 3: "_speed", 4: "_bounce", 5: "_stretched", 6: "_tweak"}
	suffix = custom_suffix if custom_suffix else effect_suffixes[effect_id]
	
	# Determine extension
	if "prores" in codec:
		output_ext = ".mov"
	elif "rawvideo" in codec:
		output_ext = ".avi"
	else:
		output_ext = ext
		
	output_name = f"{name_no_ext}{suffix}{output_ext}"
	output_path = os.path.join(out_dir, output_name) if out_dir else output_name

	if out_dir and not os.path.exists(out_dir):
		os.makedirs(out_dir)

	vr = VideoReader(file_path)
	orig_fps = vr.get_avg_fps()
	total_frames = len(vr)
	orig_duration = total_frames / orig_fps
	audio_present = has_audio(file_path)
	
	v_filter = ""
	a_filter = ""
	
	# Handle Effects
	if effect_id == 1: # Reverse
		v_filter = "reverse"
		if audio_present: a_filter = "areverse"
	elif effect_id == 2: # Lower FPS
		target_fps = float(input(f"Current FPS: {orig_fps:.2f}. Enter target FPS: "))
		v_filter = f"fps=fps={target_fps}"
		if audio_present: a_filter = "acopy"
	elif effect_id == 3: # Change FPS (Speed)
		target_fps = float(input(f"Target playback FPS (Original: {orig_fps:.2f}): "))
		speed_factor = orig_fps / target_fps
		v_filter = f"setpts={speed_factor}*PTS"
		if audio_present:
			a_factor = 1.0 / speed_factor
			a_filter = f"atempo={a_factor}"
	elif effect_id == 4: # Bounce
		v_filter = "split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0"
		if audio_present:
			a_filter = "asplit[af][ar];[ar]areverse[arr];[af][arr]concat=n=2:v=0:a=1"
	elif effect_id == 5: # Time Stretch
		target_input = input(f"Enter target duration (Orig: {orig_duration:.2f}s): ")
		target_dur = parse_duration(target_input)
		if not target_dur or target_dur <= 0: return
		speed_factor = target_dur / orig_duration
		print(f"\n{PURPLE}Interpolation Mode:{RESET} 1. Standard  2. Motion-Compensated")
		interp_choice = input("Choice [1]: ").strip()
		if interp_choice == '2':
			v_filter = f"setpts={speed_factor}*PTS,minterpolate=fps={orig_fps}:mi_mode=mci"
		else:
			v_filter = f"setpts={speed_factor}*PTS"
		if audio_present:
			a_filter = f"atempo={1.0/speed_factor}"
	elif effect_id == 6: # Passthrough
		v_filter = ""
		if audio_present: a_filter = "acopy"

	# Handle Resizing
	if resize_config:
		tw, th = resize_config["width"], resize_config["height"]
		m = resize_config["method"]
		res_f = ""
		if m == "stretch" or th == -2:
			res_f = f"scale={tw}:{th}"
		elif m == "fit":
			res_f = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"
		elif m == "crop":
			res_f = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}"
		elif m == "limit":
			res_f = f"scale='min({tw},iw)':'min({th},ih)':force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"
		
		v_filter = res_f + (f",{v_filter}" if v_filter else "")

	cmd = [FFMPEG_BIN, "-y", "-i", file_path]
	is_complex = "[" in v_filter or ";" in v_filter
	
	if effect_id == 4:
		v_filter = f"[0:v]{v_filter}[outv]"
		if audio_present: a_filter = f"[0:a]{a_filter}[outa]"
	else:
		if not v_filter: v_filter = "null"
		v_filter = f"[0:v]{v_filter}[outv]"
		if audio_present:
			if not a_filter: a_filter = "anull"
			a_filter = f"[0:a]{a_filter}[outa]"

	if audio_present:
		cmd.extend(["-filter_complex", f"{v_filter};{a_filter}", "-map", "[outv]", "-map", "[outa]", "-c:a", "aac"])
	else:
		cmd.extend(["-filter_complex", v_filter, "-map", "[outv]", "-an"])

	cmd.extend(["-c:v", codec])
	
	# Encoder compatibility settings
	if "prores" in codec:
		cmd.extend(["-profile:v", "3"])
	elif "qsv" in codec:
		# Intel QuickSync requires nv12 pixel format
		cmd.extend(["-pix_fmt", "nv12"])
	elif any(x in codec for x in ["x264", "x265", "nvenc", "amf", "videotoolbox"]):
		cmd.extend(["-pix_fmt", "yuv420p"])
		if "x264" in codec or "x265" in codec:
			cmd.extend(["-preset", "medium", "-crf", "18"])
	elif "rawvideo" in codec:
		cmd.extend(["-pix_fmt", "yuv420p"])
	else:
		# Fallback to yuv420p for other encoders
		cmd.extend(["-pix_fmt", "yuv420p"])
	
	cmd.append(output_path)

	print(f"{YELLOW}Tweaking: {base_name}...{RESET}")
	result = subprocess.run(cmd, capture_output=True, text=True)
	
	if result.returncode == 0:
		print(f"{GREEN}[Success] Saved to {output_path}{RESET}")
	else:
		print(f"{RED}FFmpeg Error:{RESET}\n{result.stderr}")

def main():
	init_ansi()
	parser = argparse.ArgumentParser(description="Tweak video files.")
	parser.add_argument("path", nargs="?", help="Video file or directory")
	parser.add_argument("-d", "--directory", help="Subdirectory for results")
	parser.add_argument("-s", "--suffix", help="Custom suffix for filename")
	parser.add_argument("-c", "--codec", action="store_true", help="Choose codec interactively")
	parser.add_argument("-r", "--resize", action="store_true", help="Choose resolution interactively")

	args = parser.parse_args()
	
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
	selected_res_config = get_resize_choice() if args.resize else None
	effect_id = get_effect_choice()

	for f in sorted(files):
		process_video(f, effect_id, args.directory, args.suffix, selected_codec, selected_res_config)

if __name__ == "__main__":
	main()