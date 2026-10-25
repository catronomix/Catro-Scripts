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

import tui


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
			print(tui.style(f"WARNING: could not restore remote "
							f"'{name}': {a.stderr.strip()}", fg="warn"),
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
	secret, placeholder = args.secret, args.placeholder

	# Validate input: empty secrets or filter-repo delimiter sequences are rejected.
	if not secret:
		print(tui.style("Error: secret must not be empty.", fg="error", cap=cap),
			  file=sys.stderr)
		return 2
	if "\n" in secret or "==>" in secret:
		print(tui.style("Error: secret must not contain a newline or '==>'.",
						fg="error", cap=cap),
			  file=sys.stderr)
		return 2

	# Confirm we are inside a repo before doing anything destructive.
	repo_root, err = find_repo_root()
	if repo_root is None:
		print(tui.style(f"Error: {err}", fg="error", cap=cap), file=sys.stderr)
		if "not inside" in err:
			print("Hint: cd to the repo root, or run: git init", file=sys.stderr)
		return 1

	# Confirm the rewrite backend exists before warning or scanning.
	filter_repo_cmd = find_filter_repo()
	if filter_repo_cmd is None:
		print(tui.style("Error: git-filter-repo not found. Install it with:",
						fg="error", cap=cap),
			  file=sys.stderr)
		print("    pip install git-filter-repo", file=sys.stderr)
		return 1

	print(tui.key_values("SANITIZE PLAN", [
		("Repo", str(repo_root)),
		("Secret", "<redacted>"),
		("Placeholder", placeholder),
		("Backend", " ".join(filter_repo_cmd)),
	], cap=cap))

	# Warn about dirty trees; rewriting with uncommitted work risks losing it.
	r = run(["git", "status", "--porcelain"])
	if r.returncode == 0 and r.stdout.strip() and not args.yes:
		print(tui.style("WARNING: working tree has uncommitted changes. "
						"Commit or stash first.", fg="warn", cap=cap))
		ans = input("Continue anyway? [y/N] ").strip().lower()
		if ans not in ("y", "yes"):
			print("Aborted.")
			return 1
	print(tui.style("WARNING: this rewrites ALL history. Back up first and "
					"force-push afterwards.", fg="warn", cap=cap))
	if not args.yes:
		ans = input("Rewrite full history now? [y/N] ").strip().lower()
		if ans not in ("y", "yes"):
			print("Aborted.")
			return 1

	# Pre-check avoids a destructive no-op (filter-repo drops origin, expires
	# reflogs, GCs) paired with a misleading SUCCESS message.
	print(tui.style("Scanning history for secret...", fg="fg", cap=cap))
	if not secret_in_history(secret):
		print(tui.style("Secret not found in repo history. Nothing to do "
						"(exit 0).", fg="success", cap=cap))
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

	try:
		# Run the rewrite over both file contents and commit messages.
		cmd = filter_repo_cmd + [
			"--replace-text", replace_file,
			"--replace-message", replace_file,
			"--force",
		]
		print(tui.style(f"Running: {' '.join(cmd)}", fg="fg", cap=cap))
		p = subprocess.run(cmd)
		if p.returncode != 0:
			print(tui.style("git-filter-repo failed.", fg="error", cap=cap),
				  file=sys.stderr)
			return 1

		# Harden the rewrite: expire reflogs and prune unreachable objects so
		# no dangling copy of the secret survives (filter-repo already GCs).
		run(["git", "reflog", "expire", "--expire=now", "--all"])
		run(["git", "gc", "--prune=now", "--aggressive"])

		# filter-repo removes `origin` (and other remotes) by design; put them back.
		restored = restore_remotes(saved_remotes)
		if saved_remotes and restored:
			detail = ", ".join(
				n + " -> " + saved_remotes[n].get("fetch", "") for n in restored)
			print(tui.style(f"Restored remote(s): {detail}", fg="fg", cap=cap))
		elif saved_remotes:
			print(tui.style("Remotes already present, nothing to restore.",
							fg="fg", cap=cap))

		# Verify the secret is gone: searchable history plus a blob-by-blob scan.
		print(tui.style("Verifying rewrite...", fg="fg", cap=cap))
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
			print(tui.style("WARNING: secret string still found after rewrite!",
							fg="error", cap=cap), file=sys.stderr)
			print("The secret may exist in untracked files, tags, stash, or "
				  "filenames (use --path renames for filenames).", file=sys.stderr)
			if leaks:
				print(f"Leaking blob: {leaks[0]}", file=sys.stderr)
			return 1

		# Report success with the force-push / rotation steps that must follow.
		print(tui.style(f"SUCCESS: secret replaced with '{placeholder}' in full "
						f"history.", fg="success", bold=True, cap=cap))
		print(tui.key_values("NEXT STEPS", [
			("1. Force-push", "git push --force --all && git push --force --tags"),
			("2. Teammates", "Everyone else must re-clone"),
			("3. Rotation", "Rotate the leaked secret"),
		], cap=cap))
		return 0
	finally:
		# Always remove the temp replacement file; it contains the raw secret.
		Path(replace_file).unlink(missing_ok=True)


if __name__ == "__main__":
	sys.exit(main())
