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

# Directories that hold `shutdown` on Unix but are not always on the PATH a
# wrapper inherits (minimal shells, services). POSIX-only: never read on Windows.
SBIN_DIRS = ("/sbin", "/usr/sbin")

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
		match = re.search(f'(\d+){unit}', duration_str)
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

def schedule_shutdown(seconds):
	"""
	Executes platform-specific shutdown commands.

	Returns True only when the command actually ran. Every failure path prints
	one diagnosis and returns False, so main() can exit non-zero instead of
	reporting success for a shutdown that was never scheduled.
	"""
	system = platform.system().lower()
	minutes = max(1, round(seconds / 60))

	if system == "windows":
		# Windows uses seconds for /t
		program = find_windows_shutdown()
		argv = [program, "/s", "/t", str(seconds)]
		success = f"\n[Success] Shutdown scheduled in {seconds} seconds."
		cancel_hint = "To cancel, type: shutdown /a"
	elif system == "linux" or system == "darwin": # Darwin is macOS
		# Unix-like systems usually take minutes for +m
		program = find_posix_program("shutdown")
		if program is None:
			print("\n[Error] 'shutdown' was not found on this system "
				  f"(looked on PATH, {', '.join(SBIN_DIRS)}).")
			return False

		argv = [program, "-h", f"+{minutes}"]
		geteuid = getattr(os, "geteuid", None)
		if geteuid is not None and geteuid() == 0:
			# Already root: call the command directly, no sudo needed.
			pass
		else:
			sudo = shutil.which("sudo")
			if sudo is None:
				print("\n[Error] 'sudo' is required but not installed, and this "
					  "process is not root; cannot schedule a shutdown.")
				return False
			argv.insert(0, sudo)
			print(f"\n[Note] Scheduling for {minutes} minute(s). System may prompt for password.")

		success = f"\n[Success] Shutdown scheduled in {minutes} minute(s)."
		cancel_hint = "To cancel, type: sudo shutdown -c"
	else:
		print(f"Unsupported operating system: {system}")
		return False

	try:
		subprocess.run(argv, check=True)
	except (OSError, subprocess.SubprocessError) as exc:
		# One handler, two distinct diagnoses: the program never launched
		# (missing binary) versus it ran and refused (permissions/returncode).
		if isinstance(exc, FileNotFoundError):
			print(f"\n[Error] '{argv[0]}' was not found on this system "
				  f"(argv: {' '.join(argv)}).")
		else:
			returncode = getattr(exc, "returncode", None)
			reason = ("insufficient permissions"
					  if isinstance(exc, PermissionError)
					  else f"returncode {returncode}")
			print(f"\n[Error] '{argv[0]}' failed with {reason} "
				  f"(argv: {' '.join(argv)}).")
		return False

	print(success)
	print(cancel_hint)
	return True

def main():
	print("=== Cross-Platform Shutdown Timer ===")
	print("Examples of valid time formats:")
	print("  - 2h30m (2 hours, 30 minutes)")
	print("  - 1d5h  (1 day, 5 hours)")
	print("  - 45m   (45 minutes)")
	print("  - 90    (90 minutes - default unit)")
	print("=====================================")

	while True:
		user_input = input("\nEnter shutdown delay (or 'q' to quit): ").strip()
		
		if user_input.lower() == 'q':
			break
			
		seconds = parse_duration(user_input)
		
		if seconds is not None and seconds > 0:
			confirm = input(f"Confirm shutdown in approx. {seconds // 60} minutes? (y/n): ")
			if confirm.lower() == 'y':
				if not schedule_shutdown(seconds):
					# A failed schedule must not look like success to the
					# wrapper or to any script chaining off this one.
					sys.exit(1)
				break
			else:
				print("Cancelled.")
		else:
			print("Invalid format. Please use units like d, h, m, or s (e.g., 1h30m).")

if __name__ == "__main__":
	main()