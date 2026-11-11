# POSIX portability regressions for shutdown.py and ts_export.py
"""
		POSIX RUNTIME REGRESSIONS
		=========================
Stdlib-only tests for the two places where the collection used to assume that a
POSIX host necessarily has sudo, and that 0o200 means "add the write bit".

Rules this suite keeps:
	- shutdown.py is never executed for real: `subprocess.run` is mocked and the
	  platform, PATH and euid lookups are patched, so no test needs root, sudo,
	  or a real `shutdown` binary, and none can schedule one.
	- ts_export.remove_readonly is exercised on temporary files at 0o444 and
	  temporary directories at 0o555. The mode it computes is asserted to be
	  additive (owner read survives, owner execute survives on directories),
	  never exactly `stat.S_IWRITE`.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

# The suite lives in <repo>/tests/; importing the modules under test needs the
# repository root on sys.path, which is also what the wrapper does in practice.
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import shutdown
import ts_export


def euid_patch(value):
	"""Patch shutdown's euid lookup, creating it on hosts that lack geteuid."""
	return mock.patch.object(shutdown.os, "geteuid", create=True, return_value=value)


class ScheduleShutdownTests(unittest.TestCase):
	"""shutdown.schedule_shutdown must resolve, report, and return a verdict."""

	def test_missing_sudo_is_a_clear_error(self):
		"""A non-root host without sudo gets one line, no traceback, no run."""
		calls = []
		with euid_patch(1000), \
			 mock.patch.object(shutdown.platform, "system", return_value="Linux"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=lambda name: "/usr/sbin/shutdown"
							   if name == "shutdown" else None), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=lambda *args, **kwargs: calls.append(args)), \
			 redirect_stdout(io.StringIO()) as out:
			ok = shutdown.schedule_shutdown(600)

		self.assertFalse(ok)
		self.assertEqual(calls, [], "a shutdown was attempted without sudo")
		text = out.getvalue()
		self.assertIn("'sudo' is required but not installed", text)
		self.assertNotIn("Traceback", text)

	def test_root_calls_shutdown_directly(self):
		"""euid 0 skips sudo entirely and calls the resolved shutdown argv."""
		calls = []
		with euid_patch(0), \
			 mock.patch.object(shutdown.platform, "system", return_value="Linux"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=lambda name: "/usr/sbin/shutdown"
							   if name == "shutdown" else None), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=lambda argv, **kwargs: calls.append(argv)), \
			 redirect_stdout(io.StringIO()):
			ok = shutdown.schedule_shutdown(600)

		self.assertTrue(ok)
		self.assertEqual(calls, [["/usr/sbin/shutdown", "-h", "+10"]])

	def test_shutdown_found_in_sbin_and_sudo_prefixed(self):
		"""/sbin and /usr/sbin are searched when PATH does not list them."""
		calls = []
		with euid_patch(1000), \
			 mock.patch.object(shutdown.platform, "system", return_value="Linux"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=lambda name: "/usr/bin/sudo"
							   if name == "sudo" else None), \
			 mock.patch.object(shutdown.os.path, "isfile",
							   side_effect=lambda path: os.path.basename(path) == "shutdown"
							   and "sbin" in path), \
			 mock.patch.object(shutdown.os, "access", return_value=True), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=lambda argv, **kwargs: calls.append(argv)), \
			 redirect_stdout(io.StringIO()):
			ok = shutdown.schedule_shutdown(600)

		self.assertTrue(ok)
		expected = os.path.join("/sbin", "shutdown")
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0][0], "/usr/bin/sudo")
		self.assertEqual(calls[0][1], expected)
		self.assertEqual(calls[0][2:], ["-h", "+10"])

	def test_failed_command_names_program_and_returncode(self):
		"""A non-zero exit returns False and reports the program and returncode."""
		argv = ["/usr/bin/sudo", "/usr/sbin/shutdown", "-h", "+10"]
		with euid_patch(1000), \
			 mock.patch.object(shutdown.platform, "system", return_value="Linux"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=lambda name: "/usr/bin/" + name), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=subprocess.CalledProcessError(1, argv)), \
			 redirect_stdout(io.StringIO()) as out:
			ok = shutdown.schedule_shutdown(600)

		self.assertFalse(ok)
		text = out.getvalue()
		self.assertIn("returncode 1", text)
		self.assertIn("/usr/bin/sudo", text)
		self.assertNotIn("was not found", text)

	def test_permission_failure_is_distinct_from_missing_binary(self):
		"""PermissionError reads as a privilege problem, not as a missing program."""
		argv = ["/usr/bin/sudo", "/usr/sbin/shutdown", "-h", "+10"]
		with euid_patch(1000), \
			 mock.patch.object(shutdown.platform, "system", return_value="Linux"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=lambda name: "/usr/bin/" + name), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=PermissionError(13, "denied", argv[0])), \
			 redirect_stdout(io.StringIO()) as out:
			ok = shutdown.schedule_shutdown(600)

		self.assertFalse(ok)
		text = out.getvalue()
		self.assertIn("insufficient permissions", text)
		self.assertNotIn("was not found", text)

	def test_missing_binary_at_exec_is_reported_as_not_found(self):
		"""A FileNotFoundError from the exec surfaces the not-found wording."""
		with euid_patch(1000), \
			 mock.patch.object(shutdown.platform, "system", return_value="Linux"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=lambda name: "/usr/bin/" + name), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=FileNotFoundError(2, "no such file")), \
			 redirect_stdout(io.StringIO()) as out:
			ok = shutdown.schedule_shutdown(600)

		self.assertFalse(ok)
		text = out.getvalue()
		self.assertIn("was not found", text)
		self.assertIn("/usr/bin/sudo", text)

	def test_windows_path_touches_no_posix_lookup(self):
		"""On Windows nothing may reach geteuid, shutil.which, /sbin or sudo."""
		calls = []
		argv = []

		def record(command, **kwargs):
			calls.append(command)
			return subprocess.CompletedProcess(command, 0)

		with mock.patch.object(shutdown.platform, "system", return_value="Windows"), \
			 mock.patch.object(shutdown.shutil, "which",
							   side_effect=AssertionError("shutil.which on Windows")), \
			 mock.patch.object(shutdown.os, "geteuid", create=True,
							   side_effect=AssertionError("geteuid on Windows")), \
			 mock.patch.object(shutdown.subprocess, "run", side_effect=record), \
			 redirect_stdout(io.StringIO()):
			ok = shutdown.schedule_shutdown(600)

			argv.extend(calls[0])
		self.assertTrue(ok)
		self.assertEqual(len(calls), 1)
		self.assertTrue(argv[0].lower().endswith(("shutdown", "shutdown.exe")),
						"unexpected Windows program: {!r}".format(argv[0]))
		self.assertNotIn("sudo", [part.lower() for part in argv])
		self.assertIn("/s", argv)

	def test_unsupported_system_returns_false(self):
		"""An unknown platform is a failure, not a silent success."""
		calls = []
		with mock.patch.object(shutdown.platform, "system", return_value="plan9"), \
			 mock.patch.object(shutdown.subprocess, "run",
							   side_effect=lambda *a, **k: calls.append(a)), \
			 redirect_stdout(io.StringIO()) as out:
			self.assertFalse(shutdown.schedule_shutdown(600))
		self.assertEqual(calls, [])
		self.assertIn("Unsupported operating system", out.getvalue())

	def test_main_exits_1_when_scheduling_fails(self):
		"""The interactive path must propagate a failed schedule as exit 1."""
		with mock.patch("builtins.input", side_effect=["45m", "y"]), \
			 mock.patch.object(shutdown, "schedule_shutdown", return_value=False), \
			 redirect_stdout(io.StringIO()):
			with self.assertRaises(SystemExit) as raised:
				shutdown.main()
		self.assertEqual(raised.exception.code, 1)

	def test_main_exits_cleanly_when_scheduling_works(self):
		"""A successful schedule keeps the historical exit 0."""
		with mock.patch("builtins.input", side_effect=["45m", "y"]), \
			 mock.patch.object(shutdown, "schedule_shutdown", return_value=True), \
			 redirect_stdout(io.StringIO()):
			shutdown.main()


class RemoveReadonlyTests(unittest.TestCase):
	"""ts_export.remove_readonly must add write permission, never replace it."""

	def test_file_mode_is_additive(self):
		"""A 0o444 file keeps owner read and gains write; never exactly S_IWRITE."""
		with tempfile.TemporaryDirectory() as td:
			path = Path(td) / "readonly.txt"
			path.write_text("x", encoding="utf-8")
			os.chmod(str(path), 0o444)
			self.addCleanup(lambda: os.chmod(str(path), 0o644)
							if path.exists() else None)

			real_chmod = os.chmod
			seen = []
			retried = []

			def spy(target, mode, **kwargs):
				seen.append((target, mode))
				return real_chmod(target, mode, **kwargs)

			with mock.patch.object(ts_export.os, "chmod", side_effect=spy):
				ts_export.remove_readonly(retried.append, str(path), None)

			self.assertEqual(retried, [str(path)])
			self.assertEqual(len(seen), 1)
			mode = seen[0][1]
			self.assertNotEqual(mode, stat.S_IWRITE,
								"the handler replaced the mode with 0o200")
			self.assertEqual(mode & stat.S_IWRITE, stat.S_IWRITE)
			self.assertEqual(mode & stat.S_IREAD, stat.S_IREAD)
			self.assertTrue(os.access(str(path), os.R_OK),
							"owner read permission was lost")
			self.assertTrue(os.access(str(path), os.W_OK),
							"owner write permission was not granted")
			if os.name != "nt":
				self.assertEqual(stat.S_IMODE(os.stat(str(path)).st_mode), 0o644)

	def test_directory_mode_keeps_owner_execute(self):
		"""A 0o555 directory keeps owner read+execute so rmtree can descend."""
		with tempfile.TemporaryDirectory() as td:
			directory = Path(td) / "readonly_dir"
			directory.mkdir()
			os.chmod(str(directory), 0o555)
			self.addCleanup(lambda: os.chmod(str(directory), 0o755)
							if directory.exists() else None)

			real_chmod = os.chmod
			seen = []
			retried = []

			def spy(target, mode, **kwargs):
				seen.append(mode)
				return real_chmod(target, mode, **kwargs)

			with mock.patch.object(ts_export.os, "chmod", side_effect=spy):
				ts_export.remove_readonly(retried.append, str(directory), None)

			self.assertEqual(retried, [str(directory)])
			self.assertEqual(len(seen), 1)
			mode = seen[0]
			self.assertNotEqual(mode, stat.S_IWRITE,
								"the handler replaced the mode with 0o200")
			self.assertEqual(mode & stat.S_IXUSR, stat.S_IXUSR)
			self.assertEqual(mode & stat.S_IREAD, stat.S_IREAD)
			if os.name != "nt":
				self.assertEqual(stat.S_IMODE(os.stat(str(directory)).st_mode), 0o755)

	def test_unreachable_path_does_not_raise(self):
		"""A chmod that cannot run is swallowed, then func() gets its chance."""
		with tempfile.TemporaryDirectory() as td:
			missing = Path(td) / "gone.txt"
			retried = []
			ts_export.remove_readonly(retried.append, str(missing), None)
		self.assertEqual(retried, [str(missing)])

	def test_remove_tree_uses_version_appropriate_handler(self):
		"""onerror on the 3.11 baseline, onexc from 3.12 on."""
		with mock.patch.object(ts_export.shutil, "rmtree") as rmtree:
			with mock.patch.object(ts_export.sys, "version_info", (3, 11, 0)):
				ts_export.remove_tree("export")
			rmtree.assert_called_once_with("export", onerror=ts_export.remove_readonly)

		with mock.patch.object(ts_export.shutil, "rmtree") as rmtree:
			with mock.patch.object(ts_export.sys, "version_info", (3, 12, 0)):
				ts_export.remove_tree("export")
			rmtree.assert_called_once_with("export", onexc=ts_export.remove_readonly)


if __name__ == "__main__":
	unittest.main()
