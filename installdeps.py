# Install script dependencies
"""
DEPENDENCY INSTALLER
-------------------
This script automatically scans all Python files in its directory, 
identifies required third-party libraries, and installs them via pip 
if they are missing.

USAGE:
Run the script, it will check for pip and then process all local .py files.

DISCLAIMER:
This script was generated with Gemini 3.
"""

import os
import sys
import ast
import subprocess
import importlib.util

def ensure_pip():
    """
    Checks if pip is available. If not, attempts to install it using the ensurepip module.
    """
    try:
        import pip
    except ImportError:
        print("Pip not found. Attempting to install pip...")
        try:
            # ensurepip is a standard library module to bootstrap pip
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--default-pip"])
            print("Pip installed successfully.")
        except Exception as e:
            print(f"Failed to install pip: {e}")
            sys.exit(1)

def get_script_directory():
    """
    Returns the absolute path of the directory where this script is located.
    """
    return os.path.dirname(os.path.abspath(__file__))

def get_imports_from_file(filepath):
    """
    Parses a Python file using the ast module to find all top-level imports.
    """
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Get the base module name (e.g., 'os' from 'os.path')
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return imports

def is_module_available(module_name):
    """
    Checks if a module is currently importable in the environment.
    """
    # Check if it's a built-in module first
    if module_name in sys.builtin_module_names:
        return True
    
    # Check if the module can be found in the current python path
    return importlib.util.find_spec(module_name) is not None

def install_package(package_name):
    """
    Uses the pip module to install a package.
    """
    print(f"Installing {package_name}...")
    try:
        # Running pip as a subprocess is the recommended way to use it from within a script
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return True
    except subprocess.CalledProcessError:
        print(f"Failed to install package: {package_name}")
        return False

def main():
    # 1. Ensure pip is available
    ensure_pip()

    # 2. Locate the directory of the current script
    script_dir = get_script_directory()
    current_script_name = os.path.basename(__file__)
    
    print(f"Scanning directory: {script_dir}")
    
    all_dependencies = set()
    
    # 3. Scan for other .py files in the same folder
    for filename in os.listdir(script_dir):
        if filename.endswith(".py") and filename != current_script_name:
            filepath = os.path.join(script_dir, filename)
            print(f"Analyzing {filename}...")
            file_imports = get_imports_from_file(filepath)
            all_dependencies.update(file_imports)

    if not all_dependencies:
        print("No dependencies found in local scripts.")
        return

    # 4. Filter for missing dependencies
    missing_deps = []
    for dep in all_dependencies:
        if not is_module_available(dep):
            missing_deps.append(dep)

    if not missing_deps:
        print("All dependencies are already satisfied.")
    else:
        print(f"Missing dependencies found: {', '.join(missing_deps)}")
        
        # 5. Attempt to install missing dependencies
        for dep in missing_deps:
            install_package(dep)
        
        print("\nDependency check and installation process complete.")

if __name__ == "__main__":
    main()