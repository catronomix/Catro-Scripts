# Replicate Python Virtual Environments
"""
			VENV Replicator
			===============
A utility to analyze an existing Python Virtual Environment and generate 
a restoration script to accurately recreate it on another system.

Usage:
	python VenvReplicator.py <path_to_source_venv> [flags]

Instructions:
	1. Run this script pointing to an existing VENV:
	   python VenvReplicator.py ./my_project_venv
	
	2. It will generate a file named 'recreate_venv.py'.
	
	3. Transfer 'recreate_venv.py' to the target system.
	
	4. Run the generated script to rebuild the environment:
	   python recreate_venv.py ./new_venv_path [-v] [-o]

Requirements:
	- Source VENV must have pip installed.
	- Target system must have an identical base Python version.
	- Generated reports ('venv_info.txt') are TAB-separated plain records: no
	  colour, no box drawing and no `=`/`-` rules, so they stay readable in any
	  editor and parseable by other tools. The generated `recreate_venv.py` is
	  plain text too - it runs in the target project, outside catro-scripts,
	  where the shared `tui` package is not importable.

Flags:
	-v, --verbose    Show full output from pip commands and subprocesses.
	-i, --info       Display information about the VENV instead of creating a script.
	                 Also outputs results to 'venv_info.txt'.
	-t, --touch      When used with -i, verifies package availability online 
	                 (PyPI or Direct URL) to anticipate installation failures.

Features:
	- Matches base Python installation version.
	- Captures direct installation URLs (Git, URLs, Local paths).
	- Preserves installation order via dependency graph analysis.
	- Generates failure reports (failed_packages.txt) if installation fails.
	- Restoration script automatically checks alternative indices (NVIDIA, etc.).

Disclaimer: This script was generated with Gemini 3
"""

import os
import sys
import json
import subprocess
import platform
import argparse
import re
import urllib.request
import urllib.error
from pathlib import Path

import tui

# Status labels returned by check_online_status(), mapped to palette keys.
# This is data handed to tui.style(): the script owns no escape strings.
STATUS_COLOURS = {
	"Online": "success",
	"Missing": "warn",
	"Unreachable": "warn",
	"No Connection": "warn",
}

# venv_info.txt is a report file, never a terminal: the library's plain mode
# gives one TAB-separated record per line with no escapes and no box glyphs.
REPORT_CAP = tui.Capabilities(level="none", unicode=False, width=None,
							  isatty=False, plain=True, reason="venv_info.txt")


def status_colour(status):
	"""Palette key for a status label; "Error <n>" is an error, not a warning."""
	return "error" if status.startswith("Error") else STATUS_COLOURS.get(status, "muted")


class venvreplicator:
    def __init__(self, venv_path, verbose=False, touch=False, cap=None):
        self.venv_path = Path(venv_path).resolve()
        self.verbose = verbose
        self.touch = touch
        # One capability record per run, threaded in from main().
        self.cap = cap if cap is not None else tui.detect()
        self.bin_name = "Scripts" if os.name == "nt" else "bin"
        self.python_exe = self.venv_path / self.bin_name / ("python.exe" if os.name == "nt" else "python")
        
        # Ensure environment supports UTF-8 to prevent charmap errors on Windows
        self.env = os.environ.copy()
        self.env["PYTHONIOENCODING"] = "utf-8"
        
        if not self.python_exe.exists():
            raise FileNotFoundError(f"Could not find Python executable at {self.python_exe}. Is this a valid VENV?")

    def ensure_pip_updated(self):
        """Attempts to upgrade pip in the source VENV to support 'inspect'."""
        if self.verbose:
            print(tui.style("Checking/Upgrading pip in source VENV to support metadata inspection...",
                            fg="header", cap=self.cap))
        
        # Capture output unless verbose is on
        kwargs = {"env": self.env}
        if not self.verbose:
            kwargs["capture_output"] = True
        
        subprocess.run(
            [str(self.python_exe), "-m", "pip", "install", "--upgrade", "pip"],
            **kwargs
        )

    def get_venv_config(self):
        """Reads pyvenv.cfg to get base version and settings."""
        cfg_path = self.venv_path / "pyvenv.cfg"
        config = {}
        if cfg_path.exists():
            with open(cfg_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        key, val = line.split('=', 1)
                        config[key.strip()] = val.strip()
        return config

    def check_online_status(self, name, version, url=None):
        """Verifies if a package exists on PyPI or if the direct URL is reachable.

        Returns a plain status label; display_info() picks the palette key, so
        this method never carries colour into the data it returns.
        """
        if url and url.startswith(('http', 'git')):
            clean_url = re.sub(r'^[a-z0-9\+ ]+\+', '', url)
            try:
                req = urllib.request.Request(clean_url, method='HEAD')
                with urllib.request.urlopen(req, timeout=5) as response:
                    return "Online" if response.status == 200 else f"Error {response.status}"
            except Exception:
                return "Unreachable"
        else:
            pypi_url = f"https://pypi.org/pypi/{name}/{version}/json"
            try:
                with urllib.request.urlopen(pypi_url, timeout=5) as response:
                    return "Online" if response.status == 200 else "Missing"
            except urllib.error.HTTPError as e:
                return "Missing" if e.code == 404 else f"Error {e.code}"
            except Exception:
                return "No Connection"

    def get_detailed_packages(self, return_raw=False):
        """
        Uses 'pip inspect' to get metadata including installation sources (direct_url).
        Determines installation order by inspecting dependencies.
        """
        cap = self.cap
        self.ensure_pip_updated()
        
        # Run pip inspect with UTF-8 encoding to avoid Windows charmap errors
        result = subprocess.run(
            [str(self.python_exe), "-m", "pip", "inspect"],
            capture_output=True, text=True, encoding='utf-8', env=self.env
        )
        
        if result.returncode != 0:
            if self.verbose:
                print(tui.style("--- DEBUG: pip inspect stderr ---\n" + result.stderr,
                                fg="error", cap=cap))
            print(tui.style("Error: pip inspect failed even after attempted upgrade.",
                            fg="error", cap=cap))
            print("Fallback: Using basic freeze. Accuracy regarding sources/order may be reduced.")
            return self.get_fallback_packages()

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            if self.verbose:
                print(tui.style("--- DEBUG: JSON Parse Error ---\n{}\nOutput: {}".format(
                    e, result.stdout), fg="error", cap=cap))
            return self.get_fallback_packages()

        installed_packages = data.get("installed", [])
        if return_raw:
            return installed_packages

        # Build dependency graph for ordering
        package_map = {pkg['metadata']['name'].lower(): pkg for pkg in installed_packages}
        processed = set()
        stack = set()
        ordered_packages = []

        def resolve(name):
            name = name.lower()
            if name in processed:
                return
            if name in stack:
                if self.verbose:
                    print(tui.style("--- DEBUG: Circular dependency detected for {}. Breaking recursion.".format(name),
                                    fg="header", cap=cap))
                return
            
            if name not in package_map:
                return
            
            stack.add(name)
            pkg = package_map[name]
            requires = pkg['metadata'].get('requires_dist', [])
            
            for req in requires:
                match = re.match(r'^([a-zA-Z0-9\-_.]+)', req)
                if match:
                    dep_name = match.group(1).lower()
                    resolve(dep_name)
            
            stack.remove(name)
            processed.add(name)
            
            dist = pkg.get('direct_url')
            if dist:
                install_str = dist.get('url')
                if install_str.startswith('file:///'):
                    print(tui.style("Warning: Package '{}' uses a local path: {}".format(
                        name, install_str), fg="warn", cap=cap))
            else:
                version = pkg['metadata']['version']
                install_str = f"{pkg['metadata']['name']}=={version}"
            
            ordered_packages.append(install_str)

        for pkg_name in package_map:
            resolve(pkg_name)

        return ordered_packages

    def get_fallback_packages(self):
        """Fallback to pip freeze if inspect is unavailable."""
        result = subprocess.run(
            [str(self.python_exe), "-m", "pip", "freeze"],
            capture_output=True, text=True, encoding='utf-8', env=self.env
        )
        return [line.strip() for line in result.stdout.split('\n') if line.strip()]

    def display_info(self):
        """Displays formatted information about the VENV and saves it to a file."""
        cap = self.cap
        config = self.get_venv_config()
        packages = self.get_detailed_packages(return_raw=True)

        meta_data = [
            ("VENV Path:", str(self.venv_path)),
            ("Python Executable:", str(self.python_exe)),
            ("Base Home:", config.get('home', 'Unknown')),
            ("Base Version:", config.get('version', 'Unknown')),
            ("System Packages:", config.get('include-system-site-packages', 'false'))
        ]

        # The console block is the house key/value layout; venv_info.txt gets
        # the same pairs as plain records.
        print(tui.key_values("VENV SOURCE INFORMATION", meta_data, cap=cap))

        print(tui.style("Gathering package details...", fg="accent", cap=cap))
        
        rows = []
        package_list = sorted(packages, key=lambda x: x['metadata']['name'].lower()) if not isinstance(packages[0], str) else packages

        for pkg in package_list:
            if isinstance(pkg, str):
                if '==' in pkg:
                    name, ver = pkg.split('==', 1)
                else:
                    name, ver = pkg, "Unknown"
                source = "PyPI"
                status_raw = self.check_online_status(name, ver) if self.touch else "Checked"
            else:
                name = pkg['metadata']['name']
                ver = pkg['metadata']['version']
                dist = pkg.get('direct_url')
                if dist:
                    source = dist.get('url')
                else:
                    installer = pkg['metadata'].get('installer', '').lower()
                    if installer and installer != 'pip':
                        source = installer.capitalize()
                    elif name.lower().startswith(('nvidia-', 'cuda-')):
                        source = "NVIDIA / PyPI"
                    else:
                        source = "PyPI"
                status_raw = self.check_online_status(name, ver, source if dist else None) if self.touch else "Checked"

            rows.append({"Package": name, "Version": ver, "Status": status_raw, "Source": source})
            if self.touch:
                print("Verified: {} ({})".format(
                    name, tui.style(status_raw, fg=status_colour(status_raw), cap=cap)))

        # One column set for both outputs: the console table renders it in box
        # mode, venv_info.txt in plain mode.
        headers = ["Package", "Version"]
        if self.touch:
            headers.append("Status")
        headers.append("Source")
        table_rows = [
            [r["Package"], r["Version"]] + ([r["Status"]] if self.touch else []) + [r["Source"]]
            for r in rows
        ]

        print()
        print(tui.section("INSTALLED PACKAGES", cap=cap))
        tui.print_table(headers, table_rows, cap=cap)
        print("Total Packages: {}".format(len(packages)))

        report = [
            "VENV SOURCE INFORMATION",
            tui.key_values("", meta_data, cap=REPORT_CAP),
            "",
            "INSTALLED PACKAGES",
            tui.render_table(headers, table_rows, cap=REPORT_CAP),
            "",
            "Total Packages: {}".format(len(packages)),
        ]
        with open("venv_info.txt", "w", encoding='utf-8') as f:
            f.write("\n".join(report) + "\n")
        print("VENV information saved to: {}".format(
            tui.style("venv_info.txt", fg="warn", cap=cap)))

    def generate_restore_script(self, output_path="recreate_venv.py"):
        cap = self.cap
        config = self.get_venv_config()
        packages = self.get_detailed_packages()
        python_version = config.get("version", platform.python_version())
        include_system = config.get("include-system-site-packages", "false")

        script_template = f'''
import os
import sys
import subprocess
import platform
import argparse
import json
from pathlib import Path

# METADATA FROM SOURCE
REQUIRED_PYTHON = "{python_version}"
INCLUDE_SYSTEM = {include_system.lower() == "true"}
PACKAGES = {json.dumps(packages, indent=4)}

# Alternative repositories
EXTRA_INDICES = [
    "https://pypi.nvidia.com",
    "https://download.pytorch.org/whl/cu121",
    "https://download.pytorch.org/whl/cu118",
    "https://download.pytorch.org/whl/cpu"
]

def check_version(override=False):
    current = platform.python_version()
    if current != REQUIRED_PYTHON:
        if override:
            print("WARNING: Python version mismatch.")
            print(f"Source VENV requires: {{REQUIRED_PYTHON}}")
            print(f"Current installation: {{current}}")
            print("Proceeding due to --override flag. Compatibility is not guaranteed.")
            return
            
        print("CRITICAL ERROR: Python version mismatch.")
        print(f"Source VENV requires: {{REQUIRED_PYTHON}}")
        print(f"Current installation: {{current}}")
        print("Please use the exact same Python installer to ensure binary compatibility.")
        print("Use --override to force installation anyway.")
        sys.exit(1)
    print(f"OK: Python version {{current}} matches.")

def recreate(target_dir, verbose=False):
    target_path = Path(target_dir).resolve()
    print(f"Recreating VENV at: {{target_path}}...")
    
    cmd = [sys.executable, "-m", "venv", str(target_path)]
    if INCLUDE_SYSTEM: cmd.append("--system-site-packages")
    subprocess.run(cmd, check=True)
    
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python_exe = target_path / bin_dir / ("python.exe" if os.name == "nt" else "python")
    sub_env = os.environ.copy()
    sub_env["PYTHONIOENCODING"] = "utf-8"
    
    print(f"Installing {{len(PACKAGES)}} packages in order...")
    # Upgrade pip
    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True, capture_output=not verbose, env=sub_env)

    failed_packages = []

    for pkg in PACKAGES:
        print(f"Installing: {{pkg}}")
        success = False
        last_error = ""

        try:
            # We use --no-deps because we are manually handling the order 
            # to ensure 100% parity with the source environment.
            install_cmd = [str(python_exe), "-m", "pip", "install", pkg, "--no-deps"]
            
            # If verbose is on, don't capture so the user sees live progress bars
            if verbose:
                result = subprocess.run(install_cmd, env=sub_env)
                if result.returncode == 0:
                    success = True
                else:
                    last_error = "Installation failed. Check console output above for specific pip errors."
            else:
                result = subprocess.run(install_cmd, capture_output=True, env=sub_env)
                if result.returncode == 0:
                    success = True
                else:
                    last_error = result.stderr.decode('utf-8', errors='replace')
        except Exception as e:
            last_error = str(e)

        if not success and "://" not in pkg:
            print(f"  Attempting alternative repositories for {{pkg}}...")
            for index in EXTRA_INDICES:
                try:
                    retry_cmd = [str(python_exe), "-m", "pip", "install", pkg, "--no-deps", "--extra-index-url", index]
                    if verbose:
                        result = subprocess.run(retry_cmd, env=sub_env)
                    else:
                        result = subprocess.run(retry_cmd, capture_output=True, env=sub_env)
                        
                    if result.returncode == 0:
                        print(f"  [FIXED] Successfully installed {{pkg}} from {{index}}")
                        success = True
                        break
                except Exception: continue

        if not success:
            print(f"  [ERROR] Failed to install {{pkg}}")
            failed_packages.append({{"pkg": pkg, "error": last_error}})
            if verbose: print(f"Error output:\\n{{last_error}}")

    if failed_packages:
        print("\\n" + "!"*60)
        print(f"RECREATION FINISHED WITH {{len(failed_packages)}} ERRORS")
        print("!"*60)
        for f in failed_packages: print(f" - {{f['pkg']}}")
        
        report_file = "failed_packages.txt"
        with open(report_file, "w", encoding='utf-8') as f:
            f.write("VENV RECREATION FAILURE REPORT\\n")
            f.write(f"Target Path: {{target_path}}\\n")
            f.write("="*30 + "\\n\\n")
            for entry in failed_packages:
                f.write(f"PACKAGE: {{entry['pkg']}}\\n")
                f.write(f"ERROR DETAILS:\\n{{entry['error']}}\\n")
                f.write("-" * 30 + "\\n")
        print(f"\\nDetailed error logs saved to: {{report_file}}")
    else:
        print("\\nSuccess! VENV recreated accurately.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Path to recreate the VENV")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full installation output")
    parser.add_argument("-o", "--override", action="store_true", help="Force install even if Python version differs")
    args = parser.parse_args()
    check_version(args.override)
    recreate(args.target, args.verbose)
'''
        with open(output_path, "w", encoding='utf-8') as f:
            f.write(script_template.strip())
        print("Restoration script generated: {}".format(
            tui.style(output_path, fg="warn", cap=cap)))

if __name__ == "__main__":
    tui.init_ansi()
    parser = argparse.ArgumentParser(description="VENV Replicator")
    parser.add_argument("source", nargs="?", default=".", help="Path to source VENV")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-i", "--info", action="store_true", help="Show VENV info and save to 'venv_info.txt'")
    parser.add_argument("-t", "--touch", action="store_true", help="Verify package availability online (PyPI/URL)")
    args = parser.parse_args()
    cap = tui.detect()

    try:
        replicator = venvreplicator(args.source, args.verbose, args.touch, cap)
        if args.info:
            replicator.display_info()
        else:
            replicator.generate_restore_script()
    except Exception as e:
        print(tui.style(f"Error: {e}", fg="error", cap=cap))
