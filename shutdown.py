# interactive system shutdown timer 
"""
			CROSS-PLATFORM SHUTDOWN TIMER
			=============================
This script provides an interactive command-line utility to schedule a system shutdown
on Windows, macOS, and Linux operating systems.

It prompts the user for a shutdown delay using flexible time formats (e.g., 2h30m, 1d, 90m).
After confirmation, it executes the appropriate platform-specific system command
to set the shutdown timer.

Usage:
	Run the script directly:
		python shutdown.py
	Or, if using the catro-scripts wrapper:
		catro-scripts shutdown

Time Input Examples:
	- 2h30m (2 hours, 30 minutes)
	- 1d5h  (1 day, 5 hours)
	- 45m   (45 minutes)
	- 90    (90 minutes - default unit if no unit specified)

Requirements:
	- No external libraries required; uses standard Python modules.
	- On Linux/macOS, scheduling a shutdown may require 'sudo' privileges,
	  and the script will attempt to use 'sudo'. If 'sudo' or 'shutdown' is
	  missing, or the command fails, the script prints one error line and
	  exits 1 instead of reporting success.
"""
import os
import platform
import re
import shutil
import sys
import subprocess

import tui

# Directories that hold `shutdown` on Unix but are not always on the PATH a
# wrapper inherits (minimal shells, services). POSIX-only: never read on Windows.
SBIN_DIRS = ("/sbin", "/usr/sbin")

# `tui.ask_text` returns this when stdin closes; a closed stdin is a quit.
_EOF = object()

# The interactive page: masthead title, the format examples and the two prompt
# rows all live inside one content-sized panel (0044).
PAGE_TITLE = "Cross-Platform Shutdown Timer"
FORMAT_EXAMPLES = (
	"Examples of valid time formats:",
	"  - 2h30m (2 hours, 30 minutes)",
	"  - 1d5h  (1 day, 5 hours)",
	"  - 45m   (45 minutes)",
	"  - 90    (90 minutes - default unit)",
)
DELAY_PROMPT = "Enter shutdown delay (or 'q' to quit): "

def parse_duration(duration_str):
	"""
	Parses strings like '1d2h30m', '2h', '45m' into total seconds.
	"""
	duration_str = duration_str.lower().strip()
	patterns = {
		'd': 86400,
		'h': 3600,
		'm': 60,
		's': 1
	}
	
	total_seconds = 0
	found = False
	
	for unit, multiplier in patterns.items():
		match = re.search(rf'(\d+){unit}', duration_str)
		if match:
			total_seconds += int(match.group(1)) * multiplier
			found = True
			
	# Fallback: if user just types a number, assume minutes
	if not found and duration_str.isdigit():
		total_seconds = int(duration_str) * 60
		found = True
		
	return total_seconds if found else None

def find_posix_program(name):
	"""
	Locates a POSIX program on PATH, then in the sbin directories.

	POSIX-only helper: the Windows branch never calls it, so no `sudo`/`/sbin`
	lookup can happen on `os.name == "nt"`.
	"""
	found = shutil.which(name)
	if found:
		return found
	for directory in SBIN_DIRS:
		candidate = os.path.join(directory, name)
		if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
			return candidate
	return None

def find_windows_shutdown():
	"""
	Resolves shutdown.exe through %SystemRoot%\\System32 (the documented location)
	and falls back to the bare name, which lets CreateProcess do its own search.

	No shutil.which/sudo/geteuid: the Windows path stays exactly as it was.
	"""
	system_root = os.environ.get("SystemRoot", r"C:\Windows")
	candidate = os.path.join(system_root, "System32", "shutdown.exe")
	return candidate if os.path.isfile(candidate) else "shutdown"

def panel_width(rows, cap, title=None):
	"""
	Content-sized panel width: the widest row plus the frame and its two
	gutters, never wider than the terminal (which still caps the panel on a
	narrow stream). `cap` handling is unchanged: plain mode ignores width.
	"""
	needed = max([tui.display_width(row) for row in rows] + [0]) + 4
	if title:
		# Room for one rule glyph, " title ", and one more rule glyph.
		needed = max(needed, tui.display_width(title) + 6)
	if cap.width:
		needed = min(needed, cap.width)
	return max(4, needed)

def page_panel(cap, prompt, error=None):
	"""
	One content-sized page panel: the masthead title in the top rule, the
	format examples, the current prompt row and, when the last answer was
	rejected, the warning row. Nothing here reads stdin.
	"""
	rows = list(FORMAT_EXAMPLES)
	rows.append("")
	if prompt:
		rows.append(tui.style(prompt, fg="header-fg", bg="bg-inside",
							  bold=True, cap=cap))
	width = panel_width(rows, cap, PAGE_TITLE)
	if error:
		# The warning is the longest row and would be cut by the panel: wrap
		# it under its marker on a terminal instead. A pipe keeps one line.
		if cap.plain:
			rows.append(tui.status("warn", error, cap=cap))
		else:
			indent = len(tui.chrome.STATUS_MARKERS["warn"]) + 1
			cell = max(1, width - 4)
			pieces = tui.wrap(error, max(1, cell - indent)) or [""]
			rows.append(tui.status("warn", pieces[0], cap=cap))
			rows.extend(" " * indent + piece for piece in pieces[1:])
	return tui.panel(PAGE_TITLE, rows, width=width, cap=cap)

def schedule_shutdown(seconds, cap=None):
	"""
	Executes platform-specific shutdown commands.

	Returns True only when the command actually ran. Every failure path prints
	one diagnosis and returns False, so main() can exit non-zero instead of
	reporting success for a shutdown that was never scheduled.
	"""
	cap = cap or tui.detect()
	system = platform.system().lower()
	minutes = max(1, round(seconds / 60))

	if system == "windows":
		# Windows uses seconds for /t
		program = find_windows_shutdown()
		argv = [program, "/s", "/t", str(seconds)]
		success = f"Shutdown scheduled in {seconds} seconds."
		cancel_hint = "To cancel, type: shutdown /a"
	elif system == "linux" or system == "darwin": # Darwin is macOS
		# Unix-like systems usually take minutes for +m
		program = find_posix_program("shutdown")
		if program is None:
			print("\n" + tui.status(
				"error",
				"'shutdown' was not found on this system "
				f"(looked on PATH, {', '.join(SBIN_DIRS)}).", cap=cap))
			return False

		argv = [program, "-h", f"+{minutes}"]
		geteuid = getattr(os, "geteuid", None)
		if geteuid is not None and geteuid() == 0:
			# Already root: call the command directly, no sudo needed.
			pass
		else:
			sudo = shutil.which("sudo")
			if sudo is None:
				print("\n" + tui.status(
					"error",
					"'sudo' is required but not installed, and this "
					"process is not root; cannot schedule a shutdown.",
					cap=cap))
				return False
			argv.insert(0, sudo)
			print("\n" + tui.status(
				"info",
				f"Scheduling for {minutes} minute(s). System may prompt for password.",
				cap=cap))

		success = f"Shutdown scheduled in {minutes} minute(s)."
		cancel_hint = "To cancel, type: sudo shutdown -c"
	else:
		print(tui.status("error", f"Unsupported operating system: {system}", cap=cap))
		return False

	try:
		subprocess.run(argv, check=True)
	except (OSError, subprocess.SubprocessError) as exc:
		# One handler, two distinct diagnoses: the program never launched
		# (missing binary) versus it ran and refused (permissions/returncode).
		if isinstance(exc, FileNotFoundError):
			print("\n" + tui.status(
				"error",
				f"'{argv[0]}' was not found on this system "
				f"(argv: {' '.join(argv)}).", cap=cap))
		else:
			returncode = getattr(exc, "returncode", None)
			reason = ("insufficient permissions"
					  if isinstance(exc, PermissionError)
					  else f"returncode {returncode}")
			print("\n" + tui.status(
				"error",
				f"'{argv[0]}' failed with {reason} "
				f"(argv: {' '.join(argv)}).", cap=cap))
		return False

	rows = [tui.status("ok", success, cap=cap),
			tui.status("info", cancel_hint, cap=cap)]
	print("\n" + tui.panel(None, rows, width=panel_width(rows, cap), cap=cap))
	return True

def main():
	tui.init_ansi()
	cap = tui.detect()

	error = None
	while True:
		# The page (masthead, examples, prompt and the last rejection) is one
		# content-sized panel; the prompt row is drawn by it, so the read is a
		# bare `tui.ask_text("")` and stdin stays the shared seam. A closed
		# stdin is a quit, not a re-prompt: the 0041 EOF sentinel ends the loop.
		print(page_panel(cap, DELAY_PROMPT, error=error))
		user_input = tui.ask_text("", eof=_EOF)

		if user_input is _EOF or user_input.lower() == 'q':
			break

		seconds = parse_duration(user_input)

		if seconds is not None and seconds > 0:
			error = None
			prompt = (f"Confirm shutdown in approx. {seconds // 60} "
					  f"minutes? (y/n): ")
			print(page_panel(cap, prompt))
			confirm = tui.ask_text("")
			if confirm.lower() == 'y':
				if not schedule_shutdown(seconds, cap=cap):
					# A failed schedule must not look like success to the
					# wrapper or to any script chaining off this one.
					sys.exit(1)
				break
			else:
				print("Cancelled.")
		else:
			error = ("Invalid format. Please use units like d, h, m, or s "
					 "(e.g., 1h30m).")

if __name__ == "__main__":
	main()