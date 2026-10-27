# Palette numeric twin: RGB resolution, xterm-256/16 indices and SGR codes
"""
			COLOUR LEVELS
			=============
The token-agnostic half of the palette: everything that turns a colour value
into a number or an escape sequence, with no knowledge of looks, `theme.ini` or
the theme document. `_rgb()` resolves a semantic key, `#rrggbb` or an
`(r, g, b)` tuple against a colours dict; `_hex()` parses the hex spelling;
`_nearest()` searches the xterm-256 table (`_XTERM256`, cached per query in
`_NEAREST`); `_sgr()` emits the one code for a level; and `rgb()`/`index()` are
the public numeric twins a curses renderer can use without emitting escapes.

`rgb()`/`index()` still resolve the look through `tui.palette` (that is where
the theme selection lives), so they import it at call time - `tui.palette`
imports this module at load, and the deferred import keeps the pair acyclic.
Nothing here reads a file or the terminal; importing it is inert.
"""

# The basic sixteen colours, the 6x6x6 cube and the 24-step grey ramp.
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


def rgb(value, theme=None):
	"""(r, g, b) for a semantic key, "#rrggbb" or an (r, g, b) tuple."""
	from . import palette  # deferred: `palette` imports this module
	return _rgb(value, palette.palette(theme), "fg")


def index(value, theme=None, level="256"):
	"""Nearest colour index for `value`, for curses `init_pair` callers.

	`value` is a semantic key, "#rrggbb" or an (r, g, b) tuple. Level "16"
	searches the basic sixteen colours only, anything else the full xterm-256
	table. The number is the one `style()` would emit at the same level, so a
	curses renderer and the escape-code renderer cannot disagree.
	"""
	stop = 16 if str(level) == "16" else None
	return _nearest(rgb(value, theme), 0, stop=stop)


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
