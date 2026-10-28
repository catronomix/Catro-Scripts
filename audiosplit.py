# Multi-track audio splitter utility
"""
			AUDIO SPLITTER
			==============
This utility takes an audio file and splits its individual channels (tracks) 
into separate mono files. Each output file is named using the original 
filename with a '_trackNN' suffix.

Usage:
	python audiosplitter.py <audio_file_path>
	python audiosplitter.py -a
	python audiosplitter.py -w "*.wav" -d "./splits" -c

Requirements:
	- pydub library (pip install pydub)
	- ffmpeg (system dependency for decoding/encoding)
"""

import os
import sys
import platform
import subprocess
import argparse
import fnmatch

import tui

# Audio Extension Group
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.aiff', '.opus')

# Safety list: common non-media extensions to ignore by default
FORBIDDEN_EXTENSIONS = (
	'.exe', '.dll', '.sys', '.ini', '.bat', '.cmd', '.sh', '.ps1', '.vbs',
	'.py', '.js', '.ts', '.html', '.css', '.json', '.xml',
	'.lnk', '.url', '.alias', '.db', '.sqlite', '.sql', '.log',
	'.msi', '.pkg', '.dmg', '.iso', '.bin', '.inf', '.config', '.yaml', '.yml'
)

# Optional dependency, imported on demand inside main() so that --help and
# argument errors work on machines without pydub installed.
AudioSegment = None

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

def get_target_files(allowed_extensions=None, include_all=False, wildcard_pattern=None, cap=None):
	"""Returns a list of files to process based on filters."""
	files = []
	current_dir = os.getcwd()
	script_name = os.path.basename(sys.argv[0])
	
	try:
		with os.scandir(current_dir) as entries:
			for entry in entries:
				if entry.is_file() and entry.name != script_name:
					filename = entry.name
					
					if wildcard_pattern and not fnmatch.fnmatch(filename, wildcard_pattern):
						continue

					if allowed_extensions:
						if not filename.lower().endswith(allowed_extensions):
							continue
					elif not include_all:
						if not filename.lower().endswith(AUDIO_EXTENSIONS):
							continue
						if filename.lower().endswith(FORBIDDEN_EXTENSIONS):
							continue
					
					files.append(filename)
	except OSError as e:
		print(tui.status("error", f"Error accessing directory: {e}", cap=cap),
			  file=sys.stderr)
		sys.exit(1)
		
	return files

def interactive_codec_menu(cap=None):
	"""Prompts the user to select an output format and codec.

	Returns `(ext, codec)`, or None when the user cancels at the prompt.
	"""
	formats = [
		{"ext": "wav", "codec": None, "label": "WAV (Uncompressed)"},
		{"ext": "mp3", "codec": "libmp3lame", "label": "MP3 (LAME)"},
		{"ext": "flac", "codec": "flac", "label": "FLAC (Lossless)"},
		{"ext": "ogg", "codec": "libvorbis", "label": "OGG (Vorbis)"},
		{"ext": "m4a", "codec": "aac", "label": "M4A (AAC)"},
		{"ext": "opus", "codec": "libopus", "label": "OPUS (Ogg Opus)"}
	]

	print()
	# The masthead and the numbered menu are the shared page chrome: the theme
	# reaches them without this script knowing any colour names.
	print(tui.header("Audio Splitter", "Output configuration", cap=cap))
	print(tui.menu([f["label"] for f in formats], selected=None, cap=cap))

	# tui.ask_int owns the validation loop, the range check and the cancel key.
	choice = tui.ask_int("Select output format", 1, len(formats))
	if choice is None:
		return None
	selected = formats[choice - 1]
	return selected["ext"], selected["codec"]

def split_audio_file(file_path, output_dir=None, custom_ext=None, custom_codec=None, cap=None):
	"""
	Splits a single multi-channel audio file into individual mono tracks.

	Returns True when the file was processed (or legitimately skipped), False
	when an error was reported, so main() can exit non-zero.
	"""
	abs_path = os.path.abspath(file_path)
	filename = os.path.basename(abs_path)
	
	try:
		print()
		print(tui.status("info", f"Loading {filename}...", cap=cap))
		audio = AudioSegment.from_file(abs_path)
		
		channel_count = audio.channels
		if channel_count <= 1:
			print(tui.status("warn",
							 f"File only has {channel_count} channel. Skipping.",
							 cap=cap))
			return True

		print(tui.status("info", f"Detected {channel_count} channels. Splitting...",
						 cap=cap))

		tracks = audio.split_to_mono()
		
		base_name = os.path.splitext(filename)[0]
		# Use custom extension if provided, otherwise stick to original or default to wav
		orig_ext = os.path.splitext(filename)[1].replace(".", "") or "wav"
		ext = custom_ext if custom_ext else orig_ext

		for i, track in enumerate(tracks):
			track_number = str(i + 1).zfill(2)
			out_name = f"{base_name}_track{track_number}.{ext}"
			
			if output_dir:
				os.makedirs(output_dir, exist_ok=True)
				final_out_path = os.path.join(output_dir, out_name)
			else:
				final_out_path = out_name
			
			print(tui.status("info", f"Exporting track {track_number}...", cap=cap))
			# Pydub export takes format and optional codec
			export_kwargs = {"format": ext}
			if custom_codec:
				export_kwargs["codec"] = custom_codec
				
			track.export(final_out_path, **export_kwargs)
			print(tui.status("ok",
							 f"Saved: {os.path.basename(final_out_path)}",
							 cap=cap))

	except Exception as e:
		print(tui.status("error", f"An error occurred with '{filename}': {e}",
						 cap=cap))
		return False

	return True

def main():
	parser = argparse.ArgumentParser(description="Split multi-channel audio into individual tracks.")
	
	parser.add_argument("file", nargs="?", help="Path to a single audio file.")
	parser.add_argument("-a", "--all", action="store_true",
						help="Process all audio files in the current directory.")
	parser.add_argument("-d", "--directory", type=str,
						help="Output results into a specific subdirectory.")
	parser.add_argument("-e", "--ext", type=str,
						help="Filter for a specific input extension only.")
	parser.add_argument("-w", "--wildcard", type=str,
						help="Filter files using wildcards (e.g., 'ambient_*.wav').")
	parser.add_argument("-c", "--codec", action="store_true",
						help="Enable interactive menu to select output encoder and container.")

	args = parser.parse_args()

	# Capabilities are resolved once: every message in the run shares them.
	tui.init_ansi()
	cap = tui.detect()

	# pydub is optional for --help/usage flows: load it only for a real run.
	global AudioSegment
	try:
		from pydub import AudioSegment
	except ImportError:
		print(tui.status("error", "Error: 'pydub' library is not installed.",
						 cap=cap))
		print("Please install it using: pip install pydub")
		sys.exit(1)

	if not check_ffmpeg():
		print()
		print(tui.status("warn", "FFmpeg is missing or not found.", cap=cap))
		print("Pydub requires FFmpeg for audio processing. Place it in the script folder or add to PATH.")
		sys.exit(1)

	# Handle configuration selection
	out_ext, out_codec = (None, None)
	if args.codec:
		# The codec menu is the only interactive path in this script, and
		# tui.ask_int re-prompts forever on a closed stdin, so refuse a pipe
		# here with the contract's tty seam instead of hanging.
		tui.require_tty("audiosplit")
		chosen = interactive_codec_menu(cap)
		if chosen is None:
			print("Cancelled.")
			return 0
		out_ext, out_codec = chosen

	# Determine file list
	files_to_process = []
	if args.file:
		if os.path.isfile(args.file):
			files_to_process.append(args.file)
		else:
			print(tui.status("error", f"Error: File '{args.file}' not found.",
							 cap=cap))
			sys.exit(1)
	elif args.all or args.wildcard or args.ext:
		allowed = None
		if args.ext:
			ext_filter = args.ext if args.ext.startswith('.') else f".{args.ext}"
			allowed = (ext_filter.lower(),)
		
		files_to_process = get_target_files(allowed, include_all=False,
											wildcard_pattern=args.wildcard, cap=cap)
	else:
		parser.print_help()
		sys.exit(0)

	if not files_to_process:
		print(tui.status("warn", "No matching files found.", cap=cap))
		sys.exit(1)

	print(tui.field("Targeting", f"{len(files_to_process)} files", cap=cap))

	failures = 0
	for file in files_to_process:
		if not split_audio_file(file, args.directory, out_ext, out_codec, cap=cap):
			failures += 1

	print()
	print(tui.panel(None, [tui.style("Processing complete.", fg="header-fg",
									bold=True, cap=cap)],
					cap=cap))
	# Any per-file error makes the whole run a failure even though processing
	# continued to the next file.
	if failures:
		sys.exit(1)

if __name__ == "__main__":
	main()
