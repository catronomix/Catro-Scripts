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

import tui

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

def create_alias(alias_name, cap):
	# Get the directory where this script is located
	script_dir = os.path.dirname(os.path.abspath(__file__))
	
	bat_path = os.path.join(script_dir, f"{alias_name}.bat")
	sh_path = os.path.join(script_dir, f"{alias_name}.sh")

	# Content for .bat file
	# %~dp0 ensures the path is relative to the alias file's location.
	# Line endings are spelled out as CRLF because cmd.exe mis-parses a batch
	# file that uses bare LF line endings.
	bat_content = "@echo off\r\ncall \"%~dp0catro-scripts.bat\" %*\r\n"

	# Content for .sh file
	# Preserves working directory and passes all arguments. The target is
	# resolved through any symlink chain first, because a generated alias is
	# commonly symlinked into a PATH directory; plain `readlink` (no -f) keeps
	# this valid on macOS bash 3.2 and busybox.
	sh_content = (
		"#!/bin/bash\n"
		"# Resolve this alias through any symlink chain so the real\n"
		"# catro-scripts.sh is found when the alias is symlinked into PATH.\n"
		"_self=\"$0\"\n"
		"_hops=0\n"
		"while [ -L \"$_self\" ] && [ \"$_hops\" -lt 40 ]; do\n"
		"\t_link=\"$(readlink \"$_self\")\"\n"
		"\tcase \"$_link\" in\n"
		"\t\t/*) _self=\"$_link\" ;;\n"
		"\t\t*) _self=\"$(dirname \"$_self\")/$_link\" ;;\n"
		"\tesac\n"
		"\t_hops=$((_hops + 1))\n"
		"done\n"
		"\"$(cd -P \"$(dirname \"$_self\")\" && pwd)/catro-scripts.sh\" \"$@\"\n"
	)

	try:
		# Create Windows .bat. newline="" disables the platform translation,
		# so the CRLF above survives verbatim.
		with open(bat_path, "w", newline="", encoding="utf-8") as f:
			f.write(bat_content)
		print(tui.style(f"[Success] Created Windows alias: {bat_path}",
						fg="success", cap=cap))

		# Create Unix .sh. newline="" keeps the LF endings verbatim.
		with open(sh_path, "w", newline="", encoding="utf-8") as f:
			f.write(sh_content)
		
		# Make the .sh file executable
		st = os.stat(sh_path)
		os.chmod(sh_path, st.st_mode | stat.S_IEXEC)
		print(tui.style(f"[Success] Created Unix alias: {sh_path}",
						fg="success", cap=cap))

	except Exception as e:
		print(tui.style(f"[Error] Failed to create alias files: {e}",
						fg="error", cap=cap), file=sys.stderr)

def main():
	# One capability record for the run: colour level, glyphs and pipe mode.
	tui.init_ansi()
	cap = tui.detect()

	# Strict check for exactly one argument (script name + 1 arg)
	if len(sys.argv) != 2:
		print("Usage: python alias.py <alias_name>")
		sys.exit(1)

	alias_name = sys.argv[1].strip().lower()
	
	# Validation for filename characters based on user requirements
	invalid_chars = '<>:"/\\|?*_.~[](){}` '
	if any(char in alias_name for char in invalid_chars):
		print(tui.style(f"[Error] Invalid alias name (illegal characters): {alias_name}",
						fg="error", cap=cap), file=sys.stderr)
		sys.exit(1)

	# Validate against forbidden system names
	if alias_name in FORBIDDEN_NAMES:
		print(tui.style(f"[Error] '{alias_name}' is a reserved command and cannot be used.",
						fg="error", cap=cap), file=sys.stderr)
		sys.exit(1)

	create_alias(alias_name, cap)

if __name__ == "__main__":
	main()