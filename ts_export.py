# TypeScript project exporter
"""
			TYPESCRIPT PROJECT EXPORTER
			===========================
This utility packages a TypeScript project for local distribution. It compiles 
TypeScript files into clean JavaScript and prepares an 'export' directory 
containing a version of the project that can be opened directly in a browser 
(via file://) without triggering ES module security warnings.

Features:
	- Detects TypeScript projects via 'tsconfig.json'.
	- Compiles TS to JS using the local 'tsc' compiler.
	- Flattens/bundles scripts using 'esbuild' (if available in node_modules).
	- Updates 'index.html' to use standard script tags instead of modules.
	- Preserves directory structure for styles and assets.

Usage:
	python ts_export.py

Requirements:
	- A project created with 'newtypescript.py' (or a similar structure).
	- Node modules installed (specifically 'typescript' and 'esbuild').
"""
import os
import shutil
import subprocess
import re
import sys
import stat

# ANSI Colors
C_PURPLE = '\033[38;2;170;0;255m'
C_CYAN = '\033[96m'
C_GREEN = '\033[92m'
C_RED = '\033[91m'
C_YELLOW = '\033[93m'
C_BOLD = '\033[1m'
C_RESET = '\033[0m'

def print_step(message):
    print(f"{C_CYAN}{C_BOLD}>>{C_RESET} {message}")

def print_success(message):
    print(f"{C_GREEN}{C_BOLD}✓{C_RESET} {message}")

def print_error(message):
    print(f"{C_RED}{C_BOLD}Error:{C_RESET} {message}")

def remove_readonly(func, path, excinfo):
    """
    Error handler for shutil.rmtree to handle read-only files.

    `stat.S_IWRITE` is only the owner write bit (0o200), so assigning it with
    os.chmod would replace the whole mode and drop owner read - and execute for
    directories. OR it onto the mode read back from lstat instead: the retry
    then works on POSIX and Windows keeps its read-only-flag behaviour.
    """
    try:
        os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IWRITE)
    except OSError:
        # Let func() surface the real error if the mode could not be changed.
        pass
    func(path)

def remove_tree(path):
    """
    Removes a tree with remove_readonly as the error handler.

    3.11 baseline uses `onerror`; 3.12 deprecated it in favour of `onexc`, so
    the newer keyword is used only where it exists. The handler keeps its
    3-argument signature, which both keywords accept.
    """
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=remove_readonly)
    else:
        shutil.rmtree(path, onerror=remove_readonly)

def check_project():
    """Verify if the current directory is a TS project."""
    if not os.path.exists('tsconfig.json'):
        return False, "No 'tsconfig.json' found. Are you in a TypeScript project directory?"
    if not os.path.isdir('node_modules'):
        return False, "node_modules not found. Please run 'npm install' first."
    return True, ""

def main():
    print(f"\n{C_PURPLE}{C_BOLD}--- TypeScript Project Export ---{C_RESET}\n")

    # 1. Validation
    is_valid, err = check_project()
    if not is_valid:
        print_error(err)
        return

    # 2. Setup Export Directory
    export_dir = 'export'
    if os.path.exists(export_dir):
        try:
            # Use the readonly handler to avoid common Windows permission errors
            remove_tree(export_dir)
        except Exception as e:
            print_error(f"Could not clear '{export_dir}' directory. Please ensure no files are open in other programs.\nDetails: {e}")
            return
            
    os.makedirs(export_dir)
    print_step(f"Created clean '{export_dir}' directory.")

    # 3. Locate Binaries
    # Use .cmd on Windows, direct path on Unix
    ext = ".cmd" if os.name == 'nt' else ""
    tsc_bin = os.path.join('node_modules', '.bin', f'tsc{ext}')
    esbuild_bin = os.path.join('node_modules', '.bin', f'esbuild{ext}')

    if not os.path.exists(tsc_bin):
        print_error("TypeScript compiler (tsc) not found in node_modules.")
        return

    # 4. Compilation / Bundling
    # We prefer esbuild for the "export" because it can bundle dependencies into a 
    # single file that doesn't require 'type=module'
    main_ts = os.path.join('scripts', 'main.ts')
    if not os.path.exists(main_ts):
        # Fallback to standard main.ts if not in scripts/
        main_ts = 'main.ts'

    out_js = os.path.join(export_dir, 'scripts', 'main.js')
    os.makedirs(os.path.dirname(out_js), exist_ok=True)

    if os.path.exists(esbuild_bin):
        print_step("Bundling with esbuild for 'file://' compatibility...")
        try:
            subprocess.check_call([
                esbuild_bin, main_ts, 
                '--bundle', 
                f'--outfile={out_js}',
                '--minify',
                '--platform=browser',
                '--target=es6'
            ], shell=(os.name == 'nt'))
            print_success("Bundled JavaScript successfully.")
        except subprocess.CalledProcessError:
            print_error("Bundling failed.")
            return
    else:
        print_step("esbuild not found, falling back to standard tsc...")
        try:
            # Simple compile - might still have module issues if multi-file
            subprocess.check_call([tsc_bin, '--outDir', export_dir, '--target', 'ES6', '--module', 'none'], shell=(os.name == 'nt'))
            print_success("Compiled JavaScript successfully.")
        except subprocess.CalledProcessError:
            print_error("Compilation failed.")
            return

    # 5. Copy Assets
    print_step("Copying styles and assets...")
    if os.path.exists('styles'):
        shutil.copytree('styles', os.path.join(export_dir, 'styles'))
    
    # Copy index.html and modify it
    if os.path.exists('index.html'):
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()

        # Transformation:
        # 1. Change .ts references to .js
        # 2. Remove type="module" to prevent CORS issues on file://
        content = content.replace('.ts', '.js')
        content = re.sub(r'\s*type\s*=\s*["\']module["\']', '', content)
        
        with open(os.path.join(export_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(content)
        print_success("Processed index.html for local loading.")

    print(f"\n{C_GREEN}{C_BOLD}✨ Export Complete!{C_RESET}")
    print(f"You can now open {C_YELLOW}'{export_dir}/index.html'{C_RESET} directly in your browser.")

if __name__ == "__main__":
    main()