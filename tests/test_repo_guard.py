# Repository write guard: the suite may read the checkout, never write it
"""
		THE TEST PROCESS CANNOT WRITE THE CHECKOUT
		==========================================
Issue #39: a theme or config write lands wherever three module globals point,
and their default is the tracked checkout (`theme_engine.THEMES_DIR`,
`theme_engine.THEME_FILE`, `tui.config.CONFIG_FILE` are `None` = the project
folder). A test that forgets one of them - or puts `None` back - writes
`themes/*.json`, `theme.ini` or `config.ini` into the developer's tree.

`tests/support.py` installs a process-wide guard for exactly that: every writer
a test can reach (the engine's `_atomic_write`, `Path.write_text`,
`Path.write_bytes`, `Path.open`, plain `open(..., "w")`) checks its resolved
target and raises `AssertionError` naming it when the target is inside the
repository. `tests/conftest.py` installs it as a session autouse fixture, so no
module has to opt in; temp folders are untouched and production runs are
untouched (the guard exists only inside the test process).

The session fixture also snapshots `themes/*.json`, `theme.ini`, `config.ini`
and `tests/fixtures/**` and asserts at the end of the run that they are still
exactly as found, so a rewrite that a test undoes cannot hide.

The tests below are `unittest.TestCase` like the rest of the suite: they pass
only if the fixture reaches unittest items, which is the proof the mechanism is
suite-wide rather than pytest-function-only.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for entry in (str(REPO), str(TESTS)):
	if entry not in sys.path:
		sys.path.insert(0, entry)

import support  # noqa: E402  (test helper, not production)
from tui import config, theme_engine  # noqa: E402  (import after sys.path setup)

SHIPPED = REPO / "themes" / "cozypurple.json"

# Recorded before the fallback install below: if this is False, the suite's
# session fixture is not protecting the checkout and the guard tests must say
# so instead of passing on their own bootstrap.
_SEEN = {}


def setUpModule():
	_SEEN["installed"] = support.guard_installed()
	# Fallback for a direct `python -m unittest` run: these tests deliberately
	# attempt a checkout write, so the guard must exist before they start.
	support.install_repo_write_guard()


class GuardInstallationTests(unittest.TestCase):
	"""The session fixture is enough: these tests do no per-module setup."""

	def test_the_suite_installed_the_guard(self):
		if "PYTEST_CURRENT_TEST" not in os.environ:
			self.skipTest("only pytest has the session hook; setUpModule "
						  "installs the guard for a plain unittest run")
		self.assertTrue(_SEEN.get("installed"),
						"no suite-wide guard: tests/conftest.py did not install it")

	def test_a_repo_write_is_refused_and_the_target_is_named(self):
		target = REPO / "themes" / "cozypurple.json"
		with self.assertRaises(AssertionError) as caught:
			target.write_text("{}", encoding="utf-8")
		self.assertIn(str(target.resolve()), str(caught.exception))

	def test_the_atomic_writer_is_refused_too(self):
		target = REPO / "themes" / "cozypurple.json"
		with self.assertRaises(AssertionError) as caught:
			theme_engine._atomic_write(target, "{}\n")
		self.assertIn(str(target.resolve()), str(caught.exception))

	def test_a_plain_open_for_writing_is_refused_too(self):
		target = REPO / "config.ini"
		with self.assertRaises(AssertionError) as caught:
			open(target, "w", encoding="utf-8")
		self.assertIn(str(target.resolve()), str(caught.exception))

	def test_temp_writes_are_unaffected(self):
		with tempfile.TemporaryDirectory() as td:
			target = Path(td) / "theme.json"
			target.write_text("{}", encoding="utf-8")
			self.assertTrue(target.is_file())
			with open(target, "w", encoding="utf-8") as handle:
				handle.write("{}\n")


class PlainUnittestPathTests(unittest.TestCase):
	"""`python -m unittest` has no conftest: the installer must stand alone."""

	def test_install_test_guard_guards_a_process_without_pytest(self):
		script = "\n".join([
			"import sys",
			"sys.path[:0] = [{!r}, {!r}]".format(str(TESTS), str(REPO)),
			"import support",
			"from pathlib import Path",
			"target = Path({!r}) / 'themes' / 'cozypurple.json'".format(str(REPO)),
			"check = support.install_test_guard()",
			"try:",
			"    target.write_text('{}', encoding='utf-8')",
			"except AssertionError as exc:",
			"    assert 'cozypurple.json' in str(exc), exc",
			"else:",
			"    raise SystemExit('the guard did not fire')",
			"check()",
		])
		done = subprocess.run([sys.executable, "-c", script], cwd=str(REPO),
							  capture_output=True, text=True, timeout=60)
		self.assertEqual(done.returncode, 0, done.stderr)


class LeakedSeamTests(unittest.TestCase):
	"""`None` means the checkout: a leaked seam must fail loudly, not write."""

	def setUp(self):
		self._previous = (config.CONFIG_FILE, theme_engine.THEME_FILE,
						  theme_engine.THEMES_DIR)

	def tearDown(self):
		config.CONFIG_FILE, theme_engine.THEME_FILE, theme_engine.THEMES_DIR = (
			self._previous)
		theme_engine._CACHE.clear()

	def test_save_theme_with_the_default_themes_dir_is_refused(self):
		theme_engine.THEMES_DIR = None
		before = SHIPPED.read_bytes()
		document = theme_engine.load_theme("cozypurple")
		with self.assertRaises(AssertionError) as caught:
			theme_engine.save_theme(document, overwrite=True)
		self.assertIn(str(SHIPPED.resolve()), str(caught.exception))
		self.assertEqual(SHIPPED.read_bytes(), before)

	def test_set_selection_with_the_default_theme_file_is_refused(self):
		theme_engine.THEME_FILE = None
		with self.assertRaises(AssertionError) as caught:
			theme_engine.set_selection(name="cozypurple")
		self.assertIn(str((REPO / "theme.ini").resolve()), str(caught.exception))

	def test_config_set_with_the_default_config_file_is_refused(self):
		config.CONFIG_FILE = None
		with self.assertRaises(AssertionError) as caught:
			config.set("color", "level", "256")
		self.assertIn(str((REPO / "config.ini").resolve()), str(caught.exception))

	def test_a_seam_left_on_the_repo_stays_guarded_after_a_raise(self):
		theme_engine.THEMES_DIR = REPO / "themes"

		def bumped_setup():
			raise RuntimeError("setUp failed after pointing at the repo")

		with self.assertRaises(RuntimeError):
			bumped_setup()
		# A broken setUp/tearDown pair must not turn the guard off.
		self.assertTrue(support.guard_installed())
		with self.assertRaises(AssertionError):
			theme_engine.save_theme(theme_engine.load_theme("cozypurple"),
									overwrite=True)


class CheckoutInvariantTests(unittest.TestCase):
	"""The as-found snapshot is the in-process net under the whole suite."""

	def test_the_snapshot_covers_the_tracked_data_files(self):
		state = support.snapshot_checkout()
		self.assertIn("themes/cozypurple.json", state)
		self.assertIn("theme.ini", state)
		self.assertIn("config.ini", state)
		self.assertIn("tests/fixtures/themes/v1-cozypurple.json", state)

	def test_a_rewrite_that_keeps_the_mtime_is_still_caught(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			(root / "themes").mkdir()
			target = root / "themes" / "cozypurple.json"
			target.write_text('{"a": 1}\n', encoding="utf-8")
			before = support.snapshot_checkout(root)
			self.assertIn("themes/cozypurple.json", before)
			stat = target.stat()
			target.write_bytes(b'{"a": 2}\n')
			# Same size, same mtime: only the content hash can see the change.
			os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
			with self.assertRaises(AssertionError) as caught:
				support.assert_checkout_unchanged(before, root)
			self.assertIn("themes/cozypurple.json", str(caught.exception))

	def test_a_removed_or_created_file_is_caught(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			before = support.snapshot_checkout(root)
			(root / "theme.ini").write_text("[theme]\n", encoding="utf-8")
			with self.assertRaises(AssertionError) as caught:
				support.assert_checkout_unchanged(before, root)
			self.assertIn("theme.ini", str(caught.exception))


class FixtureOptOutTests(unittest.TestCase):
	"""Fixture regeneration is the one legitimate checkout write."""

	def test_the_opt_out_is_scoped_to_one_subtree(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			fixtures = root / "tests" / "fixtures"
			fixtures.mkdir(parents=True)
			with mock.patch.object(support, "REPO_ROOT", root):
				target = fixtures / "soft-16.tty"
				with self.assertRaises(AssertionError):
					target.write_text("golden\n", encoding="utf-8")
				with support.allow_repo_writes(fixtures):
					target.write_text("golden\n", encoding="utf-8")
					self.assertTrue(target.is_file())
				with self.assertRaises(AssertionError):
					target.write_text("changed\n", encoding="utf-8")
				self.assertEqual(target.read_text(encoding="utf-8"), "golden\n")
				self.assertTrue(fixtures.is_dir())


if __name__ == "__main__":
	unittest.main()
