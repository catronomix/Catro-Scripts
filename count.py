# file and directory size counter
"""
			FILE & DIRECTORY SIZE COUNTER
			============================
This script provides a command-line utility to analyze disk usage by file types 
or by directory depth. It calculates total sizes and item counts, presenting 
results in an organized, color-coded list.

Features:
	- Group by file extension (default) or by directory (--dirs).
	- Recursive scanning with adjustable depth limits.
	- Human-readable size formatting or raw byte counts.
	- Rainbow-coded output for visual clarity.
	- Plain TAB-separated output when piped.
	- Show hidden files/folders with the --all flag.

Usage:
	python count.py [options] [path]

Examples:
	- python count.py                     (Current dir, file types)
	- python count.py -s                  (Current dir, recursive, all levels)
	- python count.py -d 2 ./projects     (Subdirectories exactly 2 levels deep)
	- python count.py -a -r               (Show all files including hidden, raw bytes)

Requirements:
	- No external libraries required; uses standard Python modules.
	- Supports ANSI colors on modern terminals (Windows/Linux/macOS).
"""
import os
import sys
import argparse
from collections import defaultdict

import tui

# The rainbow is data handed to tui.style(): these base-ANSI hexes are exactly
# the entries the old raw codes named (91, 33, 93, 92, 96, 94, 95), so a
# 16-colour terminal keeps the same cycle.
RAINBOW = ["#FF0000", "#808000", "#FFFF00", "#00FF00",
		   "#00FFFF", "#0000FF", "#FF00FF"]

NAME_WIDTH = 40
COUNT_WIDTH = 10
SIZE_WIDTH = 15


def is_hidden(path):
	"""Checks if a file or directory is hidden."""
	name = os.path.basename(path)
	if name.startswith('.'):
		return True
	# Windows hidden attribute check
	if os.name == 'nt':
		try:
			import ctypes
			attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
			return attrs != -1 and (attrs & 2)
		except:
			pass
	return False

def format_size(size_bytes, raw=False):
	"""Formats bytes into human-readable strings or raw bytes."""
	if raw:
		return f"{int(size_bytes)} B"
	for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
		if size_bytes < 1024.0:
			return f"{size_bytes:3.2f} {unit}"
		size_bytes /= 1024.0
	return f"{size_bytes:3.2f} PB"

def get_dir_info(start_path, show_hidden=False):
	"""Calculates total size and file count of a directory recursively."""
	total_size = 0
	file_count = 0
	try:
		for root, dirs, files in os.walk(start_path):
			if not show_hidden:
				# Filter out hidden directories from walk
				dirs[:] = [d for d in dirs if not is_hidden(os.path.join(root, d))]
			
			for f in files:
				fp = os.path.join(root, f)
				if not show_hidden and is_hidden(fp):
					continue
				if not os.path.islink(fp):
					try:
						total_size += os.path.getsize(fp)
						file_count += 1
					except OSError:
						continue
	except (OSError, PermissionError):
		pass
	return total_size, file_count

def get_stats(target_dir, mode="files", recursive=False, max_depth=99, show_hidden=False):
	"""
	Collects stats. 
	In 'files' mode: stats per extension.
	In 'dirs' mode: stats per directory at the target depth.
	"""
	stats = defaultdict(lambda: {"count": 0, "size": 0})
	target_dir = os.path.abspath(target_dir)
	base_depth = target_dir.count(os.path.sep)

	if mode == "dirs":
		try:
			for root, dirs, _ in os.walk(target_dir):
				if not show_hidden:
					dirs[:] = [d for d in dirs if not is_hidden(os.path.join(root, d))]
				
				current_rel_depth = root.count(os.path.sep) - base_depth
				
				if current_rel_depth == max_depth:
					dir_name = os.path.relpath(root, target_dir)
					size, count = get_dir_info(root, show_hidden=show_hidden)
					stats[dir_name]["size"] = size
					stats[dir_name]["count"] = count 
					dirs[:] = [] 
				elif current_rel_depth > max_depth:
					dirs[:] = []
		except (OSError, PermissionError):
			pass
			
	else: # mode == "files"
		if recursive:
			for root, dirs, files in os.walk(target_dir):
				if not show_hidden:
					dirs[:] = [d for d in dirs if not is_hidden(os.path.join(root, d))]
				
				current_depth = root.count(os.path.sep) - base_depth
				if current_depth >= max_depth:
					dirs[:] = [] 
				
				for f in files:
					filepath = os.path.join(root, f)
					if not show_hidden and is_hidden(filepath):
						continue
					try:
						if os.path.isfile(filepath) and not os.path.islink(filepath):
							ext = os.path.splitext(f)[1].lower() or "no extension"
							stats[ext]["count"] += 1
							stats[ext]["size"] += os.path.getsize(filepath)
					except (OSError, PermissionError):
						continue
		else:
			try:
				for item in os.listdir(target_dir):
					filepath = os.path.join(target_dir, item)
					if not show_hidden and is_hidden(filepath):
						continue
					if os.path.isfile(filepath) and not os.path.islink(filepath):
						ext = os.path.splitext(item)[1].lower() or "no extension"
						stats[ext]["count"] += 1
						stats[ext]["size"] += os.path.getsize(filepath)
			except (OSError, PermissionError):
				pass

	return stats

def main():
	parser = argparse.ArgumentParser(description="Show file or directory stats with sizes.")
	
	parser.add_argument("-s", "--subdirs", nargs="?", type=int, const=99, 
						help="Include subdirectories. Optional: limit depth")
	parser.add_argument("-d", "--dirs", nargs="?", type=int, const=1,
						help="Count directories instead of file types. Optional: target depth")
	parser.add_argument("-r", "--raw", action="store_true", help="Show sizes in raw bytes")
	parser.add_argument("-a", "--all", action="store_true", help="Include hidden files and directories")
	parser.add_argument("directory", nargs="?", default=".", help="Target directory (default: current)")
	
	args = parser.parse_args()
	cap = tui.detect()
	target_path = os.path.abspath(args.directory)

	if not os.path.isdir(target_path):
		print(tui.status("error",
						 f"Error: '{target_path}' is not a valid directory.",
						 cap=cap))
		sys.exit(1)

	is_dir_mode = args.dirs is not None
	is_recursive = args.subdirs is not None
	
	if is_dir_mode:
		mode = "dirs"
		depth = args.dirs
	else:
		mode = "files"
		depth = args.subdirs if is_recursive else 0

	print()
	if is_dir_mode:
		depth_desc = f"Directories at depth {depth}"
	else:
		depth_desc = f"Recursive (up to {depth} levels)" if is_recursive else "Current folder contents"

	# The scan parameters are one key/value block: aligned muted keys on a
	# terminal, the same space-joined lines as before on a pipe (the plain
	# branch keeps the historical `key value` form, not a TAB record).
	meta = [
		("Scanning:", target_path),
		("Target:", "Directories" if is_dir_mode else "File Extensions"),
		("Mode:", depth_desc),
	]
	if args.all:
		meta.append(("Options:", "Including hidden items"))
	if cap.plain:
		for key, value in meta:
			print("{} {}".format(key, value))
	else:
		print(tui.key_values(None, meta, cap=cap))
	print()

	stats = get_stats(target_path, mode=mode, recursive=is_recursive, max_depth=depth, show_hidden=args.all)

	if not stats:
		print(tui.status("warn", "No matches found.", cap=cap))
		# Helpful tip if the directory isn't actually empty but just has subdirectories
		try:
			content = os.listdir(target_path)
			if content and not is_recursive and not is_dir_mode:
				dirs_only = [c for c in content if os.path.isdir(os.path.join(target_path, c))]
				if dirs_only:
					print()
					print(tui.status(
						"info",
						"Found {} subdirectories. Use '-s' to recurse or '-d' "
						"to list them.".format(len(dirs_only)),
						cap=cap))
		except:
			pass
		return

	sorted_data = sorted(stats.items(), key=lambda x: x[1]["size"], reverse=True)

	label = "Directory (Relative Path)" if is_dir_mode else "Extension"
	count_label = "Files" if is_dir_mode else "Count"
	rows = [(name, str(data["count"]), format_size(data["size"], raw=args.raw))
			for name, data in sorted_data]

	total_count = sum(d['count'] for d in stats.values())
	total_size = sum(d['size'] for d in stats.values())
	footer_label = "TOTAL (ALL LISTED)"

	# One table for both modes: a pipe gets the same TAB records it always did
	# (header, rows, TOTAL), a terminal the boxed table. The rows keep the
	# pinned rainbow data colours as per-cell ink and the TOTAL row is bold,
	# so the summary reads as a footer without a second frame.
	headers = (label, count_label, "Total Size")
	total_row = (footer_label, str(total_count), format_size(total_size, raw=args.raw))
	row_styles = [{"fg": RAINBOW[i % len(RAINBOW)]} for i in range(len(rows))]
	row_styles.append({"bold": True})
	# The fixed widths are exact, so a name longer than NAME_WIDTH must be cut
	# by the table seam (`..`): letting it overflow would break the frame. A
	# pipe never reaches the truncation branch, so its records stay complete.
	print(tui.render_table(headers, rows + [total_row],
						   widths=(NAME_WIDTH, COUNT_WIDTH, SIZE_WIDTH),
						   row_styles=row_styles, cap=cap))
	if not cap.plain:
		print()

if __name__ == "__main__":
	tui.init_ansi()
	try:
		main()
		sys.stdout.flush()
	except BrokenPipeError:
		# Downstream reader closed the pipe; exit quietly and point stdout at
		# devnull so the interpreter's shutdown flush cannot raise again.
		os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
		sys.exit(0)
