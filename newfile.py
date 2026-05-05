import os
import re
import sys
import platform

# wildcard file and folder creator
"""
			CATRO-SCRIPTS FILE & FOLDER CREATOR
			==================================
This script provides a powerful command-line utility to generate complex file
and directory structures using series expansion (wildcards).

It supports numeric ranges with padding preservation, character series, and 
nested directory/file creation via ordered flag processing.

Usage:
	python newfile.py [-d dirs...] [-sd subdirs...] [-f files...]

Flag Order & Context:
	-d   Creates base directories and sets the current path context.
	-sd  Creates subdirectories inside the current context and moves deeper.
	-f   Creates files in the current directory context without moving deeper.

Series Examples:
	- [001-050] (Numeric range with padding)
	- [a-z]     (Character series)
	- [1-10][a-g] (Nested/combined series)

Example Command:
	python newfile.py -d project[1-3] -f index.html -sd src assets -f script.js
	# Creates 3 projects, each with index.html, src/, assets/, and script.js in both subdirs.

Requirements:
	- No external libraries required.
	- Validates filenames against OS-specific reserved names (Windows).
"""

def expand_filenames(pattern):
	"""
	Recursively expands patterns like [001-010] or [a-z] into a list of strings.
	Supports multiple brackets in one string.
	"""
	match = re.search(r'\[([a-zA-Z0-9]+)-([a-zA-Z0-9]+)\]', pattern)
	if not match:
		return [pattern]

	start_str, end_str = match.groups()
	prefix = pattern[:match.start()]
	suffix = pattern[match.end():]
	
	results = []

	# Case 1: Numeric Range
	if start_str.isdigit() and end_str.isdigit():
		width = len(start_str)
		start = int(start_str)
		end = int(end_str)
		step = 1 if start <= end else -1
		for i in range(start, end + step, step):
			current = str(i).zfill(width)
			results.extend(expand_filenames(f"{prefix}{current}{suffix}"))

	# Case 2: Character Range
	elif len(start_str) == 1 and len(end_str) == 1 and start_str.isalpha() and end_str.isalpha():
		start_ord = ord(start_str)
		end_ord = ord(end_str)
		step = 1 if start_ord <= end_ord else -1
		for i in range(start_ord, end_ord + step, step):
			current = chr(i)
			results.extend(expand_filenames(f"{prefix}{current}{suffix}"))
	else:
		return [pattern]

	return results

def is_valid_name(name):
	"""Checks if the name is valid for the current operating system."""
	if not name or len(name) > 255:
		return False

	system = platform.system()
	if system == "Windows":
		segments = re.split(r'[\\/]', name)
		reserved_names = {
			"CON", "PRN", "AUX", "NUL", 
			"COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
			"LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
		}
		for i, seg in enumerate(segments):
			if i == 0 and re.match(r'^[a-zA-Z]:$', seg):
				continue
			if re.search(r'[<>:"|?*]', seg):
				return False
			base_name = seg.split('.')[0].upper()
			if base_name in reserved_names:
				return False
	else:
		if '\0' in name:
			return False
	return True

def create_item(path, is_dir=False):
	"""Helper to create a single file or directory."""
	if not is_valid_name(path):
		print(f"[Error] Invalid path: {path}")
		return False
	try:
		if is_dir:
			if os.path.isdir(path):
				# Gracefully treat existing directory as if it were just created
				return True
			os.makedirs(path, exist_ok=True)
			print(f"[Created] Directory: {path}")
		else:
			if os.path.exists(path):
				# Explicitly skip existing files
				return True
			
			parent = os.path.dirname(path)
			if parent:
				os.makedirs(parent, exist_ok=True)
			
			with open(path, 'a'):
				os.utime(path, None)
			print(f"[Created] File: {path}")
		return True
	except Exception as e:
		print(f"[Error] Failed to create {path}: {e}")
		return False

def main():
	if len(sys.argv) < 2:
		print("Usage: python newfile.py [-d dirs...] [-sd subdirs...] [-f files...]")
		return

	# Manual parsing to maintain order of operations
	args = sys.argv[1:]
	current_targets = ["."] # Start in current directory
	
	i = 0
	while i < len(args):
		flag = args[i]
		values = []
		i += 1
		while i < len(args) and not args[i].startswith('-'):
			values.append(args[i])
			i += 1

		if not values:
			continue

		expanded_values = []
		for v in values:
			expanded_values.extend(expand_filenames(v))

		new_targets = []

		if flag in ('-d', '--dirs'):
			# Create directories in the current context
			for base in current_targets:
				for d in expanded_values:
					path = os.path.join(base, d)
					if create_item(path, is_dir=True):
						new_targets.append(path)
			current_targets = new_targets # Move context into these new dirs

		elif flag in ('-sd', '--subdir'):
			# Create subdirectories inside the current context
			for base in current_targets:
				for sd in expanded_values:
					path = os.path.join(base, sd)
					if create_item(path, is_dir=True):
						new_targets.append(path)
			current_targets = new_targets # Move context deeper

		elif flag in ('-f', '--files'):
			# Create files in every directory of the current context
			for base in current_targets:
				for f in expanded_values:
					path = os.path.join(base, f)
					create_item(path, is_dir=False)
			# Files do not change the directory context for subsequent flags
		else:
			print(f"[Warning] Unknown flag: {flag}")

if __name__ == "__main__":
	main()