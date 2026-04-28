# TypeScript project scaffolder
"""
			TYPESCRIPT PROJECT SCAFFOLDER
			=============================
This script automates the creation of a clean, modern TypeScript project environment 
powered by Vite. It generates the necessary configuration files, verifies the 
local npm environment, and automatically installs dependencies.

Features:
	- Verifies Node.js and npm installation before proceeding.
	- Generates an organized project structure with 'scripts' and 'styles' folders.
	- Generates an optimized package.json with Vite and TypeScript.
	- Configures tsconfig.json for modern ESNext development.
	- Provides a "Clean Code" vite.config.ts with predictable output naming.
	- Automatically runs 'npm install' to prepare the workspace.

Usage:
	python ts_setup.py

Requirements:
	- Python 3.x
	- Node.js and npm
"""
import os
import json
import subprocess
import sys

def create_file(path, content):
	"""Writes content to a file, creating parent directories if they don't exist."""
	os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
	with open(path, 'w', encoding='utf-8') as f:
		f.write(content)

def check_env():
	"""Checks if node and npm are installed and accessible."""
	try:
		node_version = subprocess.check_output(['node', '--version'], stderr=subprocess.STDOUT).decode().strip()
		npm_version = subprocess.check_output(['npm', '--version'], stderr=subprocess.STDOUT).decode().strip()
		return node_version, npm_version
	except (subprocess.CalledProcessError, FileNotFoundError):
		return None, None

def main():
	# 0. Environment Check
	print("Checking environment...")
	node_v, npm_v = check_env()
	if not node_v or not npm_v:
		print("Error: Node.js or npm is not installed or not in your PATH.")
		print("Please install Node.js from https://nodejs.org/ before running this script.")
		return
	
	print(f"Found Node {node_v} and npm {npm_v}")

	project_name = input("\nEnter project name: ").strip()
	if not project_name:
		print("Project name cannot be empty.")
		return

	# Create project directory
	try:
		os.makedirs(project_name)
	except FileExistsError:
		print(f"Error: Directory '{project_name}' already exists.")
		return

	os.chdir(project_name)
	print(f"Creating project structure in ./{project_name}...")

	# 1. package.json
	package_json = {
		"name": project_name,
		"private": True,
		"version": "1.0.0",
		"type": "module",
		"scripts": {
			"dev": "vite",
			"build": "vite build",
			"preview": "vite preview"
		},
		"devDependencies": {
			"typescript": "^5.0.0",
			"vite": "^5.0.0"
		}
	}
	create_file('package.json', json.dumps(package_json, indent=2))

	# 2. tsconfig.json
	tsconfig = {
		"compilerOptions": {
			"target": "ESNext",
			"module": "ESNext",
			"moduleResolution": "node",
			"strict": True,
			"skipLibCheck": True,
			"sourceMap": True,
			"isolatedModules": True,
			"moduleDetection": "force",
			"esModuleInterop": True,
			"lib": ["ESNext", "DOM"]
		}
	}
	create_file('tsconfig.json', json.dumps(tsconfig, indent=2))

	# 3. vite.config.ts
	vite_config = """import { defineConfig } from 'vite';

export default defineConfig({
  build: {
	minify: false,
	modulePreload: { polyfill: false },
	rollupOptions: {
	  output: {
		entryFileNames: `[name].js`,
		chunkFileNames: `[name].js`,
		assetFileNames: `[name].[ext]`,
	  },
	},
  },
});
"""
	create_file('vite.config.ts', vite_config)

	# 4. index.html
	index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>{project_name}</title>
	<link rel="stylesheet" href="./styles/style.css">
</head>
<body>
	<div id="app"></div>
	<script type="module" src="./scripts/main.ts"></script>
</body>
</html>
"""
	create_file('index.html', index_html)

	# 5. styles/style.css
	style_css = """body {
	font-family: system-ui, -apple-system, sans-serif;
	display: flex;
	justify-content: center;
	align-items: center;
	height: 100vh;
	margin: 0;
	background: #1a1a1a;
	color: white;
}

#app {
	text-align: center;
	border: 1px solid #333;
	padding: 2.5rem;
	border-radius: 12px;
	background: #242424;
	box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}

h1 { margin-top: 0; color: #646cff; }
code { background: #1a1a1a; padding: 0.2rem 0.4rem; border-radius: 4px; }
"""
	create_file('styles/style.css', style_css)

	# 6. scripts/main.ts
	main_ts = """// Your TypeScript entry point
const app = document.querySelector<HTMLDivElement>('#app')!;

app.innerHTML = `
  <h1>Vite + TypeScript</h1>
  <p>Project initialized successfully.</p>
  <p style="color: #888;">Edit <code>scripts/main.ts</code> to get started.</p>
`;

console.log("Environment ready: scripts and styles linked.");
"""
	create_file('scripts/main.ts', main_ts)

	# 7. Install Dependencies
	print("\nRunning 'npm install'...")
	try:
		subprocess.check_call(['npm', 'install'], shell=(os.name == 'nt'))
		print("\nDependencies installed successfully.")
	except subprocess.CalledProcessError:
		print("\nError: 'npm install' failed. You may need to run it manually.")

	print(f"\n✨ Success! Project '{project_name}' is ready.")
	print("To start the development server:")
	print(f"  cd {project_name}")
	print("  npm run dev")

if __name__ == "__main__":
	main()