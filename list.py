# List all catro-scripts
"""
			CATRO-SCRIPTS LISTER
			====================
This utility scans its directory for all Python (.py) scripts and displays them 
in a formatted ASCII box-drawing table.

Features:
	- Automatically extracts descriptions from scripts.
	- Human-readable file sizes.
	- Alternating row backgrounds (Black/Dark Grey) with Light Blue text.
	- Full box-drawing border.

Usage:
	python list.py
"""

import os
import sys

# ANSI Color Codes (TrueColor support)
class Colors:
	PURPLE = '\033[38;2;170;0;255m'
	LIGHT_BLUE = '\033[38;2;173;216;230m' # Light Blue foreground
	BG_BLACK = '\033[48;2;0;0;0m'         # Black background
	BG_GREY = '\033[48;2;45;45;45m'       # Dark Grey background
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
					# Clean up common script starters
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

		# Column widths
		w_id = 4
		w_name = 25
		w_size = 10
		w_desc = 50

		# Box Drawing Characters
		tl, tr, bl, br = '┌', '┐', '└', '┘'
		h, v = '─', '│'
		t_join, b_join, l_join, r_join, cross = '┬', '┴', '├', '┤', '┼'

		# Helper to build rows
		def make_divider(left, mid, right, cross_char):
			return (f"{Colors.PURPLE}{left}{h*(w_id+2)}{cross_char}{h*(w_name+2)}{cross_char}"
					f"{h*(w_size+2)}{cross_char}{h*(w_desc+2)}{right}{Colors.END}")

		# Borders
		top_border = make_divider(tl, t_join, tr, t_join)
		mid_border = make_divider(l_join, cross, r_join, cross)
		bot_border = make_divider(bl, b_join, br, b_join)

		# Print Header
		print(top_border)
		header = (f"{Colors.PURPLE}{v}{Colors.BOLD} {'ID':<{w_id}} {v} {'Script Name':<{w_name}} {v} "
				  f"{'Size':<{w_size}} {v} {'Description':<{w_desc}} {v}{Colors.END}")
		print(header)
		print(mid_border)

		for i, script in enumerate(scripts, 1):
			file_path = os.path.join(script_dir, script)
			size = format_bytes(os.path.getsize(file_path))
			desc = get_description(file_path)
			
			script_name = script[:-3] if script.endswith('.py') else script
			
			# Set background and foreground colors for the row
			bg = Colors.BG_BLACK if i % 2 != 0 else Colors.BG_GREY
			row_style = Colors.LIGHT_BLUE + bg
			
			# Constructing the row. 
			# We reset the color (Colors.END) before printing the final vertical border 
			# to ensure the background color doesn't bleed into it.
			row = (f"{Colors.PURPLE}{v}{row_style} {i:<{w_id}} {Colors.PURPLE}{v}{row_style} {script_name:<{w_name}} "
				   f"{Colors.PURPLE}{v}{row_style} {size:<{w_size}} {Colors.PURPLE}{v}{row_style} {desc:<{w_desc}} "
				   f"{Colors.END}{Colors.PURPLE}{v}{Colors.END}")
			print(row)

		print(bot_border)
		print(f"{Colors.PURPLE}{Colors.BOLD}Total scripts found:{Colors.END} {len(scripts)}\n")
		
	except Exception as e:
		print(f"\033[91mError scanning directory: {e}{Colors.END}")

if __name__ == "__main__":
	list_scripts()