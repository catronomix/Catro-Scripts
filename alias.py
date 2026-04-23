# alias creator for catro-scripts
"""
			CATRO-SCRIPTS ALIAS CREATOR
			==========================
This script creates wrapper files (.bat for Windows and .sh for Unix-like systems)
in the program directory. These wrappers act as a single global alias to invoke 
the main 'catro-scripts' wrapper, passing through all command-line arguments.

It does NOT create aliases for individual .py scripts; it only creates a 
shorthand for the central 'catro-scripts' dispatcher.

Usage:
	python alias.py <alias_name>

Example:
	python alias.py c
	# Creates 'c.bat' and 'c.sh' which both call 'catro-scripts'

Requirements:
	- Write permissions in the script directory.
"""
import os
import sys
import stat

# Blacklist of reserved system commands to prevent breaking shell functionality
FORBIDDEN_NAMES = {
	# Shell built-ins & navigation
	"cd", "dir", "ls", "echo", "pwd", "pushd", "popd", "exit", "quit", "set", "export",
	# System info & networking
	"ipconfig", "ifconfig", "ping", "hostname", "systeminfo", "tasklist", "top", "ps",
	# File operations
	"copy", "cp", "move", "mv", "del", "rm", "mkdir", "rmdir", "type", "cat", "more", "find",
	# Logic & shell control
	"if", "for", "while", "do", "done", "else", "then", "alias", "sh", "bash", "cmd", "powershell",
	# Package managers & interpreters
	"python", "pip", "node", "npm", "git", "ssh", "sudo", "apt", "brew", "yum",
	# Script identity
	"catro-scripts"
}

def create_alias(alias_name):
	# Get the directory where this script is located
	script_dir = os.path.dirname(os.path.abspath(__file__))
	
	bat_path = os.path.join(script_dir, f"{alias_name}.bat")
	sh_path = os.path.join(script_dir, f"{alias_name}.sh")

	# Content for .bat file
	# %~dp0 ensures the path is relative to the alias file's location
	bat_content = f"@echo off\ncall \"%~dp0catro-scripts.bat\" %*\n"

	# Content for .sh file
	# Preserves working directory and passes all arguments
	sh_content = f"#!/bin/bash\n\"$(dirname \"$0\")/catro-scripts.sh\" \"$@\"\n"

	try:
		# Create Windows .bat
		with open(bat_path, "w") as f:
			f.write(bat_content)
		print(f"[Success] Created Windows alias: {bat_path}")

		# Create Unix .sh
		with open(sh_path, "w") as f:
			f.write(sh_content)
		
		# Make the .sh file executable
		st = os.stat(sh_path)
		os.chmod(sh_path, st.st_mode | stat.S_IEXEC)
		print(f"[Success] Created Unix alias: {sh_path}")

	except Exception as e:
		print(f"[Error] Failed to create alias files: {e}")

def main():
	# Strict check for exactly one argument (script name + 1 arg)
	if len(sys.argv) != 2:
		print("Usage: python alias.py <alias_name>")
		sys.exit(1)

	alias_name = sys.argv[1].strip().lower()
	
	# Validation for filename characters based on user requirements
	invalid_chars = '<>:"/\\|?*_.~[](){}` '
	if any(char in alias_name for char in invalid_chars):
		print(f"[Error] Invalid alias name (illegal characters): {alias_name}")
		sys.exit(1)

	# Validate against forbidden system names
	if alias_name in FORBIDDEN_NAMES:
		print(f"[Error] '{alias_name}' is a reserved command and cannot be used.")
		sys.exit(1)

	create_alias(alias_name)

if __name__ == "__main__":
	main()