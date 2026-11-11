# Regression net for the retired cs.sh wrapper and the executable-EOL class
"""
		CS.SH RETIREMENT AND EXECUTABLE-EOL SWEEP
		=========================================
`cs.sh` was a stale, CRLF-saved copy of the LF dispatcher `cs`. It is untracked
and ignored, so `./cs.sh` failed with `bad interpreter: /bin/bash^M` on Linux
while every git check stayed green. This module pins the removal and, more
usefully, the class of bug behind it: any tracked executable (mode 100755) that
carries a CR byte in the worktree would break the same way.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import shutil
import subprocess
import unittest
from pathlib import Path

# The suite lives in <repo>/tests/, so the repository root is its parent.
REPO = Path(__file__).resolve().parents[1]

# git plumbing in a test should never hang on a credential or pager prompt.
GIT_TIMEOUT = 60

GIT = shutil.which("git")

# The two config files that used to special-case cs.sh by name.
CONFIG_FILES = (".gitignore", ".gitattributes")


def git(*args):
	"""Run git in the repo and return the completed process."""
	return subprocess.run(
		[GIT] + list(args),
		cwd=str(REPO),
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=GIT_TIMEOUT,
	)


def detail(proc):
	return "exit {}\nstdout:\n{}\nstderr:\n{}".format(
		proc.returncode,
		proc.stdout.decode("utf-8", "replace"),
		proc.stderr.decode("utf-8", "replace"),
	)


@unittest.skipUnless(GIT, "git is not on PATH")
class CsShRetiredTest(unittest.TestCase):
	"""cs.sh must be gone, unignored, and untracked."""

	def test_cs_sh_absent_from_worktree(self):
		"""A leftover cs.sh on disk is what produced the CRLF interpreter."""
		self.assertFalse((REPO / "cs.sh").exists(),
						 "cs.sh is back on disk; the stale CRLF copy must not exist")

	def test_cs_sh_not_tracked(self):
		"""Nothing may track a .sh twin of the dispatcher."""
		proc = git("ls-files", "cs.sh")
		self.assertEqual(proc.returncode, 0,
						 "git ls-files cs.sh failed\n{}".format(detail(proc)))
		self.assertEqual(proc.stdout.strip(), b"",
						 "cs.sh is tracked again: {}".format(
							 proc.stdout.decode("utf-8", "replace").strip()))

	def test_cs_sh_not_ignored(self):
		"""A name-based ignore hid the artifact; it must not come back."""
		proc = git("check-ignore", "-q", "cs.sh")
		self.assertEqual(proc.returncode, 1,
						 "cs.sh is still ignored (or git failed)\n{}".format(detail(proc)))

	def test_no_cs_sh_entry_in_config(self):
		"""The EOL net must cover the class, not this one filename."""
		for name in CONFIG_FILES:
			lines = (REPO / name).read_text(encoding="utf-8").splitlines()
			hits = [line for line in lines
					if line.split("#", 1)[0].strip().split()[:1] == ["cs.sh"]]
			self.assertEqual(hits, [],
							 "{} still special-cases cs.sh: {}".format(name, hits))


@unittest.skipUnless(GIT, "git is not on PATH")
class ExecutableEolTest(unittest.TestCase):
	"""Every tracked executable must be free of CR bytes."""

	def test_tracked_executables_have_no_cr(self):
		"""A CR in a 100755 file breaks the shebang on Linux."""
		proc = git("ls-files", "-s", "-z")
		self.assertEqual(proc.returncode, 0,
						 "git ls-files -s failed\n{}".format(detail(proc)))
		executables = []
		for entry in proc.stdout.split(b"\0"):
			if not entry.strip():
				continue
			meta, _, path = entry.partition(b"\t")
			if meta.split()[:1] == [b"100755"]:
				executables.append(path.decode("utf-8", "surrogateescape"))
		# An empty sweep would pass vacuously: the dispatcher is always 100755.
		self.assertTrue(executables,
						"no mode-100755 entries found; the EOL sweep is blind")
		for path in executables:
			with self.subTest(path=path):
				data = (REPO / path).read_bytes()
				self.assertNotIn(b"\r", data,
								 "{} is executable and contains a CR byte; "
								 "the kernel will refuse its shebang".format(path))


if __name__ == "__main__":
	unittest.main()
