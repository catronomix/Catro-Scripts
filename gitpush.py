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

def run(args):
	"""Run a command and raise on failure."""
	result = subprocess.run(args)
	if result.returncode != 0:
		raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}")
	return result


def main():
	# Entrypoint
	if len(sys.argv) != 2:
		print('Usage: gitpush "<commit message>"', file=sys.stderr)
		sys.exit(1)

	message = sys.argv[1]

	run(['git', 'add', '-A'])
	run(['git', 'commit', '-m', message])
	run(['git', 'push'])


if __name__ == "__main__":
	main()

