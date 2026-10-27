# Colour picker: the 16x3 HSV swatch popup over an injected Canvas
"""
			COLOUR PICKER
			==============
The modal popup: one HSV triple is the model and a 16x3 grid of two-cell
swatches is its view. Row 1 walks the hue at full saturation and value (a
vivid ramp whatever the current colour), row 2 the saturation at the current
hue and full value, row 3 the value at the current hue and saturation, so the
same grid reaches every component without text fields and no ramp collapses to
black on a dark colour. `run()` returns `#rrggbb` (None on cancel) and a
colour under WCAG AA against the look's background still warns.

The conversions and the WCAG gate live in `tui.color_math`; they are
re-exported here so `tui.colorpicker.hex_to_rgb()` and friends keep resolving.
"""

from . import (caps, colorpicker_mouse, colorpicker_panel, editor_overlays,
			   mouse, mouse_clicks, palette, widgets)
from .color_math import (STEPS, WCAG_AA, cell_index, contrast_ratio,  # noqa: F401
						 hex_to_rgb, hsv_to_rgb, luminance, rgb_to_hex,
						 rgb_to_hsv)
from .colorpicker_panel import PANEL  # noqa: F401  (tests read it here)
from .text import truncate

LIMITS = (360, 100, 100)
CELL = 2  # two cells per swatch: a 32-cell grid
WIDTH, HEIGHT = 44, 9  # bordered popup: poles, 3 grid rows, 4 info rows
SWATCH = "\u2588"  # full block; ASCII falls back to `#`
ROWS = ("hue", "saturation", "value")


class ColorPicker:
	"""A modal 16x3 HSV grid over an injected `Canvas`; `run()` returns the hex."""
	def __init__(self, canvas, value="#ffffff", *, keys=(), x=1, y=1,
				 width=WIDTH, cap=None, colours=None):
		self.canvas, self.cap, self.x, self.y = canvas, cap, int(x), int(y)
		self.width = max(CELL * STEPS + 2, int(width))
		self.height = HEIGHT
		self.colours = dict(colours or palette.palette())
		self.original = self.value = rgb_to_hex(hex_to_rgb(value))
		self.hue, self.saturation, self.brightness = rgb_to_hsv(
			hex_to_rgb(self.original))
		self.row, self.col = 0, cell_index(self.hue / 360)
		self._original_cell = (self.row, self.col)
		self.result, self.closed, self._queue, self._grab = None, False, list(keys), None
		self.clicks = mouse_clicks.ClickTracker()
		# One pad cell, the 32-cell grid, then the panel on the right; at the
		# minimum width the grid clamps to the left border so it cannot spill.
		self.grid_x = self.x + min(2, max(1, (self.width - CELL * STEPS) // 2))
		self.grid_y = self.y + 1

	# -- model -----------------------------------------------------------

	def value_at(self, row, col):
		"""The `#rrggbb` swatch at one grid cell.

		Only row 3 (value) is tinted with the complete current colour. Rows 1
		and 2 are *pickers*, not previews: hue runs at full saturation/value and
		saturation runs at the current hue but full value, so a dark current
		colour cannot collapse either ramp into a near-black strip.
		"""
		fraction = max(0, min(STEPS - 1, int(col))) / (STEPS - 1)
		if row == 0:
			hsv = (fraction * 360, 1.0, 1.0)
		elif row == 1:
			hsv = (self.hue, fraction, 1.0)
		else:
			hsv = (self.hue, self.saturation, fraction)
		return rgb_to_hex(hsv_to_rgb(hsv))

	def _refresh(self):
		"""Re-derive the hex from the HSV model."""
		self.value = rgb_to_hex(hsv_to_rgb(
			(self.hue, self.saturation, self.brightness)))

	def _snap(self):
		"""Put the marker on the current component's own cell."""
		component = (self.hue / 360, self.saturation, self.brightness)[self.row]
		self.col = cell_index(component)

	def select(self, row, col):
		"""Move the marker to a cell and apply that cell's component."""
		self.row = max(0, min(2, int(row)))
		self.col = max(0, min(STEPS - 1, int(col)))
		fraction = self.col / (STEPS - 1)
		if self.row == 0:
			self.hue = fraction * 360
		elif self.row == 1:
			self.saturation = fraction
		else:
			self.brightness = fraction
		self._refresh()
		return self.value

	# -- input -----------------------------------------------------------

	def key(self, token):
		"""Route one key token or `mouse:` event; True when consumed."""
		event = mouse.parse_token(token)
		if event is not None:
			return colorpicker_mouse.mouse(self, *event)
		if self.closed:
			return False
		if token == "esc":
			return self.close()
		if token in ("enter", "space"):
			return self.commit()
		if token in ("left", "right"):
			step = 1 if token == "right" else -1
			self.select(self.row, (self.col + step) % STEPS)
			return True
		if token in ("up", "down", "tab", "backtab", "shift-tab"):
			step = 1 if token in ("down", "tab") else -1
			self.row = (self.row + step) % len(ROWS)
			self._snap()
			return True
		if token in ("home", "end"):
			self.select(self.row, 0 if token == "home" else STEPS - 1)
			return True
		return False

	def cell_at(self, x, y):
		"""(row, col) under a point, or None when it is not on the grid."""
		if not (self.grid_y <= int(y) < self.grid_y + len(ROWS)):
			return None
		offset = int(x) - self.grid_x
		if not (0 <= offset < CELL * STEPS):
			return None
		return (int(y) - self.grid_y, offset // CELL)

	def _mouse(self, kind, x, y, modifiers=()):
		"""Delegate the mouse model to `tui.colorpicker_mouse`."""
		return colorpicker_mouse.mouse(self, kind, x, y, modifiers)

	# -- result ----------------------------------------------------------

	def commit(self, *_):
		"""Enter/space: keep the current grid colour."""
		return self.close(self.value)

	def close(self, result=None):
		"""Close the popup; `None` restores the colour it opened with."""
		result = result if isinstance(result, str) else None
		if result is None:
			self.value = self.original
			self.hue, self.saturation, self.brightness = rgb_to_hsv(
				hex_to_rgb(self.original))
			self.row, self.col = self._original_cell
		self.result, self.closed, self._grab = result, True, None
		return True

	def run(self, keys=None):
		"""Feed the injected queue until the popup closes; the result."""
		for token in (self._queue if keys is None else keys):
			if self.closed:
				break
			self.key(token)
		return self.result

	def rect(self):
		"""The popup's (x, y, width, height) on the canvas."""
		return self.x, self.y, self.width, self.height

	# -- drawing ---------------------------------------------------------

	def draw(self):
		"""Paint the bordered grid through `palette.prefix()`; returns `self`."""
		canvas, cap = self.canvas, self.cap or caps.detect()
		notice = widgets.resize_notice(canvas.width, canvas.height, cap=cap)
		if notice is not None:
			canvas.draw_text(self.x, self.y, *reversed(widgets.cells(notice)))
			return self
		editor_overlays.surface(canvas, cap, self.x, self.y, self.width,
								self.height, "Colour picker")
		glyph = SWATCH if cap.unicode else "#"
		for row in range(len(ROWS)):
			for col in range(STEPS):
				selected = (row, col) == (self.row, self.col)
				if cap.unicode:
					text = glyph * CELL
					colour = palette.prefix(fg=self.value_at(row, col),
											reverse=selected, cap=cap)
				else:
					text = "><" if selected else glyph * CELL
					colour = palette.prefix(fg=self.value_at(row, col),
											bold=selected, cap=cap)
				canvas.draw_text(self.grid_x + col * CELL,
								 self.grid_y + row, text, colour)
		self._draw_panel(glyph, cap)
		inner = max(1, self.width - 2)
		ratios = {palette.role(name): contrast_ratio(
					  self.value, self.colours[palette.role(name)])
				  for name in ("bg", "bg-stripe")
				  if palette.role(name) in self.colours}
		low = bool(ratios) and min(ratios.values()) < WCAG_AA
		if low:
			facts = "{}  below AA 4.5:1".format(self.value)
		else:
			facts = "  ".join("{} {:.1f}:1".format(*pair)
							  for pair in ratios.items())
			facts = self.value + ("  " + facts if facts else "")
		# One blank row between the facts and the HSV triple. The facts stop
		# short of the panel only when the panel is actually painted.
		panel = self._panel_x()
		limit = inner - 2 if panel is None else panel - self.x - 3
		rows = ((truncate(facts, max(1, limit)),
				 "fg-warn" if low else "fg"),
				(None, None),
				("h {:3.0f}  s {:3.0f}%  v {:3.0f}%".format(
					self.hue, self.saturation * 100, self.brightness * 100),
				 "fg-muted"),
				("arrows  Enter apply  Esc cancel", "fg-muted"))
		for offset, (text, role) in enumerate(rows, start=len(ROWS)):
			if text is None:
				continue
			canvas.draw_text(self.x + 2, self.grid_y + offset,
							 truncate(text, max(1, inner - 2)),
							 palette.prefix(fg=role, bg="bg-inside", cap=cap))
		return self

	def _panel_x(self):
		"""Left edge of the preview panel, or None when the grid leaves no room."""
		return colorpicker_panel.panel_x(self.x, self.width,
										 self.grid_x + CELL * STEPS)

	def _draw_panel(self, glyph, cap):
		"""The selected colour as a solid block beside the grid, hex beneath."""
		colorpicker_panel.draw(self.canvas, self.x, self.width,
							   self.grid_x + CELL * STEPS, self.grid_y,
							   len(ROWS), self.value, glyph, cap)
