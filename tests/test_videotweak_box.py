# Regression tests for the videotweak batch progress box
"""
			VIDEOTWEAK BATCH BOX
			====================
A folder of clips shares one `tui.progress.BatchBox`: every file moves the
current operation line, adds its ok/error row and advances the i/N bar, and the
box is closed with a summary. A single file keeps the old per-run header and
result panel byte for byte (no box at all), and a pipe degrades to TAB records.

No FFmpeg or decord runs here: both are faked.

Run with:
	python -m unittest tests.test_videotweak_box -v
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
import videotweak  # noqa: E402

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
	"""Stand-in for decord.VideoReader: 48 frames at 24 fps."""

	def __init__(self, path, *args, **kwargs):
		self.path = path

	def get_avg_fps(self):
		return 24.0

	def __len__(self):
		return 48


def done(returncode=0, stderr=""):
	return types.SimpleNamespace(returncode=returncode, stderr=stderr)


def run_main(cap, clip_names=("a.mp4", "b.mp4"), result=None, effect=6, ask=None):
	"""Drive `videotweak.main` over a scratch folder (effect 6 = passthrough)."""
	out = io.StringIO()
	result = done() if result is None else result
	decord = types.ModuleType("decord")
	decord.VideoReader = FakeReader
	with tempfile.TemporaryDirectory() as tmp:
		for name in clip_names:
			open(os.path.join(tmp, name), "w").close()
		argv = ["videotweak.py", tmp]
		with mock.patch.dict(sys.modules, {"decord": decord}), \
				mock.patch.object(sys, "argv", argv), \
				mock.patch.object(videotweak.tui, "detect", return_value=cap), \
				mock.patch.object(videotweak, "get_effect_choice",
								  lambda cap: effect), \
				mock.patch.object(videotweak, "VideoReader", FakeReader), \
				mock.patch.object(videotweak, "has_audio", return_value=False), \
				mock.patch.object(videotweak.subprocess, "run",
								  lambda *a, **k: result), \
				contextlib.redirect_stdout(out):
			if ask is None:
				videotweak.main()
			else:
				with mock.patch.object(videotweak.tui, "ask_text", ask):
					videotweak.main()
	return out.getvalue()


class TweakBatchBoxTest(unittest.TestCase):
	"""A multi-file run reuses one frame; a single file keeps the old output."""

	def test_batch_repaints_one_frame_holding_every_outcome(self):
		text = run_main(TTY)
		frames = UP.split(text)
		self.assertGreaterEqual(len(UP.findall(text)), 2,
								"two files share one redrawn box")
		for frame in frames:
			self.assertEqual(frame.count("Tweaking 2 files"), 1,
							 "each paint draws exactly one title")
		last = tui.strip_ansi(frames[-1])
		self.assertIn("[ok] Saved to", last)
		self.assertIn("Batch finished: 2/2 files saved", last)
		self.assertEqual(cursor_row(text),
						 len(frames[-1].strip("\n").split("\n")))

	def test_failure_adds_one_error_row_not_the_whole_stderr(self):
		text = run_main(TTY, result=done(
			1, "Conversion failed!\nInvalid data found when processing input\n"))
		last = tui.strip_ansi(UP.split(text)[-1])
		self.assertIn("[error] FFmpeg failed for", last)
		self.assertIn("Invalid data found", last)
		self.assertNotIn("Conversion failed!", last,
						 "inside the box only the last stderr line fits")
		self.assertIn("Batch finished: 0/2 files saved", last)

	def test_pipe_degrades_to_tab_records(self):
		text = run_main(PIPE)
		self.assertNotIn("\x1b", text)
		lines = text.strip().splitlines()
		self.assertIn("a.mp4\t0/2", lines)
		self.assertIn("b.mp4\t1/2", lines)
		self.assertTrue(any(line.startswith("ok\tSaved to ") for line in lines))
		self.assertIn("info\tBatch finished: 2/2 files saved", lines)

	def test_level_none_tty_stays_silent_until_close(self):
		text = run_main(NO_COLOR_TTY)
		self.assertNotIn("\x1b", text)
		self.assertIn("[ok] Saved to", text)
		self.assertIn("Batch finished: 2/2 files saved", text)

	def test_effect_question_is_asked_before_the_box_owns_the_cursor(self):
		asked = []

		def ask(prompt, default="", eof=None):
			asked.append(prompt)
			sys.stdout.write(prompt)  # `input()` shows the label, no newline
			return "12"

		text = run_main(TTY, effect=3, ask=ask)
		frames = UP.split(text)
		self.assertEqual(len(asked), 2, "one question per file, before the box")
		self.assertEqual(cursor_row(text),
						 len(frames[-1].strip("\n").split("\n")),
						 "a prompt must not shift every later repaint")
		self.assertIn("Batch finished: 2/2 files saved",
					  tui.strip_ansi(frames[-1]))

	def test_cancelled_question_still_owns_one_row(self):
		answers = iter(["", "12"])  # first file cancels, second answers

		def ask(prompt, default="", eof=None):
			return next(answers)

		text = run_main(TTY, effect=3, ask=ask)
		last = tui.strip_ansi(UP.split(text)[-1])
		self.assertIn("[warn] Skipped a.mp4", last)
		self.assertIn("[ok] Saved to", last)
		self.assertIn("Batch finished: 1/2 files saved", last)
		self.assertEqual(cursor_row(text),
						 len(UP.split(text)[-1].strip("\n").split("\n")))

	def test_single_file_prints_no_box(self):
		text = run_main(TTY, clip_names=("only.mp4",))
		joined = tui.strip_ansi(text)
		self.assertIn("Tweaking: only.mp4...", joined)
		self.assertIn("[ok] Saved to", joined)
		self.assertNotIn("Tweaking 1 files", text)


if __name__ == "__main__":
	unittest.main()
