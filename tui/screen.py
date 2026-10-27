# Full-screen primitives: alternate screen, cursor and the canvas host
"""
			SCREEN
			======
`Screen` owns the alternate-screen/cursor lifecycle: enter/exit, clear, home,
move, cursor visibility, the background fill and resize polling. The
double-buffered cell grid it paints into - `Canvas` and the pre-extraction
`TerminalRenderer` name - lives in `tui.canvas` and is re-exported here, so
`tui.screen.Canvas` keeps resolving for the editor, the pickers and the
screensaver plugins.

`Screen` is inert off a tty: `enter()` writes nothing, and every write goes to
the injected `stream` so behaviour is testable with fake streams.

Test seam: `terminal_size` is defined in `tui.canvas` and re-exported here. A
canvas resolves the size through `tui.canvas.terminal_size`, the host through
this module's name, so patch whichever consumer the test drives.
"""

import sys

from . import caps, palette
from .canvas import Canvas, SGR_RESET, TerminalRenderer, terminal_size  # noqa: F401

ALT_SCREEN_ON = "\033[?1049h"
ALT_SCREEN_OFF = "\033[?1049l"
CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
CLEAR_HOME = "\033[2J\033[H"


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

