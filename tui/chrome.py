# Page chrome: masthead, panels, rules, fields, status lines and menus
"""
			PAGE CHROME
			============
String-returning building blocks for a page of terminal output: a masthead, a
framed panel, a horizontal rule, a key/value field, a status line, a filled
background line and a menu. Nothing here prints and nothing returns a trailing
newline, so the caller decides how the lines land.

The module is `tui.chrome`, not `tui.page`, because `tui.page` is the pager
helper (`pager.page`) and keeping that callable is part of the public surface.
`tui/__init__.py` re-exports these helpers by name, so a caller can write
`tui.header(...)` or `from tui import chrome`.

Every colour goes through `palette.prefix()`/`palette.style()`, which is what
makes the four levels and the three themes work here for free: `true` emits
`38;2`, `256` the nearest index, `16` the basic stop, and `none` keeps the
layout while dropping every escape. The frame comes from `table.glyphs_for`:
`cap.unicode` false (or `table.style = ascii`) switches it to `+ - |`.

Two degradations are deliberate and pinned by the tests:

	- `cap.plain` (a pipe) is the machine-readable mode: no frame, no escapes,
		no background fill, one plain line per row and TAB-joined fields. A rule
		becomes an empty string and a masthead drops it; a menu keeps its numbers
		and marks the selected row with `>`.
	- Level `none` on a terminal is the mirror image: the frame and the padding
		stay, only the escapes go.

`width` arguments resolve as: explicit width > `cap.width` > the content's own
width. A framed panel or a filled bar never exceeds a width it was given.
"""

from . import caps, palette, table
from .text import display_width, pad, truncate as _truncate

# A standalone rule with no width anywhere has to pick something; this is the
# same 40-cell groove the old scripts hand-rolled.
DEFAULT_RULE_WIDTH = 40

# kind -> palette key. Unknown kinds are treated as "info" so a typo can never
# raise inside a renderer.
STATUS_COLOURS = {
	"ok": "success",
	"warn": "warn",
	"error": "error",
	"info": "accent",
}
# ASCII markers, valid under every glyph set and encoding.
STATUS_MARKERS = {
	"ok": "[ok]",
	"warn": "[warn]",
	"error": "[error]",
	"info": "[info]",
}
MENU_POINTER = ">"


def header(title, subtitle=None, *, width=None, cap=None, theme=None):
	"""Masthead: title, optional subtitle, then a border rule.

	Title is `header` + bold on `surface`, subtitle `muted` on `surface`; both
	are bands padded to the page width. Piped, it is just the lines.
	"""
	cap = cap or caps.detect()
	title = _flat(title)
	subtitle = None if subtitle is None else _flat(subtitle)
	if cap.plain:
		lines = [title]
		if subtitle:
			lines.append(subtitle)
		return "\n".join(lines)
	inner = _span(width, cap)
	if inner is None:
		inner = max(display_width(title), display_width(subtitle or "")) + 2
	inner = max(4, inner)
	lines = [_band(title, inner, fg="header", bold=True, cap=cap, theme=theme)]
	if subtitle:
		lines.append(_band(subtitle, inner, fg="muted", cap=cap, theme=theme))
	lines.append(rule(inner, cap=cap, theme=theme))
	return "\n".join(lines)


def rule(width=None, *, char=None, cap=None, theme=None):
	"""Border-coloured horizontal rule; empty when piped (a pipe has no frame)."""
	cap = cap or caps.detect()
	if cap.plain:
		return ""
	glyph = char or table.glyphs_for(cap)["h"]
	span = _span(width, cap)
	if span is None:
		span = DEFAULT_RULE_WIDTH
	return palette.style(glyph * max(1, int(span)), fg="border", cap=cap,
						 theme=theme)


def panel(title, body, *, width=None, padding=1, cap=None, theme=None):
	"""Framed box with `surface` interior and the title in the top rule.

	`body` is a string (one line per `\\n`) or an iterable of lines; lines are
	truncated to the interior, never wrapped, and never raise on odd input.
	`padding` is the number of spaces between the frame and the text on each
	side. A caller-supplied `width` wins, so a panel can be pinned to a column.
	"""
	cap = cap or caps.detect()
	padding = max(0, int(padding))
	title = "" if title is None else _flat(title)
	body_lines = _body_lines(body)
	if cap.plain:
		lines = ([title] if title else []) + body_lines
		return "\n".join(lines)
	glyphs = table.glyphs_for(cap)
	gutter = " " * padding
	content = max([display_width(line) for line in body_lines] + [0])
	needed = content + 2 * padding + 2
	if title:
		# Room for one rule glyph, " title ", and one more rule glyph.
		needed = max(needed, display_width(title) + 6)
	inner = _span(width, cap)
	if inner is None:
		inner = needed
	inner = max(4, inner)
	lines = [_top_frame(glyphs, inner, title, cap, theme)]
	cell = max(0, inner - 2 - 2 * padding)
	edge = palette.prefix(fg="border", cap=cap, theme=theme)
	inside = palette.prefix(fg="fg", bg="surface", cap=cap, theme=theme)
	reset = _reset(cap)
	for line in body_lines:
		text = _truncate(line, cell) if display_width(line) > cell else line
		lines.append(edge + glyphs["v"] + inside + gutter + pad(text, cell)
					 + gutter + edge + glyphs["v"] + reset)
	lines.append(palette.style(glyphs["bl"] + glyphs["h"] * (inner - 2)
							   + glyphs["br"], fg="border", cap=cap, theme=theme))
	return "\n".join(lines)


def field(key, value, *, width=None, cap=None, theme=None):
	"""One row of a settings block: `muted` key, `fg` value.

	`width` is the key column (so a block of fields lines up), not the whole
	line. Piped, the row is `key<TAB>value`.
	"""
	cap = cap or caps.detect()
	key = _flat(key)
	value = _flat(value)
	if cap.plain:
		return "{}\t{}".format(key, value)
	column = max(1, int(width)) if width is not None else display_width(key)
	if display_width(key) > column:
		key = _truncate(key, column)
	return "{}  {}".format(
		palette.style(pad(key, column), fg="muted", cap=cap, theme=theme),
		palette.style(value, fg="fg", cap=cap, theme=theme))


def status(kind, text, *, width=None, cap=None, theme=None):
	"""`[ok]`/`[warn]`/`[error]`/`[info]` marker plus text.

	The marker carries the colour (success/warn/error/accent) and the text stays
	`fg`, so a long message is not painted in an alarm colour. `width` is the
	total line width; the text truncates to fit. Unknown kinds render as info.
	"""
	cap = cap or caps.detect()
	kind = str(kind).strip().lower()
	colour = STATUS_COLOURS.get(kind, "accent")
	marker = STATUS_MARKERS.get(kind, STATUS_MARKERS["info"])
	text = _flat(text)
	if cap.plain:
		return "{} {}".format(marker, text)
	if width is not None:
		text = _truncate(text, max(0, int(width) - display_width(marker) - 1))
	return "{} {}".format(
		palette.style(marker, fg=colour, bold=True, cap=cap, theme=theme),
		palette.style(text, fg="fg", cap=cap, theme=theme))


def fill(text, width=None, *, bg="bg", fg="fg", cap=None, theme=None):
	"""Text padded to the full width and painted with a background role.

	This is the single-line `bg` band a full-screen page uses for footers and
	headers; it truncates rather than wrapping, because a band that spills over
	the edge paints the next row. With no width anywhere the text is styled but
	not padded. Piped, the text comes back plain.
	"""
	cap = cap or caps.detect()
	text = _flat(text)
	if cap.plain:
		return text
	span = _span(width, cap)
	if span is not None:
		span = max(0, span)
		text = _truncate(text, span) if display_width(text) > span else text
		text = pad(text, span)
	return palette.style(text, fg=fg, bg=bg, cap=cap, theme=theme)


def menu(items, selected=0, *, title=None, width=None, cap=None, theme=None):
	"""Numbered rows, one per item, with a selected-row bar.

	The selected row is `accent` on `surface` behind an ASCII `>` pointer; the
	other rows are `fg`. `selected=None` means "nothing is selected yet", which
	is what the numbered `ask_choice` prompt wants. Rows are numbered from 1 so
	a prompt can ask for the number it prints. A caller `width` pins the bar;
	otherwise it spans the widest row.
	"""
	cap = cap or caps.detect()
	items = [_flat(item) for item in items]
	title = None if title is None else _flat(title)
	labels = ["{}. {}".format(index + 1, item)
			  for index, item in enumerate(items)]
	if cap.plain:
		lines = ([title] if title else [])
		for index, label in enumerate(labels):
			lines.append(MENU_POINTER + " " + label
						 if index == selected else label)
		return "\n".join(lines)
	span = _span(width, cap)
	if span is None:
		span = max([display_width(label) + 2 for label in labels] + [0])
		if title:
			span = max(span, display_width(title) + 2)
	span = max(2, span)
	lines = []
	if title:
		lines.append(palette.style(pad(" " + title, span), fg="header",
								   bg="surface", bold=True, cap=cap, theme=theme))
	cell = span - 2
	for index, label in enumerate(labels):
		label = _truncate(label, cell) if display_width(label) > cell else label
		if index == selected:
			lines.append(palette.style(MENU_POINTER + " " + pad(label, cell),
									   fg="accent", bg="surface", bold=True,
									   cap=cap, theme=theme))
		else:
			lines.append(palette.style("  " + pad(label, cell), fg="fg",
									   cap=cap, theme=theme))
	return "\n".join(lines)


def _top_frame(glyphs, inner, title, cap, theme):
	"""Top border with the title cut into it, or a plain rule when untitled."""
	if not title:
		return palette.style(glyphs["tl"] + glyphs["h"] * (inner - 2)
							 + glyphs["tr"], fg="border", cap=cap, theme=theme)
	label = title
	if display_width(label) > inner - 6:
		label = _truncate(label, max(0, inner - 6))
	if not label:
		return palette.style(glyphs["tl"] + glyphs["h"] * (inner - 2)
							 + glyphs["tr"], fg="border", cap=cap, theme=theme)
	rest = max(0, inner - 5 - display_width(label))
	return (palette.prefix(fg="border", cap=cap, theme=theme) + glyphs["tl"]
			+ glyphs["h"]
			+ palette.prefix(fg="header", bold=True, cap=cap, theme=theme)
			+ " " + label + " "
			+ palette.prefix(fg="border", cap=cap, theme=theme)
			+ glyphs["h"] * rest + glyphs["tr"] + _reset(cap))


def _band(text, width, *, fg, bold=False, cap, theme):
	"""One full-width `surface` band with a leading space and a padded label."""
	body = " " + pad(_truncate(text, max(0, width - 2)), max(0, width - 2)) + " "
	return palette.style(body, fg=fg, bg="surface", bold=bold, cap=cap, theme=theme)


def _body_lines(body):
	"""The panel body as one flattened string per line; never empty."""
	if isinstance(body, str):
		return body.splitlines() or [""]
	return [_flat(line) for line in body] or [""]


def _flat(value):
	"""str() with newlines flattened: a page row is always one line."""
	return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _span(width, cap):
	"""Explicit width, else the terminal width, else None (content-sized)."""
	if width is not None:
		try:
			return max(0, int(width))
		except (TypeError, ValueError):
			return None
	return cap.width


def _reset(cap):
	"""The reset code, or "" when the caller asked for no styling at all."""
	return "" if cap.level == "none" else palette.RESET
