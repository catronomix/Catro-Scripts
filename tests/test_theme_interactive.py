# Theme and degradation pins for the themed interactive interfaces
"""
		THEMED INTERACTIVE INTERFACES
		==============================
The stdin/stdout interfaces (keygen, jsonl_monitor, netconfig) paint their page
from the shared palette. This pins the three things that makes visible:

	- `CATRO_THEME` changes the bytes each interface emits (the theme is not
	  baked into the script), and the page background comes from
	  `tui.Screen.fill` / the chrome bands;
	- the same interfaces degrade: `NO_COLOR` on a tty drops every escape but
	  keeps the layout, and a pipe gets no escapes and no box glyphs at all;
	- keygen's picker keys, wrap, cancel and length rules are unchanged by the
	  repaint.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
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

import tui  # noqa: E402
import jsonl_monitor  # noqa: E402
import keygen  # noqa: E402
import netconfig  # noqa: E402
from support import clean_env, module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"
THEMES = ("soft", "contrast-light")


class FakeScreen:
	"""A screen that records writes; `fill` marks the painted background."""

	def __init__(self, cols=100, rows=24, tty=True, encoding="utf-8"):
		self.cols = cols
		self.rows = rows
		self._tty = tty
		self.encoding = encoding
		self.writes = []

	def write(self, text):
		self.writes.append(str(text))

	def flush(self):
		pass

	def fill(self, role="bg"):
		if self._tty:
			self.writes.append("<fill:{}>".format(role))
		return self

	def clear(self):
		self.writes.append("<clear>")
		return self

	def move(self, x, y):
		return self

	def size(self):
		return (self.cols, self.rows)

	def poll_resize(self):
		return False

	def isatty(self):
		return self._tty

	def getvalue(self):
		return "".join(self.writes)


def tty_cap(stream=None, **environ):
	"""A styled tty capability set with the given environment switches."""
	return tui.detect(stream=stream or FakeScreen(),
					  environ=dict({"FORCE_COLOR": "3"}, **environ))


class ThemeTests(unittest.TestCase):
	"""`CATRO_THEME` must reach every interface's bytes."""

	def themed(self, theme, render):
		with mock.patch.dict(os.environ, clean_env(CATRO_THEME=theme),
							 clear=True):
			return render()

	def test_keygen_picker_changes_bytes_per_theme(self):
		def render():
			stream = FakeScreen()
			cap = tty_cap(stream)
			with mock.patch.object(keygen, "read_key", return_value="esc"):
				keygen.choose_algorithm(stream, cap, 0)
			return stream.getvalue()

		soft = self.themed("soft", render)
		light = self.themed("contrast-light", render)
		self.assertNotEqual(soft, light, "the picker ignored CATRO_THEME")
		for output in (soft, light):
			self.assertIn("\x1b[48;2;", output)  # themed background bands
			self.assertIn("<fill:bg>", output)   # full-page background paint

	def test_jsonl_monitor_changes_bytes_per_theme(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "session-a.jsonl")
			with open(path, "w", encoding="utf-8") as handle:
				handle.write(json.dumps({"turn_phase": "user", "text": "hi"}) + "\n")
			monitor = jsonl_monitor.Monitor("nanobot-chat", directory)
			monitor.poll_files()

			def render():
				screen = FakeScreen(cols=100, rows=14)
				jsonl_monitor.render_ui(monitor, {}, screen, tty_cap(screen))
				return screen.getvalue()

			soft = self.themed("soft", render)
			light = self.themed("contrast-light", render)
		self.assertIn("session-a.jsonl", tui.strip_ansi(soft))
		self.assertNotEqual(soft, light, "the monitor ignored CATRO_THEME")

	def test_netconfig_menu_changes_bytes_per_theme(self):
		cap = tty_cap()

		def render():
			return netconfig.menu(["Switch to DHCP", "Quit"], cap)

		soft = self.themed("soft", render)
		light = self.themed("contrast-light", render)
		self.assertIn("1. Switch to DHCP", tui.strip_ansi(soft))
		self.assertNotEqual(soft, light, "the menu ignored CATRO_THEME")

	def test_jsonl_legend_changes_bytes_per_theme(self):
		cap = tty_cap()
		soft = self.themed(
			"soft", lambda: "\n".join(jsonl_monitor.legend_lines("nanobot-chat", cap)))
		light = self.themed(
			"contrast-light",
			lambda: "\n".join(jsonl_monitor.legend_lines("nanobot-chat", cap)))
		self.assertIn("LEGEND", tui.strip_ansi(soft))
		self.assertNotEqual(soft, light)


class DegradationTests(unittest.TestCase):
	"""NO_COLOR keeps the layout; a pipe gets no escapes and no glyphs."""

	def test_keygen_no_colour_keeps_the_layout_without_escapes(self):
		stream = FakeScreen()
		cap = tui.detect(stream=stream, environ={"NO_COLOR": "1"})
		with mock.patch.object(keygen, "read_key", return_value="esc"):
			keygen.choose_algorithm(stream, cap, 2)
		output = stream.getvalue()
		self.assertNotIn("\x1b", output)
		# Level "none" on a tty is the mirror image of a pipe: the frame and the
		# padding stay, only the escapes go.
		self.assertIn("\u2500", output)
		self.assertIn("1. ", output)
		self.assertIn("HEX", output)

	def test_keygen_pipe_is_plain_text(self):
		stream = FakeScreen(tty=False)
		cap = tui.detect(stream=stream, environ={"NO_COLOR": "1"})
		self.assertTrue(cap.plain)
		with mock.patch.object(keygen, "read_key", return_value="esc"):
			keygen.choose_algorithm(stream, cap, 0)
		output = stream.getvalue()
		self.assertNotIn("\x1b", output)
		self.assertNotIn("<fill", output)  # no background escapes off a tty
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, output)

	def test_netconfig_pipe_menu_is_numbered_records(self):
		cap = tui.detect(stream=io.StringIO(), environ={"NO_COLOR": "1"})
		output = netconfig.menu(["eth0", "Quit"], cap)
		self.assertEqual(output, "1. eth0\n2. Quit")

	def test_16_colour_drops_truecolour_but_keeps_the_frame(self):
		stream = FakeScreen()
		cap = tui.detect(stream=stream, environ={"CATRO_COLOR": "16"})
		with mock.patch.object(keygen, "read_key", return_value="esc"):
			keygen.choose_algorithm(stream, cap, 0)
		output = stream.getvalue()
		self.assertNotIn("\x1b[38;2;", output)
		self.assertIn("\x1b[", output)


class KeygenRulesTests(unittest.TestCase):
	"""The repaint must not touch the picker/length rules."""

	def test_picker_wraps_and_confirms(self):
		stream = FakeScreen()
		cap = tty_cap(stream)
		keys = iter(["up", "enter"])
		with mock.patch.object(keygen, "read_key",
							   side_effect=lambda: next(keys)):
			picked = keygen.choose_algorithm(stream, cap, 0)
		self.assertEqual(picked, len(keygen.ALGORITHMS) - 1)

	def test_picker_cancel_returns_none(self):
		stream = FakeScreen()
		with mock.patch.object(keygen, "read_key", return_value="q"):
			self.assertIsNone(
				keygen.choose_algorithm(stream, tty_cap(stream), 3))

	def test_length_editor_accepts_digits_and_rejects_out_of_range(self):
		stream = FakeScreen()
		cap = tty_cap(stream)
		keys = iter(["9", "9", "9", "9", "enter",         # 9999: rejected
					 "1", "2", "enter"])                    # 12: accepted
		with mock.patch.object(keygen, "read_key",
							   side_effect=lambda: next(keys)):
			self.assertEqual(keygen.prompt_length(stream, cap), 12)

	def test_length_editor_cancels_on_escape(self):
		stream = FakeScreen()
		with mock.patch.object(keygen, "read_key", return_value="esc"):
			self.assertIsNone(keygen.prompt_length(stream, tty_cap(stream)))


if __name__ == "__main__":
	unittest.main()
