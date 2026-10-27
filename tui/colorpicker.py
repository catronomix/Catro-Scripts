# Colour picker: hex <-> RGB/HSV conversion and the 16x3 swatch popup
"""
			COLOUR PICKER
			==============
Pure conversions plus the modal popup: one HSV triple is the model and a
16x3 grid of two-cell swatches is its view. Row 1 walks the hue at the current
saturation and value, row 2 the saturation at the current hue and value, row 3
the value at the current hue and saturation, so the same grid reaches every
component without text fields. `run()` returns `#rrggbb` (None on cancel) and
a colour under WCAG AA against the look's background still warns.
"""

import colorsys

from . import caps, editorviews, mouse, palette, widgets
from .text import truncate

WCAG_AA, LIMITS = 4.5, (360, 100, 100)
STEPS, CELL = 16, 2  # 16 swatches of two cells each: a 32-cell grid
WIDTH, HEIGHT = 36, 8  # bordered popup: poles, 3 grid rows, 3 info rows
SWATCH = "\u2588"  # full block; ASCII falls back to `#`
ROWS = ("hue", "saturation", "value")


def hex_to_rgb(value):
	"""(r, g, b) for `#rrggbb` or `rrggbb`; `ValueError` for anything else."""
	text = str(value).strip().removeprefix("#")
	if len(text) != 6 or any(char not in "0123456789abcdefABCDEF" for char in text):
		raise ValueError("not a #rrggbb colour: {!r}".format(value))
	return tuple(int(text[at:at + 2], 16) for at in (0, 2, 4))


def rgb_to_hex(rgb):
	"""Canonical lowercase `#rrggbb` for an (r, g, b) triple."""
	return "#{:02x}{:02x}{:02x}".format(*(int(part) for part in rgb))


def rgb_to_hsv(rgb):
	"""(hue 0-360, saturation 0-1, value 0-1) for an (r, g, b) triple."""
	hue, saturation, value = colorsys.rgb_to_hsv(*(part / 255 for part in rgb))
	return (hue * 360, saturation, value)


def hsv_to_rgb(hsv):
	"""(r, g, b) for an (hue, saturation, value) triple; the hue wraps."""
	hue, saturation, value = (float(part) for part in hsv)
	red, green, blue = colorsys.hsv_to_rgb(hue % 360 / 360, min(1.0, max(0.0, saturation)),
										   min(1.0, max(0.0, value)))
	return tuple(round(part * 255) for part in (red, green, blue))


def luminance(value):
	"""WCAG 2.x relative luminance (0-1) for a `#rrggbb` colour."""
	channels = [part / 255 for part in hex_to_rgb(value)]
	return sum(w * (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
			   for w, c in zip((0.2126, 0.7152, 0.0722), channels))


def contrast_ratio(first, second):
	"""WCAG 2.x ratio (1.0-21.0) between two `#rrggbb` colours."""
	high, low = sorted((luminance(first), luminance(second)), reverse=True)
	return (high + 0.05) / (low + 0.05)


def cell_index(fraction):
	"""Grid column for a 0-1 component; 0.5 reads as the midpoint, column 8."""
	return max(0, min(STEPS - 1, int(round(float(fraction) * (STEPS - 1)))))


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
		# Centre the 32-cell grid inside the frame; one spare cell each side.
		self.grid_x = self.x + max(0, (self.width - CELL * STEPS) // 2)
		self.grid_y = self.y + 1

	# -- model -----------------------------------------------------------

	def value_at(self, row, col):
		"""The `#rrggbb` swatch at one grid cell."""
		hue, saturation, value = (self.hue, self.saturation, self.brightness)
		fraction = max(0, min(STEPS - 1, int(col))) / (STEPS - 1)
		if row == 0:
			hue = fraction * 360
		elif row == 1:
			saturation = fraction
		else:
			value = fraction
		return rgb_to_hex(hsv_to_rgb((hue, saturation, value)))

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
			return self._mouse(*event)
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
		if kind == "press":
			cell = self.cell_at(x, y)
			if cell is None:
				return False
			self._grab = cell
			self.select(*cell)
			return True
		if kind == "drag" and self._grab is not None:
			if self.grid_y <= int(y) < self.grid_y + len(ROWS):
				cell = self.cell_at(x, y)
				if cell is not None:
					self._grab = cell
					self.select(*cell)
					return True
			# Dragging past the edge clamps to the grabbed row's last cell.
			offset = min(CELL * STEPS - 1, max(0, int(x) - self.grid_x))
			self._grab = (self.row, offset // CELL)
			self.select(self.row, offset // CELL)
			return True
		if kind == "release":
			self._grab = None
			return True
		return False

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
		editorviews.fill_rect(canvas, self.x, self.y, self.width, self.height,
							  cap=cap)
		editorviews.frame(canvas, self.x, self.y, self.width, self.height,
						  "Colour picker", cap)
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
		inner = max(1, self.width - 2)
		ratios = {name: contrast_ratio(self.value, self.colours[name])
				  for name in ("bg", "zebra_bg") if name in self.colours}
		low = bool(ratios) and min(ratios.values()) < WCAG_AA
		if low:
			facts = "{}  below AA 4.5:1".format(self.value)
		else:
			facts = "  ".join("{} {:.1f}:1".format(*pair)
							  for pair in ratios.items())
			facts = self.value + ("  " + facts if facts else "")
		rows = ((facts, "warn" if low else "fg"),
				("h {:3.0f}  s {:3.0f}%  v {:3.0f}%".format(
					self.hue, self.saturation * 100, self.brightness * 100),
				 "muted"),
				("arrows move  Enter apply  Esc", "muted"))
		for offset, (text, role) in enumerate(rows):
			canvas.draw_text(self.x + 2, self.grid_y + len(ROWS) + offset,
							 truncate(text, max(1, inner - 2)),
							 palette.prefix(fg=role, bg="surface", cap=cap))
		return self
