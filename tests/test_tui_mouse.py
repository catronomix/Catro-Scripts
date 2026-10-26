# Mouse reporting tests: SGR decoding, enable/disable, key tokens
"""
			MOUSE INPUT
			============
`tui/mouse.py` decoded and reported over a fake tty: every event kind and
modifier, the mode bytes written by `enable()`/`disable()` (and the guarantee
that a non-tty stream stays silent), `token()` round-trips and the `mouse:...`
tokens `tui.keys` emits. A child process proves the module imports no platform
layer on its own.
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import keys, mouse  # noqa: E402  (import after sys.path setup)


class FakeStream:
	"""Capturing stream that is a tty only when a test says so."""

	def __init__(self, text="", tty=True):
		self._buffer = io.StringIO(text)
		self._tty = tty
		self.written = io.StringIO()

	def read(self, size=1):
		return self._buffer.read(size)

	def isatty(self):
		return self._tty

	def write(self, text):
		return self.written.write(text)

	def flush(self):
		return None


def sgr(code, x=1, y=1, final="M"):
	return "\x1b[<{};{};{}{}".format(code, x, y, final)


class BrokenStream:
	"""A tty whose writes fail, for the failed-enable path."""

	def __init__(self):
		self.written = io.StringIO()

	def isatty(self):
		return True

	def write(self, text):
		raise OSError("no tty after all")

	def flush(self):
		return None


class DecodeTests(unittest.TestCase):
	def test_press_and_release(self):
		self.assertEqual(mouse.decode(sgr(0, 3, 7)), ("press", 2, 6, ()))
		self.assertEqual(mouse.decode(sgr(0, 3, 7, "m")), ("release", 2, 6, ()))

	def test_wheel_directions(self):
		kinds = [mouse.decode(sgr(64 + index))[0] for index in range(4)]
		self.assertEqual(kinds, ["wheel-up", "wheel-down",
								 "wheel-left", "wheel-right"])

	def test_drag_and_bare_motion(self):
		self.assertEqual(mouse.decode(sgr(32, 5, 2))[0], "drag")
		self.assertEqual(mouse.decode(sgr(35, 5, 2))[0], "move")

	def test_modifiers_are_named(self):
		self.assertEqual(mouse.decode(sgr(4))[3], ("shift",))
		self.assertEqual(mouse.decode(sgr(8))[3], ("alt",))
		self.assertEqual(mouse.decode(sgr(16))[3], ("ctrl",))
		self.assertEqual(mouse.decode(sgr(28))[3], ("shift", "alt", "ctrl"))

	def test_non_mouse_input_is_none(self):
		for raw in ("", "\x1b[A", "q", "\x1b[<", "\x1b[<a;b;cM", "\x1b[<0;1M"):
			with self.subTest(raw=raw):
				self.assertIsNone(mouse.decode(raw))

	def test_token_round_trip(self):
		event = ("press", 2, 6, ("shift", "ctrl"))
		self.assertEqual(mouse.token(event), "mouse:press:2:6:shift,ctrl")
		self.assertEqual(mouse.parse_token(mouse.token(event)), event)
		self.assertEqual(mouse.token(("wheel-up", 0, 0, ())), "mouse:wheel-up:0:0")
		self.assertEqual(mouse.token(None), "")

	def test_token_never_raises_on_a_malformed_event(self):
		for event in ((), ("press",), ("press", 1), ("press", 1, 2),
					  ("press", "x", 2, ()), ("press", 1, 2, 5),
					  (1, 2, 3, 4), "press:1:2", 7):
			with self.subTest(event=event):
				self.assertEqual(mouse.token(event), "")

	def test_parse_token_ignores_key_tokens(self):
		for token in ("enter", "mouse:", "mouse:press:x:1", "mouse:press:1:2:3"):
			with self.subTest(token=token):
				self.assertIsNone(mouse.parse_token(token))


class ReportingTests(unittest.TestCase):
	def setUp(self):
		mouse.disable()

	def tearDown(self):
		mouse.disable()

	def test_enable_writes_the_sgr_modes_on_a_tty(self):
		stream = FakeStream()
		self.assertTrue(mouse.enable(stream))
		written = stream.written.getvalue()
		for code in ("?1000h", "?1002h", "?1006h"):
			self.assertIn(code, written)

	def test_keyboard_only_without_drag(self):
		stream = FakeStream()
		mouse.enable(stream, drag=False)
		written = stream.written.getvalue()
		self.assertIn("?1000h", written)
		self.assertNotIn("?1002h", written)
		self.assertIn("?1006h", written)

	def test_off_a_tty_nothing_is_written(self):
		stream = FakeStream(tty=False)
		self.assertFalse(mouse.enable(stream))
		self.assertFalse(mouse.disable(stream))
		self.assertEqual(stream.written.getvalue(), "")

	def test_disable_restores_once(self):
		stream = FakeStream()
		mouse.enable(stream)
		stream.written.truncate(0)
		stream.written.seek(0)
		self.assertTrue(mouse.disable(stream))
		restore = stream.written.getvalue()
		for code in ("?1000l", "?1002l", "?1006l"):
			self.assertIn(code, restore)
		stream.written.truncate(0)
		stream.written.seek(0)
		self.assertFalse(mouse.disable(stream))
		self.assertEqual(stream.written.getvalue(), "")

	def test_reporting_context_manager_restores(self):
		stream = FakeStream()
		with mouse.reporting(stream) as active:
			self.assertIs(active, stream)
			self.assertFalse(mouse.enable(FakeStream(tty=False)))
		self.assertIn("?1006l", stream.written.getvalue())
		self.assertFalse(mouse.disable(stream))

	def test_enable_reports_a_failed_write_and_stays_disarmed(self):
		stream = BrokenStream()
		self.assertFalse(mouse.enable(stream))
		self.assertFalse(mouse.disable(stream))
		self.assertEqual(stream.written.getvalue(), "")
		good = FakeStream()
		self.assertTrue(mouse.enable(good))
		self.assertTrue(mouse.disable(good))

	def test_reporting_restores_the_terminal_when_the_body_raises(self):
		stream = FakeStream()
		with self.assertRaises(RuntimeError):
			with mouse.reporting(stream):
				raise RuntimeError("boom")
		restore = stream.written.getvalue()
		for code in ("?1000l", "?1002l", "?1006l"):
			self.assertIn(code, restore)
		self.assertFalse(mouse.disable(stream))


class KeyTokenTests(unittest.TestCase):
	def test_decode_key_emits_a_mouse_token(self):
		self.assertEqual(keys.decode_key(sgr(0, 3, 7)), "mouse:press:2:6")
		self.assertEqual(keys.decode_key(sgr(65, 1, 1)), "mouse:wheel-down:0:0")

	def test_stream_reads_one_mouse_token(self):
		stream = FakeStream(sgr(0, 10, 4))
		self.assertEqual(keys._read_key_stream(stream, 0.5), "mouse:press:9:3")

	def test_truncated_mouse_sequence_falls_back_to_esc(self):
		stream = FakeStream("\x1b[<0;1")
		self.assertEqual(keys._read_key_stream(stream, 0.5), "esc")

	def test_ordinary_keys_are_unchanged(self):
		self.assertEqual(keys.decode_key("\x1b[A"), "up")
		self.assertEqual(keys.decode_key("\t"), "tab")


class ImportSafetyTests(unittest.TestCase):
	def test_no_platform_module_at_import(self):
		code = ("import sys, tui; from tui import mouse, widgets; "
				"print('ctypes' in sys.modules, 'msvcrt' in sys.modules, "
				"'termios' in sys.modules)")
		with tempfile.TemporaryDirectory() as td:
			env = dict(os.environ, PYTHONPYCACHEPREFIX=td)
			proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
								  env=env, stdin=subprocess.DEVNULL,
								  stdout=subprocess.PIPE,
								  stderr=subprocess.PIPE, timeout=60)
		self.assertEqual(proc.returncode, 0,
						 proc.stderr.decode("utf-8", "replace"))
		self.assertEqual(proc.stdout.decode("utf-8").strip(),
						 "False False False")


if __name__ == "__main__":
	unittest.main()
