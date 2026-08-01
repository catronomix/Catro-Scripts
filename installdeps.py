# Install script dependencies
"""
                        DEPENDENCY INSTALLER
                        ====================
This script automatically scans all Python and .screensaver files in its
directory, identifies required third-party libraries, and installs them
via pip if they are missing. It fetches a public mapping from pipreqs to
resolve import names to actual PyPI package names. Optionally, it can
scan a different working directory using the `-workdir` command-line argument.

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
import warnings

# URL for a community-maintained mapping (from pipreqs)
MAPPING_URL = "https://raw.githubusercontent.com/bndr/pipreqs/master/pipreqs/mapping"

# Manual mapping for common import name -> package name discrepancies
MANUAL_MAPPING = {
    "PIL": "Pillow",
    "aspose.words": "aspose-words",
    "aspose": "aspose-words",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "fitz": "PyMuPDF",
    "wx": "wxPython",
    "pgzero": "pgzero",
}

# Automatically handle platform-specific dependencies (e.g., curses on Windows)
if sys.platform.startswith("win"):
    MANUAL_MAPPING["curses"] = "windows-curses"


def ensure_pip():
    # Checks if pip is available and bootstraps it if missing.
    try:
        import pip
    except ImportError:
        print("Pip not found. Attempting to install pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--default-pip"])
        except Exception as e:
            print(f"Failed to bootstrap pip: {e}")
            sys.exit(1)


def get_script_directory():
    """Returns the directory of the current script."""
    return os.path.dirname(os.path.abspath(__file__))


def get_imports_from_file(filepath):
    """Parses a Python file to find all top-level imports."""
    imports = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Suppress SyntaxWarning for escape sequences in scanned files (e.g. \d)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(content, filename=filepath)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    return imports


def is_module_available(module_name):
    """Checks if a module or package is currently importable or built-in."""
    clean_name = module_name.replace("-", "_")
    if (
        clean_name in sys.builtin_module_names
        or module_name in sys.builtin_module_names
    ):
        return True
    try:
        if importlib.util.find_spec(clean_name) is not None:
            return True
    except (ImportError, AttributeError, ValueError):
        pass

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def fetch_package_mapping():
    """Fetches the import-to-package mapping from a public source."""
    print("Fetching package name mappings...")
    try:
        req = urllib.request.Request(MAPPING_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            content = response.read().decode("utf-8")
            mapping = {}
            for line in content.splitlines():
                if ":" in line:
                    imp, pkg = line.split(":", 1)
                    mapping[imp.strip()] = pkg.strip()
            return mapping
    except Exception as e:
        print(
            f"Warning: Could not fetch online mapping ({e}). Falling back to manual mappings."
        )
        return {}


def install_package(package_name):
    """
    Attempts to install a package via pip.
    Returns True on success, False on failure without raising unhandled exceptions.
    """
    print(f"Installing '{package_name}'...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            check=True,
            capture_output=False,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(
            f"Warning: Failed to install '{package_name}' (exit code {e.returncode}). Moving to next dependency..."
        )
        return False
    except Exception as e:
        print(f"Unexpected error installing '{package_name}': {e}. Continuing...")
        return False


def parse_arguments():
    """Sets up and processes command-line arguments, handling positional packages gracefully."""
    parser = argparse.ArgumentParser(
        description="Scans Python files for dependencies and/or installs explicitly requested packages."
    )

    # Positional arguments for direct package names (e.g. `python installdeps.py curses requests`)
    parser.add_argument(
        "positional_packages",
        nargs="*",
        metavar="PACKAGE",
        help="Optional list of package or module names to install directly.",
    )

    # Flag options
    parser.add_argument(
        "-p",
        "--packages",
        nargs="+",
        dest="flag_packages",
        metavar="PACKAGE",
        help="Explicit list of package or module names to install.",
    )

    parser.add_argument(
        "-workdir",
        type=str,
        help="Specify a working directory to scan instead of the script's own directory.",
    )

    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="Skip directory file scanning when explicit packages are provided.",
    )

    # Use parse_known_args to ensure extra or unexpected arguments don't crash argument parsing
    args, unknown = parser.parse_known_args()

    # Collect any leftover non-flag arguments as positional packages
    extra_packages = [u for u in unknown if not u.startswith("-")]
    if extra_packages:
        args.positional_packages.extend(extra_packages)

    return args


def main():
    args = parse_arguments()
    ensure_pip()

    # Combine positional and flag-based explicitly requested packages
    explicit_packages = set()
    if args.positional_packages:
        explicit_packages.update(args.positional_packages)
    if args.flag_packages:
        explicit_packages.update(args.flag_packages)

    scanned_imports = set()

    # Determine scanning behavior
    should_scan = not (explicit_packages and args.skip_scan)

    if should_scan:
        if args.workdir is not None:
            if args.workdir == ".":
                target_dir = os.getcwd()
            else:
                target_dir = os.path.abspath(args.workdir)
            print(f"Scanning directory: {target_dir}")
        else:
            target_dir = get_script_directory()
            print(f"Scanning directory: {target_dir}")

        current_name = os.path.basename(__file__)
        valid_extensions = (".py", ".screensaver")

        if os.path.exists(target_dir):
            for filename in os.listdir(target_dir):
                if (
                    filename.lower().endswith(valid_extensions)
                    and filename != current_name
                ):
                    file_path = os.path.join(target_dir, filename)
                    file_imports = get_imports_from_file(file_path)
                    scanned_imports.update(file_imports)
        else:
            print(f"Warning: Directory '{target_dir}' does not exist.")

    # Filter scanned imports to only those missing locally
    missing_scanned = [
        target for target in sorted(scanned_imports) if not is_module_available(target)
    ]

    # Explicitly requested packages are always processed directly
    targets_to_process = sorted(explicit_packages) + missing_scanned

    if not targets_to_process:
        print("No packages specified and all scanned dependencies are satisfied.")
        return

    # Resolve package mappings for missing modules
    mapping = fetch_package_mapping()
    mapping.update(MANUAL_MAPPING)

    failed_packages = []
    successful_packages = []

    for target in targets_to_process:
        # Map import name to PyPI package name if available
        package_to_install = mapping.get(target, target)

        success = install_package(package_to_install)
        if success:
            successful_packages.append(package_to_install)
        else:
            failed_packages.append(package_to_install)

    print("\n" + "=" * 40)
    print("INSTALLATION SUMMARY")
    print("=" * 40)
    if successful_packages:
        print(
            f"Successfully processed ({len(successful_packages)}): {', '.join(successful_packages)}"
        )
    if failed_packages:
        print(
            f"Failed to install ({len(failed_packages)}): {', '.join(failed_packages)}"
        )
        print("Continuing execution despite missing packages...")
    else:
        print("All dependencies were processed successfully.")


if __name__ == "__main__":
    main()
