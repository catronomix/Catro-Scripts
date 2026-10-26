# Colour picker: hex <-> RGB/HSV conversion and a Canvas popup
"""
			COLOUR PICKER
			==============
Pure conversions plus the modal popup: one HSV triple is the model and the
boxes plus sliders are its views, so edits stay in sync and invalid text
never commits; `run()` returns `#rrggbb` (None on cancel); sub-AA warns.
"""

import colorsys

from . import caps, mouse, palette, widgets

WCAG_AA, LIMITS = 4.5, (360, 100, 100)


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


class _Slider(widgets.Widget):
	"""One HSV track: click maps a column to a value, keys step it."""
	def __init__(self, x, y, width, maximum, *, cap=None):
		widgets.Widget.__init__(self, x, y, width, 1, cap=cap); self.maximum, self.value = int(maximum), 0

	def keep(self, value):
		self.value = max(0, min(self.maximum, int(round(float(value))))); return self.value

	def key(self, token):
		steps = {"left": -1, "down": -1, "right": 1, "up": 1, "home": -self.maximum,
				 "end": self.maximum, "pagedown": -10, "pageup": 10}
		if token not in steps: return False
		self.keep(self.value + steps[token])
		return True

	def draw(self, canvas, focused=False):
		cap = self.cap or caps.detect()
		mark = min(self.width - 1, round(self.value * (self.width - 1) / self.maximum))
		thumb, track = ("\u2588", "\u2500") if cap.unicode else ("#", "-")
		canvas.draw_text(self.x, self.y, track * self.width, palette.prefix(fg="muted", cap=cap))
		canvas.draw_char(self.x + mark, self.y, thumb, self.styled(focused, "accent"))


class ColorPicker:
	"""A modal colour picker over an injected `Canvas`; `run()` returns the hex."""
	def __init__(self, canvas, value="#ffffff", *, keys=(), x=1, y=1, width=44,
				 cap=None, colours=None):
		self.canvas, self.cap, self.x, self.y = canvas, cap, int(x), int(y)
		self.width, self.colours = max(24, int(width)), dict(colours or palette.palette())
		self.original = self.value = rgb_to_hex(hex_to_rgb(value))
		self.result, self.closed, self._queue, self._grab = None, False, list(keys), None
		self.hex_field, self.hsv_field = self._boxes = [
			widgets.TextField(self.x + 5, self.y + row, text, width=12,
							  validator=check, cap=cap)
			for check, row, text in ((self._valid_hex, 1, self.original),
									 (self._valid_hsv, 6, ""))]
		self.sliders = [_Slider(self.x + 3, self.y + 3 + row, self.width - 4, high,
								cap=cap) for row, high in enumerate(LIMITS)]
		self.ok, self.cancel = buttons = [widgets.Button(
			self.x + offset, self.y + 9, label, cap=cap, on_activate=hook)
			for offset, label, hook in ((3, "OK", self.commit), (10, "Cancel", self.close))]
		self.ring = widgets.FocusRing([self.hex_field, *self.sliders, self.hsv_field, *buttons])
		self._set(rgb_to_hsv(hex_to_rgb(self.original)), self.original)

	def _hsv_parts(self, text):
		parts = str(text).replace(" ", "").split(",")
		if len(parts) == 3 and all(p.isdigit() and int(p) <= h for p, h in zip(parts, LIMITS)):
			return tuple(int(part) for part in parts)

	def _valid_hex(self, text):
		try: return bool(hex_to_rgb(text))
		except ValueError: return "need #rrggbb"

	def _valid_hsv(self, text):
		return True if self._hsv_parts(text) else "need h,s,v"

	def _set(self, hsv, value=None):
		hue, sat, val = hsv[0] % 360, *map(lambda p: min(1.0, max(0.0, float(p))), hsv[1:])
		self.value = value or rgb_to_hex(hsv_to_rgb((hue, sat, val)))
		scaled = (hue, sat * 100, val * 100)
		for slider, number in zip(self.sliders, scaled): slider.keep(number)
		for box, text in zip(self._boxes, (self.value, "{},{},{}".format(*map(round, scaled)))):
			box.value = text if not box.editing else box.value

	def _adopt(self, field):
		if field is self.hex_field:
			return self._set(rgb_to_hsv(c := hex_to_rgb(field.value)), rgb_to_hex(c))
		return self._set(tuple(p / s for p, s in zip(self._hsv_parts(field.value), (1, 100, 100))))

	def key(self, token):
		"""Route one key token or `mouse:` event; True when consumed."""
		event = mouse.parse_token(token)
		if event is not None: return self._mouse(*event)
		if self.closed: return False
		if token == "esc": return self.close()
		focused = self.ring.current()
		typing = bool(getattr(focused, "editing", False))
		if typing and token in ("tab", "shift-tab", "backtab"):
			return True if not self._finish(focused) else self.ring.key(token)
		handled = self.ring.key(token)
		if typing and not focused.editing and not focused.error: self._adopt(focused)
		elif handled and focused in self.sliders:
			self._set((self.sliders[0].value, *[s.value / 100 for s in self.sliders[1:]]))
		if token == "enter" and not (handled or any(f.error for f in self._boxes)): return self.commit()
		return handled

	def _finish(self, field):
		if field.commit(): self._adopt(field)
		return not field.editing

	def _track(self, track, x):
		track.keep((int(x) - track.x) * track.maximum / max(1, track.width - 1))
		return self._set((self.sliders[0].value, *[s.value / 100 for s in self.sliders[1:]])) or True

	def _mouse(self, kind, x, y, modifiers=()):
		if kind == "press":
			focused = self.ring.current()
			if (getattr(focused, "editing", False) and not focused.hit_test(x, y)
					and not self.cancel.hit_test(x, y) and not self._finish(focused)): return True
			self._grab = next((s for s in self.sliders if s.hit_test(x, y)), None)
			if self._grab is None: return self.ring.click(x, y)
			self.ring.focus(self.ring.widgets.index(self._grab)); return self._track(self._grab, x)
		if kind == "drag" and self._grab is not None:
			return self._track(self._grab, x)
		if kind == "release": self._grab = None
		return False

	def commit(self, *_):
		"""OK/Enter: keep the draft unless a box is mid-edit or invalid."""
		return not any(f.error or f.editing for f in self._boxes) and self.close(self.value)

	def close(self, result=None):
		"""Close the popup; `None` restores the colour it opened with."""
		result = result if isinstance(result, str) else None
		for field in self._boxes: field.editing, field.error = False, None
		if result is None: self._set(rgb_to_hsv(hex_to_rgb(self.original)), self.original)
		self.result, self.closed, self._grab = result, True, None; return True

	def run(self, keys=None):
		"""Feed the injected queue until the popup closes; the result."""
		for token in (self._queue if keys is None else keys):
			if self.closed: break
			self.key(token)
		return self.result

	def draw(self):
		"""Paint the popup through `palette.prefix()`; returns `self`."""
		canvas, cap = self.canvas, self.cap or caps.detect()
		notice = widgets.resize_notice(canvas.width, canvas.height, cap=cap)
		if notice is not None:
			canvas.draw_text(self.x, self.y, *reversed(widgets.cells(notice))); return self
		ratios = {r: contrast_ratio(self.value, self.colours[r])
				  for r in ("bg", "zebra_bg") if r in self.colours}
		low = bool(ratios) and min(ratios.values()) < WCAG_AA
		facts = "  ".join("{} {:.1f}:1".format(*pair) for pair in ratios.items())
		error = next((field.error for field in self._boxes if field.error), "")
		rows = (("Colour picker", "header"), ("hex", "muted"), (error, "error"),
				("h", "muted"), ("s", "muted"), ("v", "muted"), ("h,s,v", "muted"),
				(facts, "warn" if low else "fg"), ("below AA 4.5:1" if low else "", "warn"))
		for row, (text, role) in enumerate(rows):
			if text: canvas.draw_text(self.x + 1, self.y + row, text,
									  palette.prefix(fg=role, bg="surface", cap=cap))
		self.ring.draw(canvas)
		return self
