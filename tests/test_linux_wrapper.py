# POSIX wrapper behavior: symlink installs and case-insensitive script names
"""
		LINUX WRAPPER REGRESSION SUITE
		==============================
Covers the two Linux-only wrapper behaviors that Windows cannot reproduce:
`catro-scripts.sh` (and `cs`, and the `.sh` alias) resolving itself through a
symlink chain before locating the scripts, and a case-insensitive script-name
fallback on a case-sensitive filesystem.

Both tests skip with an explicit reason when the host cannot exercise them:
a platform without `os.symlink`, a host without bash, or a case-insensitive
volume (Windows, macOS default) where `LIST.PY` already resolves to `list.py`.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "catro-scripts.sh"
TIMEOUT = 60
# Piped `list` output is one TAB-separated record per line (the tui contract's
# plain mode), so the header line - not a box glyph - proves the wrapper
# reached list.py.
LIST_HEADER = "ID\tScript Name\tSize\tDescription"


def bash():
	"""Absolute path to a bash that actually runs, or None.

	On Windows `shutil.which("bash")` can return the WSL stub from
	System32, which fails when no WSL distribution is installed, so every
	candidate is probed with a trivial command instead of trusted by name.
	"""
	candidates = [
		shutil.which("bash"),
		r"C:\Program Files\Git\bin\bash.exe",
		r"C:\Program Files\Git\usr\bin\bash.exe",
		"/bin/bash",
	]
	for path in candidates:
		if not path or not os.path.isfile(path):
			continue
		try:
			probe = subprocess.run([path, "-c", "exit 0"],
								   stdin=subprocess.DEVNULL,
								   stdout=subprocess.PIPE,
								   stderr=subprocess.PIPE,
								   timeout=TIMEOUT)
		except OSError:
			continue
		if probe.returncode == 0:
			return path
	return None


def run(args, cwd=None):
	"""Run a child with bounded time, captured bytes, and no stdin."""
	return subprocess.run(
		args,
		cwd=str(cwd if cwd is not None else REPO),
		stdin=subprocess.DEVNULL,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=TIMEOUT,
	)


def text(raw):
	return raw.decode("utf-8", "replace")


def detail(proc):
	return (text(proc.stderr).strip() or text(proc.stdout).strip())[-1200:]


class SymlinkInstallTest(unittest.TestCase):
	"""A symlinked wrapper must look for scripts next to the real file."""

	def setUp(self):
		if bash() is None:
			self.skipTest("bash is not on PATH")
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.dir = Path(self.tmp.name)

	def link(self, name, target):
		"""Create one symlink, skipping the test if the OS refuses."""
		path = self.dir / name
		try:
			os.symlink(str(target), str(path))
		except (OSError, NotImplementedError) as exc:
			self.skipTest("os.symlink is unavailable: {}".format(exc))
		return path

	def test_wrapper_finds_scripts_through_a_two_hop_chain(self):
		"""link2 -> link1 -> real wrapper, invoked from a temp cwd."""
		first = self.link("cs-link", WRAPPER)
		second = self.link("cs-link-2", first.name)  # relative target
		proc = run([bash(), str(second), "list"], cwd=self.dir)
		self.assertEqual(proc.returncode, 0,
						 "symlinked wrapper exited {}\n{}".format(
							 proc.returncode, detail(proc)))
		out = proc.stdout.decode("utf-8")
		self.assertIn(LIST_HEADER, out,
					  "the symlinked wrapper did not reach list.py:\n" + out[:400])

	def test_cs_dispatcher_through_a_symlink(self):
		"""A symlinked `cs` must still find its catro-scripts.sh sibling."""
		link = self.link("cs-alias", REPO / "cs")
		proc = run([bash(), str(link), "list"], cwd=self.dir)
		self.assertEqual(proc.returncode, 0,
						 "symlinked cs exited {}\n{}".format(
							 proc.returncode, detail(proc)))
		self.assertIn(LIST_HEADER, proc.stdout.decode("utf-8"),
					  "the symlinked cs did not reach catro-scripts.sh:\n" + detail(proc))


class CaseInsensitiveLookupTest(unittest.TestCase):
	"""Typed case must not decide whether a script runs."""

	def setUp(self):
		if bash() is None:
			self.skipTest("bash is not on PATH")
		# The fallback only exists because the filesystem says no. Where the
		# volume folds case, the exact-match path already works and there is
		# nothing to test.
		if os.path.exists(str(REPO / "LIST.PY")):
			self.skipTest("case-insensitive volume: LIST.PY resolves to list.py")

	def test_wrong_case_runs_the_script_and_notes_the_match(self):
		correct = run([bash(), str(WRAPPER), "list"])
		typed = run([bash(), str(WRAPPER), "List"])
		self.assertEqual(typed.returncode, 0,
						 "wrapper List exited {}\n{}".format(
							 typed.returncode, detail(typed)))
		self.assertEqual(typed.stdout, correct.stdout,
						 "wrapper List did not run list.py\n" + detail(typed))
		self.assertIn('note: "List" matched "list"', text(typed.stderr),
					  "wrapper List gave no match note:\n" + text(typed.stderr))
		# The exact-case invocation must stay silent about matching.
		self.assertNotIn("note:", text(correct.stderr),
						 "wrapper list emitted a note:\n" + text(correct.stderr))

	def test_exact_case_message_is_unchanged(self):
		"""A real miss keeps today's wording and exit code."""
		proc = run([bash(), str(WRAPPER), "nosuchscript"])
		both = text(proc.stdout) + text(proc.stderr)
		self.assertEqual(proc.returncode, 1,
						 "missing script exited {}\n{}".format(proc.returncode, both))
		self.assertIn('Error: Script "nosuchscript.py" not found in', both,
					  "missing-script message changed:\n" + both)

	def test_ambiguous_case_is_an_error(self):
		"""Two case variants: refuse instead of guessing, and list both."""
		with tempfile.TemporaryDirectory() as td:
			target = Path(td)
			shutil.copy2(str(WRAPPER), str(target / "catro-scripts.sh"))
			alpha = target / "Alpha.py"
			alpha.write_text("print('Alpha')\n", encoding="utf-8")
			lower = target / "alpha.py"
			if lower.exists() and os.path.samefile(str(alpha), str(lower)):
				self.skipTest("case-insensitive volume: cannot create two variants")
			lower.write_text("print('alpha')\n", encoding="utf-8")
			proc = run([bash(), str(target / "catro-scripts.sh"), "ALPHA"],
					   cwd=target)
			both = text(proc.stdout) + text(proc.stderr)
			self.assertEqual(proc.returncode, 1,
							 "ambiguous name exited {}\n{}".format(
								 proc.returncode, both))
			self.assertIn("more than one script", both,
						  "no ambiguity error:\n" + both)
			self.assertIn("Alpha.py", both, "candidate list is incomplete:\n" + both)
			self.assertIn("alpha.py", both, "candidate list is incomplete:\n" + both)


if __name__ == "__main__":
	unittest.main()
