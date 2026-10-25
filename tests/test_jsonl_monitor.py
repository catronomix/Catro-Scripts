# Regression tests for the live JSONL monitor after the tui migration
"""
			JSONL MONITOR MIGRATION TESTS
			==============================
Pins the three things the migration changed for `jsonl_monitor.py` without
touching its span/diff engine:

	- a non-interactive run is refused with the contract's exact one-line
	  message, exit code 2, an empty stdout and no terminal escapes;
	- the legend and the row/full-screen renderers take every colour and glyph
	  from `tui`, so at level "none" they emit no escape code and no
	  box-drawing character, and with `CATRO_ASCII` they fall back to ASCII
	  borders while staying styled;
	- the recency ramp is derived from the active palette instead of a private
	  green-to-blue pair;
	- the source keeps no private escape sequences.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402
import jsonl_monitor  # noqa: E402

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"


class FakeScreen:
	"""Records what the renderers write; no terminal, no escapes of its own."""

	def __init__(self, cols=100, rows=12):
		self.cols = cols
		self.rows = rows
		self.writes = []
		self.moves = []
		self.clears = 0

	def size(self):
		return (self.cols, self.rows)

	def move(self, x, y):
		self.moves.append((x, y))

	def write(self, text):
		self.writes.append(text)

	def clear(self):
		self.clears += 1

	def flush(self):
		pass

	def poll_resize(self):
		return False


def no_colour_cap():
	"""Level "none", ASCII glyphs: the strictest no-escape capability set."""
	return tui.detect(stream=io.StringIO(),
					  environ={"NO_COLOR": "1", "CATRO_ASCII": "1"})


def write_jsonl(directory):
	"""One nanobot-chat event file the monitor can parse and display."""
	path = os.path.join(directory, "session-a.jsonl")
	with open(path, "w", encoding="utf-8") as handle:
		for record in (
			{"turn_phase": "user", "text": "hello"},
			{"turn_phase": "answer", "event": "message", "text": "world"},
		):
			handle.write(json.dumps(record) + "\n")
	return path


def populated_monitor(directory):
	monitor = jsonl_monitor.Monitor("nanobot-chat", directory)
	monitor.poll_files()
	return monitor


class PipeRefusalTests(unittest.TestCase):
	"""A piped run must refuse cleanly, never emit a half-styled screen."""

	def test_non_tty_run_is_one_plain_line(self):
		proc = subprocess.run(
			[sys.executable, "-B", str(REPO / "jsonl_monitor.py")],
			cwd=str(REPO),
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			env=dict(os.environ, PYTHONIOENCODING="utf-8"),
			timeout=60,
		)
		stderr = proc.stderr.decode("utf-8", "replace")
		self.assertEqual(proc.returncode, 2, stderr)
		self.assertEqual(proc.stdout, b"")
		self.assertIn("[Error] jsonl_monitor needs an interactive terminal "
					  "(stdin/stdout is not a tty).", stderr)
		self.assertNotIn("\x1b", stderr)
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, stderr)


class LegendTests(unittest.TestCase):
	"""The legend chrome comes from tui.banner/section, not hand-drawn boxes."""

	def test_legend_is_escape_free_without_colour(self):
		cap = no_colour_cap()
		for name in jsonl_monitor.PARSERS:
			with self.subTest(parser=name):
				lines = jsonl_monitor.legend_lines(name, cap)
				self.assertTrue(lines)
				joined = "\n".join(lines)
				self.assertNotIn("\x1b", joined)
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, joined)

	def test_legend_falls_back_to_ascii_borders_when_forced(self):
		cap = tui.detect(environ={"FORCE_COLOR": "3", "CATRO_ASCII": "1"})
		joined = "\n".join(jsonl_monitor.legend_lines("nanobot-chat", cap))
		self.assertIn("\x1b[", joined)  # styled ...
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, joined)  # ... but with ASCII borders


class RendererTests(unittest.TestCase):
	"""Row and full-screen renderers emit capability-derived codes only."""

	def test_main_rows_have_no_escapes_or_box_glyphs(self):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			screen = FakeScreen()
			jsonl_monitor.render_ui(monitor, {}, screen, no_colour_cap())

		joined = "".join(screen.writes)
		self.assertIn("session-a.jsonl", joined)
		self.assertNotIn("\x1b", joined)
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, joined)
		self.assertEqual(jsonl_monitor._marker(no_colour_cap()), "#")

	def test_fullscreen_rows_have_no_escapes_or_box_glyphs(self):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			monitor.fullscreen_file = monitor.sorted_files[0]
			screen = FakeScreen()
			jsonl_monitor.render_fullscreen_ui(monitor, {}, screen,
											   no_colour_cap())

		joined = "".join(screen.writes)
		self.assertIn("FULL VIEW", joined)
		self.assertNotIn("\x1b", joined)
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, joined)

	def test_styled_rows_use_palette_codes(self):
		cap = tui.detect(environ={"FORCE_COLOR": "3"})
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			screen = FakeScreen()
			jsonl_monitor.render_ui(monitor, {}, screen, cap)

		joined = "".join(screen.writes)
		self.assertIn("\x1b[38;2;", joined)  # true-colour prefix from tui
		self.assertIn(tui.RESET, joined)


class RecencyTests(unittest.TestCase):
	"""The freshness ramp is the palette's success -> background fade."""

	def test_endpoints_come_from_the_palette(self):
		colours = tui.palette.palette("soft")
		self.assertEqual(jsonl_monitor.get_recency_color(0, colours),
						 jsonl_monitor._hex(colours["success"]))
		self.assertEqual(jsonl_monitor.get_recency_color(500, colours),
						 jsonl_monitor._hex(colours["bg"]))

	def test_ramp_moves_between_the_endpoints(self):
		colours = tui.palette.palette("soft")
		mid = jsonl_monitor.get_recency_color(62.5, colours)
		fresh = jsonl_monitor._hex(colours["success"])
		cold = jsonl_monitor._hex(colours["bg"])
		for channel, low, high in zip(mid, cold, fresh):
			self.assertGreaterEqual(channel, min(low, high))
			self.assertLessEqual(channel, max(low, high))

	def test_other_theme_gets_its_own_ramp(self):
		light = tui.palette.palette("contrast-light")
		self.assertEqual(jsonl_monitor.get_recency_color(500, light),
						 jsonl_monitor._hex(light["bg"]))
		self.assertNotEqual(jsonl_monitor.get_recency_color(0, light),
							jsonl_monitor.get_recency_color(0,
															tui.palette.palette("soft")))


class SourceTests(unittest.TestCase):
	"""The script must not keep a private escape layer."""

	def test_source_has_no_private_escape_sequences(self):
		source = (REPO / "jsonl_monitor.py").read_text(encoding="utf-8")
		self.assertNotIn("\\033", source)
		self.assertNotIn("\\x1b", source)
		self.assertNotIn("\\u001b", source)
		self.assertNotIn("isatty", source)
		self.assertNotIn("msvcrt", source)
		self.assertNotIn("termios", source)


if __name__ == "__main__":
	unittest.main()
