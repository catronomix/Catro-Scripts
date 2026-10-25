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

import tui


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


def print_not_installed(cap=None):
	# Install guidance shown when `opencode` is not on PATH.
	cap = cap or tui.detect()
	url = lambda text: tui.style(text, fg="fg", cap=cap)
	command = lambda text: tui.style(text, fg="success", cap=cap)
	print()
	print(tui.style("--- OPENCODE NOT FOUND ---", fg="header", bold=True, cap=cap))
	print(tui.style("The `opencode` CLI is not installed or not on your PATH.",
					fg="error", cap=cap))
	print()
	print("{} {}".format(tui.style("Get it here:", bold=True, cap=cap),
						 url("https://opencode.ai")))
	print("{} {}\n".format(tui.style("Docs (CLI):", bold=True, cap=cap),
						   url("https://opencode.ai/docs/cli")))
	print("{}".format(tui.style("Install options:", bold=True, cap=cap)))
	print("  {}   (macOS/Linux)".format(
		command("curl -fsSL https://opencode.ai/install | bash")))
	print("  {}                              (npm, cross-platform)".format(
		command("npm i -g opencode-ai")))
	print("  {}                (Windows winget)".format(
		command("winget install opencode-ai.opencode")))
	print("  {}                             (Windows chocolatey)".format(
		command("choco install opencode")))
	print()
	print("After installing, restart your shell so `opencode` is on PATH, then re-run:")
	print("  {}\n".format(command("catro-scripts opencode")))


def normalize_instruction(raw):
	# Join leftover args into one instruction; strip one layer of wrapping quotes/brackets.
	text = (raw or '').strip()
	if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
		text = text[1:-1].strip()
	if len(text) >= 2 and text[0] == '[' and text[-1] == ']':
		text = text[1:-1].strip()
	return text


def print_usage(default_model, cap=None):
	# Short usage block printed alongside the model list.
	cap = cap or tui.detect()
	command = lambda text: tui.style(text, fg="success", cap=cap)
	print()
	print(tui.style("--- USAGE ---", fg="header", bold=True, cap=cap))
	print("  {}".format(command('catro-scripts opencode "<instruction>"')))
	print("  {}  (script joins + quotes for you)".format(
		command("catro-scripts opencode <unbracketed words>")))
	print("  {}".format(command(
		'catro-scripts opencode -m <provider/model[#variant]> "<instruction>"')))
	print("  {}  (saves default)".format(
		command("catro-scripts opencode -m <provider/model[#variant]>")))
	if default_model:
		print()
		print("{} {} (from opencode.default)".format(
			tui.style("Default model:", bold=True, cap=cap),
			tui.style(default_model, fg="fg", cap=cap)))
	else:
		print()
		print("{} (none saved yet)".format(
			tui.style("Default model:", bold=True, cap=cap)))


def list_models(opencode_bin, cap=None):
	# No-instruction path: show default + delegate to `opencode models`.
	cap = cap or tui.detect()
	default_model = read_default_model()
	print()
	print(tui.style("--- AVAILABLE MODELS ---", fg="header", bold=True, cap=cap))
	if default_model:
		print("{} {}".format(tui.style("Default:", bold=True, cap=cap),
							 tui.style(default_model, fg="fg", cap=cap)))
	try:
		result = run_opencode(opencode_bin, ['models'])
		sys.exit(result.returncode)
	except OSError as e:
		print(tui.style(f"Failed to run `opencode models`: {e}", fg="error",
						cap=cap))
		sys.exit(1)
	finally:
		print_usage(read_default_model(), cap)


def run_instruction(opencode_bin, model, instruction, cap=None):
	# Wrap `opencode run [-m model] "<instruction>"` via subprocess (no shell quoting needed).
	cap = cap or tui.detect()
	cmd = [opencode_bin, 'run']
	if model:
		cmd += ['-m', model]
	cmd += [instruction]
	label = f" with model {model}" if model else ""
	print(tui.style(f"-> Running opencode{label}...", fg="border", bold=True,
					cap=cap))
	try:
		result = run_opencode(opencode_bin, cmd[1:])
		sys.exit(result.returncode)
	except OSError as e:
		print(tui.style(f"Failed to launch opencode: {e}", fg="error", cap=cap))
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
				print(tui.style("Error: -m requires a model argument "
								"(provider/model[#variant]).", fg="error"))
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
	tui.init_ansi()
	cap = tui.detect()
	opencode_bin = find_opencode()
	if not opencode_bin:
		print_not_installed(cap)
		sys.exit(1)

	model, instruction = parse_args(sys.argv[1:])

	if model and not instruction:
		# `-m <model>` alone persists the default model for future runs.
		write_default_model(model)
		print("{} (opencode.default)".format(
			tui.style(f"Saved default model: {model}", fg="success", cap=cap)))
		return

	if not instruction:
		# No instruction at all: list available models and variants.
		list_models(opencode_bin, cap)
		return

	effective_model = model or read_default_model()
	run_instruction(opencode_bin, effective_model, instruction, cap)


if __name__ == '__main__':
	main()
