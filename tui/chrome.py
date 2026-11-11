# Page chrome: masthead, panels, rules, fields, status lines and menus
"""
			PAGE CHROME
			============
String-returning building blocks for a page of terminal output: a masthead, a
horizontal rule, a key/value field, a status line, a filled background line and
a menu. Nothing here prints and nothing returns a trailing newline, so the
caller decides how the lines land.

The framed panel and the masthead/panel band painters (`panel`, `_band`,
`_top_frame`) live in `tui.chrome_panels`; `panel()` and the shared `_band`
painter are re-exported here, so `chrome.panel()` keeps resolving for
`keygen`, `jsonl_monitor` and the tests.

The two interactive seams - the styled button label and the scrollbar column,
with their decoration/style/glyph tables - live in `tui.chrome_controls` and are
re-exported here, so `chrome.button()`/`chrome.scrollbar()` keep resolving for
`tui.widgets`, `editorviews` and the properties tests.

The module is `tui.chrome`, not `tui.page`, because `tui.page` is the pager
helper (`pager.page`) and keeping that callable is part of the public surface.
`tui/__init__.py` re-exports these helpers by name, so a caller can write
`tui.header(...)` or `from tui import chrome`.

Every colour goes through `palette.prefix()`/`palette.style()`, which is what
makes the four levels and the three themes work here for free; the frame comes
from `table.glyphs_for`. Two degradations are deliberate and pinned: `cap.plain`
(a pipe) is the machine-readable mode (no frame, no escapes, no background
fill, one line per row, TAB-joined fields, a menu keeps its numbers and marks
the selected row with `>`), and level `none` on a terminal is its mirror image
(the frame and padding stay, only the escapes go). `width` resolves as explicit
width > `cap.width` > the content's own width.
"""

from . import caps, palette, table
from .chrome_controls import (ASCII_DECORATIONS, BUTTON_DECORATIONS,  # noqa: F401
							  BUTTON_STYLES, SCROLLBAR_GLYPHS, button,
							  scrollbar)
from .chrome_panels import (_band, _flat, _span, frame_roles,  # noqa: F401
							panel)
from .text import display_width, pad, truncate as _truncate, wrap as _wrap

# A standalone rule with no width anywhere has to pick something; this is the
# same 40-cell groove the old scripts hand-rolled.
DEFAULT_RULE_WIDTH = 40

# kind -> palette key. Unknown kinds are treated as "info" so a typo can never
# raise inside a renderer.
STATUS_COLOURS = {"ok": "fg-success", "warn": "fg-warn",
				  "error": "fg-error", "info": "fg-accent"}
# ASCII markers, valid under every glyph set and encoding.
STATUS_MARKERS = {"ok": "[ok]", "warn": "[warn]",
				  "error": "[error]", "info": "[info]"}
MENU_POINTER = ">"


def header(title, subtitle=None, *, width=None, cap=None, theme=None):
	"""Masthead: title, optional subtitle, then a border rule.

	Title is `header-fg` + bold on `header-bg`, subtitle `fg-muted` on the same
	band; both are padded to the page width. `header_align` left/center/right places
	the label inside the band; `left` is the shipped, byte-pinned default.
	"""
	cap = cap or caps.detect()
	title = _flat(title)
	subtitle = None if subtitle is None else _flat(subtitle)
	if cap.plain:
		lines = [title]
		if subtitle:
			lines.append(subtitle)
		return "\n".join(lines)
	align = str(palette.properties(theme).get("header_align", "left"))
	inner = _span(width, cap)
	if inner is None:
		inner = max(display_width(title), display_width(subtitle or "")) + 2
	inner = max(4, inner)
	lines = [_band(title, inner, fg="header-fg", bold=True, align=align,
				   cap=cap, theme=theme)]
	if subtitle:
		lines.append(_band(subtitle, inner, fg="fg-muted", align=align,
						   cap=cap, theme=theme))
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
	return palette.style(glyph * max(1, int(span)), fg="border-fg",
						 bg="border-bg", cap=cap, theme=theme)


def field(key, value, *, width=None, cap=None, theme=None):
	"""One row of a settings block: `fg-muted` key, `fg` value.

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
	return (palette.style(pad(key, column) + "  ", fg="fg-muted", bg="bg",
						  cap=cap, theme=theme)
			+ palette.style(value, fg="fg", bg="bg", cap=cap, theme=theme))


def status(kind, text, *, width=None, cap=None, theme=None):
	"""`[ok]`/`[warn]`/`[error]`/`[info]` marker plus text.

	The marker carries the colour (fg-success/fg-warn/fg-error/fg-accent), the
	text stays `fg`, so a long message is not painted in an alarm colour.
	`width` is the total line width; the text truncates. Unknown kinds render
	as info.
	"""
	cap = cap or caps.detect()
	kind = str(kind).strip().lower()
	colour = STATUS_COLOURS.get(kind, "fg-accent")
	marker = STATUS_MARKERS.get(kind, STATUS_MARKERS["info"])
	text = _flat(text)
	if cap.plain:
		return "{} {}".format(marker, text)
	if width is not None:
		text = _truncate(text, max(0, int(width) - display_width(marker) - 1))
	return (palette.style(marker, fg=colour, bg="bg", bold=True, cap=cap,
						  theme=theme)
			+ palette.style(" " + text, fg="fg", bg="bg", cap=cap,
							theme=theme))


def status_panel(rows, *, width=None, cap=None, theme=None):
	"""A panel of `(kind, text)` outcome rows; a long message wraps, never cuts.

	A line that fits renders exactly as `panel(None, [status(...)])`; a message
	wider than the interior is word-wrapped with the marker's width as the
	continuation indent, so an absolute path is shown whole inside the box.
	"""
	cap = cap or caps.detect()
	rows = [(str(kind).strip().lower(), _flat(text)) for kind, text in rows]
	rendered = [status(kind, text, cap=cap, theme=theme) for kind, text in rows]
	inner = _span(width, cap)
	if cap.plain or inner is None:
		return panel(None, rendered, width=width, cap=cap, theme=theme)
	cell = max(1, inner - 4)
	body = []
	for (kind, text), line in zip(rows, rendered):
		if display_width(line) <= cell:
			body.append(line)
			continue
		indent = display_width(STATUS_MARKERS.get(kind, STATUS_MARKERS["info"])) + 1
		pieces = _wrap(text, max(1, cell - indent)) or [""]
		body.append(status(kind, pieces[0], cap=cap, theme=theme))
		body.extend(" " * indent + piece for piece in pieces[1:])
	return panel(None, body, width=width, cap=cap, theme=theme)


def fill(text, width=None, *, bg="bg", fg="fg", cap=None, theme=None):
	"""Text padded to the full width and painted with a background role.

	This is the single-line `bg` band a full-screen page uses for footers and
	headers; it truncates rather than wrapping, because a band that spills over
	the edge paints the next row. No width anywhere styles without padding.
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

	The selected row is `fg-accent` on `bg-inside-active` behind a `>` pointer,
	the others `fg` on `bg-inside`. `selected=None` means "nothing selected yet"
	(`ask_choice`).
	Rows number from 1 so a prompt can ask for the number it prints; a caller
	`width` pins the bar, otherwise it spans the widest row.
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
		lines.append(palette.style(pad(" " + title, span), fg="header-fg",
								   bg="bg-inside", bold=True, cap=cap, theme=theme))
	cell = span - 2
	for index, label in enumerate(labels):
		label = _truncate(label, cell) if display_width(label) > cell else label
		if index == selected:
			lines.append(palette.style(MENU_POINTER + " " + pad(label, cell),
									   fg="fg-accent", bg="bg-inside-active",
									   bold=True, cap=cap, theme=theme))
		else:
			lines.append(palette.style("  " + pad(label, cell), fg="fg",
									   bg="bg-inside", cap=cap, theme=theme))
	return "\n".join(lines)


