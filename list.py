# List all catro-scripts
"""
			CATRO-SCRIPTS LISTER
			====================
This utility scans its directory for all Python (.py) scripts and displays them
in the house table: a box with padded columns on a terminal (coloured according
to the colour level), one TAB-separated record per line when the output is
piped.

Features:
	- Automatically extracts descriptions from scripts.
	- Human-readable file sizes.
	- Alternating row backgrounds (velvet purple / slate purple) with lavender text.
	- Full box-drawing border and fixed 4/25/10/50 column widths.
	- Plain TAB-separated output when stdout is not a terminal.

Usage:
	python list.py
"""

import os
import sys

import tui

# Fixed column widths. They are handed to the renderer verbatim so it never
# re-measures or fits the terminal: these are the exact widths the table has
# always used, and its bytes depend on them.
COLUMN_WIDTHS = [4, 25, 10, 50]

# `get_description` owns the description truncation (47 characters then ".."),
# so the renderer must not truncate that cell a second time.
DESCRIPTION_WIDTH = 47


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
					return (clean[:DESCRIPTION_WIDTH] + '..') if len(clean) > 50 else clean
	except Exception:
		pass
	return "No description found"


def list_scripts():
	# Capabilities are resolved once: the whole run uses one colour level,
	# Unicode decision and plain/tty mode.
	tui.init_ansi()
	cap = tui.detect()

	script_dir = os.path.dirname(os.path.abspath(__file__))
	current_script = os.path.basename(__file__)

	print()
	# Masthead through the page-chrome seam: title band, muted location band,
	# then the border rule (which a pipe drops, keeping the two plain lines).
	print(tui.header("--- SCRIPT DIRECTORY SCAN ---", "Location: " + script_dir,
					 cap=cap))
	print()

	try:
		files = os.listdir(script_dir)
		scripts = sorted([f for f in files if f.endswith('.py') and f != current_script])

		if not scripts:
			print(tui.status("warn",
							 "No other Python scripts found in this directory.",
							 cap=cap))
			return

		# One row per script. The cells are built exactly as the renderer will
		# print them: sizes are pre-formatted, the description is pre-truncated
		# and the widths are the fixed ones above.
		rows = []
		for i, script in enumerate(scripts, 1):
			file_path = os.path.join(script_dir, script)
			rows.append((
				i,
				script[:-3] if script.endswith('.py') else script,
				format_bytes(os.path.getsize(file_path)),
				get_description(file_path),
			))

		tui.print_table(["ID", "Script Name", "Size", "Description"], rows,
						widths=COLUMN_WIDTHS, truncate=False, cap=cap)
		print(tui.style("Total scripts found:", fg="border", bold=True, cap=cap),
			  len(scripts))
		print()

	except UnicodeEncodeError:
		# Do not swallow this one: printing it and exiting 0 would make a
		# UTF-8 problem look like a successful, empty scan.
		raise
	except BrokenPipeError:
		# The reader went away (e.g. `| head`); not a scan failure, and
		# printing an error here would write into the same dead pipe.
		raise
	except Exception as e:
		print(tui.status("error", "Error scanning directory: {}".format(e), cap=cap))
		sys.exit(1)

if __name__ == "__main__":
	try:
		list_scripts()
		sys.stdout.flush()
	except BrokenPipeError:
		# Downstream reader closed the pipe; exit quietly and point stdout at
		# devnull so the interpreter's shutdown flush cannot raise again.
		os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
		sys.exit(0)
