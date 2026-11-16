# Reusable multi-line progress box for batch runs
"""
			BATCH PROGRESS BOX
			==================
One box a batch run keeps reusing: the title, the current operation, an
overall i/N bar and a growing list of ok/warn/error rows. On a terminal every
update rewrites the same frame in place (cursor up to the frame's first line,
rewrite, erase to end of line); on a pipe each update is one TAB record and no
escape, frame glyph or padding is emitted. The frame is composed by
`chrome.panel`/`chrome.status`/`chrome.field`, so it looks like every other
page. Rendering never raises and never wraps: the panel width is clamped to the
terminal width so the emitted line count stays true.

Level "none" on a terminal keeps the frame and drops the escapes: updates are
silent and `close()` paints the final box once.
"""

import sys

from . import caps, chrome
from .progress import bar

BAR_WIDTH = 20
DEFAULT_WIDTH = 60


class BatchBox:
	"""One reused progress box; `update()` repaints, `close()` leaves it final."""

	def __init__(self, title, total, *, stream=None, cap=None, width=None):
		self.title = str(title)
		self.total = max(1, int(total))
		self.stream = sys.stdout if stream is None else stream
		self.cap = cap or caps.detect(self.stream)
		self.width = self._span(width)
		self.done = 0
		self.op = ""
		self.rows = []
		self._lines = 0
		self._shown = 0

	def _span(self, width):
		"""Outer width: explicit, else the terminal's, never over the terminal."""
		span = DEFAULT_WIDTH if width is None else max(20, int(width))
		if self.cap.width:
			span = min(span, int(self.cap.width))
		return max(20, span)

	def update(self, op=None, done=None, rows=None):
		"""Repaint with the current operation, completed count and rows."""
		if op is not None:
			self.op = str(op)
		if done is not None:
			self.done = max(0, min(int(done), self.total))
		if rows is not None:
			self.rows = [(str(kind), str(text)) for kind, text in rows]
		if self.cap.plain:
			self._record()
		elif self._live():
			self._paint()
		return self

	def add(self, kind, text):
		"""Append one outcome row and repaint."""
		self.rows.append((str(kind), str(text)))
		if self.cap.plain:
			for kind, text in self._fresh():
				self.stream.write("{}\t{}\n".format(kind, text))
			self.stream.flush()
			return self
		return self.update()

	def close(self, final_line=None):
		"""Finish at 100%, optionally add a summary row, leave the box readable."""
		if final_line is not None:
			self.rows.append(("info", str(final_line)))
		self.done = self.total
		if self.cap.plain:
			self._record()
		else:
			self._paint()
		return self

	def _live(self):
		"""In-place redraw needs a terminal that accepts cursor movement."""
		return self.cap.isatty and self.cap.level != "none"

	def _fresh(self):
		"""Rows not yet emitted to the record stream."""
		new = self.rows[self._shown:]
		self._shown = len(self.rows)
		return new

	def _record(self):
		"""One TAB record per update, plus a record per newly finished row."""
		write = self.stream.write
		write("{}\t{}/{}\n".format(self.op, self.done, self.total))
		for kind, text in self._fresh():
			write("{}\t{}\n".format(kind, text))
		self.stream.flush()

	def _bar(self):
		percent = int(round(100.0 * self.done / self.total))
		return "{}/{} {} {}%".format(self.done, self.total,
									 bar(self.done, self.total, BAR_WIDTH,
										 cap=self.cap), percent)

	def _frame(self):
		body = [chrome.field("current", self.op or "-", cap=self.cap), self._bar()]
		body.extend(chrome.status(kind, text, cap=self.cap)
					for kind, text in self.rows)
		return chrome.panel(self.title, body, width=self.width, cap=self.cap)

	def _paint(self):
		lines = self._frame().split("\n")
		out = self.stream
		if self.cap.level == "none":
			out.write("\n".join(lines) + "\n")
			self._lines = len(lines)
			out.flush()
			return
		if self._lines:
			out.write("\x1b[{}A\r".format(self._lines))
		for line in lines:
			out.write(line + "\x1b[K\n")
		for _ in range(len(lines), self._lines):
			out.write("\x1b[K\n")
		self._lines = len(lines)
		out.flush()
