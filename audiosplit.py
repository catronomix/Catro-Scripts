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

# Audio Extension Group
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.aiff', '.opus')

# Safety list: common non-media extensions to ignore by default
FORBIDDEN_EXTENSIONS = (
	'.exe', '.dll', '.sys', '.ini', '.bat', '.cmd', '.sh', '.ps1', '.vbs',
	'.py', '.js', '.ts', '.html', '.css', '.json', '.xml',
	'.lnk', '.url', '.alias', '.db', '.sqlite', '.sql', '.log',
	'.msi', '.pkg', '.dmg', '.iso', '.bin', '.inf', '.config', '.yaml', '.yml'
)

# Color Constants
CLR_ORANGE = "\033[93m"
CLR_GREEN  = "\033[92m"
CLR_BLUE   = "\033[94m"
CLR_RED    = "\033[91m"
CLR_RESET  = "\033[0m"

def init_ansi():
	"""Enables ANSI color support on Windows."""
	if platform.system().lower() == "windows":
		os.system('color')

try:
	from pydub import AudioSegment
except ImportError:
	init_ansi()
	print(f"{CLR_RED}Error: 'pydub' library is not installed.{CLR_RESET}")
	print("Please install it using: pip install pydub")
	sys.exit(1)

class ColoredArgumentParser(argparse.ArgumentParser):
	"""Custom ArgumentParser that outputs errors in red."""
	def error(self, message):
		sys.stderr.write(f"{CLR_RED}error: {message}{CLR_RESET}\n")
		self.print_usage(sys.stderr)
		sys.exit(2)

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

def get_target_files(allowed_extensions=None, include_all=False, wildcard_pattern=None):
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
		sys.stderr.write(f"{CLR_RED}Error accessing directory: {e}{CLR_RESET}\n")
		sys.exit(1)
		
	return files

def interactive_codec_menu():
	"""Prompts the user to select an output format and codec."""
	formats = [
		{"ext": "wav", "codec": None, "label": "WAV (Uncompressed)"},
		{"ext": "mp3", "codec": "libmp3lame", "label": "MP3 (LAME)"},
		{"ext": "flac", "codec": "flac", "label": "FLAC (Lossless)"},
		{"ext": "ogg", "codec": "libvorbis", "label": "OGG (Vorbis)"},
		{"ext": "m4a", "codec": "aac", "label": "M4A (AAC)"},
		{"ext": "opus", "codec": "libopus", "label": "OPUS (Ogg Opus)"}
	]

	print(f"\n{CLR_BLUE}--- Output Configuration ---{CLR_RESET}")
	for i, f in enumerate(formats, 1):
		print(f"{i}) {f['label']}")
	
	while True:
		try:
			choice = int(input(f"\nSelect output format (1-{len(formats)}): "))
			if 1 <= choice <= len(formats):
				selected = formats[choice-1]
				return selected["ext"], selected["codec"]
		except ValueError:
			pass
		print(f"{CLR_RED}Invalid selection.{CLR_RESET}")

def split_audio_file(file_path, output_dir=None, custom_ext=None, custom_codec=None):
	"""
	Splits a single multi-channel audio file into individual mono tracks.
	"""
	abs_path = os.path.abspath(file_path)
	filename = os.path.basename(abs_path)
	
	try:
		print(f"\nLoading {CLR_ORANGE}{filename}{CLR_RESET}...")
		audio = AudioSegment.from_file(abs_path)
		
		channel_count = audio.channels
		if channel_count <= 1:
			print(f"File only has {channel_count} channel. Skipping.")
			return

		print(f"Detected {channel_count} channels. Splitting...")

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
			
			print(f"Exporting track {track_number}...")
			# Pydub export takes format and optional codec
			export_kwargs = {"format": ext}
			if custom_codec:
				export_kwargs["codec"] = custom_codec
				
			track.export(final_out_path, **export_kwargs)
			print(f"{CLR_GREEN}[Success] Saved: {os.path.basename(final_out_path)}{CLR_RESET}")

	except Exception as e:
		print(f"{CLR_RED}An error occurred with '{filename}': {e}{CLR_RESET}")

def main():
	init_ansi()
	parser = ColoredArgumentParser(description="Split multi-channel audio into individual tracks.")
	
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

	if not check_ffmpeg():
		print(f"\n{CLR_ORANGE}FFmpeg is missing or not found.{CLR_RESET}")
		print("Pydub requires FFmpeg for audio processing. Place it in the script folder or add to PATH.")
		return

	# Handle configuration selection
	out_ext, out_codec = (None, None)
	if args.codec:
		out_ext, out_codec = interactive_codec_menu()

	# Determine file list
	files_to_process = []
	if args.file:
		if os.path.isfile(args.file):
			files_to_process.append(args.file)
		else:
			print(f"{CLR_RED}Error: File '{args.file}' not found.{CLR_RESET}")
			sys.exit(1)
	elif args.all or args.wildcard or args.ext:
		allowed = None
		if args.ext:
			ext_filter = args.ext if args.ext.startswith('.') else f".{args.ext}"
			allowed = (ext_filter.lower(),)
		
		files_to_process = get_target_files(allowed, include_all=False, wildcard_pattern=args.wildcard)
	else:
		parser.print_help()
		sys.exit(0)

	if not files_to_process:
		print("No matching files found.")
		return

	print(f"Targeting {len(files_to_process)} files.")
	
	for file in files_to_process:
		split_audio_file(file, args.directory, out_ext, out_codec)

	print(f"\n{CLR_BLUE}Processing complete.{CLR_RESET}")

if __name__ == "__main__":
	main()