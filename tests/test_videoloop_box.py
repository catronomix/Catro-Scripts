# Regression tests for the videoloop batch progress box
"""
			VIDEOLOOP BATCH BOX
			===================
A directory of clips shares one `tui.progress.BatchBox`: every file moves the
current operation line, adds its warn/ok row and advances the i/N bar, and the
box is closed with a summary. A single file keeps the old per-run output byte
for byte (no box at all), and a pipe degrades to TAB records.

No FFmpeg or decord runs here: both are faked.

Run with:
	python -m unittest tests.test_videoloop_box -v
"""
import contextlib
import io
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
	sys.path.append(str(TESTS))

import tui  # noqa: E402  (import after sys.path setup)
import videoloop  # noqa: E402
from support import cell_style, replay  # noqa: E402  (test helper)

TTY = tui.Capabilities(level="true", unicode=True, width=72, isatty=True,
					   plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")
NO_COLOR_TTY = tui.Capabilities(level="none", unicode=True, width=72,
								isatty=True, plain=False, reason="test")

UP = re.compile(r"\x1b\[\d+A\r")
ANY_UP = re.compile(r"\x1b\[(\d+)A")


def cursor_row(text):
	"""Net vertical movement a terminal would have applied to this byte stream."""
	return text.count("\n") - sum(int(n) for n in ANY_UP.findall(text))


class FakeReader:
	"""Stand-in for decord.VideoReader: 48 frames at 24 fps (a 2 s clip)."""

	def __init__(self, path, *args, **kwargs):
		self.path = path

	def get_avg_fps(self):
		return 24.0

	def __len__(self):
		return 48


class Done:
	returncode = 0
	stdout = "ffmpeg version 4.4\n"
	stderr = ""


def run_main(cap, clip_names=("a.mp4", "b.mp4"), extra_argv=()):
	"""Drive `videoloop.main` over a scratch folder of empty clip files."""
	out = io.StringIO()
	decord = types.ModuleType("decord")
	decord.VideoReader = FakeReader
	with tempfile.TemporaryDirectory() as tmp:
		for name in clip_names:
			open(os.path.join(tmp, name), "w").close()
		argv = ["videoloop.py", tmp] + list(extra_argv)
		with mock.patch.dict(sys.modules, {"decord": decord}), \
				mock.patch.object(sys, "argv", argv), \
				mock.patch.object(videoloop.tui, "detect", return_value=cap), \
				mock.patch.object(videoloop, "check_ffmpeg", return_value=True), \
				mock.patch.object(videoloop, "has_audio", return_value=False), \
				mock.patch.object(videoloop.subprocess, "run",
								  lambda *a, **k: Done()), \
				contextlib.redirect_stdout(out):
			videoloop.main()
	return out.getvalue()


class LoopBatchBoxTest(unittest.TestCase):
	"""A multi-file run reuses one frame; a single file keeps the old output."""

	def test_batch_repaints_one_frame_holding_every_outcome(self):
		text = run_main(TTY)
		frames = UP.split(text)
		self.assertGreaterEqual(len(UP.findall(text)), 2,
								"two files share one redrawn box")
		for frame in frames:
			self.assertEqual(frame.count("Looping 2 files"), 1,
							 "each paint draws exactly one title")
		last = tui.strip_ansi(frames[-1])
		self.assertIn("[ok] Loop saved as", last)
		self.assertIn("[warn]", last)
		self.assertIn("Batch finished: 2/2 loops saved", last)
		# The final frame is left in place, cursor parked on its last row.
		stream = text[text.index("Looping 2 files"):]
		self.assertEqual(cursor_row(stream),
						 len(frames[-1].strip("\n").split("\n")))

	def test_batch_frame_interior_keeps_the_panel_ground(self):
		box = tui.progress.BatchBox("Looping 2 files", 2, stream=io.StringIO(),
									cap=TTY)
		box.update(op="a.mp4", done=1, rows=[("warn", "long fade reduced"),
											 ("ok", "Loop saved as a_seamless.mp4")])
		ground = cell_style(tui.palette.prefix(fg="fg", bg="bg-inside",
											   cap=TTY))[1]
		self.assertIsNotNone(ground, "the look must have a distinct interior")
		cells = replay(box._frame())
		height = max(y for _x, y in cells) + 1
		width = max(x for x, _y in cells) + 1
		for y in range(1, height - 1):
			for x in range(1, width - 1):
				self.assertEqual(cells[(x, y)][1][1], ground,
								 "row {}, column {}".format(y, x))

	def test_unknown_row_kind_never_breaks_the_frame(self):
		box = tui.progress.BatchBox("Looping 1 files", 1, stream=io.StringIO(),
									cap=TTY)
		box.update(op="a.mp4", done=0)
		box.add("bogus", "odd outcome")
		box.close()
		self.assertIn("odd outcome", tui.strip_ansi(box._frame()))
		self.assertIn("[info]", tui.strip_ansi(box._frame()))

	def test_narrow_terminal_clamps_every_frame_line(self):
		narrow = tui.Capabilities(level="true", unicode=True, width=24,
								  isatty=True, plain=False, reason="test")
		text = run_main(narrow)
		for line in tui.strip_ansi(UP.split(text)[-1]).splitlines():
			self.assertLessEqual(tui.display_width(line), 24)

	def test_pipe_degrades_to_tab_records(self):
		text = run_main(PIPE)
		self.assertNotIn("\x1b", text)
		lines = text.strip().splitlines()
		self.assertIn("a.mp4\t0/2", lines)
		self.assertIn("b.mp4\t1/2", lines)
		self.assertTrue(any(line.startswith("ok\tLoop saved as ") for line in lines))
		self.assertIn("info\tBatch finished: 2/2 loops saved", lines)

	def test_level_none_tty_stays_silent_until_close(self):
		text = run_main(NO_COLOR_TTY)
		self.assertNotIn("\x1b", text)
		self.assertIn("[ok] Loop saved as", text)
		self.assertIn("Batch finished: 2/2 loops saved", text)

	def test_single_file_prints_no_box(self):
		text = run_main(TTY, clip_names=("only.mp4",))
		self.assertIn("LOOP SETTINGS", tui.strip_ansi(text))
		self.assertNotIn("Looping 1 files", text)
		self.assertNotIn("\u250c", text)


if __name__ == "__main__":
	unittest.main()
