# Regression tests for output going into a pipe
"""
			CLI PIPE / OUTPUT REGRESSION TESTS
			==================================
Covers issue #14: when the downstream reader goes away (e.g. `list | head`),
the producer must exit 0 without a traceback, a `BrokenPipeError` message or a
shutdown-flush `Exception ignored in: <_io.TextIOWrapper ...>`.

Also pins the two neighbouring output paths so the pipe guard cannot hide them:
a genuine scan error still exits 1, and an encoding failure still exits
non-zero.

Run with:
	python -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# (script, argv tail) for every command that prints a table.
PIPE_CASES = [
	("list.py", []),
	("count.py", ["."]),
	("help.py", ["list"]),
	("action.py", ["list"]),
]


def child_env(**overrides):
	"""Copy of the environment with output-related variables normalised."""
	env = dict(os.environ)
	for key in ("PYTHONUNBUFFERED", "PYTHONIOENCODING", "PYTHONUTF8"):
		env.pop(key, None)
	# The tables use box-drawing characters; a cp1252 console codepage would
	# turn these into UnicodeEncodeError, which is a different bug.
	env["PYTHONIOENCODING"] = "utf-8"
	env.update(overrides)
	return env


def run_script(script, args, env):
	return subprocess.run(
		[sys.executable, str(REPO / script), *args],
		cwd=str(REPO),
		env=env,
		stdin=subprocess.DEVNULL,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)


class ClosedPipeTests(unittest.TestCase):
	"""A reader that stops early must silence the producer, exit code 0."""

	def assert_quiet_pipe(self, script, args, unbuffered):
		env = child_env()
		if unbuffered:
			env["PYTHONUNBUFFERED"] = "1"

		proc = subprocess.Popen(
			[sys.executable, str(REPO / script), *args],
			cwd=str(REPO),
			env=env,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
		)
		# Let the producer start writing, then drop the read end like `head -1`.
		proc.stdout.read(200)
		proc.stdout.close()
		stderr = proc.stderr.read()
		proc.stderr.close()
		rc = proc.wait()

		label = f"{script} {' '.join(args)} ({'unbuffered' if unbuffered else 'buffered'})"

		if os.name == "nt" and b"Errno 22" in stderr:
			# Windows reports a closed read end as EINVAL instead of EPIPE, so
			# the BrokenPipeError guard cannot be exercised here. Linux is the
			# oracle for this case; this is a skip, not a silent pass.
			self.skipTest(f"closed read end surfaces as OSError [Errno 22] on Windows: {label}")

		self.assertEqual(rc, 0, f"{label}: exit code {rc}, stderr={stderr!r}")
		self.assertEqual(stderr, b"", f"{label}: stderr not empty")
		self.assertNotIn(b"Traceback", stderr, f"{label}: traceback leaked")
		self.assertNotIn(b"BrokenPipeError", stderr, f"{label}: BrokenPipeError leaked")
		self.assertNotIn(b"Exception ignored", stderr, f"{label}: shutdown flush raised")

	def test_closed_pipe_unbuffered(self):
		for script, args in PIPE_CASES:
			with self.subTest(script=script, args=args):
				self.assert_quiet_pipe(script, args, unbuffered=True)

	def test_closed_pipe_buffered(self):
		# Without PYTHONUNBUFFERED the write failure appears during the final
		# flush; the entrypoint must still exit 0 (not rc 120).
		for script, args in PIPE_CASES:
			with self.subTest(script=script, args=args):
				self.assert_quiet_pipe(script, args, unbuffered=False)


class BrokenPipeGuardTests(unittest.TestCase):
	"""Entrypoint guard, exercised even where a real pipe close is not EPIPE.

	Windows maps a closed read end to OSError [Errno 22], so the real-pipe
	tests above skip there; this test injects BrokenPipeError through stdout
	and runs the script's __main__ block, which is platform independent.
	"""

	GUARD_CODE = (
		"import runpy, sys\n"
		"class DeadPipe:\n"
		"    def __init__(self, real):\n"
		"        self._real = real\n"
		"    def write(self, data):\n"
		"        raise BrokenPipeError(32, 'Broken pipe')\n"
		"    def flush(self):\n"
		"        raise BrokenPipeError(32, 'Broken pipe')\n"
		"    def __getattr__(self, name):\n"
		"        return getattr(self._real, name)\n"
		"real = sys.stdout\n"
		"sys.stdout = DeadPipe(real)\n"
		"try:\n"
		"    runpy.run_path(sys.argv[1], run_name='__main__')\n"
		"finally:\n"
		"    sys.stdout = real\n"
	)

	def test_entrypoint_guard_exits_0_on_broken_pipe(self):
		for script, args in PIPE_CASES:
			with self.subTest(script=script, args=args):
				result = subprocess.run(
					[sys.executable, "-c", self.GUARD_CODE, str(REPO / script)],
					cwd=str(REPO),
					env=child_env(),
					stdin=subprocess.DEVNULL,
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE,
				)
				self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
				self.assertNotIn(b"Traceback", result.stderr)
				self.assertNotIn(b"BrokenPipeError", result.stderr)


class UnpipedOutputTests(unittest.TestCase):
	"""Normal runs are unchanged: full table, exit code 0."""

	def test_unpiped_runs_unchanged(self):
		for script, args in PIPE_CASES:
			with self.subTest(script=script, args=args):
				result = run_script(script, args, child_env())
				self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
				self.assertTrue(result.stdout.strip(), "no output produced")
				self.assertNotIn(b"Traceback", result.stderr)

	def test_list_reports_total(self):
		result = run_script("list.py", [], child_env())
		self.assertEqual(result.returncode, 0)
		self.assertIn("Total scripts found:", result.stdout.decode("utf-8", "replace"))


class NonPipeFailureTests(unittest.TestCase):
	"""The pipe guard must not swallow real failures."""

	def test_scan_error_still_exits_1(self):
		code = (
			"import importlib.util, os, sys\n"
			"spec = importlib.util.spec_from_file_location('listmod', sys.argv[1])\n"
			"mod = importlib.util.module_from_spec(spec)\n"
			"spec.loader.exec_module(mod)\n"
			"def boom(_path):\n"
			"    raise OSError('simulated scan failure')\n"
			"os.listdir = boom\n"
			"mod.list_scripts()\n"
		)
		result = subprocess.run(
			[sys.executable, "-c", code, str(REPO / "list.py")],
			cwd=str(REPO),
			env=child_env(PYTHONIOENCODING="utf-8"),
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
		)
		self.assertEqual(result.returncode, 1, result.stderr.decode("utf-8", "replace"))
		self.assertIn("Error scanning directory:", result.stdout.decode("utf-8", "replace"))

	def test_encode_failure_is_not_silent(self):
		# Box-drawing characters cannot be encoded as cp1252 -> rc must be
		# non-zero; an encode problem is not a dead reader.
		result = run_script(
			"list.py", [], child_env(PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
		)
		self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
	unittest.main()
