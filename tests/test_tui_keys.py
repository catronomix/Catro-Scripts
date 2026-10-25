# Key decoding and raw-mode tests
"""
		KEYBOARD TOKENS AND RAW MODE
		=============================
Token decoding is pure (`decode_key`), escape handling is driven with a pretend
stream, and termios is replaced by a fake module so the restore path can be
checked without a terminal. A child process proves `import tui` never pulls in
termios/msvcrt/curses.
"""

import io
import os
import queue
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import keys  # noqa: E402  (import after sys.path setup)


class FakeStream:
	"""Text stream with optional content and an optional file descriptor."""

	def __init__(self, text="", tty=True, fd=None):
		self._buffer = io.StringIO(text)
		self._tty = tty
		self._fd = fd

	def read(self, size=1):
		return self._buffer.read(size)

	def isatty(self):
		return self._tty

	def fileno(self):
		if self._fd is None:
			raise io.UnsupportedOperation("no descriptor")
		return self._fd


class DecodeTests(unittest.TestCase):
	def test_cursor_and_function_keys(self):
		cases = {
			"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
			"\x1bOA": "up", "\x1bOB": "down", "\x1b[H": "home", "\x1b[F": "end",
			"\x1b[1~": "home", "\x1b[4~": "end", "\x1b[5~": "pageup",
			"\x1b[6~": "pagedown", "\x1b[3~": "delete",
		}
		for raw, token in cases.items():
			with self.subTest(raw=raw):
				self.assertEqual(keys.decode_key(raw), token)

	def test_simple_tokens(self):
		cases = {"\r": "enter", "\n": "enter", "\t": "tab", " ": "space",
				 "\x7f": "backspace", "\x08": "backspace", "\x1b": "esc"}
		for raw, token in cases.items():
			with self.subTest(raw=raw):
				self.assertEqual(keys.decode_key(raw), token)

	def test_control_keys(self):
		self.assertEqual(keys.decode_key("\x01"), "ctrl-a")
		self.assertEqual(keys.decode_key("\x03"), "ctrl-c")
		self.assertEqual(keys.decode_key("\x1a"), "ctrl-z")

	def test_printable_characters_pass_through(self):
		self.assertEqual(keys.decode_key("q"), "q")
		self.assertEqual(keys.decode_key("\u00e9"), "\u00e9")

	def test_empty_input_is_none(self):
		self.assertIsNone(keys.decode_key(""))


class EscapeSequenceTests(unittest.TestCase):
	def read(self, text, timeout=None):
		return keys._read_key_stream(FakeStream(text), timeout)

	def test_arrow_key_is_one_token(self):
		self.assertEqual(self.read("\x1b[A"), "up")

	def test_bare_escape_is_esc(self):
		self.assertEqual(self.read("\x1b"), "esc")

	def test_pageup_with_digits_is_one_token(self):
		self.assertEqual(self.read("\x1b[5~rest"), "pageup")

	def test_unknown_sequence_is_esc(self):
		self.assertEqual(self.read("\x1b[99z"), "esc")

	def test_ordinary_key_is_decoded(self):
		self.assertEqual(self.read("x"), "x")

	def test_eof_is_none(self):
		self.assertIsNone(self.read(""))

	def test_timeout_returns_none(self):
		read_fd, write_fd = os.pipe()
		try:
			stream = FakeStream(fd=read_fd)
			self.assertIsNone(self.read_with_stream(stream, 0.01))
		finally:
			os.close(read_fd)
			os.close(write_fd)

	def read_with_stream(self, stream, timeout):
		return keys._read_key_stream(stream, timeout)


class RawModeTests(unittest.TestCase):
	class FakeTermios:
		TCSADRAIN = "drain"

		def __init__(self):
			self.settings = object()
			self.restored = None

		def tcgetattr(self, fd):
			self.settings = ("saved", fd)
			return self.settings

		def tcsetattr(self, fd, when, settings):
			self.restored = (fd, when, settings)

	class FakeTty:
		def __init__(self):
			self.calls = []

		def setcbreak(self, fd):
			self.calls.append(fd)

	def run_raw(self, body):
		fake_termios, fake_tty = self.FakeTermios(), self.FakeTty()
		stream = FakeStream(tty=True, fd=7)
		with mock.patch.dict(sys.modules, {"termios": fake_termios, "tty": fake_tty}), \
				mock.patch.object(keys, "os", SimpleNamespace(name="posix")):
			body(keys.raw_mode(stream))
		return fake_termios, fake_tty

	def test_cbreak_is_set_and_restored(self):
		fake_termios, fake_tty = self.run_raw(self._enter)
		self.assertEqual(fake_tty.calls, [7])
		self.assertEqual(fake_termios.restored, (7, "drain", ("saved", 7)))

	def test_restore_happens_on_exception(self):
		fake_termios, _ = self.run_raw(self._raise)
		self.assertEqual(fake_termios.restored, (7, "drain", ("saved", 7)))

	def _enter(self, manager):
		with manager:
			pass

	def _raise(self, manager):
		with self.assertRaises(RuntimeError):
			with manager:
				raise RuntimeError("boom")

	def test_off_a_tty_nothing_changes(self):
		stream = FakeStream(tty=False)
		with mock.patch.dict(sys.modules, {"termios": None, "tty": None}):
			with keys.raw_mode(stream) as entered:
				self.assertIs(entered, stream)


class KeyReaderTests(unittest.TestCase):
	def test_queue_and_wait(self):
		feed = queue.Queue()

		def fake_reader():
			try:
				return feed.get(timeout=0.05)
			except queue.Empty:
				return None

		reader = keys.KeyReader(reader=fake_reader).start()
		try:
			feed.put("up")
			feed.put("down")
			self.assertEqual(reader.wait(2.0), "up")
			self.assertEqual(reader.poll(), "down")
			self.assertIsNone(reader.poll())
			self.assertIsNone(reader.wait(0.05))
		finally:
			reader.stop()

	def test_stop_is_idempotent(self):
		reader = keys.KeyReader(reader=lambda: None)
		reader.start()
		reader.stop()
		reader.stop()


class ImportSafetyTests(unittest.TestCase):
	def test_no_platform_module_is_imported(self):
		code = ("import sys, tui; from tui import keys; "
				"print('termios' in sys.modules, 'msvcrt' in sys.modules, "
				"'curses' in sys.modules, 'tty' in sys.modules)")
		with tempfile.TemporaryDirectory() as td:
			env = dict(os.environ, PYTHONPYCACHEPREFIX=td)
			proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env=env,
								  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
								  stderr=subprocess.PIPE, timeout=60)
		self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
		self.assertEqual(proc.stdout.decode("utf-8").strip(), "False False False False")


if __name__ == "__main__":
	unittest.main()
