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

def set_creation_time(path, timestamp):
    """
    Attempts to set the creation time of a file.
    Note: This is highly OS-dependent (primarily Windows).
    """
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
            print(f"Warning: Could not set Windows creation time: {e}")
    else:
        # Linux/macOS generally do not support setting 'birth time' via standard APIs
        print("Notice: Unix-based systems generally do not support setting file creation time (Birth Time). Skipping.")

def copy_metadata(source_path, target_path):
    """
    Copies file system timestamps from source to target.
    """
    abs_source = os.path.abspath(source_path)
    abs_target = os.path.abspath(target_path)

    if not os.path.exists(abs_source):
        print(f"Error: Source file '{abs_source}' does not exist.")
        return

    if not os.path.exists(abs_target):
        print(f"Error: Target file '{abs_target}' does not exist.")
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
        set_creation_time(abs_target, ctime)

        print(f"Successfully synchronized system timestamps:")
        print(f"  Created:  {time.ctime(ctime)}")
        print(f"  Modified: {time.ctime(mtime)}")
        print(f"  Accessed: {time.ctime(atime)}")
        
    except Exception as e:
        print(f"An error occurred while copying system timestamps: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: catro-scripts timecopy <source_path> <target_path>")
        sys.exit(1)

    source = sys.argv[1]
    target = sys.argv[2]

    copy_metadata(source, target)