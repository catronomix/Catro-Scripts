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

# ANSI Colors
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"

def init_ansi():
    """Enables ANSI support on Windows."""
    if platform.system().lower() == "windows":
        os.system('color')

class venvreplicator:
    def __init__(self, venv_path, verbose=False, touch=False):
        self.venv_path = Path(venv_path).resolve()
        self.verbose = verbose
        self.touch = touch
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
            print(f"{C_PURPLE}Checking/Upgrading pip in source VENV to support metadata inspection...{C_RESET}")
        
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
        """Verifies if a package exists on PyPI or if the direct URL is reachable."""
        if url and url.startswith(('http', 'git')):
            clean_url = re.sub(r'^[a-z0-9\+ ]+\+', '', url)
            try:
                req = urllib.request.Request(clean_url, method='HEAD')
                with urllib.request.urlopen(req, timeout=5) as response:
                    return f"{C_YELLOW}Online{C_RESET}" if response.status == 200 else f"{C_RED}Error {response.status}{C_RESET}"
            except Exception:
                return f"{C_RED}Unreachable{C_RESET}"
        else:
            pypi_url = f"https://pypi.org/pypi/{name}/{version}/json"
            try:
                with urllib.request.urlopen(pypi_url, timeout=5) as response:
                    return f"{C_YELLOW}Online{C_RESET}" if response.status == 200 else f"{C_RED}Missing{C_RESET}"
            except urllib.error.HTTPError as e:
                return f"{C_RED}Missing{C_RESET}" if e.code == 404 else f"{C_RED}Error {e.code}{C_RESET}"
            except Exception:
                return f"{C_RED}No Connection{C_RESET}"

    def get_detailed_packages(self, return_raw=False):
        """
        Uses 'pip inspect' to get metadata including installation sources (direct_url).
        Determines installation order by inspecting dependencies.
        """
        self.ensure_pip_updated()
        
        # Run pip inspect with UTF-8 encoding to avoid Windows charmap errors
        result = subprocess.run(
            [str(self.python_exe), "-m", "pip", "inspect"],
            capture_output=True, text=True, encoding='utf-8', env=self.env
        )
        
        if result.returncode != 0:
            if self.verbose:
                print(f"{C_RED}--- DEBUG: pip inspect stderr ---\n{result.stderr}{C_RESET}")
            print(f"{C_RED}Error: pip inspect failed even after attempted upgrade.{C_RESET}")
            print("Fallback: Using basic freeze. Accuracy regarding sources/order may be reduced.")
            return self.get_fallback_packages()

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            if self.verbose:
                print(f"{C_RED}--- DEBUG: JSON Parse Error ---\n{e}\nOutput: {result.stdout}{C_RESET}")
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
                    print(f"{C_PURPLE}--- DEBUG: Circular dependency detected for {name}. Breaking recursion.{C_RESET}")
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
                    print(f"{C_YELLOW}Warning: Package '{name}' uses a local path: {install_str}{C_RESET}")
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
        config = self.get_venv_config()
        packages = self.get_detailed_packages(return_raw=True)
        
        info_lines = []
        info_lines_ansi = [] # Version with ANSI for console
        
        div_line = "=" * 85
        purple_div = f"{C_PURPLE}{div_line}{C_RESET}"
        
        info_lines.append("\n" + div_line)
        info_lines_ansi.append("\n" + purple_div)
        
        header_text = "VENV SOURCE INFORMATION"
        info_lines.append(header_text)
        info_lines_ansi.append(f"{C_YELLOW}{header_text}{C_RESET}")
        
        info_lines.append(div_line)
        info_lines_ansi.append(purple_div)
        
        meta_data = [
            (f"{'VENV Path:':<25}", str(self.venv_path)),
            (f"{'Python Executable:':<25}", str(self.python_exe)),
            (f"{'Base Home:':<25}", config.get('home', 'Unknown')),
            (f"{'Base Version:':<25}", config.get('version', 'Unknown')),
            (f"{'System Packages:':<25}", config.get('include-system-site-packages', 'false'))
        ]
        
        for k, v in meta_data:
            info_lines.append(f"{k} {v}")
            info_lines_ansi.append(f"{k} {C_YELLOW}{v}{C_RESET}")
        
        print(f"\n{C_PURPLE}Gathering package details...{C_RESET}")
        
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
                print(f"Verified: {name} ({status_raw})")

        # Column widths based on raw text (stripping ANSI for logic)
        def clean_ansi(text): return re.sub(r'\033\[[0-9;]*m', '', str(text))

        col_widths = {
            "Package": max([len(r["Package"]) for r in rows] + [7]),
            "Version": max([len(r["Version"]) for r in rows] + [7]),
            "Status": max([len(clean_ansi(r["Status"])) for r in rows] + [6]) if self.touch else 0,
            "Source": max([len(r["Source"]) for r in rows] + [6])
        }

        # Build Table
        raw_headers = f"{'Package':<{col_widths['Package']}}  {'Version':<{col_widths['Version']}}"
        if self.touch: raw_headers += f"  {'Status':<{col_widths['Status']}}"
        raw_headers += f"  {'Source':<{col_widths['Source']}}"
        
        info_lines.append("\nINSTALLED PACKAGES")
        info_lines_ansi.append(f"\n{C_YELLOW}INSTALLED PACKAGES{C_RESET}")
        
        info_lines.append("-" * len(raw_headers))
        info_lines_ansi.append(f"{C_PURPLE}{'-' * len(raw_headers)}{C_RESET}")
        
        info_lines.append(raw_headers)
        info_lines_ansi.append(f"{C_YELLOW}{raw_headers}{C_RESET}")
        
        info_lines.append("-" * len(raw_headers))
        info_lines_ansi.append(f"{C_PURPLE}{'-' * len(raw_headers)}{C_RESET}")

        for r in rows:
            # File line (No ANSI)
            clean_status = clean_ansi(r['Status'])
            line_raw = f"{r['Package']:<{col_widths['Package']}}  {r['Version']:<{col_widths['Version']}}"
            if self.touch: line_raw += f"  {clean_status:<{col_widths['Status']}}"
            line_raw += f"  {r['Source']:<{col_widths['Source']}}"
            info_lines.append(line_raw)
            
            # Console line (With ANSI)
            line_ansi = f"{C_YELLOW if 'Online' in r['Status'] or not self.touch else C_RESET}{r['Package']:<{col_widths['Package']}}{C_RESET}  {r['Version']:<{col_widths['Version']}}"
            if self.touch: line_ansi += f"  {r['Status']:<{col_widths['Status']}}"
            line_ansi += f"  {r['Source']:<{col_widths['Source']}}"
            info_lines_ansi.append(line_ansi)

        summary_raw = f"Total Packages: {len(packages)}"
        info_lines.append("-" * len(raw_headers))
        info_lines.append(summary_raw)
        info_lines.append("=" * len(raw_headers))
        
        info_lines_ansi.append(f"{C_PURPLE}{'-' * len(raw_headers)}{C_RESET}")
        info_lines_ansi.append(f"{C_YELLOW}{summary_raw}{C_RESET}")
        info_lines_ansi.append(f"{C_PURPLE}{'=' * len(raw_headers)}{C_RESET}\n")

        print("\n".join(info_lines_ansi))
        with open("venv_info.txt", "w", encoding='utf-8') as f:
            f.write("\n".join(info_lines))
        print(f"VENV information saved to: {C_YELLOW}venv_info.txt{C_RESET}")

    def generate_restore_script(self, output_path="recreate_venv.py"):
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

# ANSI Colors for Restorer
C_YELLOW = "\\033[93m"
C_RED = "\\033[91m"
C_PURPLE = "\\033[95m"
C_RESET = "\\033[0m"

def init_ansi():
    if platform.system().lower() == "windows":
        os.system('color')

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
            print(f"{{C_YELLOW}}WARNING: Python version mismatch.{{C_RESET}}")
            print(f"Source VENV requires: {{REQUIRED_PYTHON}}")
            print(f"Current installation: {{current}}")
            print("Proceeding due to --override flag. Compatibility is not guaranteed.")
            return
            
        print(f"{{C_RED}}CRITICAL ERROR: Python version mismatch.{{C_RESET}}")
        print(f"Source VENV requires: {{REQUIRED_PYTHON}}")
        print(f"Current installation: {{current}}")
        print("Please use the exact same Python installer to ensure binary compatibility.")
        print(f"Use {{C_YELLOW}}--override{{C_RESET}} to force installation anyway.")
        sys.exit(1)
    print(f"OK: Python version {{current}} matches.")

def recreate(target_dir, verbose=False):
    target_path = Path(target_dir).resolve()
    print(f"{{C_PURPLE}}Recreating VENV at: {{target_path}}...{{C_RESET}}")
    
    cmd = [sys.executable, "-m", "venv", str(target_path)]
    if INCLUDE_SYSTEM: cmd.append("--system-site-packages")
    subprocess.run(cmd, check=True)
    
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python_exe = target_path / bin_dir / ("python.exe" if os.name == "nt" else "python")
    sub_env = os.environ.copy()
    sub_env["PYTHONIOENCODING"] = "utf-8"
    
    print(f"{{C_YELLOW}}Installing {{len(PACKAGES)}} packages in order...{{C_RESET}}")
    # Upgrade pip
    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True, capture_output=not verbose, env=sub_env)

    failed_packages = []

    for pkg in PACKAGES:
        print(f"Installing: {{C_YELLOW}}{{pkg}}{{C_RESET}}")
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
            print(f"  {{C_PURPLE}}Attempting alternative repositories for {{pkg}}...{{C_RESET}}")
            for index in EXTRA_INDICES:
                try:
                    retry_cmd = [str(python_exe), "-m", "pip", "install", pkg, "--no-deps", "--extra-index-url", index]
                    if verbose:
                        result = subprocess.run(retry_cmd, env=sub_env)
                    else:
                        result = subprocess.run(retry_cmd, capture_output=True, env=sub_env)
                        
                    if result.returncode == 0:
                        print(f"  {{C_YELLOW}}[FIXED] Successfully installed {{pkg}} from {{index}}{{C_RESET}}")
                        success = True
                        break
                except Exception: continue

        if not success:
            print(f"  {{C_RED}}[ERROR] Failed to install {{pkg}}{{C_RESET}}")
            failed_packages.append({{"pkg": pkg, "error": last_error}})
            if verbose: print(f"Error output:\\n{{last_error}}")

    if failed_packages:
        print("\\n" + f"{{C_RED}}!"*60 + f"{{C_RESET}}")
        print(f"{{C_RED}}RECREATION FINISHED WITH {{len(failed_packages)}} ERRORS{{C_RESET}}")
        print(f"{{C_RED}}!"*60 + f"{{C_RESET}}")
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
        print(f"\\nDetailed error logs saved to: {{C_RED}}{{report_file}}{{C_RESET}}")
    else:
        print(f"\\n{{C_YELLOW}}Success! VENV recreated accurately.{{C_RESET}}")

if __name__ == "__main__":
    init_ansi()
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
        print(f"Restoration script generated: {C_YELLOW}{output_path}{C_RESET}")

if __name__ == "__main__":
    init_ansi()
    parser = argparse.ArgumentParser(description="VENV Replicator")
    parser.add_argument("source", nargs="?", default=".", help="Path to source VENV")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-i", "--info", action="store_true", help="Show VENV info and save to 'venv_info.txt'")
    parser.add_argument("-t", "--touch", action="store_true", help="Verify package availability online (PyPI/URL)")
    args = parser.parse_args()

    try:
        replicator = venvreplicator(args.source, args.verbose, args.touch)
        if args.info:
            replicator.display_info()
        else:
            replicator.generate_restore_script()
    except Exception as e:
        print(f"{C_RED}Error: {e}{C_RESET}")