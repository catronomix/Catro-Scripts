# House palettes, theme resolution and level downgrade
"""
			COLOR PALETTES AND STYLING
			===========================
Two hand-authored palettes with identical semantic keys - DARK reproduces the
bytes the old per-script `Colors` class emitted at truecolor, LIGHT is its
light-background pair. Neither is derived from the other.

`style()` is the only place that emits SGR codes. Its emission order is pinned:
foreground, background, attributes, text, reset. Dark at level "true" therefore
reproduces `list.py` exactly, and every downgrade (256, 16, none) is
deterministic: the same hex always resolves to the same code.
"""

import os

from . import caps, config

DARK = {
	"bg": "#000000",
	"surface": "#2D2D2D",
	"fg": "#ADD8E6",
	"muted": "#7F8C99",
	"accent": "#AA00FF",
	"success": "#50C878",
	"warn": "#F5CD68",
	"error": "#FF5F5F",
	"border": "#AA00FF",
	"header": "#AA00FF",
	"zebra_bg": "#2D2D2D",
}

LIGHT = {
	"bg": "#FFFFFF",
	"surface": "#F0EDF7",
	"fg": "#1F1B2E",
	"muted": "#5A5370",
	"accent": "#6A3FB5",
	"success": "#1E7A4C",
	"warn": "#9A6200",
	"error": "#B3261E",
	"border": "#6A3FB5",
	"header": "#6A3FB5",
	"zebra_bg": "#F0EDF7",
}

THEMES = {"dark": DARK, "light": LIGHT}

_BASE16 = (
	(0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
	(0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
	(128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
	(0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)
_CUBE = (0, 95, 135, 175, 215, 255)
_XTERM256 = (_BASE16
			 + tuple((r, g, b) for r in _CUBE for g in _CUBE for b in _CUBE)
			 + tuple((8 + 10 * step,) * 3 for step in range(24)))

_NEAREST = {}


def theme(override=None):
	"""Active theme name: override > CATRO_THEME > config.ini > "dark"."""
	return _theme_name(override)


def palette(theme=None, cap=None):
	"""Copy of the named palette (key -> "#rrggbb"). `cap` is accepted unused."""
	return dict(THEMES[_theme_name(theme)])


def style(text, fg=None, bg=None, bold=False, dim=False, reverse=False,
		  cap=None, theme=None):
	"""Wrap `text` in SGR codes for the active theme and capability level.

	`fg`/`bg` accept a semantic key, "#rrggbb" or an (r, g, b) tuple; anything
	unparseable falls back to the palette's own `fg`/`bg` instead of raising.
	Level "none" returns the bare text, with no reset code.
	"""
	cap = cap or caps.detect()
	plain = "" if text is None else str(text)
	if cap.level == "none":
		return plain
	colours = palette(theme)
	parts = []
	if fg is not None:
		parts.append(_sgr(_rgb(fg, colours, "fg"), cap.level, background=False))
	if bg is not None:
		parts.append(_sgr(_rgb(bg, colours, "bg"), cap.level, background=True))
	if bold:
		parts.append("\033[1m")
	if dim:
		parts.append("\033[2m")
	if reverse:
		parts.append("\033[7m")
	if not parts:
		return plain
	return "".join(parts) + plain + "\033[0m"


def _theme_name(mode=None):
	if mode is None or not str(mode).strip():
		mode = os.environ.get("CATRO_THEME") or config.get("theme", "mode", "dark")
	name = str(mode).strip().lower()
	return name if name in THEMES else "dark"


def _rgb(value, colours, default_key):
	"""Resolve a semantic key, hex string or RGB tuple to (r, g, b)."""
	if isinstance(value, (tuple, list)) and len(value) == 3:
		try:
			return tuple(max(0, min(255, int(part))) for part in value)
		except (TypeError, ValueError):
			return _hex(colours[default_key])
	if isinstance(value, str):
		if value.strip().lower() in colours:
			return _hex(colours[value.strip().lower()])
		try:
			return _hex(value)
		except (AttributeError, ValueError):
			pass
	return _hex(colours[default_key])


def _hex(value):
	text = str(value).strip().lstrip("#")
	if len(text) != 6:
		raise ValueError("not a #rrggbb colour: {!r}".format(value))
	return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def _sgr(rgb, level, background):
	"""Escape sequence for one colour at the requested level."""
	if level == "true":
		return "\033[{};2;{};{};{}m".format(48 if background else 38, *rgb)
	if level == "256":
		code = _nearest(rgb, 0)
		return "\033[{};5;{}m".format(48 if background else 38, code)
	index = _nearest(rgb, 0, stop=16)
	if background:
		return "\033[{}m".format(40 + index if index < 8 else 100 + index - 8)
	return "\033[{}m".format(30 + index if index < 8 else 90 + index - 8)


def _nearest(rgb, start, stop=None):
	"""(colours cached) index of the closest xterm entry; ties keep the lowest."""
	key = (rgb, start, stop)
	cached = _NEAREST.get(key)
	if cached is not None:
		return cached
	best_index, best_distance = start, None
	for index in range(start, len(_XTERM256) if stop is None else stop):
		entry = _XTERM256[index]
		distance = ((entry[0] - rgb[0]) ** 2 + (entry[1] - rgb[1]) ** 2
					+ (entry[2] - rgb[2]) ** 2)
		if best_distance is None or distance < best_distance:
			best_index, best_distance = index, distance
	_NEAREST[key] = best_index
	return best_index
