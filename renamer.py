# Sequential file renamer with filtering and safety
"""
			SEQUENTIAL FILE RENAMER
			-----------------------
This script renames files in the current directory sequentially. 
It supports custom prefixes, suffixes, and sorting methods while 
retaining the media filters and safety features of the random sorter.

USAGE:
	python renamer.py -p "holiday_" -s "_draft"
	python renamer.py --undo
	python renamer.py -f --type image
	python renamer.py --wildcard "vacation_*.jpg"
	python renamer.py -d 0 -p "PRE_"      # Keeps original names, adds prefix
	python renamer.py -o -p "IMG_"       # Keeps original names, adds prefix AND numbers at start
	python renamer.py -r " " "_"         # Replaces spaces with underscores in filenames
	python renamer.py -x " (1)"          # Renames files but removes " (1)" from original names first
	python renamer.py -xx "_TEMP"        # Only removes "_TEMP" from matching files, no other renaming
	python renamer.py -sd -p "Sub_"      # Renames files within each subfolder sequentially
	python renamer.py -sd "folder1" -p "Sub_"  # Renames files inside subfolder "folder1"
	python renamer.py -sd "folder*" -p "Sub_"  # Renames files inside subfolders starting with "folder"
	python renamer.py -t folder -p "DIR_" # Renames directories instead of files

OPTIONS:
	-p, --prefix STR   Text to put before the content
	-f, --folder       Use the parent folder's name as the prefix (or subfolder name with -sd)
	-s, --suffix STR   Text to put after the content (before extension)
	-w, --wildcard STR Filter files using wildcards (e.g., 'IMG_*.jpg')
	-r, --replace IN OUT Replace all occurrences of IN with OUT in filename (excluding extension)
	-x, --strip STR    Remove STR from the original filename before processing
	-xx, --striponly STR Only target files with STR and remove it (ignores numbering/prefix/suffix)
	-d, --digits N     Number of digits for padding. 
	                   0: Disable numbering (keep original filename)
	                   Default: auto-calculated based on file count
	-o, --original     Keep original filename but add numbering at the start.
	                   (Mutually exclusive with -d 0)
	--sort METHOD      Sorting: 'name_asc' (default), 'name_desc', 'date_asc', 'date_desc',
	                   'alphanum_asc', 'alphanum_desc', 'winname_asc', 'winname_desc'
	-k, --keep         Keep original files in place (copy instead of move)
	-t, --type TYPE    Filter by category: 'image', 'video', 'audio', or 'folder'
	-e, --ext EXT      Filter for a specific extension only
	-a, --all          Include all files, ignoring safety filters (requires confirmation)
	-sd, --subdir [PAT] Process subfolders individually. Can optionally target a specific subfolder
	                   name or a wildcard pattern (e.g., 'vacation*'). Matches all if empty.
	-u, --undo         Undo the last rename operation
"""

import os
import argparse
import sys
import shutil
import fnmatch
import re
import functools
import ctypes

# Initialize environment for ANSI colors on Windows
if os.name == 'nt':
	os.system('color')

# Color Constants
CLR_ORANGE = "\033[93m"
CLR_GREEN  = "\033[92m"
CLR_BLUE   = "\033[94m"
CLR_RED    = "\033[91m"
CLR_RESET  = "\033[0m"

# Path for the undo file in the script's directory
UNDO_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "renamer.undo")

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

def save_undo_data(history):
	"""Saves renaming history to the undo file."""
	try:
		with open(UNDO_FILE, 'w', encoding='utf-8') as f:
			for old, new in history:
				f.write(f"{old}|{new}\n")
	except Exception as e:
		sys.stderr.write(f"{CLR_RED}Could not save undo data: {e}{CLR_RESET}\n")

def perform_undo():
	"""Reverses the last rename operation in reverse order."""
	if not os.path.exists(UNDO_FILE):
		print(f"{CLR_RED}No undo history found.{CLR_RESET}")
		return

	history = []
	try:
		with open(UNDO_FILE, 'r', encoding='utf-8') as f:
			for line in f:
				parts = line.strip().split('|')
				if len(parts) == 2:
					history.append(parts)
	except Exception as e:
		sys.stderr.write(f"{CLR_RED}Error reading undo file: {e}{CLR_RESET}\n")
		return

	if not history:
		print("Undo history is empty.")
		return

	print(f"Undoing last operation ({len(history)} files)...\n")
	
	# Reverse history to undo in reverse order
	for old_path, new_path in reversed(history):
		if not os.path.exists(new_path):
			print(f"{CLR_RED}Missing: {new_path}{CLR_RESET} (cannot restore to {os.path.basename(old_path)})")
			continue
		
		try:
			os.rename(new_path, old_path)
			print(f"Restored: {CLR_ORANGE}{os.path.basename(new_path)}{CLR_RESET} -> {CLR_GREEN}{os.path.basename(old_path)}{CLR_RESET}")
		except Exception as e:
			sys.stderr.write(f"{CLR_RED}Failed to restore {new_path}: {e}{CLR_RESET}\n")

	# Clear history
	try:
		os.remove(UNDO_FILE)
	except Exception as e:
		sys.stderr.write(f"{CLR_RED}Failed to clear undo file: {e}{CLR_RESET}\n")
	
	print("\nUndo complete.")

def get_target_files(folder_path, allowed_extensions, include_all, wildcard_pattern=None, target_type=None):
	"""Returns a list of files or folders to process using scandir for efficiency."""
	script_name = os.path.basename(sys.argv[0])
	items = []
	
	try:
		with os.scandir(folder_path) as entries:
			for entry in entries:
				if target_type == 'folder':
					if entry.is_dir() and not entry.name.startswith('.') and entry.name != script_name:
						filename = entry.name
						
						# 1. Wildcard Filter
						if wildcard_pattern and not fnmatch.fnmatch(filename, wildcard_pattern):
							continue
						
						items.append(filename)
				else:
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
						
						items.append(filename)
	except OSError as e:
		sys.stderr.write(f"{CLR_RED}Error accessing directory: {e}{CLR_RESET}\n")
		sys.exit(1)
		
	return items

def natural_sort_key(s):
	"""Key function for natural/alphanumeric sorting."""
	return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def get_win_sort_key():
	"""Returns a key function using Windows StrCmpLogicalW if available, or natural sort fallback."""
	if os.name == 'nt':
		try:
			str_cmp = ctypes.windll.shlwapi.StrCmpLogicalW
			str_cmp.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
			str_cmp.restype = ctypes.c_int
			return functools.cmp_to_key(str_cmp)
		except Exception:
			pass
	return natural_sort_key

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
	elif method == 'alphanum_asc':
		files.sort(key=natural_sort_key)
	elif method == 'alphanum_desc':
		files.sort(key=natural_sort_key, reverse=True)
	elif method == 'winname_asc':
		files.sort(key=get_win_sort_key())
	elif method == 'winname_desc':
		files.sort(key=get_win_sort_key(), reverse=True)
	return files

def rename_files(folder_path, prefix, suffix, digit_count, keep, include_orig, files, replace_str=None, strip_str=None, striponly_str=None, is_folder_mode=False):
	"""Performs the sequential renaming/copying. Returns history for undo."""
	history = []
	if not files:
		print(f"No matching files found in '{os.path.basename(folder_path)}'. Nothing to do.")
		return history

	num_files = len(files)
	required_digits = len(str(num_files))

	# Handle digit padding logic for normal mode
	if striponly_str is None:
		if digit_count is None:
			digit_count = required_digits
			print(f"Auto-calculated digit padding: {digit_count}")
		elif digit_count > 0:
			if digit_count < required_digits:
				sys.stderr.write(f"{CLR_RED}Error: Specified digits ({digit_count}) is too small for {num_files} files.{CLR_RESET}\n")
				sys.stderr.write(f"Required digits: {required_digits}\n")
				sys.exit(1)
		elif digit_count == 0:
			if is_folder_mode:
				print("Numbering disabled. Using original folder names.")
			else:
				print("Numbering disabled. Using original filenames.")
	else:
		if is_folder_mode:
			print(f"Strip-only mode: Removing '{striponly_str}' from folder names.")
		else:
			print(f"Strip-only mode: Removing '{striponly_str}' from filenames.")

	item_type_str = "folders" if is_folder_mode else "files"
	print(f"Processing {num_files} {item_type_str} in '{os.path.basename(folder_path)}'...\n")

	for i, filename in enumerate(files, start=1):
		if is_folder_mode:
			name_root = filename
			extension = ""
		else:
			name_root, extension = os.path.splitext(filename)

		# Apply String Replacement (happens before other operations)
		if replace_str:
			str_in, str_out = replace_str
			name_root = name_root.replace(str_in, str_out)

		# Apply Stripping
		if striponly_str:
			# Just strip the string, no other changes
			base_new_name = name_root.replace(striponly_str, "")
		else:
			if strip_str:
				name_root = name_root.replace(strip_str, "")

			# Build new filename content
			if digit_count == 0:
				content = name_root
			elif include_orig:
				content = f"{str(i).zfill(digit_count)}_{name_root}"
			else:
				content = str(i).zfill(digit_count)
				
			base_new_name = f"{prefix}{content}{suffix}"
		
		new_name = f"{base_new_name}{extension}"
		old_path = os.path.join(folder_path, filename)

		# Check if the name hasn't changed at all
		if filename == new_name:
			print(f"Skipping: {CLR_ORANGE}{filename}{CLR_RESET} (no change)")
			continue

		# Handle collisions with incrementing suffix
		counter = 0
		final_name = new_name
		is_collision = False
		
		while os.path.exists(os.path.join(folder_path, final_name)):
			if final_name == filename:
				break
			is_collision = True
			counter += 1
			final_name = f"{base_new_name}({counter}){extension}"
		
		new_path = os.path.join(folder_path, final_name)
		display_color = CLR_BLUE if is_collision else CLR_GREEN

		try:
			if keep:
				if is_folder_mode:
					shutil.copytree(old_path, new_path)
				else:
					shutil.copy2(old_path, new_path)
				print(f"Copied: {CLR_ORANGE}{filename}{CLR_RESET} -> {display_color}{final_name}{CLR_RESET}")
			else:
				os.rename(old_path, new_path)
				print(f"Renamed: {CLR_ORANGE}{filename}{CLR_RESET} -> {display_color}{final_name}{CLR_RESET}")
				history.append((os.path.abspath(old_path), os.path.abspath(new_path)))
		except Exception as e:
			sys.stderr.write(f"{CLR_RED}Failed to process {filename}: {e}{CLR_RESET}\n")
	
	return history

if __name__ == "__main__":
	parser = ColoredArgumentParser(description="Sequentially rename files in the current folder.")
	
	action_group = parser.add_mutually_exclusive_group()

	# Options for renaming
	rename_opts = parser.add_argument_group("renaming options")
	rename_opts.add_argument("-p", "--prefix", type=str, default="",
						help="Prefix for the new filename.")
	rename_opts.add_argument("-f", "--folder", action="store_true",
						help="Use the current folder name as the prefix (or subfolder name if using -sd).")
	rename_opts.add_argument("-s", "--suffix", type=str, default="",
						help="Suffix for the new filename (before extension).")
	rename_opts.add_argument("-w", "--wildcard", type=str,
						help="Filter files using wildcards (e.g. 'holiday*.jpg').")
	rename_opts.add_argument("-r", "--replace", nargs=2, metavar=("STR_IN", "STR_OUT"),
						help="Replace all occurrences of STR_IN with STR_OUT in filename (excluding extension).")
	rename_opts.add_argument("-x", "--strip", type=str,
						help="String to strip from original filename before processing.")
	rename_opts.add_argument("-xx", "--striponly", type=str,
						help="Target files containing this string and strip it. Cannot be used with numbering/prefix/suffix.")
	rename_opts.add_argument("-d", "--digits", type=int,
						help="Number of digits for numbering (e.g. 3 for 001). Set to 0 to keep original filenames.")
	rename_opts.add_argument("-o", "--original", action="store_true",
						help="Keep original filename and place numbers at the start.")
	rename_opts.add_argument("--sort", type=str, 
						choices=['name_asc', 'name_desc', 'date_asc', 'date_desc', 
								 'alphanum_asc', 'alphanum_desc', 'winname_asc', 'winname_desc'],
						default='name_asc', help="Sorting method (default: name_asc)")
	rename_opts.add_argument("-k", "--keep", action="store_true",
						help="Keep original files in place (copy instead of move)")
	rename_opts.add_argument("-t", "--type", type=str, choices=['image', 'video', 'audio', 'folder'],
						help="Filter by category: 'image', 'video', 'audio', or 'folder'")
	rename_opts.add_argument("-e", "--ext", type=str, 
						help="Filter for a specific extension only.")
	rename_opts.add_argument("-a", "--all", action="store_true",
						help="Include all files, ignoring safety filters (requires confirmation)")
	rename_opts.add_argument("-sd", "--subdir", nargs="?", const="*", type=str,
						help="Process files inside each subfolder of the current folder individually. Can supply a name or wildcard pattern (e.g. -sd 'folder*').")

	# The undo action
	action_group.add_argument("-u", "--undo", action="store_true",
						help="Undo the last rename operation recorded in renamer.undo.")
	
	if len(sys.argv) == 1:
		parser.print_help()
		sys.exit(0)

	args = parser.parse_args()

	# Handle Undo first
	if args.undo:
		for arg in sys.argv[1:]:
			if arg in ['-p', '--prefix', '-f', '--folder', '-s', '--suffix', '-w', '--wildcard', 
					  '-r', '--replace', '-x', '--strip', '-xx', '--striponly', '-d', '--digits', 
					  '-o', '--original', '--sort', '-k', '--keep', '-t', '--type', '-e', '--ext', 
					  '-a', '--all', '-sd', '--subdir']:
				parser.error("The --undo flag is exclusive and cannot be used with other options.")
		perform_undo()
		sys.exit(0)

	# Handle mutual exclusivity for -o and -d 0
	if args.original and args.digits == 0:
		parser.error("-o/--original and -d 0 are mutually exclusive.")

	# Handle striponly constraints
	if args.striponly:
		# Check for forbidden combinations
		if any([args.prefix != "", args.folder, args.suffix != "", args.digits is not None, args.original, args.strip, args.replace is not None]):
			parser.error("--striponly (-xx) can only be combined with -w, -t, -a, -e, -k, and -sd.")

	# Handle extension filter mutual exclusion with directory type
	if args.type == 'folder' and args.ext:
		parser.error("-e/--ext and -t folder are mutually exclusive.")

	# Handle confirmation for --all flag
	if args.all:
		confirm = input(f"{CLR_RED}WARNING: You are using the --all flag. This will process system files and scripts.{CLR_RESET}\nAre you sure? (y/n): ")
		if confirm.lower() != 'y':
			print("Operation cancelled.")
			sys.exit()

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

	current_folder = os.getcwd()
	history = []

	# Resolve targets (either subfolders or the current working directory)
	if args.subdir is not None:
		subfolders = []
		try:
			with os.scandir(current_folder) as entries:
				for entry in entries:
					if entry.is_dir() and not entry.name.startswith('.'):
						if fnmatch.fnmatch(entry.name, args.subdir):
							subfolders.append(entry.name)
			subfolders.sort()
		except OSError as e:
			sys.stderr.write(f"{CLR_RED}Error accessing directories: {e}{CLR_RESET}\n")
			sys.exit(1)

		if not subfolders:
			print(f"No subfolders found matching '{args.subdir}'. Nothing to do.")
			sys.exit(0)

		# Run sequential renaming in each subfolder individually
		for subdir in subfolders:
			subfolder_path = os.path.join(current_folder, subdir)
			
			# Determine dynamic prefix for this subfolder
			final_prefix = args.prefix
			if args.folder:
				final_prefix = os.path.basename(subfolder_path)

			target_files = get_target_files(subfolder_path, allowed, args.all, args.wildcard, target_type=args.type)
			if args.striponly:
				target_files = [f for f in target_files if args.striponly in f]

			sorted_files = sort_files(subfolder_path, target_files, args.sort)

			sub_history = rename_files(
				subfolder_path, 
				final_prefix, 
				args.suffix, 
				args.digits, 
				args.keep, 
				args.original, 
				sorted_files,
				replace_str=args.replace,
				strip_str=args.strip,
				striponly_str=args.striponly,
				is_folder_mode=(args.type == 'folder')
			)
			history.extend(sub_history)
	else:
		# Standard single-folder processing
		final_prefix = args.prefix
		if args.folder:
			final_prefix = os.path.basename(current_folder)

		target_files = get_target_files(current_folder, allowed, args.all, args.wildcard, target_type=args.type)
		if args.striponly:
			target_files = [f for f in target_files if args.striponly in f]

		sorted_files = sort_files(current_folder, target_files, args.sort)

		history = rename_files(
			current_folder, 
			final_prefix, 
			args.suffix, 
			args.digits, 
			args.keep, 
			args.original, 
			sorted_files,
			replace_str=args.replace,
			strip_str=args.strip,
			striponly_str=args.striponly,
			is_folder_mode=(args.type == 'folder')
		)
	
	if history and not args.keep:
		save_undo_data(history)
		print(f"Undo history saved to: {UNDO_FILE}")
	
	print("\nProcessing complete.")