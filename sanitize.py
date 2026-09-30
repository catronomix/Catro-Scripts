# Sanitize git history by replacing a leaked secret
"""
			GIT HISTORY SANITIZER
			=====================
	This script rewrites full git history to replace a leaked secret with a
	safe placeholder. It covers file contents and commit messages, then
	expires reflogs and garbage-collects so the secret is gone from every
	commit, blob, and reflog.

	Features:
		- Pre-checks history first to avoid a destructive no-op rewrite.
		- Uses git-filter-repo with literal (non-regex) replacement text.
		- Warns on dirty working trees before rewriting.
		- Verifies history after rewrite and reports leaks clearly.
		- Full-color output with box-drawing tables.

	Usage:
		python sanitize.py "<secret>" "<placeholder>" [--yes]

	Note:
		Always quote both values. Secrets/placeholders often contain shell
		metacharacters ([ ] ( ) & ! % < >); unquoted, the shell eats them
		before Python ever runs (e.g. bare <redacted> is input redirection
		and fails with "The syntax of the command is incorrect").

	Examples:
		- python sanitize.py "Mypassword123" "<redacted-pass1>"
		- python sanitize.py "Mypassword123" "***" --yes

	Requirements:
		- No external Python libraries required; uses standard modules only.
		- Requires git plus git-filter-repo on PATH (pip install git-filter-repo).
		- Operates on the git repo in the current working directory.
		- WARNING: rewrites ALL history. Back up first, then force-push.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# House-style palette (standardized on list.py Colors approach).
class Colors:
	PURPLE = '\033[38;2;170;0;255m'
	LIGHT_BLUE = '\033[38;2;173;216;230m'
	BG_BLACK = '\033[48;2;0;0;0m'
	BG_GREY = '\033[48;2;45;45;45m'
	GREEN = '\033[38;2;0;255;0m'
	YELLOW = '\033[38;2;255;255;0m'
	RED = '\033[38;2;255;70;70m'
	BOLD = '\033[1m'
	END = '\033[0m'


def init_ansi():
	# Enable ANSI escape sequences on Windows consoles.
	if os.name == 'nt':
		os.system('')


def run(cmd, **kwargs):
	# Thin wrapper: capture stdout/stderr as text so callers can inspect it.
	# Uses UTF-8 with replacement so binary blobs in history (images, zips,
	# legacy encodings) never crash decoding on Windows (cp1252 default).
	kwargs.setdefault("encoding", "utf-8")
	kwargs.setdefault("errors", "replace")
	return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def run_bytes(cmd, **kwargs):
	# Binary-safe variant: needed when scanning blobs that may not be UTF-8.
	return subprocess.run(cmd, capture_output=True, **kwargs)


def _box_chars():
	# Use Unicode box-drawing per house style, but fall back to ASCII when
	# the console encoding (e.g. Windows cp1252) cannot render Unicode.
	try:
		for ch in "┌┐└┘─│├┤":
			ch.encode(sys.stdout.encoding or "utf-8")
		return ('┌', '┐', '└', '┘', '─', '│', '├', '┤')
	except Exception:
		return ('+', '+', '+', '+', '-', '|', '+', '+')


def print_table(title, rows):
	# Render key/value rows in a Unicode box table with alternating backgrounds.
	widths = [len(str(k)) for k, _ in rows]
	widths += [len(title)]
	w_key = max(widths) if widths else len(title)
	w_val = max([len(str(v)) for _, v in rows] + [0])
	w_key = max(w_key, 8)
	w_val = max(w_val, 8)
	total = w_key + w_val + 5
	tl, tr, bl, br, h, v, l_join, r_join = _box_chars()
	print(f"{Colors.PURPLE}{tl}{h * total}{tr}{Colors.END}")
	header = f" {title} ".center(total)
	print(f"{Colors.PURPLE}{v}{Colors.BOLD}{header}{Colors.END}{Colors.PURPLE}{v}{Colors.END}")
	print(f"{Colors.PURPLE}{l_join}{h * total}{r_join}{Colors.END}")
	for i, (k, val) in enumerate(rows):
		bg = Colors.BG_BLACK if i % 2 == 0 else Colors.BG_GREY
		style = Colors.LIGHT_BLUE + bg
		row = (f"{Colors.PURPLE}{v}{style} {str(k):<{w_key}} {v} "
			   f"{str(val):<{w_val}} {Colors.END}{Colors.PURPLE}{v}{Colors.END}")
		print(row)
	print(f"{Colors.PURPLE}{bl}{h * total}{br}{Colors.END}")


def parse_args(argv):
	# Parse CLI input into secret/placeholder plus a non-interactive flag.
	parser = argparse.ArgumentParser(
		description="Replace a secret with a placeholder across full git history.")
	parser.add_argument("secret", help="Secret string to remove (must not be empty).")
	parser.add_argument("placeholder", help="Replacement text, e.g. '<redacted>'.")
	parser.add_argument("--yes", "-y", action="store_true",
						help="Skip confirmation prompts (for automation).")
	return parser.parse_args(argv)


def find_repo_root():
	# Resolve the repo top-level; fails when git is missing or cwd is not a repo.
	try:
		r = run(["git", "rev-parse", "--show-toplevel"])
	except FileNotFoundError:
		return None, "git is not installed or not on PATH."
	if r.returncode != 0:
		return None, "current directory is not inside a git repo."
	return Path(r.stdout.strip()), ""


def find_filter_repo():
	# Locate git-filter-repo as a standalone exe or as the `git filter-repo` subcommand.
	if shutil.which("git-filter-repo"):
		return ["git-filter-repo"]
	r = run(["git", "filter-repo", "--version"])
	if r.returncode == 0:
		return ["git", "filter-repo"]
	return None


def blob_contains(oid, needle):
	# Check one blob object for the secret using raw bytes (encoding-safe).
	c = run_bytes(["git", "cat-file", "-p", oid])
	if needle in (c.stdout or b""):
		return True
	try:
		if needle.decode("utf-8", "ignore").encode() in (c.stdout or b""):
			return True
	except Exception:
		pass
	return False


def iter_blob_oids():
	# Yield blob object IDs from all revs; skips non-blob objects.
	rev = run(["git", "rev-list", "--all", "--objects"])
	if rev.returncode != 0:
		return
	for line in rev.stdout.splitlines():
		parts = line.split()
		if not parts:
			continue
		oid = parts[0]
		t = run(["git", "cat-file", "-t", oid])
		if t.stdout.strip() == "blob":
			yield oid


def secret_in_history(secret):
	# Search commit diffs/messages first (fast path), then every blob (slow path).
	v = run(["git", "log", "--all", "-p", "--format=%B"])
	if secret in (v.stdout or ""):
		return True
	needle = secret.encode("utf-8", "ignore")
	for oid in iter_blob_oids():
		if blob_contains(oid, needle):
			return True
	return False


def main(argv=None) -> int:
	init_ansi()
	args = parse_args(sys.argv[1:] if argv is None else argv)
	secret, placeholder = args.secret, args.placeholder

	# Validate input: empty secrets or filter-repo delimiter sequences are rejected.
	if not secret:
		print(f"{Colors.RED}Error: secret must not be empty.{Colors.END}", file=sys.stderr)
		return 2
	if "\n" in secret or "==>" in secret:
		print(f"{Colors.RED}Error: secret must not contain a newline or '==>'.{Colors.END}",
			  file=sys.stderr)
		return 2

	# Confirm we are inside a repo before doing anything destructive.
	repo_root, err = find_repo_root()
	if repo_root is None:
		print(f"{Colors.RED}Error: {err}{Colors.END}", file=sys.stderr)
		if "not inside" in err:
			print("Hint: cd to the repo root, or run: git init", file=sys.stderr)
		return 1

	# Confirm the rewrite backend exists before warning or scanning.
	filter_repo_cmd = find_filter_repo()
	if filter_repo_cmd is None:
		print(f"{Colors.RED}Error: git-filter-repo not found. Install it with:{Colors.END}",
			  file=sys.stderr)
		print("    pip install git-filter-repo", file=sys.stderr)
		return 1

	print_table("SANITIZE PLAN", [
		("Repo", str(repo_root)),
		("Secret", secret),
		("Placeholder", placeholder),
		("Backend", " ".join(filter_repo_cmd)),
	])

	# Warn about dirty trees; rewriting with uncommitted work risks losing it.
	r = run(["git", "status", "--porcelain"])
	if r.returncode == 0 and r.stdout.strip() and not args.yes:
		print(f"{Colors.YELLOW}WARNING: working tree has uncommitted changes. "
			  f"Commit or stash first.{Colors.END}")
		ans = input("Continue anyway? [y/N] ").strip().lower()
		if ans not in ("y", "yes"):
			print("Aborted.")
			return 1
	print(f"{Colors.YELLOW}WARNING: this rewrites ALL history. Back up first and "
		  f"force-push afterwards.{Colors.END}")
	if not args.yes:
		ans = input("Rewrite full history now? [y/N] ").strip().lower()
		if ans not in ("y", "yes"):
			print("Aborted.")
			return 1

	# Pre-check avoids a destructive no-op (filter-repo drops origin, expires
	# reflogs, GCs) paired with a misleading SUCCESS message.
	print(f"{Colors.LIGHT_BLUE}Scanning history for secret...{Colors.END}")
	if not secret_in_history(secret):
		print(f"{Colors.GREEN}Secret not found in repo history. Nothing to do (exit 0).{Colors.END}")
		return 0

	# Write the replacement file as plain UTF-8 without BOM; the literal:
	# prefix keeps regex special chars in the secret safe.
	with tempfile.NamedTemporaryFile(
		mode="w", suffix=".txt", delete=False, encoding="utf-8", newline="\n"
	) as f:
		f.write(f"literal:{secret}==>{placeholder}\n")
		replace_file = f.name

	try:
		# Run the rewrite over both file contents and commit messages.
		cmd = filter_repo_cmd + [
			"--replace-text", replace_file,
			"--replace-message", replace_file,
			"--force",
		]
		print(f"{Colors.LIGHT_BLUE}Running: {' '.join(cmd)}{Colors.END}")
		p = subprocess.run(cmd)
		if p.returncode != 0:
			print(f"{Colors.RED}git-filter-repo failed.{Colors.END}", file=sys.stderr)
			return 1

		# Harden the rewrite: expire reflogs and prune unreachable objects so
		# no dangling copy of the secret survives (filter-repo already GCs).
		run(["git", "reflog", "expire", "--expire=now", "--all"])
		run(["git", "gc", "--prune=now", "--aggressive"])

		# Verify the secret is gone: searchable history plus a blob-by-blob scan.
		print(f"{Colors.LIGHT_BLUE}Verifying rewrite...{Colors.END}")
		v = run(["git", "log", "--all", "-p", "--", "."])
		g = run(["git", "grep", "-F", secret, "--", "HEAD"])
		leaks = []
		needle = secret.encode("utf-8", "ignore")
		for oid in iter_blob_oids():
			if blob_contains(oid, needle):
				leaks.append(oid)
				break

		history_still_has_it = secret in (v.stdout or "")
		head_has_it = g.returncode == 0 and g.stdout.strip()
		if history_still_has_it or leaks or head_has_it:
			print(f"{Colors.RED}WARNING: secret string still found after rewrite!{Colors.END}",
				  file=sys.stderr)
			print("The secret may exist in untracked files, tags, stash, or "
				  "filenames (use --path renames for filenames).", file=sys.stderr)
			if leaks:
				print(f"Leaking blob: {leaks[0]}", file=sys.stderr)
			return 1

		# Report success with the force-push / rotation steps that must follow.
		print(f"{Colors.GREEN}{Colors.BOLD}SUCCESS: secret replaced with "
			  f"'{placeholder}' in full history.{Colors.END}")
		print_table("NEXT STEPS", [
			("1. Force-push", "git push --force --all && git push --force --tags"),
			("2. Teammates", "Everyone else must re-clone"),
			("3. Rotation", "Rotate the leaked secret"),
		])
		return 0
	finally:
		# Always remove the temp replacement file; it contains the raw secret.
		Path(replace_file).unlink(missing_ok=True)


if __name__ == "__main__":
	sys.exit(main())
