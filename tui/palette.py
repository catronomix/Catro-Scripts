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
`config.ini [theme] mode` value migrated behind it. `SOFT`/`CONTRAST_*`/`THEMES`
keep their names and values but are resolved on access from the shipped
document, so nothing is read at import and no renderer changed; the golden
fixture still pins `soft`'s own bytes.

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

The numeric half that needs no look at all - `rgb()`, `index()`, the hex
resolution, the xterm-256 table and `_sgr()` - lives in `tui.color_levels`; it
is re-exported here so `tui.palette.rgb()`/`index()` and the private helpers a
test may reach keep resolving at their old path.

A full-screen painter resolves the same look hundreds of times per frame, and
each resolution costs a stat plus a copy. `begin_frame()`/`end_frame()` open a
one-frame memo for the look palette, the selection and the theme properties;
`tui.editorpaint` brackets every paint with them. Outside a frame nothing is
memoized, so a caller that never opens one always reads through the engine and
keeps the mtime-keyed freshness of `tui.theme_engine`.
"""

import os

from . import caps, theme_engine
from .color_levels import (_BASE16, _CUBE, _NEAREST, _XTERM256,  # noqa: F401
						   _hex, _nearest, _rgb, _sgr, index, rgb)

# The active frame memo (None outside a frame); see the module docstring.
_FRAME = None


def begin_frame():
	"""Start one paint: colour/property resolution is memoized until `end_frame`."""
	global _FRAME
	_FRAME = {}


def end_frame():
	"""Drop the frame memo; idempotent and safe outside a frame."""
	global _FRAME
	_FRAME = None


def _memo(key, build):
	"""`build()` once per frame for `key`; always `build()` outside a frame."""
	if _FRAME is None:
		return build()
	if key not in _FRAME:
		_FRAME[key] = build()
	return _FRAME[key]

# The published look tables, resolved lazily (see `__getattr__`): name ->
# (theme id, look id in the shipped document).
_LOOK_TABLES = {
	"SOFT": ("soft", "default"),
	"CONTRAST_LIGHT": ("contrast-light", "contrast-light"),
	"CONTRAST_DARK": ("contrast-dark", "contrast-dark"),
}


def __getattr__(name):
	"""`SOFT`, `CONTRAST_LIGHT`, `CONTRAST_DARK` and `THEMES`, read on demand.

	The tables are the shipped `themes/cozypurple.json` document, resolved by
	the engine when the name is first used, so importing this module stays I/O
	free and the published hexes cannot drift from the theme file (issue #33).
	Each access returns fresh dicts: mutating one changes nothing.
	"""
	if name in _LOOK_TABLES:
		_theme_id, look_id = _LOOK_TABLES[name]
		return dict(theme_engine.builtin_looks()[look_id])
	if name == "THEMES":
		looks = theme_engine.builtin_looks()
		return {theme_id: dict(looks[look_id])
				for theme_id, look_id in _LOOK_TABLES.values()}
	raise AttributeError(
		"module {!r} has no attribute {!r}".format(__name__, name))

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
	return dict(_memo("properties", theme_engine.properties))


def palette(theme=None, cap=None):
	"""Copy of the active look (key -> "#rrggbb"). `cap` is accepted unused.

	`theme` keeps its old meaning: a look spelling (`soft`, `contrast-light`, ...)
	selects that look of the active theme, so every existing caller and test
	still names the palette it used to get.
	"""
	name, look_selector = _active(theme)
	key = ("palette", name, look_selector)
	return dict(_memo(key, lambda: theme_engine.look_palette(name, look_selector)))


def style(text, fg=None, bg=None, bold=False, dim=False, reverse=False,
		  underline=False, cap=None, theme=None):
	"""Wrap `text` in SGR codes for the active theme and capability level.

	`fg`/`bg` accept a semantic key, "#rrggbb" or an (r, g, b) tuple; anything
	unparseable falls back to the palette's own `fg`/`bg` instead of raising.
	Level "none" returns the bare text, with no reset code.
	"""
	plain = "" if text is None else str(text)
	lead = prefix(fg=fg, bg=bg, bold=bold, dim=dim, reverse=reverse,
				  underline=underline, cap=cap, theme=theme)
	if not lead:
		return plain
	return lead + plain + RESET


def prefix(fg=None, bg=None, bold=False, dim=False, reverse=False,
		   underline=False, cap=None, theme=None):
	"""The SGR codes `style()` would emit, with no text and no reset code.

	This is the seam for callers that compose a run of cells and must re-assert
	the style after each border without a reset in between (the table rows, and
	any full-screen caller driving a canvas). `underline` is the additive
	attribute the button/focus seams need, so no module hand-writes `\\033[4m`.
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
	if underline:
		parts.append("\033[4m")
	return "".join(parts)


def _active(override=None):
	"""(theme name, look) for one call: override > CATRO_THEME > theme.ini."""
	name, selector = _memo("selection", theme_engine.selection)
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
