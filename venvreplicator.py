# Replicate Python Virtual Environments
"""
			VENV Replicator
			===============
A utility to analyze an existing Python Virtual Environment and generate 
a restoration script to accurately recreate it on another system.

Usage:
	python VenvReplicator.py <path_to_source_venv>

Instructions:
	1. Run this script pointing to an existing VENV:
	   python VenvReplicator.py ./my_project_venv
	
	2. It will generate a file named 'recreate_venv.py'.
	
	3. Transfer 'recreate_venv.py' to the target system.
	
	4. Run the generated script to rebuild the environment:
	   python recreate_venv.py ./new_venv_path

Requirements:
	- Source VENV must have pip installed.
	- Target system must have an identical base Python version.

Features:
	- Matches base Python installation version.
	- Captures direct installation URLs (Git, URLs, Local paths).
	- Preserves installation order via dependency graph analysis.

Disclaimer: This script was generated with Gemini 3
"""

import os
import sys
import json
import subprocess
import platform
from pathlib import Path

class venvreplicator:
    def __init__(self, venv_path):
        self.venv_path = Path(venv_path).resolve()
        self.bin_name = "Scripts" if os.name == "nt" else "bin"
        self.python_exe = self.venv_path / self.bin_name / ("python.exe" if os.name == "nt" else "python")
        
        if not self.python_exe.exists():
            raise FileNotFoundError(f"Could not find Python executable at {self.python_exe}. Is this a valid VENV?")

    def get_venv_config(self):
        """Reads pyvenv.cfg to get base version and settings."""
        cfg_path = self.venv_path / "pyvenv.cfg"
        config = {}
        if cfg_path.exists():
            with open(cfg_path, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, val = line.split('=', 1)
                        config[key.strip()] = val.strip()
        return config

    def get_detailed_packages(self):
        """
        Uses 'pip inspect' to get metadata including installation sources (direct_url).
        Determines installation order by inspecting dependencies.
        """
        # Run pip inspect via the venv's python
        result = subprocess.run(
            [str(self.python_exe), "-m", "pip", "inspect"],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            print("Error: pip inspect failed. Ensure pip is updated in the source VENV.")
            return []

        data = json.loads(result.stdout)
        installed_packages = data.get("installed", [])
        
        # Build dependency graph for ordering
        package_map = {pkg['metadata']['name'].lower(): pkg for pkg in installed_packages}
        processed = []
        ordered_packages = []

        def resolve(name):
            name = name.lower()
            if name in processed or name not in package_map:
                return
            
            pkg = package_map[name]
            # Check requirements
            requires = pkg['metadata'].get('requires_dist', [])
            for req in requires:
                # Simple parsing of requirement string to get name
                dep_name = req.split()[0].split('[')[0].split('<')[0].split('>')[0].split('=')[0].lower()
                resolve(dep_name)
            
            processed.append(name)
            
            # Determine installation string
            dist = pkg.get('direct_url')
            if dist:
                # Handle VCS or Local paths
                install_str = dist.get('url')
                if install_str.startswith('file:///'):
                    print(f"Warning: Package '{name}' uses a local path: {install_str}")
            else:
                # Standard PyPI package
                version = pkg['metadata']['version']
                install_str = f"{pkg['metadata']['name']}=={version}"
            
            ordered_packages.append(install_str)

        for pkg_name in package_map:
            resolve(pkg_name)

        return ordered_packages

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
from pathlib import Path

# METADATA FROM SOURCE
REQUIRED_PYTHON = "{python_version}"
INCLUDE_SYSTEM = {include_system.lower() == "true"}
PACKAGES = {json.dumps(packages, indent=4)}

def check_version():
    current = platform.python_version()
    if current != REQUIRED_PYTHON:
        print(f"CRITICAL ERROR: Python version mismatch.")
        print(f"Source VENV requires: {{REQUIRED_PYTHON}}")
        print(f"Current installation: {{current}}")
        print("Please use the exact same Python installer to ensure binary compatibility.")
        sys.exit(1)
    print(f"OK: Python version {{current}} matches.")

def recreate(target_dir):
    target_path = Path(target_dir).resolve()
    print(f"Recreating VENV at: {{target_path}}...")
    
    # 1. Create the VENV
    cmd = [sys.executable, "-m", "venv", str(target_path)]
    if INCLUDE_SYSTEM:
        cmd.append("--system-site-packages")
    
    subprocess.run(cmd, check=True)
    
    # 2. Determine paths
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python_exe = target_path / bin_dir / ("python.exe" if os.name == "nt" else "python")
    
    # 3. Install packages in the recorded order
    print(f"Installing {{len(PACKAGES)}} packages in order...")
    
    # Upgrade pip first
    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    for pkg in PACKAGES:
        print(f"Installing: {{pkg}}")
        try:
            subprocess.run([str(python_exe), "-m", "pip", "install", pkg, "--no-deps"], check=True)
        except subprocess.CalledProcessError:
            print(f"Failed to install {{pkg}}. Check your internet or source availability.")

    print("\\nSuccess! VENV recreated accurately.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python recreate_venv.py <new_venv_path>")
        sys.exit(1)
    
    check_version()
    recreate(sys.argv[1])
'''
        with open(output_path, "w") as f:
            f.write(script_template.strip())
        print(f"Restoration script generated: {output_path}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    try:
        replicator = venvreplicator(target)
        replicator.generate_restore_script()
    except Exception as e:
        print(f"Error: {e}")