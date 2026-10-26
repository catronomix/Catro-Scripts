# House palettes, theme resolution and level downgrade
"""
			COLOR PALETTES AND STYLING
			===========================
Three hand-authored looks with identical semantic keys, none derived from
another (no inversion, no hue rotation). SOFT is the default: `mdreader` mode 0,
"Cozy Purple", with `muted`/`border` nudged from #9381B0 to #A392C0 so every
foreground clears the WCAG AA gate on both backgrounds. CONTRAST_LIGHT and
CONTRAST_DARK are `mdreader` modes 1 and 2, so the reader and the scripts agree.

The hexes themselves belong to `tui.theme_engine` (and `themes/cozypurple.json`);
this module stays the public API and the only place that emits SGR codes. The
active theme comes from `theme.ini` through the engine, with the legacy
`config.ini [theme] mode` value migrated behind it. `SOFT`/`THEMES` keep their
names and values, so no renderer changed and the golden fixture still pins
`soft`'s own bytes.

The default is deliberately not the old per-script `Colors` identity (#AA00FF
on #000000): that palette is gone, and `dark` survives only as an alias input
for configs written before the theme set changed.

`style()` is the only place that emits SGR codes. Its emission order is pinned:
foreground, background, attributes, text, reset. Every downgrade (256, 16, none)
is deterministic: the same hex always resolves to the same code.

`prefix()` is the same codes without the text and without the reset. It exists
for callers that must re-assert a style between cells without paying a reset -
the table renderer's rows are such a caller - and `style()` is defined in terms
of it so the two can never drift.
"""

import os

from . import caps, theme_engine

# The default look: mdreader mode 0, "Cozy Purple", mirrored from the engine's
# built-in document (`themes/cozypurple.json` carries the same hexes).
SOFT = dict(theme_engine.BUILTIN_LOOKS["default"])

# mdreader mode 1, "High Contrast Light".
CONTRAST_LIGHT = dict(theme_engine.BUILTIN_LOOKS["contrast-light"])

# mdreader mode 2, "High Contrast Dark". Selectable like the others, never
# chosen automatically.
CONTRAST_DARK = dict(theme_engine.BUILTIN_LOOKS["contrast-dark"])

THEMES = {
	"soft": SOFT,
	"contrast-light": CONTRAST_LIGHT,
	"contrast-dark": CONTRAST_DARK,
}

# Every accepted spelling, folded by `fold()` before lookup. Only the three
# names in THEMES are real palettes; the rest are inputs, including the legacy
# names older configs wrote (`dark` was the old default, not a theme now).
THEME_ALIASES = {
	"soft": "soft",
	"default": "soft",
	"cozy": "soft",
	"contrast-light": "contrast-light",
	"contrastlight": "contrast-light",
	"light": "contrast-light",
	"clight": "contrast-light",
	"contrast-dark": "contrast-dark",
	"contrastdark": "contrast-dark",
	"high-contrast": "contrast-dark",
	"highcontrast": "contrast-dark",
	"hc": "contrast-dark",
	"cdark": "contrast-dark",
	"dark": "soft",
}

# The only reset this package emits; callers composing their own spans use it
# instead of hardcoding the escape.
RESET = "\033[0m"

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


def fold(name):
	"""Fold a spelling before lookup: lowercase, spaces/underscores to "-"."""
	return "-".join(str(name).strip().lower().replace("_", " ").split())


def normalize(name):
	"""Canonical theme id for any accepted spelling; unknown -> "soft"."""
	return THEME_ALIASES.get(fold(name), "soft")


def theme(override=None):
	"""Active theme id: override > CATRO_THEME > theme.ini > "soft"."""
	return _theme_id(_active(override)[1])


def theme_name():
	"""Slug of the active theme (`cozypurple` for the shipped default)."""
	return theme_engine.selection()[0]


def look():
	"""Active look selector: `soft`, `light` or `dark`."""
	return theme_engine.selection()[1]


def document():
	"""The active theme document; the built-in one when it cannot be read."""
	return theme_engine.document()


def properties():
	"""Copy of the active theme's rendering properties."""
	return theme_engine.properties()


def palette(theme=None, cap=None):
	"""Copy of the active look (key -> "#rrggbb"). `cap` is accepted unused.

	`theme` keeps its old meaning: a look spelling (`soft`, `contrast-light`, ...)
	selects that look of the active theme, so every existing caller and test
	still names the palette it used to get.
	"""
	name, look_selector = _active(theme)
	return dict(theme_engine.look_palette(name, look_selector))


def style(text, fg=None, bg=None, bold=False, dim=False, reverse=False,
		  cap=None, theme=None):
	"""Wrap `text` in SGR codes for the active theme and capability level.

	`fg`/`bg` accept a semantic key, "#rrggbb" or an (r, g, b) tuple; anything
	unparseable falls back to the palette's own `fg`/`bg` instead of raising.
	Level "none" returns the bare text, with no reset code.
	"""
	plain = "" if text is None else str(text)
	lead = prefix(fg=fg, bg=bg, bold=bold, dim=dim, reverse=reverse,
				  cap=cap, theme=theme)
	if not lead:
		return plain
	return lead + plain + RESET


def prefix(fg=None, bg=None, bold=False, dim=False, reverse=False,
		   cap=None, theme=None):
	"""The SGR codes `style()` would emit, with no text and no reset code.

	This is the seam for callers that compose a run of cells and must re-assert
	the style after each border without a reset in between (the table rows, and
	any full-screen caller driving a canvas).
	"""
	cap = cap or caps.detect()
	if cap.level == "none":
		return ""
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
	return "".join(parts)


def rgb(value, theme=None):
	"""(r, g, b) for a semantic key, "#rrggbb" or an (r, g, b) tuple."""
	return _rgb(value, palette(theme), "fg")


def index(value, theme=None, level="256"):
	"""Nearest colour index for `value`, for curses `init_pair` callers.

	`value` is a semantic key, "#rrggbb" or an (r, g, b) tuple. Level "16"
	searches the basic sixteen colours only, anything else the full xterm-256
	table. The number is the one `style()` would emit at the same level, so a
	curses renderer and the escape-code renderer cannot disagree.
	"""
	stop = 16 if str(level) == "16" else None
	return _nearest(rgb(value, theme), 0, stop=stop)


def _active(override=None):
	"""(theme name, look) for one call: override > CATRO_THEME > theme.ini."""
	name, selector = theme_engine.selection()
	if override is not None and str(override).strip():
		return name, normalize(override)
	env = os.environ.get("CATRO_THEME", "")
	if str(env).strip():
		return name, normalize(env)
	return name, selector


# Look id -> the id `theme()` has always returned for it.
_ID_OF_LOOK = {
	"default": "soft",
	"contrast-light": "contrast-light",
	"contrast-dark": "contrast-dark",
}


def _theme_id(look_value):
	"""The legacy theme id (`soft`/`contrast-light`/`contrast-dark`) for a look."""
	look_id = theme_engine.SELECTORS.get(fold(look_value), "default")
	return _ID_OF_LOOK[look_id]


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
