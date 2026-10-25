# Cross-platform smoke tests for the catro-scripts wrapper collection
"""
		CROSS-PLATFORM SMOKE SUITE
		==========================
Stdlib-only regression net for the whole repository. Every test drives the real
scripts through `sys.executable` (never the ambient "python") so the suite is
portable and independent of whichever interpreter launched it.

Rules this suite keeps:
	- The repository root is derived from this file, so the suite runs from any
	  working directory.
	- Child processes get a bytecode cache outside the repository
	  (PYTHONPYCACHEPREFIX), so a run does not litter the tree it tests.
	- Every child process is bounded by a timeout and gets stdin=DEVNULL unless
	  the test is specifically about interactive behavior.
	- Missing platform tooling produces a skip with an explicit reason, never a
	  silent pass or a fake green.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# The suite lives in <repo>/tests/, so the repository root is the parent of the
# directory holding this file. Resolving it from __file__ keeps the suite
# cwd-independent (see the "run from a different cwd" check in the task spec).
REPO = Path(__file__).resolve().parents[1]

# No single smoke run should ever take longer than this.
TIMEOUT = 60

# A box-drawing horizontal line, the visible proof that the coloured table
# survived the trip through the wrapper as UTF-8.
BOX_HORIZONTAL = "\u2500"

# Minimum plausible table size for `list` output; a wrapper that swallows or
# mangles the table falls well below this.
MIN_LIST_OUTPUT = 8000

# Scripts that must refuse a non-interactive terminal with exit code 2.
TTY_SCRIPTS = (
	"keygen.py",
	"screensaver.py",
	"mdreader.py",
	"jsonl_monitor.py",
	"image_generator.py",
	"image_resizer.py",
	"ts_setup.py",
)

# Matches either quoting style of the __main__ guard; a source-scan test that
# only knew double quotes would silently skip scripts.
MAIN_GUARD = re.compile(r"""if\s+__name__\s*==\s*['"]__main__['"]""")

# Bytecode cache shared by every child process, created once per run and
# removed afterwards. Keeping it outside the repo means `git status` stays
# clean and the tests never write into the tree under test.
_pycache_dir = None


def setUpModule():
	global _pycache_dir
	_pycache_dir = tempfile.TemporaryDirectory(prefix="cs-smoke-pycache-")


def tearDownModule():
	if _pycache_dir is not None:
		_pycache_dir.cleanup()


def child_env(**overrides):
	"""Environment for a child process, with the out-of-tree bytecode cache."""
	env = dict(os.environ)
	if _pycache_dir is not None:
		env["PYTHONPYCACHEPREFIX"] = _pycache_dir.name
	env.update(overrides)
	return env


def run(args, cwd=None, env=None, stdin=subprocess.DEVNULL, timeout=TIMEOUT):
	"""Run a child process with bounded time and captured bytes.

	`args` is a list for normal invocations, or a full command-line string when
	a test needs to hand cmd.exe an exactly-quoted line.
	"""
	return subprocess.run(
		args,
		cwd=str(cwd if cwd is not None else REPO),
		env=env if env is not None else child_env(),
		stdin=stdin,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=timeout,
	)


def text(raw):
	"""Decode captured output without ever raising on odd bytes."""
	return raw.decode("utf-8", "replace")


def scripts():
	"""Every top-level Python script, sorted for deterministic reporting."""
	return sorted(REPO.glob("*.py"))


def source(path):
	return path.read_text(encoding="utf-8", errors="replace")


def failure_detail(proc):
	"""Compact one-line diagnosis for an assertion message."""
	detail = text(proc.stderr).strip() or text(proc.stdout).strip()
	return detail[-1200:]


def wrapper_command(argv):
	"""Build an invocation of the OS wrapper that keeps argv intact.

	POSIX: bash receives the argument vector directly, so metacharacters and
	argument counts are the shell's problem, not ours.

	Windows: cmd.exe is used, and its command line is passed as one string.
	cmd strips the single outermost pair of quotes after `/c`, so the whole
	line is shaped as `""<bat>" <quoted args>"`: the inner pair keeps the batch
	path quoted (it contains no spaces here, but the form stays correct for
	paths that do), and the outer pair stops the first token from losing its
	quotes. Every argument is quoted individually so `&`, `|`, `(` and `)`
	inside a token reach Python as one literal argument instead of splitting
	the command. This is exactly the `cmd /c ""prog" args"` convention.
	"""
	if os.name == "nt":
		quoted = " ".join('"{}"'.format(arg) for arg in argv)
		return 'cmd /d /c ""{}" {}"'.format(REPO / "catro-scripts.bat", quoted)
	return [shutil.which("bash"), str(REPO / "catro-scripts.sh")] + list(argv)


class SmokeTests(unittest.TestCase):
	"""One test per historical breakage; names are part of the contract."""

	def test_all_scripts_compile(self):
		"""Every file must at least parse under the baseline interpreter."""
		with tempfile.TemporaryDirectory() as td:
			proc = run([sys.executable, "-m", "compileall", "-q", str(REPO)], cwd=td)
		self.assertEqual(proc.returncode, 0,
						 "compileall failed:\n{}".format(failure_detail(proc)))

	def test_modules_import(self):
		"""Top-level modules must import cleanly (no side effects at import)."""
		failures = []
		for path in scripts():
			# mdreader.py may pip-install windows-curses on import; the suite
			# must never install packages, so it is covered by the --help and
			# tty tests instead.
			if path.name == "mdreader.py":
				continue
			proc = run([sys.executable, "-c", "import " + path.stem], cwd=REPO)
			if proc.returncode != 0:
				failures.append("{} (rc={}): {}".format(
					path.name, proc.returncode, text(proc.stderr).strip()[-800:]))
		self.assertEqual(failures, [], "modules failed to import:\n" +
						 "\n".join(failures))

	def test_argparse_help(self):
		"""`--help` must work for every argparse script, interactive or not."""
		candidates = [
			path for path in scripts()
			if "argparse.ArgumentParser" in source(path) and MAIN_GUARD.search(source(path))
		]
		names = {path.name for path in candidates}
		# Guard against a vacuous pass if the source scan ever stops matching.
		self.assertIn("sanitize.py", names,
					  "sanitize.py has argparse but was not detected")
		self.assertGreaterEqual(len(names), 10,
								"argparse discovery collapsed: {}".format(sorted(names)))
		for path in candidates:
			with self.subTest(script=path.name), tempfile.TemporaryDirectory() as td:
				# Run outside the repo: --help must not depend on the cwd.
				proc = run([sys.executable, str(path), "--help"], cwd=td)
				both = (text(proc.stdout) + text(proc.stderr)).lower()
				self.assertEqual(proc.returncode, 0,
								 "{} --help exited {}\n{}".format(
									 path.name, proc.returncode, failure_detail(proc)))
				self.assertIn("usage:", both,
							  "{} --help printed no usage line:\n{}".format(
								  path.name, failure_detail(proc)))

	def test_tty_preflight_exit_2(self):
		"""Interactive tools must refuse a piped stdin instead of crashing."""
		for name in TTY_SCRIPTS:
			with self.subTest(script=name):
				if name == "mdreader.py":
					# mdreader imports curses + rich and tries to pip-install a
					# missing one, which hangs in an offline container: only
					# exercise it where both are already importable.
					probe = run([sys.executable, "-c", "import curses, rich"])
					if probe.returncode != 0:
						self.skipTest("mdreader.py needs curses and rich: " +
									  failure_detail(probe))
				proc = run([sys.executable, str(REPO / name)])
				stderr = text(proc.stderr)
				self.assertEqual(proc.stdout, b"",
								 "{} wrote to stdout before refusing: {!r}".format(
									 name, proc.stdout[:200]))
				self.assertEqual(proc.returncode, 2,
								 "{} exited {}, expected 2\n{}".format(
									 name, proc.returncode, stderr[-1200:]))
				self.assertIn("interactive terminal", stderr,
							  "{} gave no preflight message:\n{}".format(name, stderr[-1200:]))
				self.assertNotIn("Traceback", stderr,
								 "{} crashed instead of refusing:\n{}".format(name, stderr[-1200:]))

	def test_list_encode_failure_is_not_silent(self):
		"""A UnicodeEncodeError in list.py must reach the caller as a non-zero rc."""
		# Regression guard: the table used to die silently with exit 0, so the
		# wrapper looked healthy while printing nothing.
		env = child_env(PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
		proc = run([sys.executable, str(REPO / "list.py")], env=env)
		self.assertNotEqual(proc.returncode, 0,
							"list.py exited 0 after failing to encode its table:\n{}".format(
								failure_detail(proc)))

	def test_wrapper_list_is_utf8(self):
		"""The wrapper must force UTF-8 so the table survives a pipe."""
		if os.name != "nt" and shutil.which("bash") is None:
			self.skipTest("bash is not on PATH")
		with tempfile.TemporaryDirectory() as td:
			# cwd stays a temp dir: list.py scans the script directory anyway,
			# and this guarantees the test cannot touch the repository.
			proc = run(wrapper_command(["list"]), cwd=td)
			self.assertEqual(proc.returncode, 0,
							 "wrapper list exited {}\n{}".format(
								 proc.returncode, failure_detail(proc)))
			# decode() raises if the wrapper emitted anything but valid UTF-8.
			out = proc.stdout.decode("utf-8")
			self.assertGreater(len(out), MIN_LIST_OUTPUT,
							   "wrapper list output was only {} chars\n{}".format(
								   len(out), out[:400]))
			self.assertIn(BOX_HORIZONTAL, out,
						  "wrapper list output lost its box-drawing characters")

	def test_wrapper_keeps_many_and_metachar_args(self):
		"""More than nine arguments and shell metacharacters must pass through."""
		if os.name != "nt" and shutil.which("bash") is None:
			self.skipTest("bash is not on PATH")
		names = ["d{}".format(i) for i in range(1, 12)]
		with tempfile.TemporaryDirectory() as td:
			argv = ["newfile"]
			for name in names:
				argv += ["-d", name]
			proc = run(wrapper_command(argv), cwd=td)
			self.assertEqual(proc.returncode, 0,
							 "wrapper newfile exited {}\n{}".format(
								 proc.returncode, failure_detail(proc)))
			# newfile treats each -d as "create this directory and descend", so
			# the eleven names must exist as a nested chain.
			current = Path(td)
			for name in names:
				current = current / name
				self.assertTrue(current.is_dir(),
								"missing directory {} (wrapper dropped arguments)".format(name))
		with tempfile.TemporaryDirectory() as td:
			# One token containing cmd's command separator: if the wrapper lets
			# cmd re-parse it, the directory is never created.
			proc = run(wrapper_command(["newfile", "-d", "a&b"]), cwd=td)
			self.assertEqual(proc.returncode, 0,
							 "wrapper newfile -d a&b exited {}\n{}".format(
								 proc.returncode, failure_detail(proc)))
			self.assertTrue((Path(td) / "a&b").is_dir(),
							"the single token 'a&b' was split or dropped")

	@unittest.skipUnless(shutil.which("git"), "git is not on PATH")
	def test_cs_index_is_lf(self):
		"""The extension-less dispatcher must stay LF in the index."""
		proc = run(["git", "show", ":cs"], cwd=REPO)
		self.assertEqual(proc.returncode, 0,
						 "git show :cs failed\n{}".format(failure_detail(proc)))
		self.assertNotIn(b"\r\n", proc.stdout,
						 "cs is stored with CRLF; bash will choke on the shebang")
		self.assertTrue(proc.stdout.startswith(b"#!"),
						"cs does not start with a shebang: {!r}".format(proc.stdout[:60]))
		eol = run(["git", "ls-files", "--eol", "cs"], cwd=REPO)
		self.assertEqual(eol.returncode, 0,
						 "git ls-files --eol cs failed\n{}".format(failure_detail(eol)))
		self.assertIn("i/lf", text(eol.stdout),
					  "git does not track cs as LF: {}".format(text(eol.stdout).strip()))

	def test_alias_writes_native_eols(self):
		"""alias.py must emit CRLF for .bat and LF for .sh."""
		with tempfile.TemporaryDirectory() as td:
			target = Path(td)
			# alias.py writes next to itself, so run a copy from a temp dir to
			# keep the repository untouched.
			shutil.copy2(str(REPO / "alias.py"), str(target / "alias.py"))
			proc = run([sys.executable, "alias.py", "smokealias"], cwd=td)
			self.assertEqual(proc.returncode, 0,
							 "alias.py exited {}\n{}".format(
								 proc.returncode, failure_detail(proc)))
			# The alias name lives in the file name: both wrappers are generic
			# dispatchers whose body only points at catro-scripts, so asserting
			# the name inside the body would test a behavior the script never
			# had. Name-in-path plus dispatcher target is what actually breaks.
			bat_path = target / "smokealias.bat"
			sh_path = target / "smokealias.sh"
			self.assertTrue(bat_path.is_file(), "alias.py created no smokealias.bat")
			self.assertTrue(sh_path.is_file(), "alias.py created no smokealias.sh")
			bat = bat_path.read_bytes()
			sh = sh_path.read_bytes()
			self.assertIn(b"\r\n", bat, "the .bat alias has no CRLF line endings")
			self.assertNotIn(b"\n", bat.replace(b"\r\n", b""),
							 "the .bat alias has a bare LF line ending")
			self.assertNotIn(b"\r", sh, "the .sh alias has CR line endings")
			self.assertIn(b"catro-scripts", bat, "the .bat alias does not call the dispatcher")
			self.assertIn(b"catro-scripts", sh, "the .sh alias does not call the dispatcher")

	def test_docs_match_repo(self):
		"""README must describe the repo as it is, not as it used to be."""
		readme = text((REPO / "README.md").read_bytes())
		lowered = readme.lower()
		self.assertNotIn("extractframe", lowered,
						 "README still documents the removed extractframe script")
		self.assertIn("3.11", readme, "README no longer states the 3.11+ baseline")
		self.assertIn("`action`", readme, "README does not document the action macro runner")
		self.assertTrue((REPO / "keygen.py").is_file(), "keygen.py is missing")
		self.assertIn("`keygen`", readme, "README has no keygen bullet")

	def test_exifcopy_missing_dependency_is_friendly(self):
		"""exifcopy must name the missing piexif and still show its usage text."""
		with tempfile.TemporaryDirectory() as td:
			# Simulate a machine without a working piexif: a module on PYTHONPATH
			# that raises on import, which shadows any real installation.
			(Path(td) / "piexif.py").write_text('raise ImportError("simulated")\n',
												encoding="utf-8")
			env = child_env(PYTHONPATH=str(Path(td)))

			# A real run: two arguments so the usage guard passes and the copy
			# path is the one that discovers the missing dependency.
			proc = run([sys.executable, str(REPO / "exifcopy.py"),
						"missing_src.jpg", "missing_dst.jpg"], env=env)
			both = text(proc.stdout) + text(proc.stderr)
			self.assertEqual(proc.returncode, 1,
							 "exifcopy exited {} without piexif\n{}".format(
								 proc.returncode, both[-1200:]))
			self.assertIn("'piexif' library is not installed", both,
						  "exifcopy gave no friendly message:\n{}".format(both[-1200:]))
			self.assertIn("-m pip install piexif", both,
						  "exifcopy printed no install hint:\n{}".format(both[-1200:]))
			self.assertNotIn("Traceback", both,
							 "exifcopy crashed instead of reporting:\n{}".format(both[-1200:]))

			# The usage path must never require the dependency.
			proc = run([sys.executable, str(REPO / "exifcopy.py")], env=env)
			both = text(proc.stdout) + text(proc.stderr)
			self.assertIn("Usage:", both,
						  "exifcopy lost its usage text without piexif:\n{}".format(both[-1200:]))
			self.assertNotIn("Traceback", both,
							 "exifcopy crashed on the usage path:\n{}".format(both[-1200:]))


if __name__ == "__main__":
	unittest.main()
