# Regression tests for the sysadmin/confirm group's boxed blocks
"""
			SYSADMIN BLOCK PANELS
			=====================
Issue 0041 batch B2a moved the plan/confirm/result blocks of `netconfig`,
`renamer`, `randomsorter`, `shutdown` and `keygen` onto `tui.panel`; their
single-line status lines stay inline `tui.status` text and the machine-readable
(piped) output keeps its exact pre-sweep bytes.

`netconfig` and `shutdown` are privileged/system tools: their mutating paths are
never executed here. The block is captured with the platform calls, the
subprocess runner and the prompts stubbed, so nothing elevates, schedules or
touches an adapter.

Run with:
	python -m unittest tests.test_b2a_panels -v
"""
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)

FRAME = "\u250c"
BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"

TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=70, isatty=True,
							plain=False, reason="test")
TTY_16 = tui.Capabilities(level="16", unicode=True, width=70, isatty=True,
						  plain=False, reason="test")
TTY_NONE = tui.Capabilities(level="none", unicode=True, width=70, isatty=True,
							plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


def capture(render, cap, theme="soft"):
	"""Run one block-producing call with `cap` and return its stdout."""
	buffer = io.StringIO()
	with mock.patch.dict(os.environ, {"CATRO_THEME": theme}), \
			mock.patch.object(tui, "detect", lambda: cap), \
			contextlib.redirect_stdout(buffer):
		try:
			render(cap)
		except SystemExit:
			pass
	return buffer.getvalue()


def run_as_main(script, argv, cap, answers=()):
	"""Execute a `__main__`-guarded script in-process with its prompts stubbed.

	The scripts in this group keep their flow under `if __name__ ==
	"__main__"`, so the only way to reach the block is to run them; the prompts
	are answered from `answers`, and `SystemExit` ends the run as usual.
	"""
	import runpy

	buffer = io.StringIO()
	answers = list(answers)
	with mock.patch.dict(os.environ, {"CATRO_THEME": "soft"}), \
			mock.patch.object(tui, "detect", lambda: cap), \
			mock.patch.object(tui, "init_ansi"), \
			mock.patch.object(tui, "require_tty"), \
			mock.patch.object(tui, "ask_text",
							   side_effect=lambda *a, **k: answers.pop(0)), \
			mock.patch.object(sys, "argv", [script] + list(argv)), \
			contextlib.redirect_stdout(buffer):
		try:
			runpy.run_path(str(REPO / script), run_name="__main__")
		except SystemExit:
			pass
	return buffer.getvalue()


class NetconfigPlanPanelTest(unittest.TestCase):
	"""The static-IP plan heading is one page-width panel."""

	def render(self, cap):
		import netconfig

		with mock.patch.object(netconfig.tui, "ask_text",
							   side_effect=["10.0.0.5", "24", "10.0.0.1"]):
			netconfig.get_manual_input(
				"eth0",
				{"eth0": {"ip": "10.0.0.2", "mask": "255.255.255.0",
						  "gw": "10.0.0.1"}},
				cap)

	def test_true_colour_frames_the_plan(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("Setting up static IP for:", tui.strip_ansi(out), out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		self.assertEqual("\nSetting up static IP for: eth0\n", out)
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, out)


class RenamerConfirmPanelTest(unittest.TestCase):
	"""The `--all` confirmation is a panel; the result lines stay inline."""

	def test_true_colour_frames_the_confirmation(self):
		out = run_as_main("renamer.py", ["--all"], TTY_TRUE, answers=["n"])
		self.assertIn(FRAME, out, out)
		plain = tui.strip_ansi(out)
		self.assertIn("You are using the --all flag", plain, out)
		self.assertIn("process system files and scripts", plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = run_as_main("renamer.py", ["--all"], TTY_16, answers=["n"])
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = run_as_main("renamer.py", ["--all"], TTY_NONE, answers=["n"])
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_pipe_keeps_the_lines_without_the_frame(self):
		out = run_as_main("renamer.py", ["--all"], PIPE, answers=["n"])
		self.assertNotIn(FRAME, out)
		self.assertNotIn("\x1b", out)
		self.assertIn("You are using the --all flag", out)


class RandomsorterConfirmPanelTest(unittest.TestCase):
	"""The `--all` confirmation is a panel; the run summary stays inline."""

	def test_true_colour_frames_the_confirmation(self):
		out = run_as_main("randomsorter.py", ["--all"], TTY_TRUE, answers=["n"])
		self.assertIn(FRAME, out, out)
		plain = tui.strip_ansi(out)
		self.assertIn("You are using the --all flag", plain, out)
		self.assertIn("process system files and scripts", plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = run_as_main("randomsorter.py", ["--all"], TTY_16, answers=["n"])
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = run_as_main("randomsorter.py", ["--all"], TTY_NONE, answers=["n"])
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = run_as_main("randomsorter.py", ["--all"], PIPE, answers=["n"])
		self.assertNotIn("\x1b", out)
		self.assertEqual("Confirm\n[error] You are using the --all flag.\n"
						 "This will process system files and scripts.\n"
						 "[info] Operation cancelled.\n", out)

	def test_empty_run_still_prints_the_same_plain_summary(self):
		"""A real non-destructive run (empty folder) keeps its exact bytes."""
		import tempfile

		previous = os.getcwd()
		with tempfile.TemporaryDirectory() as folder:
			os.chdir(folder)
			try:
				out = run_as_main("randomsorter.py", [], PIPE)
			finally:
				os.chdir(previous)
		self.assertEqual(
			"[warn] No matching files found. Nothing to do.\n"
			"\nProcessing complete.\n", out)


class ShutdownResultPanelTest(unittest.TestCase):
	"""The scheduled-shutdown result block is one panel; nothing is executed."""

	def render(self, cap):
		import shutdown

		with mock.patch.object(shutdown.platform, "system",
							   return_value="Windows"), \
				mock.patch.object(shutdown.subprocess, "run",
								  lambda *a, **k: None):
			shutdown.schedule_shutdown(600, cap=cap)

	def test_true_colour_frames_the_result(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("[ok] Shutdown scheduled in 600 seconds.",
					  tui.strip_ansi(out), out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		self.assertEqual(
			"\n[ok] Shutdown scheduled in 600 seconds.\n"
			"[info] To cancel, type: shutdown /a\n", out)

	def test_closed_stdin_quits_instead_of_reprompting(self):
		"""EOF is a quit: the delay prompt must not loop on a closed stdin."""
		import shutdown

		with mock.patch.object(tui, "detect", lambda: TTY_TRUE), \
				mock.patch.object(tui, "init_ansi"), \
				mock.patch.object(tui, "ask_text", return_value=shutdown._EOF), \
				mock.patch.object(tui, "header", lambda *a, **k: "header"), \
				contextlib.redirect_stdout(io.StringIO()):
			shutdown.main()  # returns, never schedules, never spins


class NoBareInputTest(unittest.TestCase):
	"""Batch B2a scripts ask through `tui.prompts`, never `input()` directly."""

	def test_no_bare_input_in_the_five_scripts(self):
		import ast

		for name in ("netconfig.py", "renamer.py", "randomsorter.py",
					 "shutdown.py", "keygen.py"):
			with self.subTest(script=name):
				tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
				calls = [node for node in ast.walk(tree)
						 if isinstance(node, ast.Call)
						 and isinstance(node.func, ast.Name)
						 and node.func.id == "input"]
				self.assertEqual([], calls,
								 "{} still calls input() directly".format(name))


class _Stream:
	"""Minimal keygen page target: write/flush plus the `Screen` paint calls."""

	def __init__(self):
		self.text = ""

	def write(self, value):
		self.text += value

	def flush(self):
		pass

	def clear(self):
		self.text = ""

	def fill(self):
		self.text = ""

	def getvalue(self):
		return self.text


class KeygenAppBoxTest(unittest.TestCase):
	"""`keygen` draws one fit-to-content box around the whole app.

	Issue #45: the details and key blocks used to be boxed on their own with
	nothing around the page. Every screen now renders through `keygen.draw_page`,
	which wraps the masthead and the rows in a single panel and centres it with
	`(terminal width - box width) // 2` columns of left margin.
	"""

	PAINTERS = {
		"show_key": lambda keygen, stream, cap: keygen.show_key(stream, cap, 0, 8),
		"picker": lambda keygen, stream, cap: keygen.choose_algorithm(
			stream, cap, 1),
		"length": lambda keygen, stream, cap: keygen.prompt_length(
			stream, cap, 32),
	}

	def paint(self, cap, name):
		import keygen

		stream = _Stream()
		with mock.patch.object(keygen, "read_key", return_value="esc"):
			self.PAINTERS[name](keygen, stream, cap)
		return stream.getvalue()

	def frame_rows(self, cap, name):
		"""Visible, non-blank rows of the single box, escapes stripped."""
		return [line for line in tui.strip_ansi(self.paint(cap, name)).splitlines()
				if line.strip()]

	def test_every_screen_draws_one_centred_fit_to_content_box(self):
		for name in self.PAINTERS:
			with self.subTest(screen=name):
				rows = self.frame_rows(TTY_TRUE, name)
				out = self.paint(TTY_TRUE, name)
				# One outer frame only: no inner panel frames left behind.
				self.assertEqual(1, out.count(FRAME))
				width = tui.display_width(rows[0].strip())
				self.assertLess(width, TTY_TRUE.width)  # fit to content
				self.assertTrue(rows[0].strip().endswith("\u2510"))
				self.assertTrue(rows[-1].strip().endswith("\u2518"))
				self.assertEqual(width, tui.display_width(rows[-1].strip()))
				left = (TTY_TRUE.width - width) // 2
				for row in rows:
					self.assertEqual(left, len(row) - len(row.lstrip(" ")), row)
					self.assertEqual(width, tui.display_width(row.strip()), row)

	def test_show_key_keeps_the_details_and_key_inside_the_box(self):
		out = tui.strip_ansi(self.paint(TTY_TRUE, "show_key"))
		for text in ("KEYGEN", "Algorithm", "Entropy", "[ENTER] new key"):
			self.assertIn(text, out)
		self.assertEqual(1, out.count(FRAME), out)

	def test_true_colour_still_styles_the_box(self):
		out = self.paint(TTY_TRUE, "show_key")
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = self.paint(TTY_16, "show_key")
		self.assertEqual(1, out16.count(FRAME))
		self.assertNotIn("38;2;", out16)
		out = self.paint(TTY_NONE, "show_key")
		self.assertEqual(1, out.count(FRAME), out)
		self.assertNotIn("\x1b", out)

	def test_pipe_stays_plain_without_a_frame(self):
		import keygen

		stream = _Stream()
		with mock.patch.object(keygen, "read_key", return_value="esc"):
			keygen.show_key(stream, PIPE, 0, 8)
		out = stream.getvalue()
		self.assertNotIn(FRAME, out)
		self.assertNotIn("\x1b", out)
		self.assertIn("Algorithm", out)


if __name__ == "__main__":
	unittest.main()
