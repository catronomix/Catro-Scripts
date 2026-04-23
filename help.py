# Help
"""
			SCRIPT HELP UTILITY
			===================
This utility extracts the module-level docstring from a specified script and 
displays it with color-coding based on indentation levels. It's designed to 
make reading script introductions and usage guides easier in the terminal.

Features:
	- Extracts raw docstrings using Python's 'ast' module.
	- Color-codes lines based on tab indentation depth.
	- Automatic ANSI initialization for Windows.
	- Displays help in a formatted purple ASCII box.
	- Specialized header detection and styling.

Usage:
	python help.py <script_name>

Example:
	python help.py count
	# Displays the introduction and help text for count.py
"""
import os
import sys
import ast
import platform

def init_ansi():
	# Enables ANSI escape sequences on Windows 10+ consoles.
	if platform.system().lower() == "windows":
		os.system('color')
		
def get_script_directory():
	# Returns the absolute path of the directory where this script is located.
	return os.path.dirname(os.path.abspath(__file__))

def get_docstring(filepath):
	# Extracts the raw module-level docstring without dedenting it.
	try:
		with open(filepath, 'r', encoding='utf-8') as f:
			tree = ast.parse(f.read())
			# Look for the first expression in the module
			if (tree.body and 
				isinstance(tree.body[0], ast.Expr) and 
				isinstance(tree.body[0].value, ast.Constant) and 
				isinstance(tree.body[0].value.value, str)):
				return tree.body[0].value.value
		return None
	except Exception:
		return None

def print_colored_docstring(docstring):
	# Prints the docstring with colors based on indentation depth.
	# Assumes scripts use tab characters (\t) for indentation as requested.
	
	# ANSI Color codes
	PURPLE = '\033[38;2;170;0;255m'
	HEADER_BG = '\033[48;2;60;0;90m'     # Dark Purple Background
	HEADER_FG = '\033[38;2;255;255;0m'   # Yellow Foreground
	COLORS = [
		"\033[1;37m", # Level 0: Bold White
		"\033[0;36m", # Level 1: Cyan
		"\033[0;32m", # Level 2: Green
		"\033[0;33m", # Level 3: Yellow
		"\033[0;31m", # Level 4: Red
	]
	RESET = "\033[0m"
	BOLD = "\033[1m"

	if not docstring:
		print(f"{PURPLE}┌──────────────────────────────────────────────────┐{RESET}")
		print(f"{PURPLE}│{RESET} {COLORS[4]}No intro text (docstring) found in this script. {RESET}{PURPLE}│{RESET}")
		print(f"{PURPLE}└──────────────────────────────────────────────────┘{RESET}")
		return

	raw_lines = docstring.splitlines()
	
	# Robust detection of first two content lines
	has_header = False
	header_text = ""
	start_index = 0

	# Skip leading empty lines often found in docstrings
	i = 0
	while i < len(raw_lines) and not raw_lines[i].strip():
		i += 1

	# Check if the next two lines form a header (Text + === underline)
	if i + 1 < len(raw_lines):
		title_candidate = raw_lines[i].strip()
		divider_candidate = raw_lines[i+1].strip()
		if len(divider_candidate) >= 3 and all(c == '=' for c in divider_candidate):
			has_header = True
			header_text = title_candidate
			start_index = i + 2
			# Skip any immediate blank lines after the header divider
			while start_index < len(raw_lines) and not raw_lines[start_index].strip():
				start_index += 1
	else:
		start_index = i

	content_lines = raw_lines[start_index:]
	
	# Calculate box width
	check_widths = [len(line.replace('\t', '    ')) for line in content_lines]
	if has_header:
		check_widths.append(len(header_text))
	
	max_w = max(check_widths) if check_widths else 40
	box_width = max_w + 2

	# Box Drawing Characters
	tl, tr, bl, br = '┌', '┐', '└', '┘'
	h, v = '─', '│'
	l_join, r_join = '├', '┤'

	# Top Border
	print(f"{PURPLE}{tl}{h * box_width}{tr}{RESET}")

	if has_header:
		# Header Row: Centered Yellow on Dark Purple
		# The text is centered across the full internal width of the box
		centered_header = header_text.center(box_width)
		print(f"{PURPLE}{v}{HEADER_BG}{HEADER_FG}{centered_header}{RESET}{PURPLE}{v}{RESET}")
		# Divider Row replacing the equal signs
		print(f"{PURPLE}{l_join}{h * box_width}{r_join}{RESET}")

	for line in content_lines:
		# Count leading tabs for coloring
		indent_level = 0
		for char in line:
			if char == '\t':
				indent_level += 1
			else:
				break
		
		# Select color based on depth
		color = COLORS[indent_level % len(COLORS)]
		
		# Expand tabs and calculate padding for alignment
		display_line = line.replace('\t', '    ')
		padding = " " * (max_w - len(display_line))
		
		print(f"{PURPLE}{v}{RESET} {color}{display_line}{padding} {RESET}{PURPLE}{v}{RESET}")

	# Bottom Border
	print(f"{PURPLE}{bl}{h * box_width}{br}{RESET}")

def main():
	init_ansi()
	if len(sys.argv) < 2:
		print("Usage: python help.py <script_name_without_extension>")
		sys.exit(1)

	target_name = sys.argv[1]
	script_dir = get_script_directory()
	target_path = os.path.join(script_dir, f"{target_name}.py")

	if not os.path.exists(target_path):
		print(f"\033[0;31mError: Script '{target_name}.py' not found in {script_dir}\033[0m")
		sys.exit(1)

	PURPLE = '\033[38;2;170;0;255m'
	BOLD = '\033[1m'
	RESET = '\033[0m'

	print(f"\n{PURPLE}{BOLD}--- Help for {target_name} ---{RESET}\n")
	doc = get_docstring(target_path)
	print_colored_docstring(doc)
	print("")

if __name__ == "__main__":
	main()