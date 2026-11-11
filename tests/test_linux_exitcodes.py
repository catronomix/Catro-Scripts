# Regression net for the exit codes the Linux oracle depends on
"""
		EXIT-CODE REGRESSION NET
		========================
Scripts that printed an error and then `return`ed made Python exit 0, and the
container oracle mapped `rc == 0` to PASS, so the audit baseline was green over
real failures (tracker #19). This file pins both halves of that fix:

	1. the reporter scripts exit non-zero on their error paths, with the message
	   text unchanged;
	2. `tests/container/checks.py` classifies `rc == 0` + an error line as
	   `FAIL:silent`, while USAGE/DEP stay reachable for `rc == 0`.

The dependency stubs are deliberate: the exit code must not depend on whether
`piexif`/`pydub`/`ffmpeg` happen to be installed on the host running the suite,
so the third-party modules are shadowed by tiny modules on PYTHONPATH and the
`check_ffmpeg()` boundary is patched. The real libraries are exercised by the
container extras probe, not here.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 60

# A piexif stand-in whose single write operation fails, which drives
# copy_exif() into its exception handler without needing a real image.
PIEXIF_STUB = """\
def load(path):
	return {}

def dump(data):
	return b""

def insert(exif_bytes, path):
	raise RuntimeError("simulated write failure")
"""

# A pydub stand-in: importing it satisfies the on-demand dependency check, and
# decoding always fails, which is what a corrupt audio file does.
PYDUB_STUB = """\
class AudioSegment:
	@staticmethod
	def from_file(path):
		raise RuntimeError("cannot decode")

	@staticmethod
	def silent(duration=0):
		return []
"""

# Runs the real main() with the ffmpeg probe patched out, so the workflow under
# test is main()'s own exit code, not the host's toolchain.
AUDIOSPLIT_HARNESS = """\
import sys
import audiosplit

audiosplit.check_ffmpeg = lambda: True
sys.argv = ["audiosplit.py"] + sys.argv[1:]
sys.exit(audiosplit.main())
"""


def child_env(*extra_paths):
	env = dict(os.environ)
	env["PYTHONPATH"] = os.pathsep.join(
		[str(path) for path in extra_paths] + [str(REPO)])
	return env


def run(args, cwd, env):
	return subprocess.run(
		args,
		cwd=str(cwd),
		env=env,
		stdin=subprocess.DEVNULL,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=TIMEOUT,
	)


def text(raw):
	return raw.decode("utf-8", "replace")


def stub_dir(root, name, body):
	"""Write `<root>/stubs/<name>.py` and return the stubs directory."""
	stubs = Path(root) / "stubs"
	stubs.mkdir(exist_ok=True)
	(stubs / "{}.py".format(name)).write_text(body, encoding="utf-8")
	return stubs


class ExifcopyExitCodesTest(unittest.TestCase):
	"""A reported copy error must reach the caller as exit 1."""

	def test_missing_source_and_target_exit_1(self):
		with tempfile.TemporaryDirectory() as td:
			env = child_env(stub_dir(td, "piexif", PIEXIF_STUB))
			source = Path(td) / "source.jpg"
			target = Path(td) / "target.jpg"

			proc = run([sys.executable, str(REPO / "exifcopy.py"),
						str(source), str(target)], cwd=td, env=env)
			out = text(proc.stdout)
			self.assertEqual(proc.returncode, 1,
							 "missing source exited {}\n{}".format(
								 proc.returncode, out + text(proc.stderr)))
			self.assertIn("Error: Source file", out,
						  "the message moved off stdout:\n{}".format(out))
			self.assertNotIn("Traceback", text(proc.stderr))

			# The source exists now, so the target check is the failing one.
			source.write_bytes(b"")
			proc = run([sys.executable, str(REPO / "exifcopy.py"),
						str(source), str(target)], cwd=td, env=env)
			out = text(proc.stdout)
			self.assertEqual(proc.returncode, 1,
							 "missing target exited {}\n{}".format(
								 proc.returncode, out + text(proc.stderr)))
			self.assertIn("Error: Target file", out,
						  "the message moved off stdout:\n{}".format(out))

	def test_copy_failure_exits_1_on_stderr(self):
		with tempfile.TemporaryDirectory() as td:
			env = child_env(stub_dir(td, "piexif", PIEXIF_STUB))
			source = Path(td) / "source.jpg"
			target = Path(td) / "target.jpg"
			source.write_bytes(b"")
			target.write_bytes(b"")

			proc = run([sys.executable, str(REPO / "exifcopy.py"),
						str(source), str(target)], cwd=td, env=env)
			err = text(proc.stderr)
			self.assertEqual(proc.returncode, 1,
							 "copy failure exited {}\n{}".format(
								 proc.returncode, err + text(proc.stdout)))
			self.assertIn("An error occurred: simulated write failure", err,
						  "the copy failure was not reported on stderr:\n{}".format(err))


class AudiosplitExitCodesTest(unittest.TestCase):
	"""Batch runs must be non-zero when a file fails or nothing matched."""

	def test_corrupt_file_under_all_exits_1(self):
		with tempfile.TemporaryDirectory() as td:
			env = child_env(stub_dir(td, "pydub", PYDUB_STUB))
			(Path(td) / "corrupt.wav").write_bytes(b"not a wav file")

			proc = run([sys.executable, "-c", AUDIOSPLIT_HARNESS, "-a"],
					   cwd=td, env=env)
			out = text(proc.stdout)
			self.assertEqual(proc.returncode, 1,
							 "a corrupt file exited {}\n{}".format(
								 proc.returncode, out + text(proc.stderr)))
			self.assertIn("An error occurred with 'corrupt.wav'", out,
						  "the per-file error was not reported:\n{}".format(out))

	def test_empty_directory_under_all_exits_1(self):
		with tempfile.TemporaryDirectory() as td:
			env = child_env(stub_dir(td, "pydub", PYDUB_STUB))

			proc = run([sys.executable, "-c", AUDIOSPLIT_HARNESS, "-a"],
					   cwd=td, env=env)
			out = text(proc.stdout)
			self.assertEqual(proc.returncode, 1,
							 "an empty directory exited {}\n{}".format(
								 proc.returncode, out + text(proc.stderr)))
			self.assertIn("No matching files found.", out)

	def test_no_arguments_still_exits_0(self):
		"""The no-argument run is help, not a failure."""
		with tempfile.TemporaryDirectory() as td:
			env = child_env(stub_dir(td, "pydub", PYDUB_STUB))

			proc = run([sys.executable, "-c", AUDIOSPLIT_HARNESS],
					   cwd=td, env=env)
			self.assertEqual(proc.returncode, 0,
							 "no-argument help exited {}\n{}".format(
								 proc.returncode, text(proc.stdout) + text(proc.stderr)))


def load_checks():
	"""Import tests/container/checks.py by path: it is not a package."""
	path = REPO / "tests" / "container" / "checks.py"
	spec = importlib.util.spec_from_file_location("catro_container_checks", str(path))
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class ClassifierTest(unittest.TestCase):
	"""rc == 0 alone is not evidence of success."""

	@classmethod
	def setUpClass(cls):
		cls.checks = load_checks()

	def classify(self, rc, out="", err=""):
		return self.checks.classify(dict(rc=rc, out=out, err=err, timeout=False))

	def test_rc0_with_an_error_line_is_not_pass(self):
		self.assertEqual(
			self.classify(0, out="Error: Source file 'a.jpg' does not exist.\n"),
			"FAIL:silent")
		self.assertEqual(self.classify(0, out="\n[Error] File not found: 'x.md'\n"),
						 "FAIL:silent")
		self.assertEqual(self.classify(0, out="An error occurred with 'x.wav': boom\n"),
						 "FAIL:silent")
		self.assertEqual(self.classify(0, err="error: something broke\n"),
						 "FAIL:silent")

	def test_rc0_with_usage_is_usage(self):
		self.assertEqual(self.classify(0, out="Usage: python tool.py <path>\n"),
						 "USAGE")

	def test_rc0_clean_output_is_pass(self):
		self.assertEqual(self.classify(0, out="Successfully copied EXIF data.\n"),
						 "PASS")

	def test_dependency_message_is_dep_for_rc0_and_nonzero(self):
		self.assertEqual(self.classify(0, out="Error: 'piexif' library is not installed."),
						 "DEP")
		self.assertEqual(self.classify(1, out="'pydub' library is not installed."),
						 "DEP")

	def test_tty_guard_is_still_accepted(self):
		self.assertEqual(
			self.classify(2, err="[Error] mdreader needs an interactive terminal "
								 "(stdin/stdout is not a tty).\n"),
			"PASS:tty-guard")


if __name__ == "__main__":
	unittest.main()
