# OpenCode runner wrapper
"""
			OPENCODE RUNNER
			==============
Wraps the `opencode` CLI for non-interactive runs (`opencode run "<instruction>"`).

Features:
	- Checks whether `opencode` is installed and shows install instructions when missing.
	- Lists available models and variants when called without arguments.
	- Runs an instruction, optionally with a model override via `-m <model>`.
	- Persists a default model in a sidecar file (`opencode.default`).
	- Accepts bracketed/quoted or unbracketed instructions (joins and passes as one arg).

Usage:
	catro-scripts opencode
	catro-scripts opencode -m <provider/model[#variant]> "<instruction>"
	catro-scripts opencode -m <provider/model[#variant]>
	catro-scripts opencode "<instruction>"
	catro-scripts opencode <unbracketed instruction words>

Examples:
	catro-scripts opencode
	catro-scripts opencode -m anthropic/claude-sonnet-4-5 "Explain this repository"
	catro-scripts opencode -m openai/gpt-5.2#high Review the current changes
	catro-scripts opencode Fix the failing tests in this folder

Requirements: opencode CLI (see install hint when missing)
"""

import os
import subprocess
import sys


class Colors:
	PURPLE = '\033[38;2;170;0;255m'
	LIGHT_BLUE = '\033[38;2;173;216;230m'
	BG_BLACK = '\033[48;2;0;0;0m'
	BG_GREY = '\033[48;2;45;45;45m'
	YELLOW = '\033[33m'
	GREEN = '\033[32m'
	RED = '\033[91m'
	BOLD = '\033[1m'
	END = '\033[0m'


def init_ansi():
	# Enable ANSI escape sequences on Windows consoles.
	if os.name == 'nt':
		os.system('')


def script_dir():
	# Directory holding this script; sidecar default-model file lives here.
	return os.path.dirname(os.path.abspath(__file__))


def default_file_path():
	# Sidecar file storing the default model (provider/model[#variant]).
	return os.path.join(script_dir(), 'opencode.default')


def read_default_model():
	# Return saved default model or None when unset/empty.
	try:
		path = default_file_path()
		if not os.path.exists(path):
			return None
		with open(path, 'r', encoding='utf-8') as f:
			value = f.read().strip()
			return value or None
	except OSError:
		return None


def write_default_model(model):
	# Persist the default model to the sidecar file.
	with open(default_file_path(), 'w', encoding='utf-8') as f:
		f.write(model.strip() + '\n')


def find_opencode():
	# Locate the real opencode binary on PATH (None when not installed).
	# Manual PATH scan so our own opencode.py wrapper (matched via cwd/PATHEXT
	# on Windows) is never mistaken for the real opencode binary.
	own = os.path.abspath(__file__).lower()
	pathext = [e.lower() for e in os.environ.get('PATHEXT', '.EXE;.CMD;.BAT;.COM').split(os.pathsep)]
	# On Windows prefer native executables (.exe/.cmd/.bat) over extensionless shims.
	exts = pathext + [''] if os.name == 'nt' else [''] + pathext
	names = ['opencode' + ext for ext in exts]
	for entry in os.environ.get('PATH', '').split(os.pathsep):
		entry = entry.strip().strip('"')
		if not entry or not os.path.isdir(entry):
			continue
		for name in names:
			if name.lower().endswith(('.py', '.pyw')):
				continue
			full = os.path.join(entry, name)
			if os.path.isfile(full) and os.path.abspath(full).lower() != own:
				return full
	return None


def run_opencode(opencode_bin, args):
	# Run opencode portably; .cmd/.bat shims on Windows need a shell.
	if os.name == 'nt' and opencode_bin.lower().endswith(('.cmd', '.bat')):
		return subprocess.run([opencode_bin] + args, shell=True)
	return subprocess.run([opencode_bin] + args)


def print_not_installed():
	# Install guidance shown when `opencode` is not on PATH.
	c = Colors
	print(f"\n{c.PURPLE}{c.BOLD}--- OPENCODE NOT FOUND ---{c.END}")
	print(f"{c.RED}The `opencode` CLI is not installed or not on your PATH.{c.END}\n")
	print(f"{c.BOLD}Get it here:{c.END} {c.LIGHT_BLUE}https://opencode.ai{c.END}")
	print(f"{c.BOLD}Docs (CLI):{c.END} {c.LIGHT_BLUE}https://opencode.ai/docs/cli{c.END}\n")
	print(f"{c.BOLD}Install options:{c.END}")
	print(f"  {c.GREEN}curl -fsSL https://opencode.ai/install | bash{c.END}   (macOS/Linux)")
	print(f"  {c.GREEN}npm i -g opencode-ai{c.END}                              (npm, cross-platform)")
	print(f"  {c.GREEN}winget install opencode-ai.opencode{c.END}                (Windows winget)")
	print(f"  {c.GREEN}choco install opencode{c.END}                             (Windows chocolatey)\n")
	print("After installing, restart your shell so `opencode` is on PATH, then re-run:")
	print(f"  {c.GREEN}catro-scripts opencode{c.END}\n")


def normalize_instruction(raw):
	# Join leftover args into one instruction; strip one layer of wrapping quotes/brackets.
	text = (raw or '').strip()
	if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
		text = text[1:-1].strip()
	if len(text) >= 2 and text[0] == '[' and text[-1] == ']':
		text = text[1:-1].strip()
	return text


def print_usage(default_model):
	# Short usage block printed alongside the model list.
	c = Colors
	print(f"\n{c.PURPLE}{c.BOLD}--- USAGE ---{c.END}")
	print(f"  {c.GREEN}catro-scripts opencode \"<instruction>\"{c.END}")
	print(f"  {c.GREEN}catro-scripts opencode <unbracketed words>{c.END}  (script joins + quotes for you)")
	print(f"  {c.GREEN}catro-scripts opencode -m <provider/model[#variant]> \"<instruction>\"{c.END}")
	print(f"  {c.GREEN}catro-scripts opencode -m <provider/model[#variant]>{c.END}  (saves default)")
	if default_model:
		print(f"\n{c.BOLD}Default model:{c.END} {c.LIGHT_BLUE}{default_model}{c.END} (from opencode.default)")
	else:
		print(f"\n{c.BOLD}Default model:{c.END} (none saved yet)")


def list_models(opencode_bin):
	# No-instruction path: show default + delegate to `opencode models`.
	c = Colors
	default_model = read_default_model()
	print(f"\n{c.PURPLE}{c.BOLD}--- AVAILABLE MODELS ---{c.END}")
	if default_model:
		print(f"{c.BOLD}Default:{c.END} {c.LIGHT_BLUE}{default_model}{c.END}")
	try:
		result = run_opencode(opencode_bin, ['models'])
		sys.exit(result.returncode)
	except OSError as e:
		print(f"{c.RED}Failed to run `opencode models`: {e}{c.END}")
		sys.exit(1)
	finally:
		print_usage(read_default_model())


def run_instruction(opencode_bin, model, instruction):
	# Wrap `opencode run [-m model] "<instruction>"` via subprocess (no shell quoting needed).
	c = Colors
	cmd = [opencode_bin, 'run']
	if model:
		cmd += ['-m', model]
	cmd += [instruction]
	label = f" with model {model}" if model else ""
	print(f"{c.PURPLE}{c.BOLD}-> Running opencode{label}...{c.END}")
	try:
		result = run_opencode(opencode_bin, cmd[1:])
		sys.exit(result.returncode)
	except OSError as e:
		print(f"{c.RED}Failed to launch opencode: {e}{c.END}")
		sys.exit(1)


def parse_args(argv):
	# Parse `-m <model>` plus the trailing instruction; returns (model, instruction).
	# All non-flag tokens are joined into one instruction so unbracketed words work.
	model = None
	rest = []
	i = 0
	while i < len(argv):
		token = argv[i]
		if token in ('-m', '--model'):
			# Model flag consumes the next token as the model reference.
			if i + 1 >= len(argv) or argv[i + 1].startswith('-'):
				print(f"{Colors.RED}Error: -m requires a model argument (provider/model[#variant]).{Colors.END}")
				sys.exit(2)
			model = argv[i + 1].strip()
			i += 2
		elif token in ('-h', '--help'):
			print(__doc__)
			sys.exit(0)
		else:
			rest.append(token)
			i += 1
	instruction = normalize_instruction(' '.join(rest))
	return model, instruction


def main():
	# Entrypoint: install check -> parse flags -> list models / save default / run.
	init_ansi()
	opencode_bin = find_opencode()
	if not opencode_bin:
		print_not_installed()
		sys.exit(1)

	model, instruction = parse_args(sys.argv[1:])

	if model and not instruction:
		# `-m <model>` alone persists the default model for future runs.
		write_default_model(model)
		print(f"{Colors.GREEN}Saved default model: {model}{Colors.END} (opencode.default)")
		return

	if not instruction:
		# No instruction at all: list available models and variants.
		list_models(opencode_bin)
		return

	effective_model = model or read_default_model()
	run_instruction(opencode_bin, effective_model, instruction)


if __name__ == '__main__':
	main()
