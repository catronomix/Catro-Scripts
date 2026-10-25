# Pager tests
"""
			PAGED OUTPUT
			=============
`page()` must dump everything unchanged off a tty and page in place on one. The
key read is a *blocking* read: a polling select would return None immediately,
advance the offset and flash every page past the reader. These tests drive the
real read path over a pipe and record what `select()` was asked for, with a fake
select that blocks until the feeder writes (so the test stays portable: real
select() cannot wait on a pipe on Windows).
"""

import io
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import keys, pager  # noqa: E402  (import after sys.path setup)


class FakeStream:
	"""Text stream with a tty flag and no file descriptor."""

	def __init__(self, tty=True):
		self._buffer = io.StringIO()
		self._tty = tty
		self.encoding = "utf-8"

	def write(self, text):
		return self._buffer.write(text)

	def flush(self):
		pass

	def getvalue(self):
		return self._buffer.getvalue()

	def isatty(self):
		return self._tty

	def fileno(self):
		raise io.UnsupportedOperation("no descriptor")


class PipeStream:
	"""stdin replacement that reads bytes from a real pipe descriptor."""

	def __init__(self, fd):
		self._fd = fd
		self.encoding = "utf-8"

	def read(self, size=1):
		return os.read(self._fd, size).decode("utf-8")

	def isatty(self):
		return True

	def fileno(self):
		return self._fd


class PagerTests(unittest.TestCase):
	def feed(self, chars, delay=0.05):
		"""Write `chars` to a pipe, one at a time, and signal readiness."""
		read_fd, write_fd = os.pipe()
		ready = threading.Event()

		def writer():
			for char in chars:
				time.sleep(delay)
				os.write(write_fd, char.encode("utf-8"))
				ready.set()

		thread = threading.Thread(target=writer)
		thread.start()
		return read_fd, write_fd, ready, thread

	def run_page(self, lines, chars, page_size=2):
		read_fd, write_fd, ready, thread = self.feed(chars)
		stream = FakeStream(tty=True)
		timeouts = []
		posix = mock.Mock(name="os")
		posix.name = "posix"

		def fake_select(readers, writers, errors, timeout):
			timeouts.append(timeout)
			if timeout is not None:
				return ([], [], [])
			# A blocking read: wait for the feeder, like select() would.
			ready.wait(5.0)
			ready.clear()
			return (list(readers), [], [])

		try:
			with mock.patch("select.select", fake_select), \
					mock.patch.object(keys, "os", posix), \
					mock.patch.object(sys, "stdin", PipeStream(read_fd)):
				pager.page(lines, page_size=page_size, stream=stream)
		finally:
			thread.join(5.0)
			os.close(read_fd)
			os.close(write_fd)
		return stream.getvalue(), timeouts

	def test_non_tty_prints_every_line_unchanged(self):
		stream = FakeStream(tty=False)
		pager.page(["one", "two", "three"], page_size=1, stream=stream)
		self.assertEqual(stream.getvalue(), "one\ntwo\nthree\n")
		self.assertNotIn("\033", stream.getvalue())

	def test_blocking_mode_can_read_every_page(self):
		"""Two spaces then q: all three pages show, and select was never polled."""
		lines = ["line-{}".format(index) for index in range(6)]
		out, timeouts = self.run_page(lines, (" ", " ", "q"))
		for line in lines:
			self.assertIn(line, out, "page never showed {!r}".format(line))
		self.assertTrue(timeouts, "the reader never reached select()")
		self.assertEqual([timeout for timeout in timeouts if timeout is not None], [],
						 "blocking keys must pass None to select(), not 0")

	def test_exit_key_stops_early(self):
		lines = ["line-{}".format(index) for index in range(10)]
		out, _ = self.run_page(lines, ("q",))
		self.assertIn("line-0\n", out)
		self.assertNotIn("line-8", out)


if __name__ == "__main__":
	unittest.main()
