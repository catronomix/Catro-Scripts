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

import os
import sys
import subprocess
import platform

# ANSI color codes
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

def colorize(text, color):
    """Wrap text with ANSI color codes if stdout is a TTY."""
    if sys.stdout.isatty():
        return f"{color}{text}{C.RESET}"
    return text

def init_ansi():
    # Enables ANSI escape sequences on Windows 10+ consoles.
    if platform.system().lower() == "windows":
        os.system("color")

def run(args, check=True):
	"""Run a command and raise on failure unless check is False."""
	result = subprocess.run(args)
	if check and result.returncode != 0:
		raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}")
	return result


def main():
	# Entrypoint
	if len(sys.argv) != 2:
		print(colorize('Usage: gitpush "<commit message>"', C.RED), file=sys.stderr)
		sys.exit(1)

	message = sys.argv[1]

	print(colorize(f"→ Staging all changes...", C.CYAN))
	run(['git', 'add', '-A'])
	# Commit only if there is something to commit; otherwise proceed to push.
	print(colorize(f"→ Committing: {message}", C.CYAN))
	commit_result = run(['git', 'commit', '-m', message], check=False)
	if commit_result.returncode != 0:
		# Check whether the working tree is clean (nothing to commit).
		status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
		if status.stdout.strip() == '':
			print(colorize('  Nothing to commit; skipping commit.', C.YELLOW))
		else:
			raise RuntimeError(f"Commit failed ({commit_result.returncode}): git commit -m {message}")

	# If origin is ahead, pull with rebase before pushing to avoid non-fast-forward rejection.
	print(colorize("→ Pushing to origin...", C.CYAN))
	push_result = run(['git', 'push'], check=False)
	if push_result.returncode != 0:
		print(colorize('  Push failed; attempting pull --rebase then retrying push...', C.YELLOW))
		run(['git', 'pull', '--rebase'])
		run(['git', 'push'])

	print(colorize("✓ Done.", C.GREEN))


if __name__ == "__main__":
	main()

