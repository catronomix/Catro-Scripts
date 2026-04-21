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
	  and the script will attempt to use 'sudo'.
"""
import os
import platform
import re
import sys
import subprocess

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

def schedule_shutdown(seconds):
	"""
	Executes platform-specific shutdown commands.
	"""
	system = platform.system().lower()
	minutes = max(1, round(seconds / 60))
	
	try:
		if system == "windows":
			# Windows uses seconds for /t
			subprocess.run(["shutdown", "/s", "/t", str(seconds)], check=True)
			print(f"\n[Success] Shutdown scheduled in {seconds} seconds.")
			print("To cancel, type: shutdown /a")
			
		elif system == "linux" or system == "darwin": # Darwin is macOS
			# Unix-like systems usually take minutes for +m
			# Note: This may require sudo privileges
			print(f"\n[Note] Scheduling for {minutes} minute(s). System may prompt for password.")
			
			if system == "darwin":
				# macOS syntax: shutdown -h +minutes
				subprocess.run(["sudo", "shutdown", "-h", f"+{minutes}"], check=True)
			else:
				# Linux syntax: shutdown +minutes
				subprocess.run(["sudo", "shutdown", "-h", f"+{minutes}"], check=True)
				
			print(f"\n[Success] Shutdown scheduled in {minutes} minute(s).")
			print("To cancel, type: sudo shutdown -c")
			
		else:
			print(f"Unsupported operating system: {system}")
			
	except subprocess.CalledProcessError as e:
		print(f"\n[Error] Failed to schedule shutdown: {e}")
	except PermissionError:
		print("\n[Error] Insufficient permissions. Please run the script with administrative/sudo privileges.")

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
				schedule_shutdown(seconds)
				break
			else:
				print("Cancelled.")
		else:
			print("Invalid format. Please use units like d, h, m, or s (e.g., 1h30m).")

if __name__ == "__main__":
	main()