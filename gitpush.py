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

def run(args, check=True):
	"""Run a command and raise on failure unless check is False."""
	result = subprocess.run(args)
	if check and result.returncode != 0:
		raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}")
	return result


def main():
	# Entrypoint
	if len(sys.argv) != 2:
		print('Usage: gitpush "<commit message>"', file=sys.stderr)
		sys.exit(1)

	message = sys.argv[1]

	run(['git', 'add', '-A'])
	# Commit only if there is something to commit; otherwise proceed to push.
	commit_result = run(['git', 'commit', '-m', message], check=False)
	if commit_result.returncode != 0:
		# Check whether the working tree is clean (nothing to commit).
		status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
		if status.stdout.strip() == '':
			print('Nothing to commit; skipping commit.')
		else:
			raise RuntimeError(f"Commit failed ({commit_result.returncode}): git commit -m {message}")

	# If origin is ahead, pull with rebase before pushing to avoid non-fast-forward rejection.
	push_result = run(['git', 'push'], check=False)
	if push_result.returncode != 0:
		print('Push failed; attempting pull --rebase then retrying push...')
		run(['git', 'pull', '--rebase'])
		run(['git', 'push'])


if __name__ == "__main__":
	main()

