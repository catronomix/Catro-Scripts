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
	- Displays help in the house purple box.
	- Plain text when the output is piped.
	- Specialized header detection and styling.
	- Smart command aliasing when catro-scripts wrapper is present.

Usage:
	python help.py <script_name>

Example:
	python help.py count
	# Displays the introduction and help text for count.py
"""
import os
import sys
import ast
import re

import tui

# Indentation depth -> style data handed to tui.style(). The hexes are the
# base-ANSI entries on purpose: each old raw code (1;37, 0;36, 0;32, 0;33, 0;31)
# is exactly what the level-16 downgrade of these colours produces, so a
# 16-colour terminal keeps the same palette it always had.
INDENT_STYLES = [
	{"fg": "#C0C0C0", "bold": True},  # Level 0: bold white
	{"fg": "#008080"},  # Level 1: cyan
	{"fg": "#008000"},  # Level 2: green
	{"fg": "#808000"},  # Level 3: yellow
	{"fg": "#800000"},  # Level 4: red
]

BOX_WIDTH_FLOOR = 40


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


def print_colored_docstring(docstring, cap=None):
	# Prints the docstring with colors based on indentation depth.
	# Assumes scripts use tab characters (\t) for indentation as requested.
	cap = cap or tui.detect()
	glyphs = tui.table.glyphs_for(cap)

	if not docstring:
		message = "No intro text (docstring) found in this script."
		if cap.plain:
			print(message)
			return
		# Themed status line instead of a one-line hand-drawn box: same words,
		# but the marker and text come from the palette roles.
		print(tui.status("error", message, cap=cap))
		return

	# Check for catro-scripts wrapper to allow command aliasing in help text
	script_dir = get_script_directory()
	has_wrapper = os.path.exists(os.path.join(script_dir, "catro-scripts.bat")) or \
				  os.path.exists(os.path.join(script_dir, "catro-scripts.sh"))

	if has_wrapper:
		# Replace "python {scriptname}.py" with "catro-scripts {scriptname}"
		docstring = re.sub(r'python (\S+)\.py', r'catro-scripts \1', docstring)

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

	max_w = max(check_widths) if check_widths else BOX_WIDTH_FLOOR
	box_width = max_w + 2

	if cap.plain:
		# Piped output: text only, one line per document line, no box and no
		# padding. The indentation stays visible as the original spaces.
		if has_header:
			print(header_text)
			print()
		for line in content_lines:
			print(line.replace('\t', '    '))
		return

	tl, tr, bl, br = glyphs["tl"], glyphs["tr"], glyphs["bl"], glyphs["br"]
	h, v, l_join, r_join = glyphs["h"], glyphs["v"], glyphs["ml"], glyphs["mr"]

	# Top Border
	print(tui.style(tl + h * box_width + tr, fg="border-fg", cap=cap))

	if has_header:
		# Header Row: the docstring title as a themed section heading, framed by
		# the box borders. No per-script yellow-on-purple any more.
		centered_header = header_text.center(box_width)
		print(tui.style(v, fg="border-fg", cap=cap)
			  + tui.section(centered_header, cap=cap)
			  + tui.style(v, fg="border-fg", cap=cap))
		# Divider Row replacing the equal signs
		print(tui.style(l_join + h * box_width + r_join, fg="border-fg", cap=cap))

	for line in content_lines:
		# Count leading tabs for coloring
		indent_level = 0
		for char in line:
			if char == '\t':
				indent_level += 1
			else:
				break

		# Select style based on depth
		indent_style = INDENT_STYLES[indent_level % len(INDENT_STYLES)]

		# Expand tabs and calculate padding for alignment
		display_line = line.replace('\t', '    ')
		padding = " " * (max_w - len(display_line))

		print(tui.style(v, fg="border-fg", cap=cap) + " "
			  + tui.style(display_line + padding, cap=cap, **indent_style) + " "
			  + tui.style(v, fg="border-fg", cap=cap))

	# Bottom Border
	print(tui.style(bl + h * box_width + br, fg="border-fg", cap=cap))


def main():
	tui.init_ansi()
	cap = tui.detect()

	if len(sys.argv) < 2:
		print("Usage: python help.py <script_name_without_extension>")
		sys.exit(1)

	target_name = sys.argv[1]
	script_dir = get_script_directory()
	target_path = os.path.join(script_dir, f"{target_name}.py")

	if not os.path.exists(target_path):
		print(tui.status(
			"error",
			f"Error: Script '{target_name}.py' not found in {script_dir}",
			cap=cap))
		sys.exit(1)

	print()
	print(tui.header(f"--- Help for {target_name} ---", cap=cap))
	print()
	doc = get_docstring(target_path)
	print_colored_docstring(doc, cap)
	print("")


if __name__ == "__main__":
	try:
		main()
		sys.stdout.flush()
	except BrokenPipeError:
		# Downstream reader closed the pipe; exit quietly and point stdout at
		# devnull so the interpreter's shutdown flush cannot raise again.
		os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
		sys.exit(0)
