# Regression tests for the migrated script rendering
"""
			SCRIPT MIGRATION SEAMS
			======================
Pins what the Phase A migration deliberately kept as data rather than as private
ANSI strings:

	- help.INDENT_STYLES: the indentation palette must still resolve to the old
		16-colour codes (1;37, 0;36, 0;32, 0;33, 0;31), so a 16-colour terminal
		sees the same colours it always did.
	- count.RAINBOW: same idea for the old 91/33/93/92/96/94/95 cycle.
	- action.list_actions(): fixed widths and its own `..` truncation survive,
		while a pipe gets the library's plain TAB-separated records.
	- list.py with NO_COLOR: colour off is not a pipe - a tty keeps the box and
		loses only the escapes.
	- No migrated script still carries a private escape sequence or its own
		`Colors` class: that is the gate this migration has to keep closed.
	- `ThemedOutputTest`: every in-scope script that prints output calls at
		least one shared page-chrome/table helper (`tui.header`, `tui.panel`,
		`tui.rule`, `tui.status`, `tui.field`, `tui.fill`, `tui.menu`, or the
		table/section/key-values helpers) instead of printing bare headings.
		The gate is strict: `PENDING_THEMING` is empty after the c1-c5 groups
		merged, and the only exemptions are `SCREEN_RENDERERS` (full-screen
		engines that paint their own frame) and `DELEGATES` (`theme.py`, whose
		page is `tui/__main__.py`) - both explicit tuples, each checked to
		really be what it claims.

Run with:
	python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import ast
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))

import tui  # noqa: E402  (import after sys.path setup)
import keygen  # noqa: E402  (imported for its picker marker)
from support import clean_env, module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()


def cap16():
	return tui.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")


def is_tui_call(node, name):
	"""True for a `tui.<name>(...)` / `tui.chrome.<name>(...)` call node."""
	if not isinstance(node, ast.Call):
		return False
	func = node.func
	if not isinstance(func, ast.Attribute) or func.attr != name:
		return False
	owner = func.value
	if isinstance(owner, ast.Name):
		return owner.id == "tui"
	return (isinstance(owner, ast.Attribute) and owner.attr == "chrome"
			and isinstance(owner.value, ast.Name) and owner.value.id == "tui")


class FakeTty:
	"""A tty-able stdout: writes are captured, no file descriptor."""

	def __init__(self, tty=True, encoding="utf-8"):
		self._buffer = io.StringIO()
		self._tty = tty
		self.encoding = encoding

	def write(self, text):
		return self._buffer.write(text)

	def flush(self):
		pass

	def isatty(self):
		return self._tty

	def getvalue(self):
		return self._buffer.getvalue()


class NoPrivateAnsiTest(unittest.TestCase):
	"""The gate: migrated scripts only style through tui."""

	# Phase A scripts plus every Phase B script (seven crunch groups). Adding a
	# script here is the price of moving it onto tui/: the gate below is what
	# keeps a private escape sequence from creeping back in.
	MIGRATED = ("list.py", "help.py", "action.py", "count.py",
				"oc.py", "oc_volta.py", "sanitize.py", "screensaver.py",
				# B1 interactive
				"keygen.py", "fakeserver.py",
				# B2 jsonl
				"jsonl_monitor.py",
				# B3 curses
				"mdreader.py",
				# B4 video
				"videofade.py", "videoframes.py", "videojoin.py",
				"videoloop.py", "videomux.py", "videotweak.py",
				# B5 media
				"image_resizer.py", "audiosplit.py", "image_generator.py",
				"ts_setup.py", "webp.py",
				# B6 system/net
				"netconfig.py", "gitpush.py", "ts_export.py",
				"venvreplicator.py",
				# B7 file tools
				"renamer.py", "alias.py", "newfile.py", "getaudio.py",
				"exifcopy.py", "timecopy.py", "randomsorter.py",
				"shutdown.py", "installdeps.py",
				# B8 speech/reader
				"readerbox.py",
				# the theme command (delegates to tui.__main__)
				"theme.py")

	def test_migrated_scripts_have_no_private_ansi(self):
		for name in self.MIGRATED:
			source = (REPO / name).read_text(encoding="utf-8")
			self.assertNotIn("\\033", source,
							 "{} still hardcodes an escape sequence".format(name))
			self.assertNotIn("class Colors", source,
							 "{} still has a private Colors class".format(name))


class ThemedOutputTest(unittest.TestCase):
	"""Every in-scope script renders through the shared page chrome.

	The rule is one line: a script that prints output must call a shared
	chrome/table helper, so headings, rules, status lines and key/value blocks
	look like the rest of the collection instead of being hand-printed. A
	private escape sequence is `NoPrivateAnsiTest`; a bare `print("Title")` is
	what this one catches.

	Strict since the phase-C close-out: `PENDING_THEMING` is empty and the only
	exemptions left are `SCREEN_RENDERERS` (full-screen engines) and
	`DELEGATES` (an entrypoint whose page lives in `tui/__main__.py`).
	"""

	HELPERS = ("header", "panel", "rule", "status", "field", "fill",
			   "banner", "section", "print_table", "key_values",
			   "render_table", "menu")

	# `tui.<helper>` (or `tui.chrome.<helper>`) and the `from tui import ...`
	# spelling both count: the call, not the import style, is what matters.
	CALL = re.compile(r"\btui\.(?:chrome\.)?(?:{})\b".format("|".join(HELPERS)))
	IMPORT = re.compile(r"from\s+tui(?:\.chrome)?\s+import\s+[^\n]*\b(?:{})\b"
						.format("|".join(HELPERS)))

	# Closed at phase-C close-out: the c1-c5 groups are merged and every
	# in-scope script now calls a shared helper, so this is empty on purpose.
	# It stays as the one place a temporarily unthemed script may be named;
	# adding a name here is a visible diff and needs a reason.
	PENDING_THEMING = ()

	# Entrypoints that only delegate. `theme.py` imports and calls
	# `tui.__main__.main`, so its page is rendered in `tui/__main__.py` - a
	# package module, not a root script - and the file-level regex below cannot
	# see it. This is one explicit tuple rather than a silent skip: a test
	# checks each name really is that delegate, so the exemption cannot be
	# reused for a script that grows its own output.
	DELEGATES = ("theme.py",)

	# Full-screen engines: they own the whole screen (curses, the alternate
	# screen or the plugin canvas) and paint their frame from the palette, so
	# the inline page helper is the wrong seam. mdreader is pinned instead by
	# tests/test_mdreader.py::test_chrome_pairs_are_palette_roles.
	SCREEN_RENDERERS = ("fakeserver.py", "jsonl_monitor.py", "mdreader.py",
						"readerbox.py", "screensaver.py")

	def uses_chrome(self, name):
		source = (REPO / name).read_text(encoding="utf-8")
		return bool(self.CALL.search(source) or self.IMPORT.search(source))

	def test_migrated_covers_every_script(self):
		# The gate is only honest if the list it walks is the whole set: a new
		# root script that is missing from MIGRATED would escape both checks.
		scripts = {path.name for path in REPO.glob("*.py")}
		self.assertEqual(scripts - set(NoPrivateAnsiTest.MIGRATED), set(),
						 "new scripts must be added to MIGRATED (and themed)")

	def test_skip_lists_stay_inside_migrated(self):
		migrated = set(NoPrivateAnsiTest.MIGRATED)
		self.assertEqual(set(self.PENDING_THEMING) - migrated, set(),
						 "PENDING_THEMING names a script MIGRATED does not walk")
		self.assertEqual(set(self.SCREEN_RENDERERS) - migrated, set(),
						 "SCREEN_RENDERERS names a script MIGRATED does not walk")
		self.assertEqual(set(self.DELEGATES) - migrated, set(),
						 "DELEGATES names a script MIGRATED does not walk")
		search = (set(self.PENDING_THEMING), set(self.SCREEN_RENDERERS),
				  set(self.DELEGATES))
		for index, first in enumerate(search):
			for second in search[index + 1:]:
				self.assertEqual(first & second, set(),
								 "a script is exempt twice")

	def test_delegates_are_really_pure_delegates(self):
		# The exemption says "the page is in tui/__main__, not here". If one of
		# these ever grows its own rendering, it has to pass the chrome gate
		# instead of sliding through on a stale tuple entry.
		for name in self.DELEGATES:
			source = (REPO / name).read_text(encoding="utf-8")
			self.assertIn("from tui.__main__ import", source,
						  "{} is exempted as a delegate but no longer "
						  "delegates to tui/__main__".format(name))

	def test_in_scope_scripts_use_shared_chrome(self):
		unthemed = [
			name for name in NoPrivateAnsiTest.MIGRATED
			if name not in self.PENDING_THEMING
			and name not in self.SCREEN_RENDERERS
			and name not in self.DELEGATES
			and not self.uses_chrome(name)
		]
		self.assertEqual(
			unthemed, [],
			"these scripts print without a shared chrome helper "
			"(tui.header/panel/rule/status/field/fill/menu or the table "
			"helpers): {}".format(", ".join(unthemed)))


class NoNestedSectionTest(unittest.TestCase):
	"""A section inside a panel doubles the heading.

	A `tui.panel` already frames its rows, so a `tui.section` in that slot
	paints a second heading band inside the box; the page helper there is
	`tui.style(..., fg="header-fg", bold=True)`.
	"""

	def test_no_script_puts_a_section_inside_a_panel(self):
		offenders = []
		for name in NoPrivateAnsiTest.MIGRATED:
			tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
			for node in ast.walk(tree):
				if not is_tui_call(node, "panel"):
					continue
				for arg in node.args:
					for inner in ast.walk(arg):
						if is_tui_call(inner, "section"):
							offenders.append("{}:{}".format(name, inner.lineno))
		self.assertEqual(offenders, [],
						 "tui.section nested inside tui.panel: {}".format(
							 ", ".join(offenders)))


class ActionInitAnsiTest(unittest.TestCase):
	"""action.main() must enable ANSI before it resolves capabilities.

	A Windows console without VT processing prints literal ESC[...m codes, so the
	console bootstrap has to run once before the first detect() call. The shared
	recorder pins both the count and the order.
	"""

	def test_main_inits_ansi_once_before_first_detect(self):
		import action as action_module
		events = []
		real_detect = tui.detect

		def record_init_ansi():
			events.append("init_ansi")

		def record_detect(*args, **kwargs):
			events.append("detect")
			return real_detect(*args, **kwargs)

		with mock.patch.dict(os.environ, clean_env(), clear=True), \
				mock.patch.object(sys, "argv", ["action.py"]), \
				mock.patch.object(action_module, "load_actions", return_value={}), \
				mock.patch.object(action_module, "list_actions"), \
				mock.patch.object(tui, "init_ansi", side_effect=record_init_ansi), \
				mock.patch.object(tui, "detect", side_effect=record_detect):
			action_module.main()

		self.assertEqual(events.count("init_ansi"), 1,
						 "main() did not call tui.init_ansi() exactly once")
		self.assertIn("detect", events, "main() never resolved capabilities")
		self.assertLess(events.index("init_ansi"), events.index("detect"),
						"tui.init_ansi() must run before the first tui.detect()")


class ScreensaverMenuTest(unittest.TestCase):
	"""The menu decodes keys through tui.keys; a real terminal smoke is owed."""

	class Stream:
		def __init__(self, tty=True):
			self._buffer = io.StringIO()
			self._tty = tty

		def write(self, text):
			return self._buffer.write(text)

		def flush(self):
			pass

		def isatty(self):
			return self._tty

		def getvalue(self):
			return self._buffer.getvalue()

	def setUp(self):
		import screensaver as module
		self.screensaver = module

	def test_step_wraps_up_and_down(self):
		self.assertEqual(self.screensaver.menu_step(3, 0, "up"), ("move", 2))
		self.assertEqual(self.screensaver.menu_step(3, 2, "down"), ("move", 0))
		self.assertEqual(self.screensaver.menu_step(3, 1, "up"), ("move", 0))

	def test_step_enter_selects_and_escape_exits(self):
		self.assertEqual(self.screensaver.menu_step(3, 1, "enter"),
						 ("select", 1))
		for key in ("esc", "ctrl-c"):
			self.assertEqual(self.screensaver.menu_step(3, 1, key),
							 ("exit", 1))

	def test_step_unknown_key_redraws_in_place(self):
		self.assertEqual(self.screensaver.menu_step(3, 1, "x"), ("move", 1))
		self.assertEqual(self.screensaver.menu_step(3, 1, None), ("move", 1))

	def test_step_digit_selects_the_row_it_labels(self):
		self.assertEqual(self.screensaver.menu_step(3, 0, "2"), ("select", 1))
		self.assertEqual(self.screensaver.menu_step(3, 2, "1"), ("select", 0))
		self.assertEqual(self.screensaver.menu_step(3, 0, "3"), ("select", 2))

	def test_step_out_of_range_digit_redraws_in_place(self):
		self.assertEqual(self.screensaver.menu_step(3, 1, "4"), ("move", 1))
		self.assertEqual(self.screensaver.menu_step(3, 1, "0"), ("move", 1))

	def test_select_returns_the_file_through_the_decoded_keys(self):
		stream = self.Stream()
		keys = iter(["down", "enter"])
		with mock.patch.object(sys, "stdout", stream), \
				mock.patch.object(tui.keys, "read_key",
								  side_effect=lambda *a, **k: next(keys)), \
				mock.patch.object(tui.keys, "raw_mode",
								  return_value=contextlib.nullcontext()):
			chosen = self.screensaver.get_menu_selection(
				["alpha.screensaver", "beta.screensaver"])
		self.assertTrue(chosen.endswith("beta.screensaver"), chosen)
		self.assertIn(tui.screen.CURSOR_HIDE, stream.getvalue())
		self.assertIn(tui.screen.ALT_SCREEN_ON, stream.getvalue())

	def test_escape_leaves_with_status_zero_and_restores_the_cursor(self):
		stream = self.Stream()
		with mock.patch.object(sys, "stdout", stream), \
				mock.patch.object(tui.keys, "read_key", return_value="esc"), \
				mock.patch.object(tui.keys, "raw_mode",
								  return_value=contextlib.nullcontext()):
			with self.assertRaises(SystemExit) as caught:
				self.screensaver.get_menu_selection(["alpha.screensaver"])
		self.assertEqual(caught.exception.code, 0)
		out = stream.getvalue()
		self.assertIn(tui.screen.CURSOR_SHOW, out)
		self.assertIn(tui.screen.ALT_SCREEN_OFF, out)


class KeygenMarkerTests(unittest.TestCase):
	"""The picker pointer must survive a legacy codepage.

	`cap.unicode` only proves the box glyphs encode. cp437/cp850 draw boxes but
	cannot take U+25B6, so the old unconditional marker raised
	`UnicodeEncodeError` inside the picker; the ASCII `>` is the fallback.
	"""

	def cap(self, unicode=True):
		return mock.Mock(unicode=unicode, plain=False, level="256")

	def test_utf8_stream_keeps_the_pointer(self):
		stream = mock.Mock(encoding="utf-8")
		self.assertEqual(keygen.marker_for(stream, self.cap()), "\u25b6")

	def test_legacy_codepage_falls_back_to_ascii(self):
		stream = mock.Mock(encoding="cp437")
		self.assertEqual(keygen.marker_for(stream, self.cap()), ">")

	def test_no_unicode_capability_falls_back_to_ascii(self):
		stream = mock.Mock(encoding="utf-8")
		self.assertEqual(keygen.marker_for(stream, self.cap(unicode=False)), ">")

	def test_unknown_encoding_falls_back_to_ascii(self):
		stream = mock.Mock(encoding="no-such-codec")
		self.assertEqual(keygen.marker_for(stream, self.cap()), ">")

	def test_stream_without_an_encoding_falls_back_to_ascii(self):
		stream = mock.Mock(spec=["write"])
		self.assertEqual(keygen.marker_for(stream, self.cap()), ">")


if __name__ == "__main__":
	unittest.main()
