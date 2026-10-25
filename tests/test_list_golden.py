# Golden fixture for list.py's default rendering (contract invariant 1)
"""
			LIST GOLDEN BYTES
			=================
Invariant 1 of the `tui` contract is a regression pin: the migrated `list.py`
must render exactly the bytes committed under `expected/`, for the default theme
and for the capability variants. The independent driver in `.devteam/artifacts/`
proves that against a live checkout, but it is untracked tooling and can drift
with the working tree. This module is the checked-in net.

The default identity changed when the final theme set landed: `soft` is
`mdreader`'s cozy purple, not the old purple-on-black, and no hex from the old
palette reproduces it. These fixtures were regenerated from the code after that
change, never hand-edited, so they pin `soft`'s own bytes from now on.

A fixed synthetic fixture directory (`tests/fixtures/list_golden/scripts/`, three
tiny scripts) is materialised into a temporary directory with LF endings so the
byte sizes are stable on every platform, and `list.py` is run in-process against
it with a fake tty. The table region - from the line above the header through
`Total scripts found:` - must equal the committed expected bytes for each
capability case:

	soft-16.tty      level 16, soft theme, unicode glyphs
	truecolor.tty    level true, soft theme, unicode glyphs
	unicode-off.tty  level 16, CATRO_ASCII, ASCII box glyphs
	no-color.tty     NO_COLOR on a tty: box, no escapes

The `Location:` header names an absolute temporary path and is deliberately
outside the compared region.

Regenerate after an intentional rendering change only:

	python tests/test_list_golden.py --regen

and review the diff before committing it.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "list_golden"
EXPECTED = FIXTURES / "expected"
SCRIPTS = FIXTURES / "scripts"

# The scrub list keeps a developer's real terminal preferences (and config.ini
# through CATRO_*) out of the comparison.
SCRUBBED = ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "CATRO_COLOR",
			"CATRO_ASCII", "CATRO_THEME", "TERM", "COLORTERM", "CLICOLOR")

CASES = {
	"soft-16.tty": {"CATRO_COLOR": "16", "CATRO_THEME": "soft"},
	"truecolor.tty": {"FORCE_COLOR": "3", "CATRO_THEME": "soft"},
	"unicode-off.tty": {"CATRO_COLOR": "16", "CATRO_THEME": "soft",
						"CATRO_ASCII": "1"},
	"no-color.tty": {"NO_COLOR": "1", "CATRO_THEME": "soft"},
}


class Stream:
	"""A tty-looking stdout that captures text and has no file descriptor."""

	def __init__(self):
		self._chunks = []
		self.encoding = "utf-8"

	def write(self, text):
		self._chunks.append(text)

	def flush(self):
		pass

	def getvalue(self):
		return "".join(self._chunks)

	def isatty(self):
		return True

	def fileno(self):
		raise OSError("no file descriptor")


def materialise(target):
	"""Write the committed fixtures into `target` with LF endings."""
	target = Path(target)
	target.mkdir(parents=True, exist_ok=True)
	for source in sorted(SCRIPTS.glob("*.py")):
		text = source.read_text(encoding="utf-8")
		with open(target / source.name, "w", encoding="utf-8",
				  newline="\n") as handle:
			handle.write(text)
	return target


def table_region(out):
	"""The stable part of list.py's output: table top through the footer."""
	lines = out.splitlines()
	header = next(index for index, line in enumerate(lines)
				  if "ID" in line and "Script Name" in line)
	footer = next(index for index, line in enumerate(lines)
				  if "Total scripts found:" in line)
	return "\n".join(lines[header - 1:footer + 1]) + "\n"


def render(environ, script_dir):
	"""Run the real list_scripts() against `script_dir` and return the region."""
	import importlib

	list_module = importlib.import_module("list")
	stream = Stream()
	env = {key: value for key, value in os.environ.items()
		   if key not in SCRUBBED}
	env.update(environ)
	with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch.object(tui, "init_ansi"), \
			mock.patch.object(sys, "stdout", stream), \
			mock.patch.object(list_module, "__file__",
							  str(Path(script_dir) / "list.py")):
		list_module.list_scripts()
	return table_region(stream.getvalue())


class ListGoldenFixtureTest(unittest.TestCase):
	"""list.py's table bytes are pinned for four capability cases."""

	@classmethod
	def setUpClass(cls):
		cls._temp = tempfile.TemporaryDirectory(prefix="list-golden-")
		cls.script_dir = materialise(cls._temp.name)

	@classmethod
	def tearDownClass(cls):
		cls._temp.cleanup()

	def check(self, name):
		expected = (EXPECTED / name).read_text(encoding="utf-8")
		actual = render(CASES[name], self.script_dir)
		self.assertTrue(expected.strip(), "the golden file is empty")
		self.assertEqual(actual, expected,
						 "list.py bytes changed for {}:\n{}".format(
							 name, actual[:1200]))
		self.assertNotIn(str(self.script_dir), actual,
						 "an absolute path leaked into the golden region")
		self.assertIn("Total scripts found: 3", tui.strip_ansi(actual))

	def test_soft_16(self):
		self.check("soft-16.tty")

	def test_truecolor(self):
		self.check("truecolor.tty")

	def test_unicode_off(self):
		self.check("unicode-off.tty")

	def test_no_color_tty(self):
		self.check("no-color.tty")


def regenerate():
	EXPECTED.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory(prefix="list-golden-") as temp:
		script_dir = materialise(temp)
		for name, environ in CASES.items():
			text = render(environ, script_dir)
			with open(EXPECTED / name, "w", encoding="utf-8",
					  newline="\n") as handle:
				handle.write(text)
			print("wrote", EXPECTED / name)


if __name__ == "__main__":
	if "--regen" in sys.argv:
		regenerate()
	else:
		unittest.main()
