# Full-screen primitives: alternate screen, cursor, canvas
"""
			SCREEN AND CANVAS
			==================
`Screen` owns the alternate-screen/cursor lifecycle. `Canvas` is the
double-buffered cell grid the screensaver used to call `TerminalRenderer`; the
old name is kept as a subclass so `.screensaver` files keep working unchanged
(width, height, clear, draw_char, draw_text, render).

Both are inert off a tty: `Screen.enter()` writes nothing, and every write goes
to the injected `stream` so behaviour is testable with fake streams. Colors stay
raw ANSI strings, so existing plugins keep passing their own escape codes.

Test seam: patch `tui.screen.terminal_size` to return a fixed (width, height).
"""

import os
import shutil
import sys

from . import caps, palette

ALT_SCREEN_ON = "\033[?1049h"
ALT_SCREEN_OFF = "\033[?1049l"
CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
SGR_RESET = "\033[0m"
CLEAR_HOME = "\033[2J\033[H"


def terminal_size(stream=None):
	"""(columns, lines) for `stream`, falling back to the process terminal."""
	stream = sys.stdout if stream is None else stream
	try:
		size = os.get_terminal_size(stream.fileno())
		return (size.columns, size.lines)
	except (OSError, ValueError, AttributeError):
		pass
	try:
		size = shutil.get_terminal_size()
		return (size.columns, size.lines)
	except (OSError, ValueError):
		return (80, 24)


def _isatty(stream):
	try:
		return bool(stream.isatty())
	except (AttributeError, ValueError, OSError):
		return False


class Screen:
	"""Alternate screen plus cursor lifecycle for one terminal session."""

	def __init__(self, stream=None):
		self.stream = sys.stdout if stream is None else stream
		self.entered = False
		self._size = terminal_size(self.stream)

	def __enter__(self):
		self.enter()
		return self

	def __exit__(self, *exc_info):
		self.exit()
		return False

	def enter(self):
		"""Alt screen on, cursor hidden, cleared and homed; no-op off a tty."""
		if not _isatty(self.stream):
			return self
		self.stream.write(ALT_SCREEN_ON + CURSOR_HIDE + CLEAR_HOME)
		self.stream.flush()
		self.entered = True
		self._size = terminal_size(self.stream)
		return self

	def exit(self):
		"""Cursor shown, SGR reset, alt screen off; safe to call twice."""
		if not self.entered:
			return self
		self.stream.write(CURSOR_SHOW + SGR_RESET + ALT_SCREEN_OFF)
		self.stream.flush()
		self.entered = False
		return self

	def clear(self):
		self.write(CLEAR_HOME)
		return self

	def fill(self, role="bg"):
		"""Clear the screen and paint every row with the theme background.

		`role` is a palette key (or an explicit colour) - `bg` is the page
		background. Off a tty nothing is written; at colour level "none" there
		is nothing to paint, so nothing is written either (not even the clear,
		which is itself an escape). Returns `self` for chaining.
		"""
		if not _isatty(self.stream):
			return self
		cap = caps.detect(self.stream)
		if cap.level == "none":
			return self
		width, height = self.size()
		row = (palette.prefix(bg=role, cap=cap) + " " * width
			   + palette.RESET)
		self.write(CLEAR_HOME + "\n".join([row] * height))
		self.flush()
		return self

	def home(self):
		self.write("\033[H")
		return self

	def move(self, x, y):
		self.write("\033[{};{}H".format(int(y) + 1, int(x) + 1))
		return self

	def hide_cursor(self):
		self.write(CURSOR_HIDE)
		return self

	def show_cursor(self):
		self.write(CURSOR_SHOW)
		return self

	def write(self, text):
		self.stream.write(text)
		return self

	def flush(self):
		self.stream.flush()
		return self

	def size(self):
		"""Current (columns, lines), refreshed from the stream."""
		self._size = terminal_size(self.stream)
		return self._size

	def poll_resize(self):
		"""True when the terminal size changed since the last call."""
		width, height = terminal_size(self.stream)
		if (width, height) == self._size:
			return False
		self._size = (width, height)
		return True


class Canvas:
	"""Double-buffered character grid with color-per-cell support."""

	def __init__(self, width=None, height=None, stream=None):
		self.stream = sys.stdout if stream is None else stream
		if width is None or height is None:
			width, height = terminal_size(self.stream)
		self.width = max(1, int(width))
		self.height = max(1, int(height))
		self._buffer = []
		self._colors = []
		self._blank()
		self._previous = None
		self._previous_colors = None

	def _blank(self):
		self._buffer = [[" "] * self.width for _ in range(self.height)]
		self._colors = [[None] * self.width for _ in range(self.height)]

	def clear(self):
		"""Blank the grid, re-reading the terminal size first."""
		width, height = terminal_size(self.stream)
		if (width, height) != (self.width, self.height):
			self.width = max(1, int(width))
			self.height = max(1, int(height))
			self._blank()
		else:
			for row in self._buffer:
				row[:] = [" "] * self.width
			for row in self._colors:
				row[:] = [None] * self.width
		self._previous = None
		self._previous_colors = None

	def draw_char(self, x, y, char, color=None):
		"""Draw one character at (x, y); out-of-bounds writes are dropped."""
		x, y = int(x), int(y)
		if not (0 <= x < self.width and 0 <= y < self.height):
			return
		text = str(char)
		self._buffer[y][x] = text[0] if text else " "
		self._colors[y][x] = color

	def draw_text(self, x, y, text, color=None):
		"""Draw a string from (x, y), one cell per character."""
		for offset, char in enumerate(str(text)):
			self.draw_char(x + offset, y, char, color)

	def hline(self, x, y, length, char="\u2500"):
		for offset in range(int(length)):
			self.draw_char(x + offset, y, char)

	def vline(self, x, y, length, char="\u2502"):
		for offset in range(int(length)):
			self.draw_char(x, y + offset, char)

	def box(self, x, y, width, height):
		"""Rectangle outline; `width`/`height` count the border cells."""
		width, height = int(width), int(height)
		if width < 2 or height < 2:
			return
		self.hline(x + 1, y, width - 2)
		self.hline(x + 1, y + height - 1, width - 2)
		self.vline(x, y + 1, height - 2)
		self.vline(x + width - 1, y + 1, height - 2)
		for corner, cx, cy in (("\u250c", x, y), ("\u2510", x + width - 1, y),
							   ("\u2514", x, y + height - 1),
							   ("\u2518", x + width - 1, y + height - 1)):
			self.draw_char(cx, cy, corner)

	def region(self, x, y, width, height):
		"""Snapshot of a rectangle, one string per clipped row."""
		lines = []
		start = max(0, int(x))
		end = min(int(x) + int(width), self.width)
		for row in range(max(0, int(y)), min(int(y) + int(height), self.height)):
			lines.append("".join(self._buffer[row][start:end]) if start < end else "")
		return lines

	def render(self, full=True):
		"""Write one frame and flush: full repaint, or a changed-cell diff."""
		if full or self._previous is None:
			frame = self._full_frame()
		else:
			frame = self._diff_frame()
		self._previous = [row[:] for row in self._buffer]
		self._previous_colors = [row[:] for row in self._colors]
		self.stream.write(frame)
		self.stream.flush()

	def _full_frame(self):
		out = ["\033[H"]
		current = None
		for y in range(self.height):
			for x in range(self.width):
				color = self._colors[y][x]
				if color != current:
					out.append(color if color else SGR_RESET)
					current = color
				out.append(self._buffer[y][x])
			if y < self.height - 1:
				out.append("\n")
		if current is not None:
			out.append(SGR_RESET)
		return "".join(out)

	def _diff_frame(self):
		previous_colors = self._previous_colors or self._previous
		out = []
		for y in range(self.height):
			for x in range(self.width):
				color = self._colors[y][x]
				if (self._buffer[y][x] == self._previous[y][x]
						and color == previous_colors[y][x]):
					continue
				out.append("\033[{};{}H".format(y + 1, x + 1))
				out.append(color if color else SGR_RESET)
				out.append(self._buffer[y][x])
		if out:
			out.append(SGR_RESET)
		return "".join(out)


class TerminalRenderer(Canvas):
	"""The pre-extraction screensaver renderer API, unchanged."""
