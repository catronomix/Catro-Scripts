# Regression tests for the transient overwrite prompt
"""
			OVERWRITE PROMPT
			================
`tui.overwrite` answers one question when a target already exists: y overwrites,
n skips, Y overwrites every later target and a aborts. On a terminal the question
is painted on the row under the batch box, one key is read, the row is erased and
the box is repainted, so no prompt text survives and the next repaint still lands
on the top border. A pipe (or any non-terminal stdin) never asks: the target is
treated as n.

No FFmpeg or decord runs here.

Run with:
	python -m unittest tests.test_overwrite_prompt -v
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
import videojoin  # noqa: E402
import videoloop  # noqa: E402
import videotweak  # noqa: E402

TTY = tui.Capabilities(level="true", unicode=True, width=72, isatty=True,
					   plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")
NO_COLOR_TTY = tui.Capabilities(level="none", unicode=True, width=72,
								isatty=True, plain=False, reason="test")

ANY_UP = re.compile(r"\x1b\[(\d+)A")
REWIND = re.compile(r"\x1b\[(\d+)A\r")


def cursor_row(text):
	"""Net vertical movement a terminal would have applied to this byte stream."""
	return text.count("\n") - sum(int(n) for n in ANY_UP.findall(text))


def keys_of(*tokens):
	"""A reader stub that yields `tokens` in order and fails when exhausted."""
	pending = list(tokens)

	def read():
		return pending.pop(0)
	return read


class PromptTextTest(unittest.TestCase):
	"""The question names every answer, on the palette and truncated to width."""

	def test_prompt_states_every_answer(self):
		self.assertEqual(tui.overwrite.PROMPT,
						 "File exists! Overwrite? ([y]es, [n]o, [Y]es to all, [a]bort): ")
		for answer in ("[y]es", "[n]o", "[Y]es to all", "[a]bort"):
			self.assertIn(answer, tui.overwrite.PROMPT)

	def test_prompt_uses_palette_roles_at_every_colour_level(self):
		texts = {level: tui.strip_ansi(tui.overwrite._question(
			tui.Capabilities(level=level, unicode=True, width=72, isatty=True,
							 plain=False, reason="test")))
			for level in ("16", "256", "true")}
		for level, plain in texts.items():
			self.assertEqual(plain, tui.overwrite.PROMPT, level)
		wide = tui.overwrite._question(TTY)
		self.assertIn("38;2;", wide, "truecolour keeps 24-bit SGR")
		self.assertNotIn("38;2;", tui.overwrite._question(
			tui.Capabilities(level="256", unicode=True, width=72, isatty=True,
							 plain=False, reason="test")))
		self.assertNotIn("38;", tui.overwrite._question(
			tui.Capabilities(level="16", unicode=True, width=72, isatty=True,
							 plain=False, reason="test")),
			"the 16-colour level downgrades to a basic colour")

	def test_narrow_terminal_truncates_the_row(self):
		narrow = tui.Capabilities(level="true", unicode=True, width=20,
								  isatty=True, plain=False, reason="test")
		line = tui.overwrite._question(narrow)
		self.assertLessEqual(tui.display_width(tui.strip_ansi(line)), 19)


class GateAnswersTest(unittest.TestCase):
	"""y/n/Y/a semantics, one question per target, no question off a tty."""

	def setUp(self):
		self.out = io.StringIO()
		self.box = tui.progress.BatchBox("Batch", 2, stream=self.out, cap=TTY)
		self.box.update(op="job", done=0)
		patcher = mock.patch.object(tui.overwrite, "_stdin_tty",
									return_value=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def gate(self, reader):
		return tui.overwrite.OverwriteGate(cap=TTY, box=self.box,
										   reader=reader)

	def test_yes_overwrites_only_this_target(self):
		gate = self.gate(keys_of("y"))
		self.assertTrue(gate.allow())
		self.assertFalse(gate.overwrite_all)
		self.assertFalse(gate.aborted)

	def test_no_skips_the_target(self):
		gate = self.gate(keys_of("n"))
		self.assertFalse(gate.allow())
		self.assertFalse(gate.aborted)

	def test_yes_to_all_stops_asking(self):
		gate = self.gate(keys_of("Y"))
		self.assertTrue(gate.allow())
		self.assertTrue(gate.overwrite_all)
		self.assertTrue(gate.allow(), "the second target is not asked about")
		self.assertEqual(tui.strip_ansi(self.out.getvalue()).count(
			tui.overwrite.PROMPT), 1)

	def test_abort_stops_the_run(self):
		gate = self.gate(keys_of("a"))
		self.assertFalse(gate.allow())
		self.assertTrue(gate.aborted)
		self.assertFalse(gate.allow(), "an aborted gate never writes")

	def test_escape_aborts_instead_of_hanging(self):
		gate = self.gate(keys_of("esc"))
		self.assertFalse(gate.allow())
		self.assertTrue(gate.aborted)

	def test_other_keys_reask(self):
		gate = self.gate(keys_of("x", "y"))
		self.assertTrue(gate.allow())
		self.assertEqual(tui.strip_ansi(self.out.getvalue()).count(
			tui.overwrite.PROMPT), 2,
			"each attempt paints exactly one question")


class TransientRowTest(unittest.TestCase):
	"""The question disappears: erase + repaint leaves the frame intact."""

	def setUp(self):
		self.out = io.StringIO()
		self.box = tui.progress.BatchBox("Batch", 2, stream=self.out, cap=TTY)
		self.box.update(op="job", done=0)

	def test_question_is_erased_and_the_box_repainted_in_place(self):
		frame_lines = len(self.box._frame().split("\n"))
		before = self.out.getvalue()
		start_row = cursor_row(before)
		gate = tui.overwrite.OverwriteGate(cap=TTY, box=self.box, reader=keys_of("n"))
		with mock.patch.object(tui.overwrite, "_stdin_tty", return_value=True):
			self.assertFalse(gate.allow())
		text = self.out.getvalue()

		self.assertEqual(tui.strip_ansi(text).count(tui.overwrite.PROMPT), 1)
		tail = text.rsplit("\r\x1b[2K", 1)[1]
		self.assertNotIn("Overwrite?", tail, "the transient row is gone")
		rewind = REWIND.match(tail)
		self.assertIsNotNone(rewind, "the erase repaints the frame")
		self.assertEqual(int(rewind.group(1)), frame_lines,
						 "the repaint rewinds the frame's own lines")
		self.assertEqual(cursor_row(text), start_row,
						 "the cursor is parked under the frame again")
		self.assertEqual(tui.strip_ansi(tail).split("\n")[0].count("Batch"), 1)
		self.assertEqual([line for line in tui.strip_ansi(tail).split("\n") if line][-1][0], "\u255a",
						 "the frame's bottom border is drawn last")

	def test_repeated_questions_keep_the_frame_height(self):
		frame_lines = len(self.box._frame().split("\n"))
		gate = tui.overwrite.OverwriteGate(cap=TTY, box=self.box,
										   reader=keys_of("x", "z", "n"))
		with mock.patch.object(tui.overwrite, "_stdin_tty", return_value=True):
			self.assertFalse(gate.allow())
		self.assertEqual(cursor_row(self.out.getvalue()), frame_lines)

	def test_without_a_box_the_row_is_still_erased(self):
		out = io.StringIO()
		cap = tui.Capabilities(level="true", unicode=True, width=72,
							   isatty=True, plain=False, reason="test")
		gate = tui.overwrite.OverwriteGate(cap=cap, stream=out, reader=keys_of("n"))
		with mock.patch.object(tui.overwrite, "_stdin_tty", return_value=True):
			self.assertFalse(gate.allow())
		text = out.getvalue()
		self.assertIn(tui.overwrite.PROMPT, tui.strip_ansi(text))
		self.assertTrue(text.endswith("\r\x1b[2K"), text)
		self.assertEqual(cursor_row(text), 0)


class NonInteractiveTest(unittest.TestCase):
	"""Off a terminal the gate never reads and never waits."""

	def test_pipe_treats_an_existing_target_as_no(self):
		out = io.StringIO()
		gate = tui.overwrite.OverwriteGate(cap=PIPE, stream=out,
										   reader=keys_of())
		self.assertFalse(gate.allow())
		self.assertFalse(gate.aborted)
		self.assertEqual(out.getvalue(), "")

	def test_tty_stdout_with_piped_stdin_never_asks(self):
		out = io.StringIO()
		gate = tui.overwrite.OverwriteGate(cap=TTY, stream=out, reader=keys_of())
		with mock.patch.object(tui.overwrite, "_stdin_tty", return_value=False):
			self.assertFalse(gate.allow())
		self.assertEqual(out.getvalue(), "")

	def test_level_none_tty_reads_a_plain_line(self):
		out = io.StringIO()
		gate = tui.overwrite.OverwriteGate(cap=NO_COLOR_TTY, stream=out,
										   reader=keys_of())
		with mock.patch.object(tui.overwrite, "_stdin_tty", return_value=True), \
				mock.patch("builtins.input", return_value="n") as ask:
			self.assertTrue(gate.interactive)
			self.assertFalse(gate.transient, "no escapes at level none")
			self.assertFalse(gate.allow())
		self.assertIn(tui.overwrite.PROMPT, ask.call_args[0][0])
		self.assertNotIn("\x1b", out.getvalue())


class _FakeReader:
	"""Stand-in for decord.VideoReader: 48 frames at 24 fps."""

	def __init__(self, path, *args, **kwargs):
		self.path = path

	def get_avg_fps(self):
		return 24.0

	def __len__(self):
		return 48


class _Done:
	returncode = 0
	stdout = "ffmpeg version 4.4\n"
	stderr = ""


class ScriptSkipTest(unittest.TestCase):
	"""All three scripts skip an existing target and never call FFmpeg for it."""

	def gate(self, box):
		return tui.overwrite.OverwriteGate(cap=TTY, box=box, reader=keys_of())

	def test_videoloop_skips_without_running_ffmpeg(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Looping 1 files", 1, stream=out, cap=TTY)
		box.update(op="a.mp4", done=0)
		with tempfile.TemporaryDirectory() as tmp:
			video = os.path.join(tmp, "a.mp4")
			open(video, "w").close()
			open(os.path.join(tmp, "a_seamless.mp4"), "w").close()
			with mock.patch.object(videoloop, "check_ffmpeg", return_value=True), \
					mock.patch.object(videoloop.subprocess, "run") as run, \
					mock.patch.object(tui.overwrite, "_stdin_tty",
									  return_value=False):
				videoloop.process_loop(video, 1.0, 0.0, "libx264", "esin",
									   "_seamless", True, None, TTY,
									   box=box, gate=self.gate(box))
		run.assert_not_called()
		self.assertIn(("warn", "Skipped {}: output exists".format(
			os.path.join(tmp, "a_seamless.mp4"))), box.rows)
		self.assertIn("Skipped", tui.strip_ansi(out.getvalue()))

	def test_videojoin_skips_without_running_ffmpeg(self):
		out = io.StringIO()
		decord = types.ModuleType("decord")
		decord.VideoReader = _FakeReader
		start = os.getcwd()
		with tempfile.TemporaryDirectory() as tmp:
			for name in ("a", "b"):
				os.makedirs(os.path.join(tmp, name))
				open(os.path.join(tmp, name, "clip.mp4"), "w").close()
				open(os.path.join(tmp, name, name + "_joined.mp4"),
					 "w").close()
			os.chdir(tmp)
			try:
				with mock.patch.dict(sys.modules, {"decord": decord}), \
						mock.patch.object(sys, "argv", ["videojoin.py", "--dir"]), \
						mock.patch.object(videojoin.tui, "detect", return_value=TTY), \
						mock.patch.object(videojoin, "check_ffmpeg", return_value=True), \
						mock.patch.object(videojoin, "has_audio", return_value=False), \
						mock.patch.object(videojoin.subprocess, "run") as run, \
						mock.patch("builtins.input") as ask, \
						mock.patch.object(tui.overwrite, "_stdin_tty",
										  return_value=False):
					with mock.patch("sys.stdout", out):
						videojoin.main()
			finally:
				os.chdir(start)
		run.assert_not_called()
		ask.assert_not_called()
		text = tui.strip_ansi(out.getvalue())
		self.assertIn("output exists", text)
		self.assertIn("0/2 directories joined", text)

	def test_videotweak_skips_without_running_ffmpeg(self):
		out = io.StringIO()
		box = tui.progress.BatchBox("Tweaking 1 files", 1, stream=out, cap=TTY)
		box.update(op="a.mp4", done=0)
		media = {"fps": 24.0, "frames": 48, "audio": False}
		with tempfile.TemporaryDirectory() as tmp:
			video = os.path.join(tmp, "a.mp4")
			open(video, "w").close()
			open(os.path.join(tmp, "a_tweak.mp4"), "w").close()
			with mock.patch.object(videotweak.subprocess, "run") as run, \
					mock.patch.object(tui.overwrite, "_stdin_tty",
									  return_value=False):
				videotweak.process_video(video, 6, tmp, None, "libx264",
										 ".mp4", None, TTY, box=box,
										 media=media, answers={},
										 gate=self.gate(box))
		run.assert_not_called()
		self.assertIn(("warn", "Skipped {}: output exists".format(
			os.path.join(tmp, "a_tweak.mp4"))), box.rows)
		self.assertIn("Skipped", tui.strip_ansi(out.getvalue()))

	def test_videoloop_single_file_main_skips_inside_the_box(self):
		out = io.StringIO()
		decord = types.ModuleType("decord")
		decord.VideoReader = _FakeReader
		with tempfile.TemporaryDirectory() as tmp:
			video = os.path.join(tmp, "a.mp4")
			open(video, "w").close()
			open(os.path.join(tmp, "a_seamless.mp4"), "w").close()
			run = mock.Mock(return_value=_Done())
			with mock.patch.dict(sys.modules, {"decord": decord}), \
					mock.patch.object(sys, "argv", ["videoloop.py", video]), \
					mock.patch.object(videoloop.tui, "detect", return_value=TTY), \
					mock.patch.object(videoloop, "check_ffmpeg", return_value=True), \
					mock.patch.object(videoloop.subprocess, "run", run), \
					mock.patch.object(tui.overwrite, "_stdin_tty",
									  return_value=False), \
					contextlib.redirect_stdout(out):
				videoloop.main()
		self.assertFalse([call for call in run.call_args_list
						  if "-y" in call.args[0]],
						 "the skipped target must not reach FFmpeg")
		text = tui.strip_ansi(out.getvalue())
		self.assertIn("[warn] Skipped", text)
		self.assertIn("Batch finished: 0/1 loop saved", text)

	def test_videotweak_single_file_main_skips_inside_the_box(self):
		out = io.StringIO()
		decord = types.ModuleType("decord")
		decord.VideoReader = _FakeReader
		start = os.getcwd()
		with tempfile.TemporaryDirectory() as tmp:
			open(os.path.join(tmp, "a.mp4"), "w").close()
			open(os.path.join(tmp, "a_tweak.mp4"), "w").close()
			run = mock.Mock(return_value=_Done())
			os.chdir(tmp)
			try:
				with mock.patch.dict(sys.modules, {"decord": decord}), \
						mock.patch.object(sys, "argv", ["videotweak.py", "a.mp4"]), \
						mock.patch.object(videotweak.tui, "detect",
										  return_value=TTY), \
						mock.patch.object(videotweak, "get_effect_choice",
										  lambda cap: 6), \
						mock.patch.object(videotweak, "has_audio",
										  return_value=False), \
						mock.patch.object(videotweak.subprocess, "run", run), \
						mock.patch.object(tui.overwrite, "_stdin_tty",
										  return_value=False), \
						contextlib.redirect_stdout(out):
					videotweak.main()
			finally:
				os.chdir(start)
		self.assertFalse([call for call in run.call_args_list
						  if "-y" in call.args[0]],
						 "the skipped target must not reach FFmpeg")
		text = tui.strip_ansi(out.getvalue())
		self.assertIn("[warn] Skipped", text)
		self.assertIn("Batch finished: 0/1 file saved", text)

	def test_videojoin_single_file_main_skips_inside_the_box(self):
		out = io.StringIO()
		decord = types.ModuleType("decord")
		decord.VideoReader = _FakeReader
		start = os.getcwd()
		with tempfile.TemporaryDirectory() as tmp:
			open(os.path.join(tmp, "clip.mp4"), "w").close()
			open(os.path.join(tmp, "joined_video.mp4"), "w").close()
			os.chdir(tmp)
			try:
				with mock.patch.dict(sys.modules, {"decord": decord}), \
						mock.patch.object(sys, "argv",
										  ["videojoin.py", "clip.mp4"]), \
						mock.patch.object(videojoin.tui, "detect",
										  return_value=TTY), \
						mock.patch.object(videojoin, "check_ffmpeg",
										  return_value=True), \
						mock.patch.object(videojoin.subprocess, "run") as run, \
						mock.patch.object(tui.overwrite, "_stdin_tty",
										  return_value=False), \
						mock.patch("sys.stdout", out):
					videojoin.main()
			finally:
				os.chdir(start)
		run.assert_not_called()
		text = tui.strip_ansi(out.getvalue())
		self.assertIn("[warn] Skipped joined_video.mp4: output exists", text)
		self.assertIn("Batch finished: 0/1 output joined", text)


if __name__ == "__main__":
	unittest.main()
