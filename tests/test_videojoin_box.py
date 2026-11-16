# Regression tests for the videojoin batch progress box
"""
			VIDEOJOIN BATCH BOX
			===================
`tui.progress.BatchBox` reuses one frame for a whole batch: every update rewrites
the same box in place (cursor up, rewrite, erase to end of line), and the box
grows to hold the outcome rows. A pipe gets one TAB record per update with no
escape and no frame glyph. The `--dir` loop passes its box into
`run_ffmpeg_join`, so the per-job header/panel blocks are folded into it.

These checks never run FFmpeg or decord: the reader and subprocess are faked.

Run with:
	python -m unittest tests.test_videojoin_box -v
"""
import io
import os
import re
import sys
import tempfile
import types
import unittest
import contextlib
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
	sys.path.append(str(TESTS))

import tui  # noqa: E402  (import after sys.path setup)
import videojoin  # noqa: E402
from support import cell_style, replay  # noqa: E402  (test helper)

TTY = tui.Capabilities(level="true", unicode=True, width=72, isatty=True,
					   plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")
NO_COLOR_TTY = tui.Capabilities(level="none", unicode=True, width=72,
								isatty=True, plain=False, reason="test")

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"
UP = re.compile(r"\x1b\[\d+A\r")
ANY_UP = re.compile(r"\x1b\[(\d+)A")


def cursor_row(text):
	"""Net vertical movement a terminal would have applied to this byte stream."""
	return text.count("\n") - sum(int(n) for n in ANY_UP.findall(text))


class BatchBoxTest(unittest.TestCase):
	"""One frame is reused, its height follows the rows, pipes stay plain."""

	def test_tty_repaints_the_same_frame_in_place(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Batch", 3, stream=out, cap=TTY)
		box.update(op="first-dir", done=0)
		box.add("ok", "first joined")
		box.update(op="second-dir", done=1)
		box.add("error", "second failed")
		box.update(op="third-dir", done=2)
		box.close("batch done")
		text = out.getvalue()

		# Six paints, five in-place rewinds: the first frame is not rewound.
		frames = UP.split(text)
		self.assertEqual(len(frames), 6)
		self.assertEqual(len(UP.findall(text)), 5)
		for frame in frames:
			self.assertEqual(frame.count("Batch"), 1,
							 "each paint draws exactly one title")
		# Height follows the rows, and the final frame keeps every outcome.
		first = [line for line in frames[0].split("\n") if line]
		last = [line for line in frames[-1].split("\n") if line]
		plain_last = tui.strip_ansi(frames[-1])
		self.assertGreater(len(last), len(first))
		self.assertIn("first joined", plain_last)
		self.assertIn("second failed", plain_last)
		self.assertIn("batch done", plain_last)
		self.assertIn("[ok]", plain_last)
		self.assertIn("[error]", plain_last)

	def test_shrinking_frame_keeps_the_rewind_in_step(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Batch", 2, stream=out, cap=TTY)
		box.update(op="dir-a", done=0, rows=[("ok", "one"), ("ok", "two")])
		self.assertEqual(cursor_row(out.getvalue()), box._lines)
		box.update(op="dir-b", done=1)                 # same height, fresh frame
		self.assertEqual(cursor_row(out.getvalue()), box._lines)
		box.update(rows=[])                            # shrink by two rows
		self.assertEqual(cursor_row(out.getvalue()), box._lines,
						 "surplus clear lines must be rewound")
		box.update(op="dir-c")                         # next paint must not drift
		self.assertEqual(cursor_row(out.getvalue()), box._lines)

	def test_narrow_terminal_is_not_widened_past_cap_width(self):
		narrow = tui.Capabilities(level="true", unicode=True, width=12,
								  isatty=True, plain=False, reason="test")
		out = io.StringIO()
		box = tui.progress.BatchBox("Batch", 1, stream=out, cap=narrow)
		box.update(op="dir-a", done=0)
		box.close("done")
		self.assertEqual(box.width, 12)
		for line in box._frame().split("\n"):
			self.assertLessEqual(tui.display_width(line), 12)

	def test_pipe_degrades_to_tab_records(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Batch", 2, stream=out, cap=PIPE)
		box.update(op="dir-a", done=0)
		box.add("ok", "first joined")
		box.update(op="dir-b", done=1)
		box.close("batch done")
		text = out.getvalue()

		self.assertNotIn("\x1b", text)
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, text)
		lines = text.strip().splitlines()
		self.assertIn("dir-a\t0/2", lines)
		self.assertIn("ok\tfirst joined", lines)
		self.assertIn("info\tbatch done", lines)
		for line in lines:
			self.assertIn("\t", line)

	def test_level_none_tty_keeps_the_frame_without_escapes(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Batch", 1, stream=out, cap=NO_COLOR_TTY)
		box.update(op="dir-a", done=0)
		self.assertEqual(out.getvalue(), "")
		box.add("ok", "first joined")
		box.close("batch done")
		text = out.getvalue()

		self.assertNotIn("\x1b", text)
		self.assertIn("[ok]", text)
		self.assertIn("batch done", text)


class FrameGroundTest(unittest.TestCase):
	"""The tty frame's whole interior sits on the panel's `bg-inside` ground."""

	def test_every_interior_cell_carries_the_panel_ground(self):
		box = tui.progress.BatchBox("Batch", 2, stream=io.StringIO(), cap=TTY)
		box.update(op="dir-a", done=1, rows=[("ok", "first joined"),
											("error", "second failed")])
		ground = cell_style(tui.palette.prefix(fg="fg", bg="bg-inside",
											   cap=TTY))[1]
		self.assertIsNotNone(ground, "the look must have a distinct interior")
		cells = replay(box._frame())
		height = max(y for _x, y in cells) + 1
		width = max(x for x, _y in cells) + 1
		for y in range(1, height - 1):
			for x in range(1, width - 1):
				self.assertEqual(
					cells[(x, y)][1][1], ground,
					"row {}, column {}: {!r}".format(y, x, cells[(x, y)]))

	def test_plain_frame_stays_unescaped(self):
		box = tui.progress.BatchBox("Batch", 1, stream=io.StringIO(), cap=PIPE)
		box.update(op="dir-a", done=0)
		self.assertNotIn("\x1b", box._frame())
		self.assertNotIn("\u2502", box._frame())


class FakeReader:
	"""Stand-in for decord.VideoReader: enough shape/fps/length to build a job."""

	def __init__(self, path):
		self.path = path

	def __getitem__(self, index):
		return types.SimpleNamespace(shape=(480, 640, 3))

	def get_avg_fps(self):
		return 30.0

	def __len__(self):
		return 30


class JoinBoxWiringTest(unittest.TestCase):
	"""`run_ffmpeg_join(box=...)` writes into the box instead of printing blocks."""

	def test_job_rows_land_in_the_box(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Batch", 1, stream=out, cap=TTY)
		done = types.SimpleNamespace(returncode=0, stderr="")
		with tempfile.TemporaryDirectory() as tmp, \
				mock.patch.object(videojoin, "VideoReader", FakeReader), \
				mock.patch.object(videojoin, "check_ffmpeg", return_value=True), \
				mock.patch.object(videojoin, "has_audio", return_value=False), \
				mock.patch.object(videojoin.subprocess, "run", return_value=done):
			ok = videojoin.run_ffmpeg_join(
				["a.mp4", "b.mp4"], False, "libx264",
				{"width": 640, "height": 480, "method": "stretch"},
				"out.mp4", TTY, working_dir=tmp, box=box)

		self.assertTrue(ok)
		kinds = [kind for kind, _ in box.rows]
		self.assertIn("ok", kinds)
		self.assertTrue([text for kind, text in box.rows if "out.mp4" in text])
		text = out.getvalue()
		self.assertIn("Executing FFmpeg", text)
		self.assertGreaterEqual(len(UP.findall(text)), 1,
								"the box is redrawn, not reprinted as blocks")

	def test_failure_without_a_box_keeps_the_full_ffmpeg_stderr(self):
		done = types.SimpleNamespace(
			returncode=1, stderr="Conversion failed!\nInvalid data found when processing input\n")
		out = io.StringIO()
		with tempfile.TemporaryDirectory() as tmp, \
				mock.patch.object(videojoin, "VideoReader", FakeReader), \
				mock.patch.object(videojoin, "check_ffmpeg", return_value=True), \
				mock.patch.object(videojoin, "has_audio", return_value=False), \
				mock.patch.object(videojoin.subprocess, "run", return_value=done), \
				contextlib.redirect_stdout(out):
			ok = videojoin.run_ffmpeg_join(
				["a.mp4"], False, "libx264",
				{"width": 640, "height": 480, "method": "stretch"},
				"out.mp4", TTY, working_dir=tmp)

		self.assertFalse(ok)
		text = tui.strip_ansi(out.getvalue())
		self.assertIn("FFmpeg Error Output:", text)
		self.assertIn("Conversion failed!", text)
		self.assertIn("Invalid data found when processing input", text)

	def test_dir_mode_keeps_one_box_for_every_subdirectory(self):
		done = types.SimpleNamespace(returncode=0, stderr="")
		(argv, start) = (sys.argv, os.getcwd())
		with tempfile.TemporaryDirectory() as tmp:
			for name in ("a", "b"):
				os.makedirs(os.path.join(tmp, name))
				open(os.path.join(tmp, name, "clip.mp4"), "w").close()
			os.chdir(tmp)
			out = io.StringIO()
			decord = types.ModuleType("decord")
			decord.VideoReader = FakeReader
			try:
				with mock.patch.dict(sys.modules, {"decord": decord}), \
						mock.patch.object(sys, "argv", ["videojoin.py", "--dir"]), \
						mock.patch.object(videojoin.tui, "detect", return_value=TTY), \
						mock.patch.object(videojoin, "check_ffmpeg", return_value=True), \
						mock.patch.object(videojoin, "has_audio", return_value=False), \
						mock.patch.object(videojoin.subprocess, "run", return_value=done), \
						contextlib.redirect_stdout(out):
					videojoin.main()
			finally:
				os.chdir(start)
				sys.argv = argv

		text = out.getvalue()
		joined = tui.strip_ansi(text)
		self.assertIn("Joining 2 directories", joined)
		self.assertIn("2/2 directories joined", joined)
		self.assertGreaterEqual(len(UP.findall(text)), 2,
								"two jobs share one redrawn box")


if __name__ == "__main__":
	unittest.main()
