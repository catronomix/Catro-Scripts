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
		- House-style key/value blocks; plain TAB output when piped.
		- With the secret omitted, reads it at a masked prompt (no echo) and
		  blanks the prompt row when it is done.
		- The secret is never taken from argv or handed to a child process:
		  prompt, --stdin or --env only (issue 0050).

	Usage:
		python sanitize.py [--placeholder "<text>"] [--yes]
		python sanitize.py --stdin --yes                 # secret on stdin
		python sanitize.py --env [VAR] [--yes]           # secret in env

	Note:
		The secret is never accepted as a command-line argument. argv is
		visible in shell history and to every other process on the machine
		(ps, Task Manager, EDR tooling) while the run is alive, and in the
		history file long after. Read it from the masked prompt (default), a
		pipe (--stdin) or an environment variable (--env VAR); the variable
		is removed from the process environment before any git subprocess
		starts. The placeholder is not sensitive and stays a normal option.
		Quote the placeholder: it may contain shell metacharacters
		([ ] ( ) & ! % < >); unquoted, the shell eats them before Python runs
		(e.g. bare <redacted> is input redirection).
		The masked prompt guarantees the typed secret is not echoed and the
		prompt row is cleared; it cannot scrub a scrollback the terminal has
		already committed by other means.

	Examples:
		- python sanitize.py                              (prompts, default placeholder)
		- python sanitize.py --placeholder "<redacted-pass1>"
		- type secret.txt | python sanitize.py --stdin --yes
		- python sanitize.py --env MY_SECRET --yes        (variable already set,
		  e.g. by a secret manager; not assigned inline on the command line)

	Requirements:
		- No external Python libraries required; uses standard modules only.
		- Requires git plus git-filter-repo on PATH (pip install git-filter-repo).
		- Operates on the git repo in the current working directory.
		- WARNING: rewrites ALL history. Back up first, then force-push.
"""

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tui

# Width of the centred plan/summary panels; narrower terminals win.
PLAN_WIDTH = 60

# Default variable read by a bare `--env`: a name, never the secret itself.
DEFAULT_SECRET_ENV = "SANITIZE_SECRET"

# Refusal for anything positional: the value may be the secret, so it is never
# echoed back and only the safe sources are named.
ARGV_REFUSAL = (
	"the secret is not accepted as a command-line argument: it leaks through "
	"the process list and shell history. Use the masked prompt, --stdin, or "
	"--env [VAR] instead; pass the placeholder with --placeholder.")


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


def parse_args(argv):
	# Parse CLI input into a placeholder plus one secret source. No value that
	# could be the secret is ever accepted on the command line, so any stray
	# positional (or unknown option, which argparse would otherwise echo back)
	# is refused with ARGV_REFUSAL. Keeping a hidden positional lets a legacy
	# invocation be recognised and rejected by name instead of being dropped.
	parser = argparse.ArgumentParser(
		description="Replace a secret with a placeholder across full git history.",
		usage="%(prog)s [--placeholder TEXT] [--stdin | --env [VAR]] [--yes]",
		epilog="The secret is read from the masked prompt, stdin (--stdin) or "
			   "an environment variable (--env [VAR]); it is never accepted as "
			   "an argument.")
	parser.add_argument("-p", "--placeholder", default=None,
						help="Replacement text, e.g. '<redacted>' "
							 "(default: '<redacted>').")
	parser.add_argument("--stdin", action="store_true",
						help="Read the secret from stdin (needs --yes, off a tty).")
	parser.add_argument("--env", metavar="VAR", nargs="?", default=None,
						const=DEFAULT_SECRET_ENV,
						help="Read the secret from environment variable VAR "
							 "(default: %s)." % DEFAULT_SECRET_ENV)
	parser.add_argument("--yes", "-y", action="store_true",
						help="Skip confirmation prompts (for automation).")
	parser.add_argument("legacy", nargs="*", help=argparse.SUPPRESS)
	args, unknown = parser.parse_known_args(argv)
	# Report a single refusal whenever anything positional or unrecognised is
	# left: the token itself is never printed (it may be the secret).
	if args.legacy or unknown:
		parser.error(ARGV_REFUSAL)
	if args.stdin and args.env is not None:
		parser.error("--stdin and --env are different sources; pick one")
	return args


def secret_from_env(name):
	# Read and drop the variable in the same step: every git/filter-repo child
	# inherits the environment, so leaving it set would widen the leak we are
	# closing (a child's environ is readable too).
	secret = os.environ.pop(name, None)
	return secret


def _vt_ready(stream):
	# False only for a real Windows console that rejects VT escapes: there the
	# erase bytes would be typed out as literal "[1A[2K". Everything else
	# (POSIX ttys, test doubles) is assumed to render them.
	if os.name != "nt" or not hasattr(stream, "fileno"):
		return True
	return tui.console_vt.can_vt(stream)


def blank_prompt_row(cap, stream=None):
	# Erase the row the masked prompt left behind so the prompt text does not
	# stay in the scrollback. Silent when the run asked for no escapes at all
	# (level "none") or the console cannot take them; no-op off a terminal.
	if cap is not None and cap.level == "none":
		return
	stream = sys.stderr if stream is None else stream
	try:
		if not stream.isatty():
			return
	except (AttributeError, ValueError, OSError):
		return
	if not _vt_ready(stream):
		return
	stream.write(tui.screen.ERASE_ROW_UP)
	stream.flush()


def plan_block(title, pairs, cap):
	# The plan and the next-steps block: a small centred panel on a terminal,
	# the same TAB records as before in a pipe. Values wrap inside the box, so a
	# long repo path or the force-push command is shown whole instead of cut.
	if cap.plain:
		return tui.key_values(title, pairs, cap=cap)
	key_width = max([len(key) for key, _ in pairs] or [0])
	rows = ["{}  {}".format(key.ljust(key_width), value) for key, value in pairs]
	needed = max([tui.display_width(row) for row in rows] or [0]) + 4
	needed = max(needed, tui.display_width(title) + 6)
	width = max(PLAN_WIDTH, needed)
	if cap.width:
		width = min(width, cap.width)
	cell = max(1, width - 4)
	body = []
	for key, value in pairs:
		lead = "{}  ".format(key.ljust(key_width))
		hang = " " * len(lead)
		pieces = tui.wrap(value, max(1, cell - len(lead))) or [""]
		body.append(lead + pieces[0])
		body.extend(hang + piece for piece in pieces[1:])
	lines = tui.panel(title, body, width=width, cap=cap).splitlines()
	box = max([tui.display_width(line) for line in lines] or [0])
	margin = " " * max(0, ((cap.width or box) - box) // 2)
	return "\n".join(margin + line for line in lines)


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


def tree_contains(needle, rev="HEAD"):
	# Scan one tree in-process. `git grep -F <secret>` would hand the secret to
	# a child's argv, which is exactly the exposure this script now refuses, so
	# the blobs are listed by object id and inspected here instead.
	tree = run(["git", "ls-tree", "-r", "-z", rev])
	if tree.returncode != 0:
		return False
	for entry in (tree.stdout or "").split("\0"):
		meta, _, _path = entry.partition("\t")
		parts = meta.split()
		if len(parts) < 3 or parts[1] != "blob" or parts[0] == "160000":
			continue
		if blob_contains(parts[2], needle):
			return True
	return False


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


def get_remotes():
	# Snapshot remotes as {name: {"fetch": url, "push": url}} so they can be
	# restored after filter-repo (which strips `origin` by design to prevent
	# an accidental force-push of rewritten history).
	remotes = {}
	r = run(["git", "remote", "-v"])
	if r.returncode != 0:
		return remotes
	for line in (r.stdout or "").splitlines():
		parts = line.split()
		if len(parts) < 3:
			continue
		name, url, kind = parts[0], parts[1], parts[2].strip("()")
		entry = remotes.setdefault(name, {})
		if kind in ("fetch", "push"):
			entry.setdefault(kind, url)
	return remotes


def restore_remotes(saved):
	# Re-add any remotes missing after the rewrite; returns list of restored names.
	if not saved:
		return []
	r = run(["git", "remote"])
	existing = set((r.stdout or "").split()) if r.returncode == 0 else set()
	restored = []
	for name, urls in saved.items():
		if name in existing:
			continue
		fetch_url = urls.get("fetch") or urls.get("push")
		if not fetch_url:
			continue
		a = run(["git", "remote", "add", name, fetch_url])
		if a.returncode != 0:
			print(tui.status(
				"warn", f"could not restore remote '{name}': "
				f"{a.stderr.strip()}"),
				  file=sys.stderr)
			continue
		push_url = urls.get("push")
		if push_url and push_url != fetch_url:
			run(["git", "remote", "set-url", "--push", name, push_url])
		restored.append(name)
	return restored


def main(argv=None) -> int:
	tui.init_ansi()
	cap = tui.detect()
	args = parse_args(sys.argv[1:] if argv is None else argv)
	secret, placeholder = None, args.placeholder
	if placeholder is None:
		placeholder = "<redacted>"

	# Secret intake: never argv. --stdin reads a pipe (a terminal would echo the
	# typed value and is also where the y/n confirmations come from, so that
	# combination is refused); --env reads a variable and drops it before any
	# child starts. The default is the masked prompt, which needs a terminal.
	if args.stdin:
		if not args.yes:
			sys.stderr.write(
				"[Error] sanitize --stdin needs --yes: stdin is the secret, so "
				"there is no terminal left to confirm the rewrite.\n")
			return 2
		try:
			echoing = sys.stdin.isatty()
		except (AttributeError, ValueError, OSError):
			echoing = False
		if echoing:
			sys.stderr.write(
				"[Error] sanitize --stdin refuses a terminal: the secret would "
				"be echoed. Omit --stdin to use the masked prompt.\n")
			return 2
		secret = sys.stdin.read().rstrip("\r\n")
	elif args.env is not None:
		secret = secret_from_env(args.env)
		if secret is None:
			sys.stderr.write(
				f"[Error] environment variable {args.env} is not set.\n")
			return 2
	else:
		if not sys.stdin.isatty():
			sys.stderr.write(
				"[Error] sanitize needs an interactive terminal to prompt for "
				"the secret (stdin is not a tty). Use --stdin or --env [VAR] "
				"for automation.\n")
			return 2
		# The prompt (and its erase) land on stderr, so its capability - not the
		# page's stdout - decides whether the erase escapes may be written.
		prompt_cap = tui.detect(sys.stderr)
		try:
			secret = getpass.getpass("Secret: ")
		except (EOFError, KeyboardInterrupt):
			print("Aborted.")
			return 1
		finally:
			# getpass never echoes the typed value; blank its prompt row too.
			blank_prompt_row(prompt_cap)

	replace_file = None
	try:
		# Validate input: empty secrets or filter-repo delimiter sequences are
		# rejected.
		if not secret:
			print(tui.status("error", "Error: secret must not be empty.",
							 cap=cap), file=sys.stderr)
			return 2
		if "\n" in secret or "==>" in secret:
			print(tui.status("error",
							 "Error: secret must not contain a newline or '==>'.",
							 cap=cap),
				  file=sys.stderr)
			return 2

		# Confirm we are inside a repo before doing anything destructive.
		repo_root, err = find_repo_root()
		if repo_root is None:
			print(tui.status("error", f"Error: {err}", cap=cap), file=sys.stderr)
			if "not inside" in err:
				print("Hint: cd to the repo root, or run: git init", file=sys.stderr)
			return 1

		# Confirm the rewrite backend exists before warning or scanning.
		filter_repo_cmd = find_filter_repo()
		if filter_repo_cmd is None:
			print(tui.status("error",
							 "Error: git-filter-repo not found. Install it with:",
							 cap=cap),
				  file=sys.stderr)
			print("    pip install git-filter-repo", file=sys.stderr)
			return 1

		print(plan_block("SANITIZE PLAN", [
			("Repo", str(repo_root)),
			("Secret", "<redacted>"),
			("Placeholder", placeholder),
			("Backend", " ".join(filter_repo_cmd)),
		], cap))

		# Warn about dirty trees; rewriting with uncommitted work risks losing it.
		r = run(["git", "status", "--porcelain"])
		if r.returncode == 0 and r.stdout.strip() and not args.yes:
			print(tui.status("warn",
							 "WARNING: working tree has uncommitted changes. "
							 "Commit or stash first.", cap=cap))
			ans = input("Continue anyway? [y/N] ").strip().lower()
			if ans not in ("y", "yes"):
				print("Aborted.")
				return 1
		print(tui.status("warn", "WARNING: this rewrites ALL history. Back up "
						 "first and force-push afterwards.", cap=cap))
		if not args.yes:
			ans = input("Rewrite full history now? [y/N] ").strip().lower()
			if ans not in ("y", "yes"):
				print("Aborted.")
				return 1

		# Pre-check avoids a destructive no-op (filter-repo drops origin,
		# expires reflogs, GCs) paired with a misleading SUCCESS message.
		print(tui.status("info", "Scanning history for secret...", cap=cap))
		if not secret_in_history(secret):
			print(tui.status("ok", "Secret not found in repo history. Nothing to "
							 "do (exit 0).", cap=cap))
			return 0

		# Snapshot remotes: git-filter-repo strips `origin` by design, so save
		# them now and restore after the rewrite.
		saved_remotes = get_remotes()

		# Write the replacement file as plain UTF-8 without BOM; the literal:
		# prefix keeps regex special chars in the secret safe.
		with tempfile.NamedTemporaryFile(
			mode="w", suffix=".txt", delete=False, encoding="utf-8", newline="\n"
		) as f:
			f.write(f"literal:{secret}==>{placeholder}\n")
			replace_file = f.name

		# Run the rewrite over both file contents and commit messages.
		cmd = filter_repo_cmd + [
			"--replace-text", replace_file,
			"--replace-message", replace_file,
			"--force",
		]
		print(tui.field("Running:", " ".join(cmd), cap=cap))
		p = subprocess.run(cmd)
		if p.returncode != 0:
			print(tui.status("error", "git-filter-repo failed.", cap=cap),
				  file=sys.stderr)
			return 1

		# Harden the rewrite: expire reflogs and prune unreachable objects so
		# no dangling copy of the secret survives (filter-repo already GCs).
		run(["git", "reflog", "expire", "--expire=now", "--all"])
		run(["git", "gc", "--prune=now", "--aggressive"])

		# filter-repo removes `origin` (and other remotes) by design; put them
		# back.
		restored = restore_remotes(saved_remotes)
		if saved_remotes and restored:
			detail = ", ".join(
				n + " -> " + saved_remotes[n].get("fetch", "") for n in restored)
			print(tui.field("Restored remote(s):", detail, cap=cap))
		elif saved_remotes:
			print(tui.status("info", "Remotes already present, nothing to restore.",
							 cap=cap))

		# Verify the secret is gone: searchable history plus a blob-by-blob scan.
		# The scan is in-process on purpose; the secret must never reach a
		# child's argv (see tree_contains).
		print(tui.status("info", "Verifying rewrite...", cap=cap))
		v = run(["git", "log", "--all", "-p", "--", "."])
		leaks = []
		needle = secret.encode("utf-8", "ignore")
		for oid in iter_blob_oids():
			if blob_contains(oid, needle):
				leaks.append(oid)
				break

		history_still_has_it = secret in (v.stdout or "")
		head_has_it = tree_contains(needle)
		if history_still_has_it or leaks or head_has_it:
			print(tui.status("error",
							 "Secret string still found after rewrite!",
							 cap=cap), file=sys.stderr)
			print("The secret may exist in untracked files, tags, stash, or "
				  "filenames (use --path renames for filenames).", file=sys.stderr)
			if leaks:
				print(f"Leaking blob: {leaks[0]}", file=sys.stderr)
			return 1

		# Report success with the force-push / rotation steps that must follow.
		print(tui.status("ok",
						 f"Secret replaced with '{placeholder}' in full history.",
						 cap=cap))
		print(plan_block("NEXT STEPS", [
			("1. Force-push", "git push --force --all && git push --force --tags"),
			("2. Teammates", "Everyone else must re-clone"),
			("3. Rotation", "Rotate the leaked secret"),
		], cap))
		return 0
	finally:
		# Always remove the temp replacement file (it holds the raw secret) and
		# overwrite the local copy before it leaves scope.
		if replace_file is not None:
			Path(replace_file).unlink(missing_ok=True)
		if secret:
			secret = "\0" * len(secret)
		del secret


if __name__ == "__main__":
	sys.exit(main())
