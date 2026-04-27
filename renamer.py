# Sequential file renamer with filtering and safety
"""
			SEQUENTIAL FILE RENAMER
			-----------------------
This script renames files in the current directory sequentially. 
It supports custom prefixes, suffixes, and sorting methods while 
retaining the media filters and safety features of the random sorter.

USAGE:
	python renamer.py -p "holiday_" -s "_draft"
	python renamer.py -f --type image
	python renamer.py --wildcard "vacation_*.jpg"
	python renamer.py -d 0 -p "PRE_"      # Keeps original names, adds prefix
	python renamer.py -o -p "IMG_"       # Keeps original names, adds prefix AND numbers at start

OPTIONS:
	-p, --prefix STR   Text to put before the content
	-f, --folder       Use the parent folder's name as the prefix
	-s, --suffix STR   Text to put after the content (before extension)
	-w, --wildcard STR Filter files using wildcards (e.g., 'IMG_*.jpg')
	-d, --digits N     Number of digits for padding. 
	                   0: Disable numbering (keep original filename)
	                   Default: auto-calculated based on file count
	-o, --original     Keep original filename but add numbering at the start.
	                   (Mutually exclusive with -d 0)
	--sort METHOD      Sorting: 'name_asc' (default), 'name_desc', 'date_asc', 'date_desc'
	-k, --keep         Keep original files in place (copy instead of move)
	-t, --type TYPE    Filter by 'image', 'video', or 'audio'
	-e, --ext EXT      Filter for a specific extension only
	-a, --all          Include all files, ignoring safety filters (requires confirmation)
"""

import os
import argparse
import sys
import shutil
import fnmatch

# Initialize environment for ANSI colors on Windows
if os.name == 'nt':
	os.system('color')

# Color Constants
CLR_ORANGE = "\033[93m"
CLR_GREEN  = "\033[92m"
CLR_RED    = "\033[91m"
CLR_RESET  = "\033[0m"

# Predefined extension groups
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.svg', '.heic', '.jfif')
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v')
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.aiff')

# Safety list: common non-media extensions to ignore by default
FORBIDDEN_EXTENSIONS = (
	'.exe', '.dll', '.sys', '.ini', '.bat', '.cmd', '.sh', '.ps1', '.vbs', # Executables/Scripts
	'.py', '.js', '.ts', '.html', '.css', '.json', '.xml',                # Dev files
	'.lnk', '.url', '.alias',                                             # Shortcuts
	'.db', '.sqlite', '.sql', '.log',                                     # Data/Logs
	'.msi', '.pkg', '.dmg', '.iso', '.bin',                               # Installers
	'.inf', '.config', '.yaml', '.yml'                                    # Configuration
)

class ColoredArgumentParser(argparse.ArgumentParser):
	"""Custom ArgumentParser that outputs errors in red."""
	def error(self, message):
		sys.stderr.write(f"{CLR_RED}error: {message}{CLR_RESET}\n")
		self.print_usage(sys.stderr)
		sys.exit(2)

def get_target_files(folder_path, allowed_extensions, include_all, wildcard_pattern=None):
	"""Returns a list of files to process using scandir for efficiency."""
	script_name = os.path.basename(sys.argv[0])
	files = []
	
	try:
		with os.scandir(folder_path) as entries:
			for entry in entries:
				if entry.is_file() and entry.name != script_name:
					filename = entry.name
					
					# 1. Wildcard Filter
					if wildcard_pattern and not fnmatch.fnmatch(filename, wildcard_pattern):
						continue

					# 2. Extension Filters
					if allowed_extensions:
						if not filename.lower().endswith(allowed_extensions):
							continue
					elif not include_all:
						if filename.lower().endswith(FORBIDDEN_EXTENSIONS):
							continue
					
					files.append(filename)
	except OSError as e:
		sys.stderr.write(f"{CLR_RED}Error accessing directory: {e}{CLR_RESET}\n")
		sys.exit(1)
		
	return files

def sort_files(folder_path, files, method):
	"""Sorts files based on the chosen method."""
	if method == 'name_asc':
		files.sort()
	elif method == 'name_desc':
		files.sort(reverse=True)
	elif method == 'date_asc':
		files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)))
	elif method == 'date_desc':
		files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)), reverse=True)
	return files

def rename_files(folder_path, prefix, suffix, digit_count, keep, include_orig, files):
	"""Performs the sequential renaming/copying."""
	if not files:
		print("No matching files found. Nothing to do.")
		return

	num_files = len(files)
	required_digits = len(str(num_files))

	# Handle digit padding logic
	if digit_count is None:
		digit_count = required_digits
		print(f"Auto-calculated digit padding: {digit_count}")
	elif digit_count > 0:
		if digit_count < required_digits:
			sys.stderr.write(f"{CLR_RED}Error: Specified digits ({digit_count}) is too small for {num_files} files.{CLR_RESET}\n")
			sys.stderr.write(f"Required digits: {required_digits}\n")
			sys.exit(1)
	elif digit_count == 0:
		print("Numbering disabled. Using original filenames.")

	print(f"Processing {num_files} files...\n")

	for i, filename in enumerate(files, start=1):
		name_root, extension = os.path.splitext(filename)
		
		# Build new filename content
		if digit_count == 0:
			content = name_root
		elif include_orig:
			# Number at start, then original name
			content = f"{str(i).zfill(digit_count)}_{name_root}"
		else:
			# Just the number
			content = str(i).zfill(digit_count)
			
		new_name = f"{prefix}{content}{suffix}{extension}"
		
		old_path = os.path.join(folder_path, filename)
		new_path = os.path.join(folder_path, new_name)

		# Check if the name hasn't changed at all
		if filename == new_name:
			print(f"Skipping: {CLR_ORANGE}{filename}{CLR_RESET} (no change)")
			continue

		# Basic collision check
		if os.path.exists(new_path):
			print(f"Skipping: {CLR_GREEN}{new_name}{CLR_RESET} already exists.")
			continue

		try:
			if keep:
				shutil.copy2(old_path, new_path)
				print(f"Copied: {CLR_ORANGE}{filename}{CLR_RESET} -> {CLR_GREEN}{new_name}{CLR_RESET}")
			else:
				os.rename(old_path, new_path)
				print(f"Renamed: {CLR_ORANGE}{filename}{CLR_RESET} -> {CLR_GREEN}{new_name}{CLR_RESET}")
		except Exception as e:
			sys.stderr.write(f"{CLR_RED}Failed to process {filename}: {e}{CLR_RESET}\n")

if __name__ == "__main__":
	parser = ColoredArgumentParser(description="Sequentially rename files in the current folder.")
	
	parser.add_argument("-p", "--prefix", type=str, default="",
						help="Prefix for the new filename.")

	parser.add_argument("-f", "--folder", action="store_true",
						help="Use the current folder name as the prefix.")
	
	parser.add_argument("-s", "--suffix", type=str, default="",
						help="Suffix for the new filename (before extension).")
	
	parser.add_argument("-w", "--wildcard", type=str,
						help="Filter files using wildcards (e.g. 'holiday*.jpg').")
	
	parser.add_argument("-d", "--digits", type=int,
						help="Number of digits for numbering (e.g. 3 for 001). Set to 0 to keep original filenames.")
	
	parser.add_argument("-o", "--original", action="store_true",
						help="Keep original filename and place numbers at the start.")
	
	parser.add_argument("--sort", type=str, choices=['name_asc', 'name_desc', 'date_asc', 'date_desc'],
						default='name_asc', help="Sorting method (default: name_asc)")

	parser.add_argument("-k", "--keep", action="store_true",
						help="Keep original files in place (copy instead of move)")

	parser.add_argument("-t", "--type", type=str, choices=['image', 'video', 'audio'],
						help="Filter by category: 'image', 'video', or 'audio'")

	parser.add_argument("-e", "--ext", type=str, 
						help="Filter for a specific extension only.")

	parser.add_argument("-a", "--all", action="store_true",
						help="Include all files, ignoring safety filters (requires confirmation)")

	# Handle case where no arguments are provided (show help instead of hanging/exiting silently)
	if len(sys.argv) == 1:
		parser.print_help()
		sys.exit(0)

	args = parser.parse_args()

	# Handle mutual exclusivity for -o and -d 0
	if args.original and args.digits == 0:
		parser.error("-o/--original and -d 0 are mutually exclusive.")

	# Handle confirmation for --all flag
	if args.all:
		confirm = input(f"{CLR_RED}WARNING: You are using the --all flag. This will process system files and scripts.{CLR_RESET}\nAre you sure? (y/n): ")
		if confirm.lower() != 'y':
			print("Operation cancelled.")
			sys.exit()

	# Determine prefix
	current_folder = os.getcwd()
	final_prefix = args.prefix
	if args.folder:
		# Get base name of the current directory
		final_prefix = os.path.basename(current_folder)

	# Determine extension filter
	allowed = None
	if args.ext:
		target_ext = args.ext if args.ext.startswith('.') else f".{args.ext}"
		allowed = (target_ext.lower(),)
	elif args.type == 'image':
		allowed = IMAGE_EXTENSIONS
	elif args.type == 'video':
		allowed = VIDEO_EXTENSIONS
	elif args.type == 'audio':
		allowed = AUDIO_EXTENSIONS
	
	# Get and sort target files
	target_files = get_target_files(current_folder, allowed, args.all, args.wildcard)
	sorted_files = sort_files(current_folder, target_files, args.sort)
	
	# Execute renaming
	rename_files(current_folder, final_prefix, args.suffix, args.digits, args.keep, args.original, sorted_files)
	
	print("\nProcessing complete.")