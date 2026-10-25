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
import re
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

# Every CSI form tui emits; anything left after this substitution that still
# contains ESC is a sequence cut mid-way (truncate() counted escape bytes).
COMPLETE_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


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


def colour_cap():
	"""True colour: the styled legend whose escapes used to be clipped."""
	return tui.detect(environ={"FORCE_COLOR": "3"})


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
	"""The legend is one closed frame built from tui glyphs and prefixes."""

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


class PlainStream:
	"""A pipe that can still encode box glyphs (probes unicode detection)."""

	encoding = "utf-8"

	def isatty(self):
		return False

	def write(self, text):
		pass

	def flush(self):
		pass


class LegendFrameTests(unittest.TestCase):
	"""One box: one top rule, one bottom rule, borders, one even width."""

	def assert_frame(self, lines, glyphs):
		self.assertTrue(lines)
		for line in lines:
			self.assertEqual(tui.display_width(line),
							 jsonl_monitor.LEGEND_WIDTH, repr(line))
		self.assertTrue(lines[0].startswith(glyphs["tl"]), lines[0])
		self.assertTrue(lines[-1].startswith(glyphs["bl"]), lines[-1])
		distinct = len({glyphs["tl"], glyphs["ml"], glyphs["bl"]}) == 3
		if distinct:  # in ASCII every rule starts with the same "+"
			self.assertEqual(
				sum(line.startswith(glyphs["tl"]) for line in lines), 1,
				"legend opened more than once")
			self.assertEqual(
				sum(line.startswith(glyphs["bl"]) for line in lines), 1,
				"legend closed more than once (stray rule after the body?)")
			self.assertGreaterEqual(
				sum(line.startswith(glyphs["ml"]) for line in lines), 1,
				"legend has no section separator")
		for line in lines[1:-1]:
			self.assertIn(line[0], (glyphs["v"], glyphs["ml"]), repr(line))
			self.assertIn(line[-1], (glyphs["v"], glyphs["mr"]), repr(line))

	def test_unicode_frame_at_level_none(self):
		cap = tui.detect(stream=PlainStream(), environ={"NO_COLOR": "1"})
		self.assertEqual(cap.level, "none")
		self.assertTrue(cap.unicode)
		glyphs = tui.table.glyphs_for(cap)
		for name in jsonl_monitor.PARSERS:
			with self.subTest(parser=name):
				lines = jsonl_monitor.legend_lines(name, cap)
				self.assert_frame(lines, glyphs)
				self.assertIn("LEGEND", lines[1])

	def test_ascii_frame_has_no_stray_rule(self):
		cap = no_colour_cap()
		glyphs = tui.table.glyphs_for(cap)
		for name in jsonl_monitor.PARSERS:
			with self.subTest(parser=name):
				lines = jsonl_monitor.legend_lines(name, cap)
				self.assert_frame(lines, glyphs)
				# In ASCII every rule is "+---+", so identity is checked by
				# adjacency instead: a second close (or a banner fragment)
				# always lands next to another rule.
				rules = [set(line) <= {"+", "-"} and "-" in line
						 for line in lines]
				self.assertTrue(rules[0])
				self.assertTrue(rules[-1])
				self.assertFalse(rules[-2], "rule stacked before the close")
				for index in range(1, len(rules) - 1):
					if rules[index]:
						self.assertFalse(rules[index - 1],
										 "two rules stacked at %d" % index)


class StatusBarTests(unittest.TestCase):
	"""Composed chrome never spills past the terminal edge."""

	def render(self, cols):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			screen = FakeScreen(cols=cols, rows=14)
			cache = {}
			jsonl_monitor.render_ui(monitor, cache, screen, no_colour_cap())
		return screen, cache

	def test_no_row_is_wider_than_the_terminal(self):
		for cols in (80, 100, 120):
			with self.subTest(cols=cols):
				screen, _ = self.render(cols)
				for line in screen.writes:
					self.assertLessEqual(tui.display_width(line), cols,
										 repr(line))
				status = [line for line in screen.writes
						  if "Parser:" in tui.strip_ansi(line)]
				self.assertEqual(len(status), 1)
				self.assertEqual(tui.display_width(status[0]), cols)

	def test_status_line_is_truncated_not_spilled(self):
		screen, _ = self.render(80)
		status = [tui.strip_ansi(line) for line in screen.writes
				  if "Parser:" in tui.strip_ansi(line)][0]
		self.assertIn("..", status)  # ellipsised to fit, not cut silently
		self.assertNotIn("Quit", status)

	def test_identical_render_writes_nothing_new(self):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			screen = FakeScreen(cols=100, rows=14)
			cache = {}
			jsonl_monitor.render_ui(monitor, cache, screen, no_colour_cap())
			first = list(screen.writes)
			jsonl_monitor.render_ui(monitor, cache, screen, no_colour_cap())
			self.assertEqual(screen.writes, first)

	def test_wide_glyphs_are_clipped_not_wrapped(self):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			active = monitor.sorted_files[0]
			# Built directly: strip_special() would drop non-ASCII input, so a
			# span is the only way a wide glyph reaches the painter here.
			monitor.files_state[active].events = [{
				"phase": "answer",
				"spans": [jsonl_monitor.Span("\u65e5" * 60,
											 fg=(255, 255, 255))],
			}]
			monitor.fullscreen_file = active
			screen = FakeScreen(cols=80, rows=14)
			jsonl_monitor.render_fullscreen_ui(monitor, {}, screen,
											   no_colour_cap())
		for line in screen.writes:
			self.assertLessEqual(tui.display_width(line), 80, repr(line))

	def test_fullscreen_footer_is_centred(self):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			monitor.fullscreen_file = monitor.sorted_files[0]
			cache = {}
			screen = FakeScreen(cols=100, rows=14)
			jsonl_monitor.render_fullscreen_ui(monitor, cache, screen,
											   no_colour_cap())
		footer = tui.strip_ansi(cache["fs_footer"])
		self.assertEqual(tui.display_width(footer), 100)
		# Balance, not "starts with a space": the old .ljust() footer also
		# ended in one, and only a centred bar has padding on both sides.
		left = len(footer) - len(footer.lstrip(" "))
		right = len(footer) - len(footer.rstrip(" "))
		self.assertGreater(left, 0, repr(footer))
		self.assertGreater(right, 0, repr(footer))
		self.assertLessEqual(abs(left - right), 1, repr(footer))


class LegendPopupTests(unittest.TestCase):
	"""A styled legend is drawn either whole or not at all.

	Clipping an already-styled legend with `tui.truncate()` counts escape bytes
	as cells: at cols < 47 the rows shrank to 10-40 cells, sequences were cut
	mid-form and the closing reset was lost, leaking the surface background.
	The overlay is optional help, so a too-narrow terminal simply skips it.
	"""

	def assert_whole_escapes(self, writes):
		for line in writes:
			self.assertNotIn(
				"\x1b", COMPLETE_ESCAPE.sub("", line),
				"escape cut mid-sequence: " + repr(line))

	def render_main(self, cols, cap):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			monitor.show_legend = True
			screen = FakeScreen(cols=cols, rows=14)
			cache = {}
			jsonl_monitor.render_ui(monitor, cache, screen, cap)
		return screen, cache

	def render_fullscreen(self, cols, cap):
		with tempfile.TemporaryDirectory() as directory:
			write_jsonl(directory)
			monitor = populated_monitor(directory)
			monitor.show_legend = True
			monitor.fullscreen_file = monitor.sorted_files[0]
			screen = FakeScreen(cols=cols, rows=14)
			cache = {}
			jsonl_monitor.render_fullscreen_ui(monitor, cache, screen, cap)
		return screen, cache

	def popup_rows(self, cache):
		return [cache[key] for key in cache
				if isinstance(key, str) and key.startswith("popup_")]

	def test_narrow_terminal_skips_the_styled_popup(self):
		for cols in (45, 46):
			for name, renderer in (("main", self.render_main),
								   ("fullscreen", self.render_fullscreen)):
				with self.subTest(cols=cols, renderer=name):
					screen, cache = renderer(cols, colour_cap())
					visible = tui.strip_ansi("".join(screen.writes))
					self.assertNotIn("COLOR LEGEND", visible)
					self.assertEqual(self.popup_rows(cache), [])
					self.assert_whole_escapes(screen.writes)
					for line in screen.writes:
						self.assertLessEqual(tui.display_width(line), cols,
											 repr(line))
					self.assertTrue(screen.writes, "monitor stopped drawing")

	def test_drawn_popup_rows_share_one_width(self):
		for cols in (47, 100):
			for name, renderer in (("main", self.render_main),
								   ("fullscreen", self.render_fullscreen)):
				with self.subTest(cols=cols, renderer=name):
					screen, cache = renderer(cols, colour_cap())
					rows = self.popup_rows(cache)
					self.assertTrue(rows, "popup missing at %d cols" % cols)
					self.assert_whole_escapes(rows)
					self.assert_whole_escapes(screen.writes)
					widths = {tui.display_width(row) for row in rows}
					self.assertEqual(widths, {jsonl_monitor.LEGEND_WIDTH},
									 repr(sorted(widths)))
					for row in rows:
						self.assertTrue(row.endswith(tui.RESET), repr(row))
						self.assertLessEqual(tui.display_width(row), cols)


if __name__ == "__main__":
	unittest.main()
