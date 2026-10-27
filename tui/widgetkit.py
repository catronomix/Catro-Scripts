# Canvas widget kit: rectangle base, clipping panel, focus styling
"""
			WIDGET KIT
			===========
The mechanical half of `tui.widgets`: the `Widget` rectangle/hit-test base, the
`Panel`/`Clip` clipping rectangle, `cells()` (lead-colour / visible-text split
of one styled string), the focus prefix and the small-terminal fallback. Split
out of `widgets.py` for budget headroom and re-exported by `tui.widgets`, so
`from tui.widgets import Panel, cells, ...` keeps working.

Nothing here prints or writes to a stream: every helper returns a string, a
prefix or a rectangle; ANSI stripping goes through `tui.text.strip_ansi` alone.
"""

import re

from . import caps, palette
from .text import strip_ansi

MIN_WIDTH, MIN_HEIGHT = 90, 24  # three live previews plus the panels beside them
SMALL_TERMINAL = "too small"
_LEAD = re.compile("^((?:\033\\[[0-9;]*m)+)")


def cells(text):
	"""(colour, visible text) split of one styled string, for a canvas cell."""
	text = str(text)
	match = _LEAD.match(text)
	lead = match.group(1) if match else ""
	return (lead or None, strip_ansi(text[len(lead):]))


def focus_prefix(focused, cap=None, *, fg="fg", bg="bg"):
	"""A self-contained focus-visible cell colour, or None when not focused.

	The theme's `focus_style` picks the attribute (`reverse` by default,
	`accent` fg, or `underline`), but `fg`/`bg` are re-asserted first: a canvas
	cell carries no state of its own, so a prefix that only had the attribute
	would inherit whatever ground the previously drawn cell left behind. Two
	adjacent focused rows therefore cannot bleed into each other.
	"""
	if not focused:
		return None
	cap = cap or caps.detect()
	if cap.level == "none":
		return None
	style = palette.properties().get("focus_style")
	if style == "accent":
		return palette.prefix(fg="fg-accent", bg=bg, cap=cap) or None
	if style == "underline":
		return palette.prefix(fg=fg, bg=bg, underline=True, cap=cap) or None
	return palette.prefix(fg=fg, bg=bg, reverse=True, cap=cap) or None


def small_terminal(width, height):
	"""True when the terminal is below the editor's comfortable minimum."""
	try:
		return int(width) < MIN_WIDTH or int(height) < MIN_HEIGHT
	except (TypeError, ValueError):
		return True


def resize_notice(width, height, *, cap=None):
	"""The `too small` fallback line for an undersized terminal, else None."""
	if small_terminal(width, height):
		return palette.style("{} - resize to at least {}x{}".format(
			SMALL_TERMINAL, MIN_WIDTH, MIN_HEIGHT), fg="fg-warn",
			cap=cap or caps.detect())
	return None

class Widget:
	"""Common rectangle, hit test, clipping painter and focus styling."""
	def __init__(self, x, y, width, height=1, *, cap=None):
		self.x, self.y, self.cap = int(x), int(y), cap
		self.width, self.height = max(1, int(width)), max(1, int(height))
	def hit_test(self, x, y):
		"""A mouse point either belongs to this rectangle or it does not."""
		return (self.x <= int(x) < self.x + self.width
				and self.y <= int(y) < self.y + self.height)
	def paint(self, canvas, x, y, text, colour=None):
		canvas.draw_text(x, y, str(text)[:max(0, self.x + self.width - x)], colour)
	def styled(self, focused, fg="fg"):
		"""The prefix for this widget's own row, focused or not."""
		cap = self.cap or caps.detect()
		return (focus_prefix(focused, cap, fg=fg)
				or palette.prefix(fg=fg, cap=cap) or None)
	def draw(self, canvas, focused=False):
		raise NotImplementedError
	def key(self, token):
		"""Handle one key token; True when the widget consumed it."""
		return False
	def click(self, x, y):
		"""Mouse press at a point; True when it landed on the widget."""
		return self.hit_test(x, y)
	def double_click(self, x, y):
		"""Second click at the same point: the default is another click."""
		return self.click(x, y)

class Panel(Widget):
	"""A clipping rectangle: a child can never draw outside the panel's rows."""
	def __init__(self, x, y, width, height, *, cap=None):
		Widget.__init__(self, x, y, width, height, cap=cap)
		self.children = []
	def draw(self, canvas, focused=False):
		target = Clip(canvas, self.x, self.y, self.width, self.height)
		for child in self.children:
			child.draw(target, focused=focused and child is self.children[0])

class Clip:
	"""The `draw_char`/`draw_text` subset of `Canvas`, restricted to a rect."""
	def __init__(self, canvas, x, y, width, height):
		self.canvas, self.x, self.y = canvas, int(x), int(y)
		self.width, self.height = int(width), int(height)
	def draw_char(self, x, y, char, color=None):
		if (self.x <= int(x) < self.x + self.width
				and self.y <= int(y) < self.y + self.height):
			self.canvas.draw_char(x, y, char, color)
	def draw_text(self, x, y, text, color=None):
		for offset, char in enumerate(str(text)):
			self.draw_char(x + offset, y, char, color)
