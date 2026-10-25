# Cross-platform single-key input
"""
			KEYBOARD INPUT
			===============
Raw (cbreak) mode, key decoding and a background reader, generalised from
`keygen.py` and the screensaver's listener.

Tokens: up, down, left, right, home, end, pageup, pagedown, enter, esc,
backspace, delete, tab, space, ctrl-a .. ctrl-z, or the character itself. A bare
ESC is told apart from an escape sequence by a short read timeout.

No platform module is imported at import time, and `raw_mode()` leaves the
terminal alone when stdin is not a tty. `decode_key()` is the pure token decoder
the tests drive with pretend input, and `KeyReader(reader=...)` accepts a fake
reader so the thread can be tested without a keyboard.
"""

import os
import sys
import threading
import time
from contextlib import contextmanager

ESCAPE_TIMEOUT = 0.05

_SEQUENCES = {
	"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
	"\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left",
	"\x1b[H": "home", "\x1b[F": "end", "\x1b[1~": "home", "\x1b[4~": "end",
	"\x1b[5~": "pageup", "\x1b[6~": "pagedown", "\x1b[3~": "delete",
	"\x1b[2~": "insert",
}

_SIMPLE = {
	"\r": "enter", "\n": "enter", "\t": "tab", " ": "space",
	"\x7f": "backspace", "\x08": "backspace", "\x1b": "esc",
}

# msvcrt second byte of an extended key -> token.
_WINDOWS_SPECIAL = {
	"H": "up", "P": "down", "M": "right", "K": "left",
	"G": "home", "O": "end", "I": "pageup", "Q": "pagedown",
	"S": "delete", "R": "insert",
}


def decode_key(text):
	"""Normalise one decoded key (or escape sequence) into a token."""
	if not text:
		return None
	if text in _SEQUENCES:
		return _SEQUENCES[text]
	if text in _SIMPLE:
		return _SIMPLE[text]
	if len(text) > 1:
		return "esc" if text.startswith("\x1b") else text[0]
	code = ord(text)
	if 1 <= code <= 26:
		return "ctrl-" + chr(code + 96)
	return text


@contextmanager
def raw_mode(stream=None):
	"""Put the terminal in cbreak mode for the block; always restore it."""
	stream = sys.stdin if stream is None else stream
	if os.name == "nt" or not _isatty(stream):
		yield stream
		return
	import termios
	import tty

	fd = stream.fileno()
	settings = termios.tcgetattr(fd)
	try:
		tty.setcbreak(fd)
		yield stream
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, settings)


def read_key(timeout=None, stream=None):
	"""One normalised key token, or None when `timeout` expires."""
	if os.name == "nt":
		return _read_key_windows(timeout)
	return _read_key_stream(sys.stdin if stream is None else stream, timeout)


class KeyReader:
	"""Background thread that keeps the latest key tokens in a queue."""

	def __init__(self, reader=None):
		self._reader = reader or (lambda: read_key(timeout=0.1))
		self._keys = []
		self._lock = threading.Lock()
		self._stop = threading.Event()
		self._thread = None

	def start(self):
		if self._thread is None:
			self._stop.clear()
			self._thread = threading.Thread(target=self._run, daemon=True)
			self._thread.start()
		return self

	def stop(self):
		self._stop.set()
		thread = self._thread
		self._thread = None
		if thread is not None:
			thread.join(1.0)
		return self

	def poll(self):
		"""Next token, or None when the queue is empty."""
		with self._lock:
			return self._keys.pop(0) if self._keys else None

	def wait(self, timeout=None):
		"""Block until a token arrives or `timeout` expires."""
		deadline = None if timeout is None else time.monotonic() + timeout
		while True:
			key = self.poll()
			if key is not None:
				return key
			if deadline is not None and time.monotonic() >= deadline:
				return None
			time.sleep(0.01)

	def _run(self):
		while not self._stop.is_set():
			try:
				key = self._reader()
			except Exception:
				return
			if key is None:
				continue
			with self._lock:
				self._keys.append(key)


def _read_key_stream(stream, timeout):
	if not _wait(stream, timeout):
		return None
	text = _read_byte(stream)
	if not text:
		return None
	if text == "\x1b":
		return _decode_escape(stream)
	return decode_key(text)


def _read_byte(stream):
	"""One character, taken from the descriptor itself when there is one.

	`select()` only sees the descriptor, never Python's text buffer, so the two
	must not be mixed while a cursor sequence is in flight: the first buffered
	`read(1)` could swallow the whole `\\x1b[6~`, leaving the readiness check
	with an empty descriptor - a real terminal then decoded pagedown as a bare
	ESC and the pager closed on the first key. Reading the descriptor directly
	keeps the bytes and the readiness test looking at the same place.
	"""
	fd = _fileno(stream)
	if fd is None:
		return stream.read(1) or None
	try:
		data = os.read(fd, 1)
	except OSError:
		return None
	return data.decode("utf-8", "replace") or None


def _decode_escape(stream):
	"""ESC already consumed: resolve a cursor/function sequence or a bare ESC."""
	second = _read_more(stream)
	if second not in ("[", "O"):
		return "esc"
	sequence = "\x1b" + second
	char = _read_more(stream)
	if char is None:
		return "esc"
	sequence += char
	while sequence[-1].isdigit() or sequence[-1] == ";":
		char = _read_more(stream)
		if char is None:
			break
		sequence += char
	return _SEQUENCES.get(sequence, "esc")


def _read_more(stream):
	if not _wait(stream, ESCAPE_TIMEOUT):
		return None
	return _read_byte(stream)


def _wait(stream, timeout):
	"""True when a byte is ready; a non-fd stream (tests) always is."""
	fd = _fileno(stream)
	if fd is None:
		return True
	import select

	try:
		# A blocking read passes None: select() then waits instead of polling,
		# which is what keeps `pager.page()` from flashing on POSIX.
		wait = None if timeout is None else timeout
		return bool(select.select([fd], [], [], wait)[0])
	except (OSError, ValueError):
		return False


def _read_key_windows(timeout=None):
	import msvcrt

	deadline = None if timeout is None else time.monotonic() + timeout
	while not msvcrt.kbhit():
		if deadline is not None and time.monotonic() >= deadline:
			return None
		time.sleep(0.01)
	first = msvcrt.getch()
	if first in (b"\x00", b"\xe0"):
		return _WINDOWS_SPECIAL.get(msvcrt.getch().decode("latin-1", "ignore"))
	return decode_key(first.decode("utf-8", "ignore"))


def _fileno(stream):
	try:
		return stream.fileno()
	except (AttributeError, ValueError, OSError):
		return None


def _isatty(stream):
	try:
		return bool(stream.isatty())
	except (AttributeError, ValueError, OSError):
		return False
