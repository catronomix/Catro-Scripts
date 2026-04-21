# Install script dependencies
"""
			DEPENDENCY INSTALLER
			-------------------
This script automatically scans all Python files in its directory, 
identifies required third-party libraries, and installs them via pip 
if they are missing. It fetches a public mapping from pipreqs to resolve
import names to actual PyPI package names. Optionally, it can scan a 
different working directory using the `-workdir` command-line argument.

Usage:
    python installdeps.py
    python installdeps.py -workdir /path/to/your/project
"""

import os
import sys
import ast
import subprocess
import importlib.util
import json
import argparse
import urllib.request

# URL for a community-maintained mapping (from pipreqs)
MAPPING_URL = "https://raw.githubusercontent.com/bndr/pipreqs/master/pipreqs/mapping"

# Manual mapping for common import name -> package name discrepancies
# This will take precedence over the fetched online mapping.
MANUAL_MAPPING = {
    "PIL": "Pillow",
    "aspose.words": "aspose-words",
	"aspose": "aspose-words",
}

def ensure_pip():
	"""Checks if pip is available and bootstraps it if missing."""
	try:
		import pip
	except ImportError:
		try:
			subprocess.check_call([sys.executable, "-m", "ensurepip", "--default-pip"])
		except Exception as e:
			print(f"Failed to install pip: {e}")
			sys.exit(1)

def get_script_directory():
	"""Returns the directory of the current script."""
	return os.path.dirname(os.path.abspath(__file__))

def get_imports_from_file(filepath):
	"""Parses a Python file to find all top-level imports."""
	imports = set()
	try:
		with open(filepath, 'r', encoding='utf-8') as f:
			tree = ast.parse(f.read())
		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				for alias in node.names:
					imports.add(alias.name.split('.')[0])
			elif isinstance(node, ast.ImportFrom):
				if node.module:
					imports.add(node.module.split('.')[0])
	except Exception as e:
		print(f"Error parsing {filepath}: {e}")
	return imports

def is_module_available(module_name):
	"""Checks if a module is currently importable or built-in."""
	if module_name in sys.builtin_module_names:
		return True
	return importlib.util.find_spec(module_name) is not None

def fetch_package_mapping():
	"""Fetches the import-to-package mapping from a public source."""
	print("Fetching package name mappings...")
	try:
		with urllib.request.urlopen(MAPPING_URL) as response:
			content = response.read().decode('utf-8')
			# The mapping is typically stored as 'import_name:package_name' per line
			mapping = {}
			for line in content.splitlines():
				if ':' in line:
					imp, pkg = line.split(':', 1)
					mapping[imp.strip()] = pkg.strip()
			return mapping
	except Exception as e:
		print(f"Warning: Could not fetch online mapping ({e}). Falling back to import names.")
		return {}

def install_package(package_name):
	"""Installs a package via pip."""
	print(f"Installing {package_name}...")
	try:
		subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
		return True
	except subprocess.CalledProcessError:
		print(f"Failed to install: {package_name}")
		return False

def main():
	parser = argparse.ArgumentParser(description="Scans Python files for dependencies and installs them.")
	parser.add_argument("-workdir", type=str, help="Specify a working directory to scan instead of the script's own directory.")
	args = parser.parse_args()

	ensure_pip()
	
	if args.workdir is not None: # -workdir was provided, either with a value or without
		if args.workdir == '.': # If -workdir was provided without a path, it defaults to '.'
			target_dir = os.getcwd()
			print(f"Scanning for dependencies in current working directory: {target_dir}")
		else: # -workdir was provided with a specific path
			target_dir = os.path.abspath(args.workdir)
			print(f"Scanning for dependencies in specified directory: {target_dir}")
	else:
		target_dir = get_script_directory()
		print(f"Scanning for dependencies in script's directory: {target_dir}")

	current_name = os.path.basename(__file__)
	
	all_imports = set()
	for filename in os.listdir(target_dir):
		if filename.endswith(".py") and filename != current_name:
			all_imports.update(get_imports_from_file(os.path.join(target_dir, filename)))

	missing_imports = [imp for imp in all_imports if not is_module_available(imp)]
	
	if not missing_imports:
		print("All dependencies satisfied.")
		return

	# Fetch mapping only if needed
	mapping = fetch_package_mapping()
	# Merge manual mapping, allowing it to override fetched entries
	mapping.update(MANUAL_MAPPING)
	print(f"Using {len(MANUAL_MAPPING)} manual mappings.")

	for imp in missing_imports:
		# Resolve using mapping or fallback to import name
		pkg = mapping.get(imp, imp)
		install_package(pkg)

if __name__ == "__main__":
	main()