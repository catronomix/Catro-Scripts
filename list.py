# List all catro-scripts
"""
SCRIPT LISTER
-------------
This utility scans the directory where this specific file is located and lists 
all Python (.py) scripts found. It features a purple table layout and 
alternating green text colors.

DISCLAIMER:
This script was generated with Gemini 3.
"""

import os
import sys

# ANSI Color Codes (TrueColor support for hex equivalents)
class Colors:
	PURPLE = '\033[38;2;170;0;255m'
	GREEN_1 = '\033[38;2;0;255;0m'    # 00FF00
	GREEN_2 = '\033[38;2;34;255;34m'  # 22FF22
	BOLD = '\033[1m'
	END = '\033[0m'

def format_bytes(size):
	"""Convert bytes to a human-readable format."""
	for unit in ['B', 'KB', 'MB']:
		if size < 1024.0:
			return f"{size:3.1f} {unit}"
		size /= 1024.0
	return f"{size:3.1f} GB"

def get_description(filepath):
	"""Extracts the first non-empty line from a script as its description."""
	try:
		with open(filepath, 'r', encoding='utf-8') as f:
			for line in f:
				line = line.strip()
				if line:
					# Clean up common script starters like """, ''', or #
					clean = line.lstrip('"/#\'').strip()
					return (clean[:47] + '..') if len(clean) > 50 else clean
	except Exception:
		pass
	return "No description found"

def list_scripts():
	# Initialize Windows console for ANSI escape sequences
	if os.name == 'nt':
		os.system('')

	script_dir = os.path.dirname(os.path.abspath(__file__))
	current_script = os.path.basename(__file__)
	
	print(f"\n{Colors.PURPLE}{Colors.BOLD}--- SCRIPT DIRECTORY SCAN ---{Colors.END}")
	print(f"{Colors.PURPLE}Location:{Colors.END} {script_dir}\n")
	
	try:
		files = os.listdir(script_dir)
		scripts = sorted([f for f in files if f.endswith('.py') and f != current_script])
		
		if not scripts:
			print(f"{Colors.PURPLE}No other Python scripts found in this directory.{Colors.END}")
			return

		# Table Header
		header = f"{Colors.PURPLE}{Colors.BOLD}{'ID':<4} | {'Filename':<25} | {'Size':<10} | {'Description'}{Colors.END}"
		divider = f"{Colors.PURPLE}{'-' * 4}-+-{'-' * 25}-+-{'-' * 10}-+-{'-' * 50}{Colors.END}"
		
		print(header)
		print(divider)

		for i, script in enumerate(scripts, 1):
			file_path = os.path.join(script_dir, script)
			size = format_bytes(os.path.getsize(file_path))
			desc = get_description(file_path)
			
			# Alternate colors: 00FF00 and 22FF22
			row_color = Colors.GREEN_1 if i % 2 != 0 else Colors.GREEN_2
			
			print(f"{row_color}{i:<4} | {script:<25} | {size:<10} | {desc}{Colors.END}")

		print(divider)
		print(f"{Colors.PURPLE}{Colors.BOLD}Total scripts found:{Colors.END} {len(scripts)}\n")
		
	except Exception as e:
		print(f"\033[91mError scanning directory: {e}{Colors.END}")

if __name__ == "__main__":
	list_scripts()