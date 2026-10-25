# Quickly push changes to git repo
"""
						GIT ADD-COMMIT-PUSH
						==========================
This script provides a shorthand for pushing changes in a git repo to the origin in one line

It takes the commit message as a single argument and:
	- stages all changes
	- commits the changes with the provided message
	- pushes to the origin.

Usage:
	catro-scripts gitpush "<commit message>"

Requirements: none
"""

import sys
import subprocess

import tui


def run(args, check=True):
	"""Run a command and raise on failure unless check is False."""
	result = subprocess.run(args)
	if check and result.returncode != 0:
		raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}")
	return result


def main():
	# One detection per run: the colour level, Unicode decision and plain mode
	# stay fixed for every line this script prints.
	cap = tui.detect()

	# Entrypoint
	if len(sys.argv) != 2:
		print(tui.style('Usage: gitpush "<commit message>"', fg="error", cap=cap),
			  file=sys.stderr)
		sys.exit(1)

	message = sys.argv[1]

	print(tui.style("→ Staging all changes...", fg="accent", cap=cap))
	run(['git', 'add', '-A'])
	# Commit only if there is something to commit; otherwise proceed to push.
	print(tui.style(f"→ Committing: {message}", fg="accent", cap=cap))
	commit_result = run(['git', 'commit', '-m', message], check=False)
	if commit_result.returncode != 0:
		# Check whether the working tree is clean (nothing to commit).
		status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
		if status.stdout.strip() == '':
			print(tui.style('  Nothing to commit; skipping commit.', fg="warn", cap=cap))
		else:
			raise RuntimeError(f"Commit failed ({commit_result.returncode}): git commit -m {message}")

	# If origin is ahead, pull with rebase before pushing to avoid non-fast-forward rejection.
	print(tui.style("→ Pushing to origin...", fg="accent", cap=cap))
	push_result = run(['git', 'push'], check=False)
	if push_result.returncode != 0:
		print(tui.style('  Push failed; attempting pull --rebase then retrying push...',
						fg="warn", cap=cap))
		run(['git', 'pull', '--rebase'])
		run(['git', 'push'])

	print(tui.style("✓ Done.", fg="success", cap=cap))


if __name__ == "__main__":
	tui.init_ansi()
	main()

