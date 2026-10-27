# Canvas widgets: buttons, fields, list, scrollbar
"""
			INTERACTIVE WIDGETS
			====================
Canvas-based widgets for the full-screen theme editor: each owns a rectangle on a
`Canvas`, draws through `Canvas.draw_*`, styles with `palette.prefix()` and exposes
`hit_test(x, y)`, so keys and mouse drive one model. `Button` renders through
`chrome.button()`, `ScrollBar` reads `chrome.scrollbar()` back for its geometry.

The mechanical half (`Widget`, `Panel`, `Clip`, `cells`, `focus_prefix`,
`small_terminal`, `resize_notice`) lives in `tui.widgetkit` and is re-exported
here, so `from tui.widgets import Panel, cells, ...` keeps working. No widget ever
writes to a stream.
"""

from . import caps, chrome, palette
from .text import display_width, pad, strip_ansi
from .widgetkit import (Clip, MIN_HEIGHT, MIN_WIDTH, SMALL_TERMINAL, Panel,
						Widget, cells, focus_prefix, resize_notice,
						small_terminal)

class Button(Widget):
	"""A `chrome.button()` label: Enter/Space/click activates unless disabled."""
	def __init__(self, x, y, label, *, disabled=False, on_activate=None, cap=None):
		self.label, self.disabled = str(label), bool(disabled)
		self.on_activate, self.activated = on_activate, False
		visible = cells(chrome.button(self.label, disabled=self.disabled,
									  cap=cap))[1]
		Widget.__init__(self, x, y, display_width(visible), 1, cap=cap)
	def activate(self):
		"""Fire the button; a disabled button can never be activated."""
		if self.disabled:
			return False
		self.activated = True
		if callable(self.on_activate):
			self.on_activate(self)
		return True
	def key(self, token):
		return self.activate() if token in ("enter", "space") else False
	def click(self, x, y):
		return self.hit_test(x, y) and self.activate()
	def draw(self, canvas, focused=False):
		colour, visible = cells(chrome.button(
			self.label, focused=focused, disabled=self.disabled, cap=self.cap))
		self.paint(canvas, self.x, self.y, visible, colour)

class TextField(Widget):
	"""Inline editor: cursor, validator, Esc restores, Enter commits.

	`validator(value)` returns True or None for an acceptable draft, a message
	string to reject it with that error, or anything falsy for `invalid`."""
	def __init__(self, x, y, value="", *, width=20, validator=None, cap=None):
		Widget.__init__(self, x, y, width, 1, cap=cap)
		self.value = self._original = str(value)
		self.validator, self.error, self.editing = validator, None, False
		self.cursor = len(self.value)
	def begin(self):
		"""Start editing, keeping the current value as the cancel target."""
		self._original, self.editing, self.error = self.value, True, None
		self.cursor = len(self.value)
	def cancel(self):
		"""Esc: restore the value editing began from."""
		self.value, self.editing, self.error = self._original, False, None
		self.cursor = len(self.value)
	def commit(self):
		"""Enter: keep the draft when the validator accepts it."""
		if self.editing and not self._validate():
			return False
		self._original, self.editing = self.value, False
		return True
	def key(self, token):
		if not self.editing:
			if token != "enter":
				return False
			self.begin()
			return True
		if token == "esc":
			self.cancel()
			return True
		if token == "enter":
			return self.commit()
		if token in ("left", "right", "home", "end"):
			self.cursor = {"left": max(0, self.cursor - 1),
						   "right": min(len(self.value), self.cursor + 1),
						   "home": 0, "end": len(self.value)}[token]
			return True
		if token in ("backspace", "delete"):
			self._replace(self.cursor - (token == "backspace"),
						  self.cursor + (token == "delete"))
			return True
		text = " " if token == "space" else token
		if len(text) == 1 and text.isprintable():
			self._replace(self.cursor, self.cursor, text)
			return True
		return False
	def _replace(self, start, end, text=""):
		"""Replace `value[start:end]` with `text`, cursor after it."""
		start = max(0, start)
		self.value = self.value[:start] + text + self.value[end:]
		self.cursor = start + len(text)
	def _validate(self):
		"""Run the validator: True when the draft may be committed."""
		try:
			result = True if self.validator is None else self.validator(self.value)
		except Exception:
			result = False
		valid = result is True or result is None
		self.error = None if valid else (
			result if isinstance(result, str) and result else "invalid")
		return valid
	def click(self, x, y):
		if not self.hit_test(x, y):
			return False
		if not self.editing:
			self.begin()
		self.cursor = min(len(self.value), max(0, int(x) - self.x))
		return True
	def draw(self, canvas, focused=False):
		cap = self.cap or caps.detect()
		ink = "error" if self.error else "fg"
		base = palette.prefix(fg=ink, cap=cap) or None
		mark = min(self.cursor, self.width - 1) if self.editing else None
		for offset, char in enumerate(pad(self.value, self.width)[:self.width]):
			canvas.draw_char(self.x + offset, self.y, char,
							 focus_prefix(focused and offset == mark, cap,
										  fg=ink) or base)

class SelectField(Widget):
	"""`< option >` cycler: left/right/Enter move through the options."""
	def __init__(self, x, y, options, *, index=0, width=None, cap=None):
		self.options = [str(option) for option in options] or [""]
		Widget.__init__(self, x, y, width or 4 + max(
			display_width(option) for option in self.options), 1, cap=cap)
		self.index = int(index) % len(self.options)
	def selected(self):
		"""The option currently shown."""
		return self.options[self.index]
	def cycle(self, step=1):
		"""Move through the options by `step`, wrapping."""
		self.index = (self.index + int(step)) % len(self.options)
		return self.selected()
	def key(self, token):
		if token in ("right", "enter", "space"):
			self.cycle()
		elif token == "left":
			self.cycle(-1)
		else:
			return False
		return True
	def click(self, x, y):
		return self.hit_test(x, y) and bool(self.cycle())
	def draw(self, canvas, focused=False):
		self.paint(canvas, self.x, self.y, pad("< {} >".format(self.selected()),
											   self.width), self.styled(focused))

class CheckField(Widget):
	"""A boolean row (`[x] label`) for properties such as `table_zebra`."""
	def __init__(self, x, y, label="", value=False, *, width=None, cap=None):
		self.label, self.value = str(label), bool(value)
		Widget.__init__(self, x, y, width or 4 + display_width(self.label), 1,
						cap=cap)
	def toggle(self):
		"""Flip the value and return it."""
		self.value = not self.value
		return self.value
	def key(self, token):
		return self.toggle() if token in ("enter", "space") else False
	def click(self, x, y):
		if not self.hit_test(x, y):
			return False
		self.toggle()
		return True
	def draw(self, canvas, focused=False):
		self.paint(canvas, self.x, self.y, pad("[{}] {}".format(
			"x" if self.value else " ", self.label), self.width),
			self.styled(focused))

class ListBox(Widget):
	"""Scrollable rows: arrows, Home/End, PageUp/PageDown, click, wheel."""
	def __init__(self, x, y, items, *, width=20, height=5, selected=0, cap=None,
				 on_activate=None):
		Widget.__init__(self, x, y, width, height, cap=cap)
		self.items = [str(item) for item in items]
		self.selected = max(0, min(len(self.items) - 1, int(selected)))
		self.offset = 0
		self.on_activate = on_activate
		self.ensure_visible()
	def ensure_visible(self):
		"""Keep the selection inside the visible window."""
		if not self.items:
			self.selected = self.offset = 0
			return
		self.offset = max(0, min(self.offset, len(self.items) - self.height))
		if self.selected < self.offset:
			self.offset = self.selected
		elif self.selected >= self.offset + self.height:
			self.offset = self.selected - self.height + 1
	def move(self, delta):
		"""Move the selection by `delta` rows and scroll it into view."""
		if self.items:
			self.selected = max(0, min(len(self.items) - 1,
									   self.selected + int(delta)))
			self.ensure_visible()
		return self.selected
	def visible(self):
		"""The rows currently on screen."""
		return self.items[self.offset:self.offset + self.height]
	def key(self, token):
		steps = {"up": -1, "down": 1, "pageup": -self.height,
				 "pagedown": self.height, "home": -len(self.items),
				 "end": len(self.items)}
		if token not in steps:
			return False
		self.move(steps[token])
		return True
	def click(self, x, y):
		if not self.hit_test(x, y):
			return False
		index = self.offset + int(y) - self.y
		if 0 <= index < len(self.items):
			self.selected = index
			self.ensure_visible()
		return True
	def double_click(self, x, y):
		"""Second click on a row: select it, then fire the host's Enter hook."""
		if not self.click(x, y):
			return False
		if callable(self.on_activate):
			self.on_activate(self)
		return True
	def draw(self, canvas, focused=False):
		for row, item in enumerate(self.visible()):
			colour = self.styled(focused and self.offset + row == self.selected)
			self.paint(canvas, self.x, self.y + row, pad(item, self.width), colour)

class ScrollBar(Widget):
	"""One column whose thumb and track come from `chrome.scrollbar()`.

	`geometry()` reads the rendered column back instead of duplicating the
	chrome thumb arithmetic, so bar and hit-testing cannot drift."""
	def __init__(self, x, y, height, *, total=None, offset=0, cap=None):
		Widget.__init__(self, x, y, 1, height, cap=cap)
		self.total, self.offset = total, max(0, int(offset))
		self.dragging, self._grab = False, 0
	def bar(self):
		"""The column as chrome builds it, one styled cell per row."""
		return chrome.scrollbar(self.height, offset=self.offset,
								total=self.total, cap=self.cap or caps.detect())
	def span(self):
		"""Rows of content hidden below the visible height."""
		total = self.height if self.total is None else max(0, int(self.total))
		return max(0, total - self.height)
	def geometry(self):
		"""(start, length) of the thumb, read from the rendered column."""
		plain = [strip_ansi(cell) for cell in self.bar()]
		if len(set(plain)) < 2:
			return (0, len(plain))
		track = max(set(plain), key=plain.count)
		rows = [row for row, glyph in enumerate(plain) if glyph != track]
		return (rows[0], len(rows)) if rows else (0, len(plain))
	def offset_for(self, start):
		"""Offset that puts the thumb's top at `start` (clamped)."""
		room, span = max(0, self.height - self.geometry()[1]), self.span()
		shown = min(room, max(0, int(start)))
		return min(span, max(0, round(shown * span / room))) if room and span else 0
	def press(self, x, y):
		"""Click: grab the thumb (`"thumb"`), jump the offset (`"jump"`), or None."""
		if not self.hit_test(x, y):
			return None
		row = max(0, min(self.height - 1, int(y) - self.y))
		start, length = self.geometry()
		if start <= row < start + length:
			self.dragging, self._grab = True, row - start
			return "thumb"
		self.offset = self.offset_for(row)
		return "jump"
	def drag(self, x, y):
		"""Move a held thumb to the pointer and return the new offset."""
		if self.dragging:
			self.offset = self.offset_for(int(y) - self.y - self._grab)
		return self.offset
	def release(self):
		"""Drop the thumb grab; safe when nothing is being dragged."""
		self.dragging = False
		return self
	def wheel(self, steps):
		"""Scroll by wheel notches, clamped to the scrollable span."""
		self.offset = min(self.span(), max(0, self.offset + int(steps)))
		return self.offset
	def click(self, x, y):
		return self.press(x, y) is not None
	def draw(self, canvas, focused=False):
		highlight = focus_prefix(focused, self.cap or caps.detect())
		for row, cell in enumerate(self.bar()):
			colour, char = cells(cell)
			canvas.draw_char(self.x, self.y + row, char, highlight or colour)

