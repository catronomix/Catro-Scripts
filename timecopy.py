# Clone file timestamps
"""
			Full Metadata Cloner
			====================
A utility to copy external file system timestamps (Creation, Modification, 
and Access dates) from a source file to a target file.

Usage:
	python timecopy.py <source_path> <target_path>

Requirements:
	- Supports any file type for system timestamps.

Warning:
	- Unix does not support direct spoofing of file creation times.

Disclaimer: This script was generated with Gemini 3
"""

import sys
import os
import time
import ctypes

import tui

def set_creation_time(path, timestamp, cap=None):
	"""
	Attempts to set the creation time of a file.
	Note: This is highly OS-dependent (primarily Windows).
	"""
	cap = cap or tui.detect()
	if os.name == 'nt':  # Windows
		try:
			# Convert python timestamp to Windows FILETIME
			# 100-nanosecond intervals since Jan 1, 1601
			timestamp = int((timestamp * 10000000) + 116444736000000000)
			ctime = ctypes.c_int64(timestamp)
			
			# Open file handle
			handle = ctypes.windll.kernel32.CreateFileW(
				path, 0x0100, 0, None, 3, 0x80, None
			)
			if handle != -1:
				# SetFileTime(handle, lpCreationTime, lpLastAccessTime, lpLastWriteTime)
				ctypes.windll.kernel32.SetFileTime(handle, ctypes.byref(ctime), None, None)
				ctypes.windll.kernel32.CloseHandle(handle)
		except Exception as e:
			print(tui.status("warn", f"Could not set Windows creation time: {e}",
							 cap=cap))
	else:
		# Linux/macOS generally do not support setting 'birth time' via standard APIs
		print(tui.status("info", "Notice: Unix-based systems generally do not support "
						 "setting file creation time (Birth Time). Skipping.",
						 cap=cap))

def copy_metadata(source_path, target_path, cap=None):
	"""
	Copies file system timestamps from source to target.
	"""
	cap = cap or tui.detect()
	abs_source = os.path.abspath(source_path)
	abs_target = os.path.abspath(target_path)

	if not os.path.exists(abs_source):
		print(tui.status("error", f"Error: Source file '{abs_source}' does not exist.",
						 cap=cap))
		return

	if not os.path.exists(abs_target):
		print(tui.status("error", f"Error: Target file '{abs_target}' does not exist.",
						 cap=cap))
		return

	# --- Copy File System Timestamps ---
	try:
		stats = os.stat(abs_source)
		atime = stats.st_atime
		mtime = stats.st_mtime
		
		# On some systems st_ctime is change time, on Windows it's creation
		# Use st_birthtime if available (macOS/BSD)
		ctime = getattr(stats, 'st_birthtime', stats.st_ctime)

		# Set Access and Modification times
		os.utime(abs_target, (atime, mtime))
		
		# Set Creation time (Windows specific via kernel call)
		set_creation_time(abs_target, ctime, cap=cap)

		print(tui.section("Successfully synchronized system timestamps:", cap=cap))
		print(tui.key_values(None, [
			("Created", time.ctime(ctime)),
			("Modified", time.ctime(mtime)),
			("Accessed", time.ctime(atime)),
		], cap=cap))
		
	except Exception as e:
		print(tui.status("error", f"An error occurred while copying system timestamps: {e}",
						 cap=cap))

def main():
	tui.init_ansi()
	cap = tui.detect()

	if len(sys.argv) != 3:
		print("Usage: catro-scripts timecopy <source_path> <target_path>")
		sys.exit(1)

	source = sys.argv[1]
	target = sys.argv[2]

	copy_metadata(source, target, cap=cap)

if __name__ == "__main__":
	main()
