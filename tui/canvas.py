# Canvas: the double-buffered cell grid and its frame emitter
"""
			CANVAS AND EMISSION
			====================
`Canvas` is the double-buffered cell grid and the only place that turns cells
into terminal bytes: `draw_*`/`hline`/`vline`/`box` mutate the buffer and
`render()` emits a full repaint or a changed-cell diff (one CUP per contiguous
run, one SGR per SGR-state change). `TerminalRenderer` is the pre-extraction
screensaver name, kept as a subclass so `.screensaver` files keep working.

Self-contained by design - no `Screen`, no alternate screen, no cursor or input,
grid in/frame out - which makes it the landing zone for the stale-tint repaint
fix: a repaint may only consult `_buffer`, `_colors` and `_previous*`.
`terminal_size` lives here because a canvas must know its size; `tui.screen`
re-exports it.
"""

import os
import shutil
import sys

SGR_RESET = "\033[0m"

# No cell colour ever equals this: the first changed cell always emits.
_SGR_UNKNOWN = object()


def _sgr_state(color):
	"""(fg, bg, attrs) the SGR state `color` leaves active on the terminal."""
	fg = bg = None
	attrs = set()
	for chunk in str(color or "").split("\033[")[1:]:
		params = chunk.split("m")[0].split(";")
		code = int(params[0] or 0)
		if code in (38, 48):
			fg, bg = ((";".join(params), bg) if code == 38
					  else (fg, ";".join(params)))
		elif 30 <= code <= 37 or 90 <= code <= 97:
			fg = code
		elif 40 <= code <= 47 or 100 <= code <= 107:
			bg = code
		else:
			attrs.add(code)
	return fg, bg, frozenset(attrs)


def _emit_sgr(out, active, color):
	"""Append `color`'s codes; reset first when a run would inherit state."""
	state = _sgr_state(color)
	if state != active:
		if active is not _SGR_UNKNOWN and color and not (
				active[2] <= state[2]
				and (state[0] is not None or active[0] is None)
				and (state[1] is not None or active[1] is None)):
			out.append(SGR_RESET)
		out.append(color if color else SGR_RESET)
	return state


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
		out, active = ["\033[H"], _SGR_UNKNOWN
		for y in range(self.height):
			for x in range(self.width):
				active = _emit_sgr(out, active, self._colors[y][x])
				out.append(self._buffer[y][x])
			if y < self.height - 1:
				out.append("\n")
		if active is not _SGR_UNKNOWN and any(active):
			out.append(SGR_RESET)
		return "".join(out)

	def _diff_frame(self):
		"""Changed-cell diff: one CUP per contiguous run, SGR only on a change.

		`active` is the SGR state the terminal really holds, so the reset a
		sticky attribute needs is paid only by the run that would inherit it.
		"""
		previous_colors = self._previous_colors or self._previous
		out = []
		active = _SGR_UNKNOWN
		for y in range(self.height):
			row = self._buffer[y]
			was = self._previous[y]
			colors = self._colors[y]
			old = previous_colors[y]
			x = 0
			while x < self.width:
				if row[x] == was[x] and colors[x] == old[x]:
					x += 1
					continue
				start = x
				while x < self.width and not (row[x] == was[x]
											  and colors[x] == old[x]):
					x += 1
				out.append("\033[{};{}H".format(y + 1, start + 1))
				for cell in range(start, x):
					active = _emit_sgr(out, active, colors[cell])
					out.append(row[cell])
		if out:
			out.append(SGR_RESET)
		return "".join(out)


class TerminalRenderer(Canvas):
	"""The pre-extraction screensaver renderer API, unchanged."""
