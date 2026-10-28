# Capability detection tests for tui.caps
"""
		CAPABILITY MATRIX
		==================
Pins the documented precedence (NO_COLOR > FORCE_COLOR > CATRO_COLOR >
config.ini > autodetect), plain mode on pipes, the Unicode degradation rules and
the require_tty preflight. No test needs a real terminal: streams are fakes and
environments are plain dicts.
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, config  # noqa: E402  (import after sys.path setup)


class FakeStream:
	"""In-memory stream with a controllable tty flag and encoding."""

	def __init__(self, tty=True, encoding="utf-8", text=""):
		self._buffer = io.StringIO(text)
		self.encoding = encoding
		self._tty = tty

	def write(self, text):
		return self._buffer.write(text)

	def read(self, size=1):
		return self._buffer.read(size)

	def getvalue(self):
		return self._buffer.getvalue()

	def flush(self):
		pass

	def isatty(self):
		return self._tty

	def fileno(self):
		raise io.UnsupportedOperation("fake stream has no file descriptor")


class CapabilityTests(unittest.TestCase):
	def setUp(self):
		self._config_file = config.CONFIG_FILE

	def tearDown(self):
		config.CONFIG_FILE = self._config_file

	def detect(self, environ=None, tty=True, encoding="utf-8", windows=False,
			   vt=False):
		# The Windows VT probe is a seam: `vt` is what it reports, and
		# `self.probe` proves when the real console was never touched.
		with mock.patch.object(caps, "_IS_WINDOWS", windows), \
				mock.patch.object(caps, "_vt_probe", return_value=vt,
								  create=True) as probe:
			self.probe = probe
			return caps.detect(FakeStream(tty, encoding), environ or {})

	def test_no_color_wins_over_everything(self):
		cap = self.detect({"NO_COLOR": "1", "FORCE_COLOR": "3",
						   "COLORTERM": "truecolor", "TERM": "xterm-256color"})
		# No colour, but still a terminal: the layout survives.
		self.assertEqual((cap.level, cap.reason, cap.plain),
						 ("none", "NO_COLOR", False))

	def test_empty_no_color_is_ignored(self):
		cap = self.detect({"NO_COLOR": "", "TERM": "xterm-256color"})
		self.assertEqual((cap.level, cap.reason), ("256", "TERM"))

	def test_force_color_levels(self):
		for value, expected in (("1", "16"), ("2", "256"), ("3", "true"), ("", None)):
			with self.subTest(force=value):
				environ = {"FORCE_COLOR": value}
				cap = self.detect(environ, tty=False)
				self.assertEqual(cap.level, expected or "none")

	def test_clicolor_force_counts_as_force_color(self):
		cap = self.detect({"CLICOLOR_FORCE": "1"})
		self.assertEqual((cap.level, cap.reason), ("16", "FORCE_COLOR"))

	def test_catro_color_beats_config_and_autodetect(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("color", "level", "16")
			cap = self.detect({"CATRO_COLOR": "256", "COLORTERM": "truecolor"})
			self.assertEqual((cap.level, cap.reason), ("256", "CATRO_COLOR"))

	def test_invalid_catro_color_is_ignored(self):
		cap = self.detect({"CATRO_COLOR": "banana", "TERM": "xterm-256color"})
		self.assertEqual((cap.level, cap.reason), ("256", "TERM"))

	def test_config_level_beats_autodetect(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("color", "level", "none")
			cap = self.detect({"COLORTERM": "truecolor"})
			self.assertEqual((cap.level, cap.reason, cap.plain),
							 ("none", "config.ini", False))

	def test_config_auto_falls_through_to_autodetect(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("color", "level", "auto")
			cap = self.detect({"COLORTERM": "truecolor"})
			self.assertEqual((cap.level, cap.reason), ("true", "COLORTERM"))

	def test_autodetect_matrix(self):
		cases = (
			({"TERM": "dumb"}, "none", "TERM=dumb"),
			({"COLORTERM": "truecolor"}, "true", "COLORTERM"),
			({"COLORTERM": "24bit"}, "true", "COLORTERM"),
			({"TERM": "xterm-direct"}, "true", "TERM"),
			({"TERM": "screen-truecolor"}, "true", "TERM"),
			({"TERM": "xterm-256color"}, "256", "TERM"),
			({"TERM": "xterm"}, "16", "tty"),
			({}, "16", "tty"),
		)
		for environ, level, reason in cases:
			with self.subTest(environ=environ):
				cap = self.detect(environ)
				self.assertEqual((cap.level, cap.reason), (level, reason))

	def test_ssh_caps_the_level_at_256(self):
		cap = self.detect({"TERM": "xterm", "SSH_CLIENT": "10.0.0.1 1 22"})
		self.assertEqual((cap.level, cap.reason), ("256", "ssh"))
		piped = self.detect({"SSH_TTY": "/dev/pts/1"}, tty=False)
		self.assertEqual((piped.level, piped.plain), ("none", True))

	def test_pipe_is_plain_and_level_none(self):
		cap = self.detect({"TERM": "xterm-256color"}, tty=False)
		self.assertEqual((cap.level, cap.plain, cap.isatty), ("none", True, False))
		self.assertIsNone(cap.width)

	def test_level_none_on_a_tty_is_not_plain(self):
		# "No colour" and "machine-readable layout" are different decisions: a
		# monochrome terminal still gets borders, alignment and truncation.
		for environ in ({"NO_COLOR": "1"}, {"TERM": "dumb"},
						{"CATRO_COLOR": "none"}):
			with self.subTest(environ=environ):
				cap = self.detect(environ, tty=True)
				self.assertEqual((cap.level, cap.plain, cap.isatty),
								 ("none", False, True))

	def test_no_color_disables_colour_for_any_non_empty_value(self):
		# no-color.org semantics: the value does not matter, only its presence.
		for value in ("0", "false", "no", "off", "1", "anything"):
			with self.subTest(value=value):
				cap = self.detect({"NO_COLOR": value, "COLORTERM": "truecolor"})
				self.assertEqual((cap.level, cap.reason), ("none", "NO_COLOR"))

	def test_explicit_colour_request_defeats_plain_on_a_pipe(self):
		# Contract invariant 2 (amended): an explicit request on a pipe turns
		# plain OFF, so `FORCE_COLOR=3 list.py | cat` gets the full styled table
		# (borders, padding, zebra) instead of bare TAB records.
		cases = (
			({"FORCE_COLOR": "3"}, "true"),
			({"FORCE_COLOR": "1"}, "16"),
			({"CLICOLOR_FORCE": "1"}, "16"),
			({"CATRO_COLOR": "256"}, "256"),
		)
		for environ, level in cases:
			with self.subTest(environ=environ):
				cap = self.detect(environ, tty=False)
				self.assertEqual((cap.level, cap.plain, cap.isatty),
								 (level, False, False))

	def test_no_color_and_config_are_not_explicit_requests(self):
		# NO_COLOR is a refusal and config.ini a standing default: neither makes
		# a pipe styled, and NO_COLOR wins over FORCE_COLOR on the same run.
		cases = ({"NO_COLOR": "1", "FORCE_COLOR": "3"}, {"CATRO_COLOR": "none"})
		for environ in cases:
			with self.subTest(environ=environ):
				cap = self.detect(environ, tty=False)
				self.assertEqual((cap.level, cap.plain), ("none", True))
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("color", "level", "true")
			cap = self.detect({}, tty=False)
			self.assertEqual((cap.level, cap.reason, cap.plain),
							 ("true", "config.ini", True))

	def test_legacy_windows_console_falls_back_to_16(self):
		# A conhost that refuses the VT probe with no marker env is legacy.
		cap = self.detect({}, windows=True, vt=False)
		self.assertEqual((cap.level, cap.reason), ("16", "windows-legacy-console"))

	def test_conhost_vt_capable_is_truecolor(self):
		# Modern conhost accepts ENABLE_VIRTUAL_TERMINAL_PROCESSING even though
		# it exports no marker variable at all.
		cap = self.detect({}, windows=True, vt=True)
		self.assertEqual((cap.level, cap.reason), ("true", "vt-console"))

	def test_probe_failure_never_downgrades_colorterm(self):
		# COLORTERM is a declaration by the program that launched us (and is
		# inherited across consoles), so it outranks the probe.
		cap = self.detect({"COLORTERM": "truecolor"}, windows=True, vt=False)
		self.assertEqual((cap.level, cap.reason), ("true", "COLORTERM"))
		self.probe.assert_not_called()

	def test_vt_console_keeps_colorterm(self):
		cap = self.detect({"COLORTERM": "truecolor"}, windows=True, vt=True)
		self.assertEqual((cap.level, cap.reason), ("true", "COLORTERM"))
		self.probe.assert_not_called()

	def test_mintty_xterm_is_256(self):
		# Git for Windows ships mintty with TERM=xterm, so the 256color branch
		# never matches and mintty needs its own conservative rule.
		cap = self.detect({"TERM": "xterm", "TERM_PROGRAM": "mintty",
						   "MSYSTEM": "MINGW64"}, windows=True)
		self.assertEqual((cap.level, cap.reason), ("256", "mintty"))

	def test_mintty_truecolor_opt_in(self):
		cap = self.detect({"TERM": "xterm", "TERM_PROGRAM": "mintty",
						   "MSYSTEM": "MINGW64", "COLORTERM": "truecolor"},
						  windows=True)
		self.assertEqual((cap.level, cap.reason), ("true", "COLORTERM"))

	def test_inherited_term_still_256(self):
		# A console that inherits TERM=xterm-256color keeps its 256 answer.
		cap = self.detect({"TERM": "xterm-256color"}, windows=True)
		self.assertEqual((cap.level, cap.reason), ("256", "TERM"))
		self.probe.assert_not_called()

	def test_pipe_stays_plain_with_vt_probe(self):
		cap = self.detect({"TERM": "xterm-256color"}, tty=False, windows=True,
						  vt=True)
		self.assertEqual((cap.level, cap.plain), ("none", True))
		self.probe.assert_not_called()

	def test_no_color_beats_vt_probe(self):
		cap = self.detect({"NO_COLOR": "1"}, windows=True, vt=True)
		self.assertEqual((cap.level, cap.reason), ("none", "NO_COLOR"))
		self.probe.assert_not_called()

	def test_dumb_beats_vt_probe(self):
		cap = self.detect({"TERM": "dumb"}, windows=True, vt=True)
		self.assertEqual((cap.level, cap.reason), ("none", "TERM=dumb"))
		self.probe.assert_not_called()

	def test_probe_not_called_off_windows_or_pipe(self):
		self.detect({}, windows=False, vt=True)
		self.probe.assert_not_called()
		self.detect({"TERM": "xterm-256color"}, tty=False, windows=True, vt=True)
		self.probe.assert_not_called()

	def test_modern_windows_console_keeps_colorterm(self):
		cap = self.detect({"COLORTERM": "truecolor", "WT_SESSION": "1"}, windows=True)
		self.assertEqual((cap.level, cap.reason), ("true", "COLORTERM"))

	def test_windows_terminal_is_truecolor_without_colorterm(self):
		# Stock PowerShell/cmd in Windows Terminal exports only WT_SESSION:
		# the console is truecolor, so the fallthrough must not cap it at 16.
		cap = self.detect({"WT_SESSION": "1b2c3d4e"}, windows=True)
		self.assertEqual((cap.level, cap.reason, cap.plain), ("true", "WT_SESSION", False))
		# WT wins over a 256-colour TERM the same way COLORTERM does.
		cap = self.detect({"WT_SESSION": "1", "TERM": "xterm-256color"}, windows=True)
		self.assertEqual((cap.level, cap.reason), ("true", "WT_SESSION"))

	def test_unicode_flag(self):
		cases = (
			({}, "utf-8", True),
			({"LANG": "en_US.UTF-8"}, "utf-8", True),
			({"CATRO_ASCII": "1"}, "utf-8", False),
			({"TERM": "dumb"}, "utf-8", False),
			({"LANG": "C"}, "cp1252", False),
			({"LC_ALL": "POSIX"}, "cp1252", False),
			# The stream encoding is the UTF-8 hint, so a C locale still gets glyphs.
			({"LANG": "C"}, "utf-8", True),
		)
		for environ, encoding, expected in cases:
			with self.subTest(environ=environ, encoding=encoding):
				self.assertEqual(self.detect(environ, encoding=encoding).unicode, expected)

	def test_non_utf8_stream_degrades_to_ascii_glyphs(self):
		self.assertFalse(self.detect({}, encoding="cp1252").unicode)

	def test_require_tty_exits_two_with_one_line(self):
		stderr = io.StringIO()
		with mock.patch.object(sys, "stdin", FakeStream(False)), \
				mock.patch.object(sys, "stdout", FakeStream(False)), \
				redirect_stderr(stderr), \
				self.assertRaises(SystemExit) as raised:
			caps.require_tty("theme")
		self.assertEqual(raised.exception.code, 2)
		self.assertEqual(
			stderr.getvalue(),
			"[Error] theme needs an interactive terminal (stdin/stdout is not a tty).\n")

	def test_require_tty_passes_on_a_terminal(self):
		with mock.patch.object(sys, "stdin", FakeStream(True)), \
				mock.patch.object(sys, "stdout", FakeStream(True)):
			caps.require_tty("theme")

	def test_init_ansi_is_a_no_op_off_windows(self):
		with mock.patch.object(caps, "_IS_WINDOWS", False), \
				mock.patch.object(caps.os, "system") as system:
			caps.init_ansi()
		system.assert_not_called()

	def test_init_ansi_enables_ansi_on_windows(self):
		with mock.patch.object(caps, "_IS_WINDOWS", True), \
				mock.patch.object(caps.os, "system") as system:
			caps.init_ansi()
		system.assert_called_once_with("")


class ConsoleVtProbeTests(unittest.TestCase):
	"""tui.console_vt.can_vt is inert off Windows and never raises."""

	def test_can_vt_is_false_off_windows(self):
		from tui import console_vt
		with mock.patch.object(console_vt, "_IS_WINDOWS", False), \
				mock.patch.object(console_vt, "_handle") as handle:
			self.assertFalse(console_vt.can_vt())
		handle.assert_not_called()

	def test_can_vt_is_false_when_the_handle_probe_raises(self):
		from tui import console_vt
		with mock.patch.object(console_vt, "_IS_WINDOWS", True), \
				mock.patch.object(console_vt, "_handle",
								  side_effect=OSError("no console")):
			self.assertFalse(console_vt.can_vt())


if __name__ == "__main__":
	unittest.main()
