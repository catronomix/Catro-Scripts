# OpenCode updater for Volta installs
"""
			OPENCODE / VOLTA UPDATER
			========================
Updates the `opencode` CLI on this machine the only way that actually works
when it is installed through Volta.

Why a dedicated script: `volta install @opencode/cli@latest` on its own leaves a
broken command. Volta skips npm lifecycle scripts, and `@opencode/cli` ships a
229-byte placeholder at `bin/opencode.exe` that its `postinstall.mjs` is
supposed to replace with the real platform binary (`@opencode/cli-windows-x64`).
Without that step `opencode` answers "This version of ... is not compatible
with the version of Windows you're running".

The workflow this script automates:
	1. read the installed version from Volta's image package.json (what the
	   `opencode` shim really runs),
	2. read the latest version from the npm registry,
	3. `volta install @opencode/cli@<target>`,
	4. run the package's own `postinstall.mjs` to place the real binary,
	5. verify the binary answers `--version` with the target version,
	6. optionally restart the opencode service (`--restart`).

Features:
	- `--check` reports installed vs latest and changes nothing.
	- `--version <v>` pins a target release instead of `latest`.
	- `--force` re-runs the install even when the versions already match.
	- Detects an already-broken placeholder binary and repairs it in place.
	- `--restart` restarts the service (kills a running agent session first).
	- Clear failure exit codes: 0 done, 1 failed, 2 bad arguments.

Usage:
	catro-scripts oc_volta
	catro-scripts oc_volta --check
	catro-scripts oc_volta --version 2.4.1
	catro-scripts oc_volta --force --restart

Requirements:
	- Volta with `@opencode/cli` installed (https://volta.sh)
	- `npm` on PATH (version lookup) and `node` (the postinstall step)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

import tui

# npm package that owns the CLI and the binary its postinstall installs.
PACKAGE = '@opencode/cli'

# A placeholder binary is a text stub of a few hundred bytes; the real
# platform binary is tens of megabytes, so this threshold separates them
# without hashing anything.
STUB_MAX_BYTES = 4096


def volta_home():
	"""Volta's install root.

	Volta honours `$VOLTA_HOME`, otherwise `~/.volta` - except on Windows,
	where the installer uses `%LOCALAPPDATA%\\Volta` and sets no variable. Pick
	the first candidate that actually holds Volta's package image, so a wrong
	guess cannot silently point the update at a directory nobody uses.
	"""
	configured = os.environ.get('VOLTA_HOME', '').strip()
	candidates = []
	if configured:
		candidates.append(configured)
	local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
	if local_app_data:
		candidates.append(os.path.join(local_app_data, 'Volta'))
	candidates.append(os.path.join(os.path.expanduser('~'), '.volta'))
	packages = os.path.join('tools', 'image', 'packages')
	for candidate in candidates:
		if os.path.isdir(os.path.join(candidate, packages)):
			return candidate
	return candidates[0]


def package_dir():
	"""Directory Volta unpacks `@opencode/cli` into (the shim's real target)."""
	return os.path.join(volta_home(), 'tools', 'image', 'packages',
						'@opencode', 'cli', 'node_modules', '@opencode', 'cli')


def package_json_path():
	return os.path.join(package_dir(), 'package.json')


def binary_path():
	"""The binary the `opencode` shim executes, inside the package."""
	name = 'opencode.exe' if os.name == 'nt' else 'opencode'
	return os.path.join(package_dir(), 'bin', name)


def postinstall_path():
	return os.path.join(package_dir(), 'postinstall.mjs')


def resolve_command(name):
	"""Locate an executable, preferring a native binary over a .cmd shim."""
	return shutil.which(name)


def run_command(argv, capture=True):
	"""Run argv, routing .cmd/.bat Windows shims through cmd.exe.

	Volta and npm both surface as shims, and Windows cannot spawn a `.cmd`
	directly from a list-form subprocess call.
	"""
	executable = resolve_command(argv[0])
	if not executable:
		raise FileNotFoundError(argv[0])
	command = [executable] + list(argv[1:])
	if os.name == 'nt' and executable.lower().endswith(('.cmd', '.bat')):
		command = subprocess.list2cmdline(command)
		return subprocess.run(command, shell=True, capture_output=capture,
							  text=True)
	return subprocess.run(command, capture_output=capture, text=True)


def installed_version():
	"""Version Volta actually has on disk, or None when it is not installed."""
	try:
		with open(package_json_path(), 'r', encoding='utf-8') as handle:
			return (json.load(handle).get('version') or '').strip() or None
	except (OSError, ValueError):
		return None


def latest_version():
	"""Latest published version of the npm package, or None on failure."""
	try:
		result = run_command(['npm', 'view', PACKAGE, 'version'])
	except (OSError, FileNotFoundError):
		return None
	if result.returncode != 0:
		return None
	return (result.stdout or '').strip().strip('"').strip() or None


def binary_size(path=None):
	try:
		return os.path.getsize(path or binary_path())
	except OSError:
		return 0


def binary_is_stub(path=None):
	"""True when the binary is the un-replaced postinstall placeholder."""
	size = binary_size(path)
	return 0 < size < STUB_MAX_BYTES


def probe_version(path=None):
	"""Ask the binary for its version; None when it cannot run at all."""
	target = path or binary_path()
	if not os.path.isfile(target):
		return None
	try:
		result = subprocess.run([target, '--version'], capture_output=True,
								text=True, timeout=120)
	except (OSError, subprocess.SubprocessError):
		return None
	if result.returncode != 0:
		return None
	# The CLI prints "opencode v2.4.1"; keep only the version token so the
	# comparison against the npm version stays exact.
	for token in (result.stdout or '').replace('\n', ' ').split():
		token = token.strip().lstrip('v')
		if token and token[0].isdigit():
			return token
	return None


def install_version(target):
	"""`volta install <package>@<target>`; returns (ok, detail)."""
	reference = '{}@{}'.format(PACKAGE, target)
	try:
		result = run_command(['volta', 'install', reference], capture=False)
	except (OSError, FileNotFoundError) as error:
		return False, 'cannot run volta: {}'.format(error)
	if result.returncode != 0:
		return False, 'volta install exited {}'.format(result.returncode)
	return True, reference


def run_postinstall():
	"""Run the package's postinstall so the real platform binary lands.

	This is the step Volta skips and the one that makes the difference between
	a working `opencode` and a placeholder text file.
	"""
	script = postinstall_path()
	if not os.path.isfile(script):
		return False, 'postinstall.mjs missing from {}'.format(package_dir())
	node = resolve_command('node')
	if not node:
		return False, 'node is not on PATH (needed for postinstall.mjs)'
	try:
		result = subprocess.run([node, script], cwd=package_dir(),
								capture_output=True, text=True, timeout=900)
	except (OSError, subprocess.SubprocessError) as error:
		return False, 'postinstall failed to run: {}'.format(error)
	if result.returncode != 0:
		detail = (result.stdout or '') + (result.stderr or '')
		detail = detail.strip().splitlines()[-3:]
		return False, 'postinstall exited {}: {}'.format(
			result.returncode, ' | '.join(detail) or 'no output')
	return True, 'postinstall.mjs'


def restart_service():
	"""Restart the opencode service so the running server picks up the binary."""
	try:
		offline = run_command(['opencode', 'service', 'restart'], capture=False)
	except (OSError, FileNotFoundError) as error:
		return False, 'cannot run opencode: {}'.format(error)
	if offline.returncode != 0:
		return False, 'opencode service restart exited {}'.format(
			offline.returncode)
	return True, 'service restarted'


def print_page(rows, cap, title=None):
	"""Render a compact status panel; `title` adds a header band (first page only)."""
	body = []
	for kind, text in rows:
		if kind in ('ok', 'warn', 'error', 'info'):
			body.append(tui.status(kind, text, cap=cap))
		elif kind == 'field':
			body.append(text)
	print()
	if title:
		print(tui.header(title, cap=cap))
		print()
	print(tui.panel('volta: {}'.format(volta_home()), body, cap=cap))
	print()


def upgrade(args, cap):
	"""The whole workflow. Returns the process exit code."""
	current = installed_version()
	if current is None:
		print_page([
			('error', '`{}` is not installed through Volta '
					  '(no package at {}).'.format(PACKAGE, package_dir())),
			('info', 'Install it first: volta install {}@latest'.format(
				PACKAGE)),
		], cap)
		return 1

	# A pinned --version is authoritative; otherwise ask the registry. When the
	# registry is unreachable the healthy local install is still usable, so a
	# missing answer only fails the run when there is work to do.
	target = args.version or latest_version()
	if target is None:
		if args.version is None and not args.force:
			healthy = probe_version() == current
			print_page([
				('warn', 'Could not read the latest version from npm '
						 '(offline? no npm?).'),
				('field', tui.field('Installed:', current, cap=cap)),
				('ok' if healthy else 'error',
				 'Local binary is {}; pass --version <v> to pin a '
				 'target.'.format('healthy' if healthy else 'broken')),
			], cap)
			return 0 if healthy else 1
		target = current

	outdated = current != target
	needs_repair = binary_is_stub() or probe_version() != current

	# Report the state first, so a --check run and a real run open the same way.
	print()
	print(tui.header('--- OPENCODE UPDATE ---', cap=cap))
	print()
	print(tui.field('Installed:', current, cap=cap))
	print(tui.field('Target:', target, cap=cap))
	print(tui.field('Binary:', 'placeholder (needs postinstall)'
					if binary_is_stub() else 'ok', cap=cap))
	print()

	if args.check:
		# Read-only mode: never touch the install, just classify it.
		if outdated:
			print(tui.status('warn', 'Update available: {} -> {} '
									 '(re-run without --check).'.format(
										 current, target), cap=cap))
		elif needs_repair:
			print(tui.status('warn', 'Version is current but the binary '
									 'needs the postinstall step '
									 '(re-run without --check).', cap=cap))
		else:
			print(tui.status('ok', 'Up to date at {}.'.format(current),
							 cap=cap))
		print()
		return 0

	if not outdated and not needs_repair and not args.force:
		print(tui.status('ok', 'Already up to date ({}).'.format(current),
						 cap=cap))
		print()
		return 0

	rows = []
	if outdated or args.force:
		ok, detail = install_version(target)
		rows.append(('ok' if ok else 'error',
					 'volta install: {}'.format(detail)))
		if not ok:
			print_page(rows, cap)
			return 1
	else:
		rows.append(('warn', 'Version unchanged; repairing the binary only.'))

	ok, detail = run_postinstall()
	rows.append(('ok' if ok else 'error', 'postinstall: {}'.format(detail)))
	if not ok:
		print_page(rows, cap)
		return 1

	# Verification is the point of the whole exercise: the install command
	# succeeding means nothing if the shim still runs a placeholder.
	seen = probe_version()
	verified = seen == target
	rows.append(('ok' if verified else 'error',
				 'verify: binary reports {} (expected {})'.format(
					 seen or 'nothing', target)))
	if binary_is_stub():
		rows.append(('error', 'binary is still the postinstall placeholder'))
		verified = False
	if not verified:
		print_page(rows, cap)
		return 1

	if args.restart:
		ok, detail = restart_service()
		rows.append(('ok' if ok else 'warn', 'restart: {}'.format(detail)))
	else:
		rows.append(('info', 'service not restarted '
							 '(pass --restart when no session is running)'))

	print_page(rows, cap)
	print(tui.status('ok', 'opencode is now {}.'.format(seen), cap=cap))
	print()
	return 0


def parse_args(argv):
	parser = argparse.ArgumentParser(
		prog='catro-scripts oc_volta',
		description='Update the Volta-installed opencode CLI, including the '
					'postinstall step Volta skips.')
	parser.add_argument('--check', action='store_true',
						help='report installed vs latest and change nothing')
	parser.add_argument('--version', metavar='V',
						help='install this exact version instead of latest')
	parser.add_argument('--force', action='store_true',
						help='reinstall even when the versions already match')
	parser.add_argument('--restart', action='store_true',
						help='restart the opencode service after updating '
							 '(ends any running agent session)')
	return parser.parse_args(argv)


def main():
	tui.init_ansi()
	cap = tui.detect()
	args = parse_args(sys.argv[1:])
	sys.exit(upgrade(args, cap))


if __name__ == '__main__':
	main()
