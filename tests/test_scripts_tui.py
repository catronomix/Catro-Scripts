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

Run with:
	python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
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
from support import clean_env  # noqa: E402  (test helper, not production)


def cap16():
	return tui.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")


class HelpIndentStylesTest(unittest.TestCase):
	"""help.py's indentation mapping is data passed to tui.style()."""

	def setUp(self):
		import help as help_module
		self.help = help_module

	def test_each_level_keeps_its_16_colour_code(self):
		expected = ["\033[37m", "\033[36m", "\033[32m", "\033[33m", "\033[31m"]
		self.assertEqual(len(self.help.INDENT_STYLES), len(expected))
		for level, code in enumerate(expected):
			styled = tui.style("x", cap=cap16(),
							   **self.help.INDENT_STYLES[level])
			self.assertIn(code, styled,
						  "indentation level {} lost its {} code: {!r}".format(
							  level, code, styled))
			self.assertTrue(styled.endswith("x" + tui.RESET))

	def test_level_zero_is_still_bold(self):
		styled = tui.style("x", cap=cap16(), **self.help.INDENT_STYLES[0])
		self.assertIn("\033[1m", styled)


class CountRainbowTest(unittest.TestCase):
	"""count.py's rainbow is data passed to tui.style()."""

	def test_each_row_keeps_its_16_colour_code(self):
		import count as count_module
		expected = ["\033[91m", "\033[33m", "\033[93m", "\033[92m",
					"\033[96m", "\033[94m", "\033[95m"]
		self.assertEqual(len(count_module.RAINBOW), len(expected))
		for code, colour in zip(expected, count_module.RAINBOW):
			styled = tui.style("x", fg=colour, cap=cap16())
			self.assertIn(code, styled,
						  "{} lost its {} code: {!r}".format(colour, code, styled))


class NoPrivateAnsiTest(unittest.TestCase):
	"""The gate: migrated scripts only style through tui."""

	# Phase A scripts migrated onto tui/; Phase B scripts (keygen, mdreader, ...)
	# join this list when they migrate.
	MIGRATED = ("list.py", "help.py", "action.py", "count.py",
				"opencode.py", "sanitize.py", "screensaver.py")

	def test_migrated_scripts_have_no_private_ansi(self):
		for name in self.MIGRATED:
			source = (REPO / name).read_text(encoding="utf-8")
			self.assertNotIn("\\033", source,
							 "{} still hardcodes an escape sequence".format(name))
			self.assertNotIn("class Colors", source,
							 "{} still has a private Colors class".format(name))


class ListNoColorTest(unittest.TestCase):
	"""A monochrome tty keeps the table; a monochrome pipe stays plain."""

	class Stream:
		"""Minimal tty-able stdout: writes are captured, no file descriptor."""

		def __init__(self, tty, encoding="utf-8"):
			self._buffer = io.StringIO()
			self._tty = tty
			self.encoding = encoding

		def write(self, text):
			return self._buffer.write(text)

		def flush(self):
			pass

		def getvalue(self):
			return self._buffer.getvalue()

		def isatty(self):
			return self._tty

		def fileno(self):
			raise io.UnsupportedOperation("no file descriptor")

	def render(self, tty, environ=None):
		import importlib
		list_module = importlib.import_module("list")
		stream = self.Stream(tty)
		env = {key: value for key, value in clean_env().items()
			   if key not in ("TERM", "COLORTERM")}
		env.update(environ or {"NO_COLOR": "1"})
		with mock.patch.dict(os.environ, env, clear=True), \
				mock.patch.object(tui, "init_ansi"), \
				mock.patch.object(sys, "stdout", stream):
			list_module.list_scripts()
		return stream.getvalue()

	def test_no_color_tty_still_draws_the_box(self):
		out = self.render(tty=True)
		self.assertIn("\u250c", out, "a monochrome tty lost the top border:\n" + out[:400])
		self.assertIn("\u2502", out)
		self.assertIn("ID", out)
		self.assertNotIn("\x1b", out, "NO_COLOR output still carries escapes")
		self.assertNotIn("\t", out, "a tty degraded to TAB records")
		self.assertIn("Total scripts found:", out)

	def test_no_color_zero_still_disables_colour(self):
		# no-color.org: any non-empty value means no colour, "0" included.
		out = self.render(tty=True, environ={"NO_COLOR": "0"})
		self.assertNotIn("\x1b", out)
		self.assertIn("\u250c", out)

	def test_ascii_glyphs_when_unicode_is_decided_off(self):
		# A tty is where caps.unicode is the deciding factor: at a pipe the box
		# is stripped because the layout is plain, not because of unicode, so a
		# pipe test cannot tell the two apart. CATRO_ASCII on a tty must keep
		# the box and swap its glyphs for ASCII equivalents.
		out = self.render(tty=True, environ={"CATRO_ASCII": "1"})
		self.assertIn("+", out, "ASCII box corners are missing:\n" + out[:400])
		self.assertIn("|", out)
		for glyph in "\u2500\u2502\u250c\u2510\u2514\u2518":
			self.assertNotIn(glyph, out, "CATRO_ASCII left a unicode glyph")
		self.assertIn("ID", out)
		self.assertIn("Total scripts found:", out)

	def test_forced_colour_pipe_gets_the_full_styled_table(self):
		# Contract invariant 2 (amended): an explicit request on a pipe turns
		# plain OFF, so the pipe gets borders, padding and zebra rows - not bare
		# TAB records with a styled banner on top.
		out = self.render(tty=False, environ={"FORCE_COLOR": "3"})
		self.assertIn("\x1b[38;2;163;146;192m\u250c", out,
					  "the top border is missing its accent colour")
		self.assertIn("\u2502", out)
		self.assertIn("\x1b[48;2;27;23;38m", out, "the zebra row lost its background")
		self.assertIn("\x1b[48;2;41;34;56m", out)
		self.assertIn(" ID   ", out, "the header lost its padding")
		self.assertNotIn("\t", out, "a forced pipe fell back to TAB records")

	def test_catro_color_16_pipe_is_decorated_with_16_colour_codes(self):
		out = self.render(tty=False, environ={"CATRO_COLOR": "16"})
		self.assertIn("\x1b[37m\u250c", out)
		self.assertNotIn("\x1b[38;2;", out, "16-colour output carried truecolor")
		self.assertNotIn("\t", out)

	def test_no_color_beats_force_color_on_a_pipe(self):
		out = self.render(tty=False,
						  environ={"FORCE_COLOR": "3", "NO_COLOR": "1"})
		self.assertNotIn("\x1b", out, "NO_COLOR lost to FORCE_COLOR on a pipe")
		self.assertIn("ID\tScript Name\tSize\tDescription", out)

	def test_no_color_pipe_stays_tab_separated(self):
		out = self.render(tty=False)
		self.assertNotIn("\x1b", out)
		for glyph in "\u2500\u2502\u250c\u2510\u2514\u2518\u253c":
			self.assertNotIn(glyph, out)
		header = "ID\tScript Name\tSize\tDescription"
		self.assertIn(header, out)
		record = out.split(header + "\n", 1)[1].splitlines()[0]
		self.assertEqual(len(record.split("\t")), 4)


class ActionPlainTableTest(unittest.TestCase):
	"""action.list_actions() keeps its layout and emits plain records in a pipe."""

	def render(self, actions):
		import action as action_module
		with tempfile.TemporaryDirectory() as td:
			path = os.path.join(td, "actions.json")
			with open(path, "w", encoding="utf-8") as handle:
				json.dump(actions, handle)
			buffer = io.StringIO()
			with mock.patch.dict(os.environ, clean_env(), clear=True), \
					mock.patch.object(action_module, "ACTIONS_FILE", path):
				with contextlib.redirect_stdout(buffer):
					action_module.list_actions()
		return buffer.getvalue()

	def records(self, out):
		lines = out.splitlines()
		start = lines.index("ID\tAction Name\tCommand\tDescription") + 1
		body = lines[start:]
		end = next(index for index, line in enumerate(body)
				   if line.startswith("Total macros saved:"))
		return body[:end]

	def test_list_actions_detects_capabilities_once(self):
		import action as action_module
		with tempfile.TemporaryDirectory() as td:
			path = os.path.join(td, "actions.json")
			with open(path, "w", encoding="utf-8") as handle:
				json.dump({"ping": {"command": "ping", "description": "x"}}, handle)
			buffer = io.StringIO()
			with mock.patch.dict(os.environ, clean_env(), clear=True), \
					mock.patch.object(action_module, "ACTIONS_FILE", path), \
					mock.patch.object(tui, "detect", wraps=tui.detect) as detect:
				with contextlib.redirect_stdout(buffer):
					action_module.list_actions()
		self.assertEqual(detect.call_count, 1,
						 "list_actions() re-detected the terminal")

	def test_pipe_is_tab_separated_without_ansi_or_glyphs(self):
		out = self.render({
			"ping": {"command": "ping 127.0.0.1", "description": "Loopback"},
		})
		records = self.records(out)
		self.assertEqual(len(records), 1, out)
		self.assertEqual(records[0].split("\t"),
						 ["1", "ping", "ping 127.0.0.1", "Loopback"])
		self.assertNotIn("\x1b", out)
		for glyph in "\u2500\u2502\u250c\u2510\u2514\u2518\u253c":
			self.assertNotIn(glyph, out)

	def test_long_cells_keep_the_table_truncation_rule(self):
		command = "x" * 40
		description = "y" * 40
		out = self.render({
			"long": {"command": command, "description": description},
		})
		fields = self.records(out)[0].split("\t")
		self.assertEqual(fields[2], "x" * 28 + "..")
		self.assertEqual(fields[3], "y" * 32 + "..")


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

	def test_draw_menu_marks_only_the_selected_row(self):
		stream = self.Stream()
		self.screensaver.draw_menu(stream, ["alpha", "beta"], 1, cap16())
		out = stream.getvalue()
		self.assertEqual(out.count("  > "), 1)
		self.assertIn("  > beta", out)
		self.assertNotIn("  > alpha", out)
		self.assertIn("Use UP/DOWN arrows", out)

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


if __name__ == "__main__":
	unittest.main()
