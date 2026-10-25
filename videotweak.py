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
	-a, --all        Process all video files in the current directory.
	-e, --ext        Filter files by specific extension (e.g., mp4, webp).
	-d, --directory  Output results into a specific subdirectory.
	-s, --suffix     Apply a custom suffix to the output filename.
	-c, --codec      Enable interactive menu to select output encoder and container.
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
import json

import tui

# Optional dependency, imported on demand inside main() so that --help works
# without decord installed.
VideoReader = None

# Supported video extensions
DEFAULT_VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.webm', '.avi', '.webp', '.flv', '.mpeg', '.mpg', '.mts', '.m2ts')

CODEC_TO_CONTAINERS = {
	"libx264": [(".mp4", "MP4"), (".mkv", "Matroska"), (".mov", "QuickTime")],
	"libx265": [(".mp4", "MP4"), (".mkv", "Matroska"), (".mov", "QuickTime")],
	"libsvtav1": [(".mp4", "MP4"), (".mkv", "Matroska"), (".webm", "WebM")],
	"libaom-av1": [(".mp4", "MP4"), (".mkv", "Matroska"), (".webm", "WebM")],
	"mpeg4": [(".mp4", "MP4"), (".avi", "AVI"), (".mov", "QuickTime")],
	"rawvideo": [(".avi", "AVI"), (".mkv", "Matroska"), (".mov", "QuickTime")],
	"prores_ks": [(".mov", "QuickTime (Standard)"), (".mkv", "Matroska")],
	"h264_nvenc": [(".mp4", "MP4"), (".mkv", "Matroska"), (".mov", "QuickTime")],
	"h264_videotoolbox": [(".mp4", "MP4"), (".mkv", "Matroska"), (".mov", "QuickTime")],
	"h264_amf": [(".mp4", "MP4"), (".mkv", "Matroska"), (".mov", "QuickTime")],
	"h264_qsv": [(".mp4", "MP4"), (".mkv", "Matroska"), (".mov", "QuickTime")],
}

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
		pattern = re.compile(r' V.{5} ([^ ]+) +(.*)')
		for line in result.stdout.split('\n'):
			match = pattern.match(line)
			if match:
				encoders.append((match.group(1), match.group(2)))
		return encoders
	except:
		return []

def has_audio(filename):
	"""Check if the video file contains an audio stream using resilient JSON probing."""
	cmd = [
		FFPROBE_BIN, "-v", "quiet", 
		"-print_format", "json", 
		"-show_streams", "-show_format", "-select_streams", "a", filename
	]
	try:
		result = subprocess.run(cmd, capture_output=True, text=True)
		data = json.loads(result.stdout)
		# Priority 1: Direct stream identification
		if 'streams' in data and len(data['streams']) > 0:
			return True
		# Priority 2: Format-level stream count (often more robust for interleaved .mts)
		elif 'format' in data and int(data['format'].get('nb_streams', 0)) > 1:
			return True
	except Exception: 
		pass
	return False

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

def get_codec_choice(cap):
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
	available_options = []
	for cmd, desc in preferred.items():
		if cmd in system_encoders:
			available_options.append((cmd, desc))
	
	available_options.append(("SHOW_ALL", "[Show All Available System Encoders]"))

	print()
	print(tui.section("--- Select Output Codec ---", cap=cap))
	for i, (cmd, desc) in enumerate(available_options, 1):
		if cmd == "SHOW_ALL":
			print("{} {}".format(tui.style("{}.", fg="accent", cap=cap),
								 tui.style(desc, fg="warn", cap=cap)))
		else:
			print("{} {} - {}".format(
				tui.style("{}.", fg="accent", cap=cap),
				tui.style("{:<18}".format(cmd), bold=True, cap=cap),
				desc))
	
	codec = ""
	while True:
		choice = input(f"\nChoose Codec (1-{len(available_options)}) [1]: ").strip()
		if not choice: 
			codec = available_options[0][0]
			break
		if choice.isdigit() and 1 <= int(choice) <= len(available_options):
			selected_cmd = available_options[int(choice)-1][0]
			if selected_cmd == "SHOW_ALL":
				all_enc = sorted(system_encoders.items())
				print()
				print(tui.section("--- All Available Video Encoders ---", cap=cap))
				for j, (name, desc) in enumerate(all_enc, 1):
					print("{} {} {}".format(
						tui.style(f"{j:3}.", fg="accent", cap=cap),
						tui.style(f"{name:<20}", bold=True, cap=cap),
						desc[:60]))
				sub_choice = input(f"\nSelect by number: ").strip()
				if sub_choice.isdigit() and 1 <= int(sub_choice) <= len(all_enc):
					codec = all_enc[int(sub_choice)-1][0]
					break
				continue
			codec = selected_cmd
			break
		print(tui.style("Invalid choice.", fg="error", cap=cap))

	# Container selection based on compatible pairs
	containers = CODEC_TO_CONTAINERS.get(codec, [(".mp4", "MP4"), (".mkv", "Matroska")])
	print()
	print(tui.section("--- Select Output Container ---", cap=cap))
	for i, (ext, desc) in enumerate(containers, 1):
		print("{} {} ({})".format(
			tui.style("{}.", fg="accent", cap=cap),
			tui.style("{:<6}".format(ext), bold=True, cap=cap),
			desc))
	
	while True:
		choice = input(f"\nChoose Container (1-{len(containers)}) [1]: ").strip()
		if not choice:
			return codec, containers[0][0]
		if choice.isdigit() and 1 <= int(choice) <= len(containers):
			return codec, containers[int(choice)-1][0]
		print(tui.style("Invalid choice.", fg="error", cap=cap))

def get_resize_choice(cap):
	print()
	print(tui.section("--- Resize Configuration ---", cap=cap))
	try:
		w = int(input("{} ".format(tui.style("Target Width (px):", fg="accent", cap=cap))).strip())
		if w % 2 != 0: w += 1
		
		h_in = input("{} ".format(tui.style("Target Height (px) [Enter for Auto]:", fg="accent", cap=cap))).strip()
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
	print()
	print(tui.style("Select Resize Method:", fg="warn", cap=cap))
	for i, (cmd, desc) in enumerate(methods, 1):
		print("{} {} - {}".format(
			tui.style("{}.", fg="accent", cap=cap),
			tui.style("{:<8}".format(cmd), bold=True, cap=cap),
			desc))
	
	while True:
		choice = input(f"\nChoose (1-{len(methods)}) [1]: ").strip()
		if not choice: 
			method = "fit"
			break
		if choice.isdigit() and 1 <= int(choice) <= len(methods):
			method = methods[int(choice)-1][0]
			break
		print(tui.style("Invalid choice.", fg="error", cap=cap))

	quant = 2
	if method == "limit":
		q_opts = [0, 2, 4, 8, 16, 32, 64]
		print()
		print(tui.style("Select Edge Quantization (pixels):", fg="warn", cap=cap))
		print("{} {}".format(tui.style("Options:", fg="accent", cap=cap),
							 ", ".join(map(str, q_opts))))
		while True:
			q_in = input(f"Choose quantization [2]: ").strip()
			if not q_in:
				quant = 2
				break
			if q_in.isdigit() and int(q_in) in q_opts:
				quant = int(q_in)
				break
			print(tui.style("Invalid choice.", fg="error", cap=cap))

	return {"width": w, "height": h, "method": method, "quant": quant}

def get_effect_choice(cap):
	print()
	print(tui.section("--- Select Tweak Effect ---", cap=cap))
	effects = [
		"Reverse",
		"Lower FPS (Drop frames, keep duration)",
		"Change FPS (Change speed/length)",
		"Bounce (Forward + Reverse)",
		"Time Stretch (Exact Duration)",
		"Passthrough (Transcode/Resize only)",
	]
	for i, desc in enumerate(effects, 1):
		print("{} {}".format(tui.style("{}.", fg="accent", cap=cap), desc))
	
	while True:
		choice = input(f"\nChoose (1-6): ").strip()
		if choice in ['1', '2', '3', '4', '5', '6']:
			return int(choice)
		print(tui.style("Invalid choice.", fg="error", cap=cap))

def process_video(file_path, effect_id, out_dir, custom_suffix, codec, target_ext, resize_config, cap=None):
	cap = cap if cap is not None else tui.detect()
	base_name = os.path.basename(file_path)
	name_no_ext, ext = os.path.splitext(base_name)
	
	effect_suffixes = {1: "_reversed", 2: "_lowfps", 3: "_speed", 4: "_bounce", 5: "_stretched", 6: "_tweak"}
	suffix = custom_suffix if custom_suffix else effect_suffixes[effect_id]
	
	output_name = f"{name_no_ext}{suffix}{target_ext}"
	output_path = os.path.join(out_dir, output_name) if out_dir else output_name

	if out_dir and not os.path.exists(out_dir):
		os.makedirs(out_dir)

	# Metadata check using VideoReader
	vr = VideoReader(file_path)
	orig_fps = vr.get_avg_fps()
	total_frames = len(vr)
	orig_duration = total_frames / orig_fps
	audio_present = has_audio(file_path)
	
	v_filter = ""
	a_filter = ""
	needs_complex = False
	
	if effect_id == 1: # Reverse
		v_filter, a_filter, needs_complex = "reverse", "areverse", True
	elif effect_id == 2: # Lower FPS
		target_fps = float(input(f"Current FPS: {orig_fps:.2f}. Enter target FPS: "))
		v_filter = f"fps=fps={target_fps}"
	elif effect_id == 3: # Change FPS (Speed)
		target_fps = float(input(f"Target playback FPS (Original: {orig_fps:.2f}): "))
		speed_factor = orig_fps / target_fps
		v_filter = f"setpts={speed_factor}*PTS"
		if audio_present:
			a_filter, needs_complex = f"atempo={1.0 / speed_factor}", True
	elif effect_id == 4: # Bounce
		v_filter = "split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0"
		if audio_present:
			a_filter = "asplit[af][ar];[ar]areverse[arr];[af][arr]concat=n=2:v=0:a=1"
		needs_complex = True
	elif effect_id == 5: # Time Stretch
		target_input = input(f"Enter target duration (Orig: {orig_duration:.2f}s): ")
		target_dur = parse_duration(target_input)
		if not target_dur or target_dur <= 0: return
		speed_factor = target_dur / orig_duration
		print()
		print(tui.style("Interpolation Mode:", fg="header", bold=True, cap=cap)
			  + " 1. Standard  2. Motion-Compensated")
		interp_choice = input("Choice [1]: ").strip()
		if interp_choice == '2':
			v_filter = f"setpts={speed_factor}*PTS,minterpolate=fps={orig_fps}:mi_mode=mci"
		else:
			v_filter = f"setpts={speed_factor}*PTS"
		if audio_present:
			a_filter, needs_complex = f"atempo={1.0/speed_factor}", True

	# Spatial resizing logic
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
			q = resize_config["quant"]
			res_f = f"scale='trunc(min({tw},iw*min({tw}/iw,{th}/ih))/{q})*{q}':'trunc(min({th},ih*min({tw}/iw,{th}/ih))/{q})*{q}'"
		v_filter = res_f + (f",{v_filter}" if v_filter else "")

	# Build FFMPEG Command
	cmd = [FFMPEG_BIN, "-y", "-i", file_path]
	
	if needs_complex:
		# Use complex graph only for temporal modifications.
		# Explicit mapping of labels prevents automatic selection conflicts.
		v_chain = f"[0:v]{v_filter or 'null'}[outv]"
		if audio_present:
			a_chain = f"[0:a]{a_filter or 'anull'}[outa]"
			cmd.extend(["-filter_complex", f"{v_chain};{a_chain}", "-map", "[outv]", "-map", "[outa]"])
		else:
			cmd.extend(["-filter_complex", v_chain, "-map", "[outv]"])
	else:
		# Spatial only / Passthrough path (Mimics working getaudio logic)
		# By NOT using manual -map here, FFmpeg uses its best-stream automatic selection
		# which is proven to be the most resilient way to handle interleaved .mts files.
		if v_filter:
			cmd.extend(["-vf", v_filter])
		# If we strictly want to ensure video exists, we could use -map 0:v? but 
		# automatic selection is usually safer for problematic source containers.
	
	# Set Video Codec
	cmd.extend(["-c:v", codec])
	
	# Handle specific codec requirements
	if "prores" in codec:
		cmd.extend(["-profile:v", "3", "-pix_fmt", "yuv422p10le"])
		if audio_present:
			# Professional MOV standard: PCM 16-bit 48kHz
			cmd.extend(["-c:a", "pcm_s16le", "-ar", "48000"])
	else:
		cmd.extend(["-pix_fmt", "yuv420p"])
		if audio_present:
			cmd.extend(["-c:a", "aac", "-b:a", "192k"])
	
	if not audio_present: 
		cmd.append("-an")

	cmd.append(output_path)

	print(tui.style(f"Tweaking: {base_name}...", fg="warn", cap=cap))
	result = subprocess.run(cmd, capture_output=True, text=True)
	
	if result.returncode == 0:
		print(tui.style(f"[Success] Saved to {output_path}", fg="success", cap=cap))
	else:
		print(tui.style("FFmpeg Error:", fg="error", cap=cap) + "\n" + result.stderr)

def main():
	tui.init_ansi()
	parser = argparse.ArgumentParser(description="Tweak video files.")
	parser.add_argument("path", nargs="?", help="Video file or directory")
	group = parser.add_mutually_exclusive_group()
	group.add_argument("-a", "--all", action="store_true", help="Process all videos in current directory")
	group.add_argument("-e", "--ext", help="Filter by extension")
	parser.add_argument("-d", "--directory", help="Subdirectory for results")
	parser.add_argument("-s", "--suffix", help="Custom suffix for filename")
	parser.add_argument("-c", "--codec", action="store_true", help="Choose codec and container interactively")
	parser.add_argument("-r", "--resize", action="store_true", help="Choose resolution interactively")

	args = parser.parse_args()
	# Capabilities are resolved once: one colour level, unicode decision and
	# plain/tty mode for the whole run.
	cap = tui.detect()
	target = args.path if args.path else "."

	# decord is only needed for an actual run, not for --help.
	global VideoReader
	try:
		from decord import VideoReader
	except ImportError:
		print(tui.style("Error: 'decord' library is not installed.", fg="error", cap=cap))
		print(f"Please install it using: {sys.executable} -m pip install decord")
		sys.exit(1)
	
	if args.ext:
		ext_filter = args.ext if args.ext.startswith('.') else f".{args.ext}"
		filter_criteria = (ext_filter.lower(),)
	else:
		filter_criteria = DEFAULT_VIDEO_EXTS

	files = []
	if os.path.isfile(target) and not (args.all or args.ext):
		files = [target]
	else:
		search_dir = target if os.path.isdir(target) else "."
		files = [os.path.join(search_dir, f) for f in os.listdir(search_dir) 
				 if f.lower().endswith(filter_criteria) and os.path.isfile(os.path.join(search_dir, f))]
	
	if not files:
		print(tui.style("No video files found matching criteria.", fg="error", cap=cap))
		return

	if args.codec:
		selected_codec, selected_ext = get_codec_choice(cap)
	else:
		selected_codec = "libx264"
		selected_ext = ".mp4"

	selected_res_config = get_resize_choice(cap) if args.resize else None
	effect_id = get_effect_choice(cap)

	for f in sorted(files):
		if not args.codec:
			_, current_ext = os.path.splitext(f)
			# Default to MP4 if source is a transport stream, otherwise keep original
			target_ext = ".mp4" if current_ext.lower() in ['.mts', '.m2ts'] else current_ext
		else:
			target_ext = selected_ext

		process_video(f, effect_id, args.directory, args.suffix, selected_codec, target_ext, selected_res_config, cap)

if __name__ == "__main__":
	main()