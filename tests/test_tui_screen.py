# Screen and canvas tests
"""
		FULL-SCREEN PRIMITIVES
		=======================
`Screen` must be inert off a tty and idempotent on exit; `Canvas` must clip
draws, pad its grid, resize on clear() and support both a full repaint and a
changed-cell diff. "Terminal size" is patched, so no test needs a real terminal.
"""

import io
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation, repaint_errors  # noqa: E402  (test helper)

setUpModule, tearDownModule = module_isolation()

from tui import canvas as canvas_module  # noqa: E402
from tui import screen  # noqa: E402  (import after sys.path setup)


class FakeStream:
	def __init__(self, tty=True, encoding="utf-8"):
		self._buffer = io.StringIO()
		self.encoding = encoding
		self._tty = tty

	def write(self, text):
		return self._buffer.write(text)

	def getvalue(self):
		return self._buffer.getvalue()

	def flush(self):
		pass

	def isatty(self):
		return self._tty

	def fileno(self):
		raise io.UnsupportedOperation("fake stream has no file descriptor")


class ScreenTests(unittest.TestCase):
	def test_enter_and_exit_write_the_lifecycle_codes(self):
		stream = FakeStream(True)
		lifecycle = screen.Screen(stream)
		lifecycle.enter()
		self.assertTrue(lifecycle.entered)
		self.assertEqual(stream.getvalue(),
						 screen.ALT_SCREEN_ON + screen.CURSOR_HIDE + screen.CLEAR_HOME)
		lifecycle.exit()
		self.assertFalse(lifecycle.entered)
		self.assertEqual(stream.getvalue()[-len(screen.ALT_SCREEN_OFF) - len(screen.CURSOR_SHOW)
										 - len(screen.SGR_RESET):],
						 screen.CURSOR_SHOW + screen.SGR_RESET + screen.ALT_SCREEN_OFF)

	def test_exit_is_idempotent(self):
		stream = FakeStream(True)
		lifecycle = screen.Screen(stream)
		lifecycle.enter()
		lifecycle.exit()
		written = stream.getvalue()
		lifecycle.exit()
		self.assertEqual(stream.getvalue(), written)

	def test_the_alternate_screen_is_never_entered_off_a_tty(self):
		stream = FakeStream(False)
		with screen.Screen(stream) as lifecycle:
			pass
		self.assertEqual(stream.getvalue(), "")
		self.assertFalse(lifecycle.entered)

	def test_cursor_and_clear_codes(self):
		stream = FakeStream(True)
		lifecycle = screen.Screen(stream)
		lifecycle.clear().home().move(2, 3).hide_cursor().show_cursor()
		self.assertEqual(stream.getvalue(),
						 screen.CLEAR_HOME + "\033[H" + "\033[4;3H"
						 + screen.CURSOR_HIDE + screen.CURSOR_SHOW)

	def test_poll_resize_reports_a_change_once(self):
		stream = FakeStream(True)
		with mock.patch.object(screen, "terminal_size", lambda stream=None: (80, 24)):
			lifecycle = screen.Screen(stream)
			self.assertEqual(lifecycle.size(), (80, 24))
			self.assertFalse(lifecycle.poll_resize())
		with mock.patch.object(screen, "terminal_size", lambda stream=None: (100, 30)):
			self.assertTrue(lifecycle.poll_resize())
			self.assertFalse(lifecycle.poll_resize())


class CanvasTests(unittest.TestCase):
	def make(self, width=10, height=4):
		return screen.Canvas(width=width, height=height, stream=FakeStream(True))

	def test_draw_char_clips_out_of_bounds(self):
		canvas = self.make()
		canvas.draw_char(-1, 0, "x")
		canvas.draw_char(0, -1, "x")
		canvas.draw_char(10, 0, "x")
		canvas.draw_char(0, 4, "x")
		self.assertEqual(canvas.region(0, 0, 10, 4), [" " * 10] * 4)

	def test_draw_text_stops_at_the_right_edge(self):
		canvas = self.make()
		canvas.draw_text(8, 1, "abcdef")
		self.assertEqual(canvas.region(0, 1, 10, 1), ["        ab"])

	def test_region_is_a_clipped_snapshot(self):
		canvas = self.make()
		canvas.draw_text(0, 0, "hello")
		self.assertEqual(canvas.region(1, 0, 3, 1), ["ell"])
		self.assertEqual(canvas.region(-2, -2, 4, 3), ["he"])
		self.assertEqual(canvas.region(9, 3, 5, 5), [" "])

	def test_hvline_and_box(self):
		canvas = self.make(6, 5)
		canvas.box(0, 0, 4, 3)
		self.assertEqual(canvas.region(0, 0, 4, 3), [
			"\u250c\u2500\u2500\u2510",
			"\u2502  \u2502",
			"\u2514\u2500\u2500\u2518",
		])

	def test_clear_resizes_when_the_terminal_changes(self):
		canvas = self.make()
		with mock.patch.object(canvas_module, "terminal_size", lambda stream=None: (6, 3)):
			canvas.clear()
		self.assertEqual((canvas.width, canvas.height), (6, 3))
		self.assertEqual(len(canvas.region(0, 0, 6, 3)), 3)

	def test_clear_keeps_the_size_and_blanks_the_grid(self):
		canvas = self.make()
		canvas.draw_text(0, 0, "data")
		with mock.patch.object(canvas_module, "terminal_size", lambda stream=None: (10, 4)):
			canvas.clear()
		self.assertEqual((canvas.width, canvas.height), (10, 4))
		self.assertEqual(canvas.region(0, 0, 10, 1), [" " * 10])

	def test_full_render_frames_the_grid(self):
		stream = FakeStream(True)
		canvas = screen.Canvas(width=3, height=2, stream=stream)
		canvas.draw_char(0, 0, "a", "\033[31m")
		canvas.render()
		frame = stream.getvalue()
		self.assertTrue(frame.startswith("\033[H"))
		self.assertEqual(frame.count("\n"), 1)
		self.assertIn("\033[31m", frame)
		self.assertIn("\033[31ma\033[0m", frame)

	def test_diff_render_writes_nothing_when_unchanged(self):
		stream = FakeStream(True)
		canvas = screen.Canvas(width=3, height=2, stream=stream)
		canvas.render()
		stream._buffer.seek(0)
		stream._buffer.truncate()
		canvas.render(full=False)
		self.assertEqual(stream.getvalue(), "")

	def test_diff_render_moves_only_to_changed_cells(self):
		stream = FakeStream(True)
		canvas = screen.Canvas(width=3, height=2, stream=stream)
		canvas.render()
		stream._buffer.seek(0)
		stream._buffer.truncate()
		canvas.draw_char(2, 1, "z")
		canvas.render(full=False)
		self.assertEqual(stream.getvalue(), "\033[2;3H\033[0mz\033[0m")

	def test_diff_render_batches_a_contiguous_run_into_one_cursor_move(self):
		stream = FakeStream(True)
		canvas = screen.Canvas(width=12, height=3, stream=stream)
		canvas.render()
		stream._buffer.seek(0)
		stream._buffer.truncate()
		canvas.draw_text(2, 0, "abcd", "\033[31m")
		canvas.draw_text(0, 2, "xy")
		canvas.render(full=False)
		frame = stream.getvalue()
		moves = re.findall(r"\033\[(\d+);(\d+)H", frame)
		self.assertEqual(moves, [("1", "3"), ("3", "1")])
		self.assertEqual(frame.count("\033[31m"), 1)
		self.assertEqual(frame.count("abcd"), 1)
		self.assertNotIn("\033[1;1H", frame)

	def test_colors_are_raw_ansi_strings(self):
		canvas = self.make()
		canvas.draw_char(0, 0, "q", "\033[7m")
		self.assertEqual(canvas._colors[0][0], "\033[7m")


class FillTests(unittest.TestCase):
	"""`Screen.fill()` paints the page background, or writes nothing at all."""

	def run_fill(self, level="true", tty=True, size=(6, 3), role="bg"):
		stream = FakeStream(tty)
		cap = screen.caps.Capabilities(level=level, unicode=True, width=None,
									   isatty=tty, plain=False, reason="test")
		with mock.patch.object(screen.caps, "detect", return_value=cap), \
				mock.patch.object(screen, "terminal_size", lambda stream=None: size):
			lifecycle = screen.Screen(stream)
			result = lifecycle.fill(role)
		self.assertIs(result, lifecycle)
		return stream.getvalue()

	def test_every_row_is_painted_with_the_background(self):
		row = "\033[48;2;27;23;38m" + " " * 6 + "\033[0m"
		self.assertEqual(self.run_fill(), screen.CLEAR_HOME + "\n".join([row] * 3))

	def test_role_is_a_palette_key(self):
		self.assertIn("\033[48;2;41;34;56m", self.run_fill(role="surface"))

	def test_nothing_is_written_off_a_tty(self):
		self.assertEqual(self.run_fill(tty=False), "")

	def test_nothing_is_written_at_level_none(self):
		self.assertEqual(self.run_fill(level="none"), "")

	def test_level_sixteen_uses_the_basic_background_code(self):
		out = self.run_fill(level="16")
		self.assertIn("\033[40m", out)
		self.assertNotIn("48;2", out)


class TerminalRendererTests(unittest.TestCase):
	def test_old_screensaver_api_is_kept(self):
		renderer = screen.TerminalRenderer(stream=FakeStream(True))
		self.assertIsInstance(renderer.width, int)
		self.assertIsInstance(renderer.height, int)
		renderer.clear()
		renderer.draw_char(0, 0, "@", "\033[32m")
		renderer.draw_text(1, 1, "ok")
		renderer.render()
		renderer.clear()
		self.assertIsInstance(renderer, screen.Canvas)

	def test_clears_to_spaces(self):
		renderer = screen.TerminalRenderer(stream=FakeStream(True))
		renderer.draw_text(0, 0, "abc")
		renderer.clear()
		self.assertEqual(renderer.region(0, 0, renderer.width, 1), [" " * renderer.width])
class SplitShimTests(unittest.TestCase):
	"""The emission layer moved to `tui.canvas`; the old paths must still win."""

	def test_the_moved_names_still_resolve_through_the_screen_module(self):
		for name in ("Canvas", "TerminalRenderer", "SGR_RESET", "terminal_size"):
			with self.subTest(name=name):
				self.assertIs(getattr(screen, name), getattr(canvas_module, name))

	def test_the_screensaver_name_is_still_a_canvas_subclass(self):
		self.assertTrue(issubclass(canvas_module.TerminalRenderer, canvas_module.Canvas))


class RepaintStyleTests(unittest.TestCase):
	"""A repaint is absolute: no cell may inherit the cell painted before it.

	`repaint_errors()` replays the emitted bytes through an SGR state machine,
	so these tests fail on the stale-tint leak (a run with only a foreground
	code after a reverse run) even though every cell's *bytes* were re-emitted.
	"""

	FG = "\033[38;2;212;200;235m"
	FOCUS = FG + "\033[48;2;27;23;38m\033[7m"

	def canvas(self, width=10, height=3):
		return screen.Canvas(width, height, stream=FakeStream(True))

	def drain(self, canvas):
		"""Throw the bytes rendered so far away; returns the stream."""
		canvas.stream._buffer.seek(0)
		canvas.stream._buffer.truncate()
		return canvas.stream

	def test_an_up_move_restores_the_vacated_row(self):
		canvas = self.canvas()
		canvas.draw_text(0, 0, "alpha", self.FG)
		canvas.draw_text(0, 1, "beta ", self.FG)
		canvas.draw_text(0, 2, "gamma", self.FOCUS)
		canvas.render()
		stream = self.drain(canvas)
		# The selection moved from row 3 to row 2: row 3 is now a plain row and
		# comes after the focused run, which is where the leak used to land.
		canvas.draw_text(0, 0, "alpha", self.FG)
		canvas.draw_text(0, 1, "beta ", self.FOCUS)
		canvas.draw_text(0, 2, "gamma", self.FG)
		canvas.render(full=False)
		frame = stream.getvalue()
		self.assertEqual(repaint_errors(canvas, frame), [])
		self.assertIn("\033[3;1H" + screen.SGR_RESET + self.FG, frame)

	def test_a_down_move_keeps_the_bytes_it_always_emitted(self):
		canvas = self.canvas()
		canvas.draw_text(0, 0, "alpha", self.FG)
		canvas.draw_text(0, 1, "beta ", self.FOCUS)
		canvas.draw_text(0, 2, "gamma", self.FG)
		canvas.render()
		stream = self.drain(canvas)
		canvas.draw_text(0, 1, "beta ", self.FG)
		canvas.draw_text(0, 2, "gamma", self.FOCUS)
		canvas.render(full=False)
		self.assertEqual(stream.getvalue(),
						 "\033[2;1H" + self.FG + "beta "
						 + "\033[3;1H" + self.FOCUS + "gamma"
						 + screen.SGR_RESET)

	def test_a_full_frame_never_inherits_a_mid_frame_reverse(self):
		canvas = self.canvas(6, 3)
		canvas.draw_text(0, 0, "aaaaaa", self.FG)
		canvas.draw_text(0, 1, "bbbbbb", self.FOCUS)
		canvas.draw_text(0, 2, "cccccc", self.FG)
		canvas.render()
		frame = canvas.stream.getvalue()
		self.assertTrue(frame.startswith("\033[H"))
		self.assertEqual(repaint_errors(canvas, frame), [])
		self.assertIn("\033[0m" + self.FG + "cccccc", frame)

	def test_a_colour_shared_by_two_runs_is_emitted_once(self):
		# Pure-foreground churn must stay byte-identical: no reset is owed when
		# the next run wants everything that is already active.
		canvas = self.canvas()
		canvas.render()
		canvas.draw_text(0, 0, "aa", self.FG)
		canvas.draw_text(0, 1, "bb", self.FG)
		stream = self.drain(canvas)
		canvas.render(full=False)
		frame = stream.getvalue()
		self.assertEqual(frame.count(self.FG), 1)
		self.assertNotIn(screen.SGR_RESET + self.FG, frame)
		self.assertEqual(repaint_errors(canvas, frame), [])

	def test_redrawing_an_unchanged_run_writes_nothing(self):
		canvas = self.canvas()
		canvas.draw_text(0, 1, "beta ", self.FOCUS)
		canvas.render()
		stream = self.drain(canvas)
		canvas.draw_text(0, 1, "beta ", self.FOCUS)
		canvas.render(full=False)
		self.assertEqual(stream.getvalue(), "")


if __name__ == "__main__":
	unittest.main()
