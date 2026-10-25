# Theme coverage for the themed one-off commands
"""
			THEMED CORE COMMANDS
			====================
Pins the two halves of the theme contract for the commands migrated onto the
page-chrome seam (`list`, `help`, `action`, `count`, `opencode`, `sanitize`):

	- on a terminal, `CATRO_THEME` changes the bytes: `soft` and
		`contrast-dark` resolve different palette roles, so the same command must
		not print the same bytes under both;
	- a pipe (and `NO_COLOR`) degrades: no escape sequences at all, and the
		pipe bytes are the same whichever theme is selected, because a plain
		record stream is not allowed to depend on a colour choice.

Every command is driven in-process through its real entrypoint with a fake tty
stdout, so this is the script's own chrome being measured, not a helper's.

Run with:
	python -m unittest discover -s tests -v
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)

# Scratch a developer's own environment out of the comparison.
SCRUBBED = ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "CATRO_COLOR",
			"CATRO_ASCII", "CATRO_THEME", "TERM", "COLORTERM", "CLICOLOR")

# The list golden fixtures are a stable directory of tiny scripts: reusing them
# keeps the scan input (and its sizes) identical on every platform.
LIST_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "list_golden" / "scripts"

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u253c\u252c\u2534\u251c\u2524"

ACTION_FIXTURE = {
	"ping": {"command": "ping 127.0.0.1", "description": "Ping loopback"},
	"long": {"command": "x" * 60, "description": "y" * 60},
}

# Stable inputs: the byte comparison between two runs must not see a different
# temporary path, so the fixture directory is materialised once per module.
FIXTURE_ROOT = None
COUNT_DIR = None
ACTIONS_PATH = None


def setUpModule():
	global FIXTURE_ROOT, COUNT_DIR, ACTIONS_PATH
	FIXTURE_ROOT = Path(tempfile.mkdtemp(prefix="theme-core-"))
	COUNT_DIR = FIXTURE_ROOT / "count"
	COUNT_DIR.mkdir()
	(COUNT_DIR / "one.txt").write_text("x" * 64, encoding="utf-8")
	(COUNT_DIR / "two.py").write_text("y" * 128, encoding="utf-8")
	ACTIONS_PATH = FIXTURE_ROOT / "actions.json"
	ACTIONS_PATH.write_text(json.dumps(ACTION_FIXTURE), encoding="utf-8")


def tearDownModule():
	shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)


class Stream:
	"""A tty-able stdout: writes are captured, no file descriptor."""

	def __init__(self, tty=True):
		self._buffer = io.StringIO()
		self._tty = tty
		self.encoding = "utf-8"

	def write(self, text):
		return self._buffer.write(text)

	def flush(self):
		pass

	def isatty(self):
		return self._tty

	def fileno(self):
		raise OSError("no file descriptor")

	def getvalue(self):
		return self._buffer.getvalue()


def render_list():
	import list as list_module
	with mock.patch.object(list_module, "__file__",
						   str(LIST_FIXTURES / "list.py")):
		list_module.list_scripts()


def render_help():
	import help as help_module
	with mock.patch.object(sys, "argv", ["help.py", "list"]):
		help_module.main()


def render_action():
	import action as action_module
	with mock.patch.object(action_module, "ACTIONS_FILE", str(ACTIONS_PATH)), \
			mock.patch.object(sys, "argv", ["action.py", "list"]):
		action_module.main()


def render_count():
	import count as count_module
	with mock.patch.object(sys, "argv", ["count.py", str(COUNT_DIR)]):
		count_module.main()


def render_opencode():
	import opencode as opencode_module
	# The install-guidance page needs no binary and no network: it is pure copy.
	opencode_module.print_not_installed()


def render_sanitize():
	import sanitize
	ok = mock.Mock(returncode=0, stdout="", stderr="")
	with mock.patch.object(sys, "argv",
						   ["sanitize.py", "SECRET", "<redacted>", "--yes"]), \
			mock.patch.object(sanitize, "find_repo_root",
							  return_value=(Path("/tmp/repo"), "")), \
			mock.patch.object(sanitize, "find_filter_repo",
							  return_value=["git", "filter-repo"]), \
			mock.patch.object(sanitize, "secret_in_history", return_value=False), \
			mock.patch.object(sanitize, "run", return_value=ok):
		sanitize.main()


# (label, driver) - one entry per migrated command in this group.
COMMANDS = [
	("list", render_list),
	("help", render_help),
	("action", render_action),
	("count", render_count),
	("opencode", render_opencode),
	("sanitize", render_sanitize),
]


def render(driver, theme=None, tty=True, extra=None):
	"""Run one command with a scrubbed environment and a fake stdout."""
	env = {key: value for key, value in os.environ.items()
		   if key not in SCRUBBED}
	if tty:
		# An explicit colour request is what keeps the fake tty out of plain
		# mode; a pipe must stay a pipe, so it gets no request.
		env["FORCE_COLOR"] = "3"
	if theme:
		env["CATRO_THEME"] = theme
	env.update(extra or {})
	stream = Stream(tty)
	errors = io.StringIO()
	with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch.object(tui, "init_ansi"), \
			mock.patch.object(sys, "stdout", stream), \
			mock.patch("sys.stderr", errors):
		driver()
	return stream.getvalue()


class ThemeChangesTheBytesTest(unittest.TestCase):
	"""Soft and contrast-dark are different palettes, so the bytes differ."""

	def test_every_command_renders_differently_per_theme(self):
		for label, driver in COMMANDS:
			with self.subTest(command=label):
				soft = render(driver, theme="soft")
				dark = render(driver, theme="contrast-dark")
				self.assertIn("\x1b", soft, f"{label} printed no colour on a tty")
				self.assertNotEqual(
					soft, dark,
					f"{label} ignored CATRO_THEME: soft and contrast-dark agree")


class DegradedOutputTest(unittest.TestCase):
	"""NO_COLOR and a pipe drop every escape, and a pipe ignores the theme."""

	def test_no_color_on_a_tty_keeps_the_layout_without_escapes(self):
		for label, driver in COMMANDS:
			with self.subTest(command=label):
				out = render(driver, theme="soft", extra={"NO_COLOR": "1"})
				self.assertTrue(out.strip(), f"{label} printed nothing")
				self.assertNotIn("\x1b", out,
								 f"{label} carried escapes under NO_COLOR")

	def test_pipe_output_is_plain_and_theme_independent(self):
		for label, driver in COMMANDS:
			with self.subTest(command=label):
				soft = render(driver, theme="soft", tty=False)
				dark = render(driver, theme="contrast-dark", tty=False)
				self.assertTrue(soft.strip(), f"{label} printed nothing in a pipe")
				self.assertNotIn("\x1b", soft, f"{label} styled a pipe")
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, soft,
									 f"{label} drew a box glyph in a pipe")
				self.assertEqual(
					soft, dark,
					f"{label} let the selected theme change its pipe bytes")


if __name__ == "__main__":
	unittest.main()
