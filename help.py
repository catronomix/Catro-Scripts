# Help
import os
import sys
import ast
import platform

def init_ansi():
	# Enables ANSI escape sequences on Windows 10+ consoles.
	if platform.system().lower() == "windows":
		os.system('color')
		
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

def print_colored_docstring(docstring):
	# Prints the docstring with colors based on indentation depth.
	# Assumes scripts use tab characters (\t) for indentation as requested.
	
	# ANSI Color codes
	PURPLE = "\033[0;35m"
	COLORS = [
		"\033[1;37m", # Level 0: Bold White
		"\033[0;36m", # Level 1: Cyan
		"\033[0;32m", # Level 2: Green
		"\033[0;33m", # Level 3: Yellow
		"\033[0;31m", # Level 4: Red
	]
	RESET = "\033[0m"

	divider = f"{PURPLE}--------------------------------------------------{RESET}"

	if not docstring:
		print(divider)
		print(f"{COLORS[4]}No intro text (docstring) found in this script.{RESET}")
		print(divider)
		return

	print(divider)
	lines = docstring.splitlines()
	for line in lines:
		# Count leading tabs
		indent_level = 0
		for char in line:
			if char == '\t':
				indent_level += 1
			else:
				break
		
		# Select color based on depth (looping colors if depth > 4)
		color = COLORS[indent_level % len(COLORS)]
		print(f"{color}{line}{RESET}")
	print(divider)

def main():
	
	init_ansi()
	if len(sys.argv) < 2:
		print("Usage: python help_script.py <script_name_without_extension>")
		sys.exit(1)

	target_name = sys.argv[1]
	script_dir = get_script_directory()
	target_path = os.path.join(script_dir, f"{target_name}.py")

	if not os.path.exists(target_path):
		print(f"Error: Script '{target_name}.py' not found in {script_dir}")
		sys.exit(1)

	print(f"\n--- Help for {target_name} ---\n")
	doc = get_docstring(target_path)
	print_colored_docstring(doc)
	print("")

if __name__ == "__main__":
	main()