# Progress indicators
"""
			SPINNER, PROGRESS BAR, LIVE REGION
			====================================
Three small indicators for work that takes long enough to need feedback. On a
non-tty stream, and when colour is off (a pipe or level "none"), each one
degrades to a single final line: no carriage-return animation, no escape codes,
never an error.
"""

import sys

from . import caps
from .text import pad, truncate

SPINNER_FRAMES = ("\u280b", "\u2819", "\u2839", "\u2838", "\u283c",
				  "\u2834", "\u2826", "\u2827", "\u2807", "\u280f")


class Spinner:
	"""Single-line animation; `tick()` per step, `stop()` at the end."""

	def __init__(self, frames=SPINNER_FRAMES, interval=0.1, stream=None, cap=None):
		self.frames = tuple(frames) or SPINNER_FRAMES
		self.interval = float(interval)
		self.stream = sys.stdout if stream is None else stream
		self.cap = cap or caps.detect(self.stream)
		self._index = 0
		self._line = ""

	def __enter__(self):
		return self

	def __exit__(self, *exc_info):
		self.stop()

	def tick(self, label=""):
		"""Advance one frame; a no-op when animation is off."""
		if not _animating(self.cap):
			return self
		frame = self.frames[self._index % len(self.frames)]
		self._index += 1
		self._line = "{} {}".format(frame, label).rstrip()
		self.stream.write("\r" + self._line)
		self.stream.flush()
		return self

	def stop(self, label=None):
		"""Stop animating and print at most one final line."""
		text = self._line if label is None else str(label)
		if not _animating(self.cap):
			if text:
				self.stream.write(text + "\n")
				self.stream.flush()
			return self
		self.stream.write("\r\033[K")
		if text:
			self.stream.write(text + "\n")
		self.stream.flush()
		return self


def bar(value, total, width, *, cap=None):
	"""One bar's glyphs: `value/total` filled cells, then the empty track.

	The seam the editor's preview uses, so the progress look has exactly one
	implementation; `ProgressBar._bar` delegates here.
	"""
	cap = cap or caps.detect()
	total, width = max(1, int(total)), max(0, int(width))
	filled = int(round(width * max(0, min(int(value), total)) / total))
	return ("\u2588" if cap.unicode else "#") * filled \
		+ ("\u2591" if cap.unicode else "-") * (width - filled)


class ProgressBar:
	"""`label 42% (21/50)` style progress, animated only on a tty."""

	def __init__(self, total, width=30, stream=None, cap=None, label=""):
		self.total = max(1, int(total))
		self.width = max(5, int(width))
		self.stream = sys.stdout if stream is None else stream
		self.cap = cap or caps.detect(self.stream)
		self.label = str(label)
		self.value = 0

	def update(self, value, label=None):
		self.value = max(0, min(int(value), self.total))
		if label is not None:
			self.label = str(label)
		if not _animating(self.cap):
			return self
		self.stream.write("\r" + self.line(self._bar()))
		self.stream.flush()
		return self

	def finish(self, label=None):
		"""Print the final summary line once."""
		if label is not None:
			self.label = str(label)
		if _animating(self.cap):
			self.stream.write("\r\033[K")
		self.stream.write(self.line() + "\n")
		self.stream.flush()
		return self

	def line(self, bar=None):
		"""The summary text: `label [bar] n% (value/total)`."""
		percent = int(round(100.0 * self.value / self.total))
		parts = [self.label] if self.label else []
		if bar is not None:
			parts.append(bar)
		parts.append("{}% ({}/{})".format(percent, self.value, self.total))
		return " ".join(parts)

	def _bar(self):
		return bar(self.value, self.total, self.width, cap=self.cap)


class LiveRegion:
	"""A fixed rectangle on a `Screen` that is repainted in place."""

	def __init__(self, screen, x, y, width, max_lines=1):
		self.screen = screen
		self.x = int(x)
		self.y = int(y)
		self.width = max(1, int(width))
		self.max_lines = max(1, int(max_lines))

	def update(self, lines):
		"""Replace the region content; plain output degrades to lines."""
		if isinstance(lines, str):
			lines = [lines]
		rows = [str(line) for line in lines][:self.max_lines]
		if not _isatty(self.screen.stream):
			for row in rows:
				self.screen.write(row + "\n")
			self.screen.flush()
			return self
		for index, row in enumerate(rows):
			self.screen.move(self.x, self.y + index)
			self.screen.write(pad(truncate(row, self.width), self.width))
		for index in range(len(rows), self.max_lines):
			self.screen.move(self.x, self.y + index)
			self.screen.write(" " * self.width)
		self.screen.flush()
		return self


def _animating(cap):
	"""True when in-place animation is both possible and wanted.

	Animation needs a real terminal *and* colour: a forced-colour pipe has
	`plain` off but still cannot repaint a line, so `\\r\\033[K` would land in a
	file. Level "none" means no escape codes either; every case prints one
	final line.
	"""
	return cap.isatty and cap.level != "none"


def _isatty(stream):
	try:
		return bool(stream.isatty())
	except (AttributeError, ValueError, OSError):
		return False
