# Editor views: canvas helpers, the theme list and the slug rules
"""
			EDITOR VIEWS
			=============
The canvas-level half of `tui.editor`: `clear`/`blank_rect`/`fill_rect` (the
erase primitives an incremental frame repaints through), the panel `frame`, the
small-terminal `notice`, the Load popup's theme rows and the slug rules. They
paint onto an injected `Canvas` through `palette.prefix()`, so the editor emits
no private ANSI and every colour still degrades through the normal four levels.

The kitchen-sink look preview itself - and the `glyphs_for`/`button_text`
helpers it needs - lives in `tui.editor_preview`; this module re-exports it so
`editorviews.draw_preview(...)` keeps resolving for the painter.

The module is the fan-in leaf for the editor: the look/panel/button captions
and the help copy live in `tui.editor_nav`, the preview in `tui.editor_preview`,
and both are re-exported here, so `editorviews.LOOK_ORDER`/`PANELS`/
`preview_title` keep resolving while neither submodule imports anything back.
"""

import re

from . import palette, table, theme_engine, widgets
from .editor_nav import (BUTTONS, HELP_LINE, HELP_LINES, LOOK_LABELS,  # noqa: F401
						 LOOK_ORDER, PANELS, look_label, preview_title,
						 preview_titles)
from .editor_preview import (_draw_scrollbar, button_text,  # noqa: F401
							 draw_preview, glyphs_for)
from .text import truncate

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Properties panel rows, in schema order, and the two key column widths.
PROPERTY_KEYS = tuple(theme_engine.PROPERTY_VALUES)
PROPERTY_WIDTH = max(len(key) for key in PROPERTY_KEYS)
COLOUR_WIDTH = max(len(key) for key in theme_engine.PALETTE_KEYS)


def clear(canvas):
	"""Blank the whole grid without re-reading the terminal size."""
	for row in range(canvas.height):
		canvas.draw_text(0, row, " " * canvas.width)


def blank_rect(canvas, x, y, width, height):
	"""Erase a rectangle to blank, uncoloured cells.

	An incremental frame repaints every band it owns, so the only leftovers a
	closing overlay can leave are its own box; erasing that box before the
	painters run is what makes `draw(full=False)` safe without a full clear.
	"""
	blank = " " * max(0, width)
	for row in range(max(0, height)):
		canvas.draw_text(x, y + row, truncate(blank, width), None)


def fill_rect(canvas, x, y, width, height, *, fg="fg", bg="bg-inside",
			  cap=None):
	"""Paint a rectangle of spaces so an overlay hides what is behind it."""
	colour = palette.prefix(fg=fg, bg=bg, cap=cap)
	blank = " " * max(0, width)
	for row in range(max(0, height)):
		canvas.draw_text(x, y + row, truncate(blank, width), colour)


def notice(canvas, cap=None):
	"""The `too small` fallback plus the only key that still works."""
	line = widgets.resize_notice(canvas.width, canvas.height, cap=cap)
	if line is None:
		return None
	colour, visible = widgets.cells(line)
	canvas.draw_text(0, 0, visible, colour)
	hint = "Q or Delete quits"
	canvas.draw_text(0, 1, hint, palette.prefix(fg="fg-muted", cap=cap))
	return visible


def frame(canvas, x, y, width, height, title=None, cap=None):
	"""A box frame with an optional title cut into the top rule."""
	glyphs = table.glyphs_for(cap)
	edge = palette.prefix(fg="border-fg", cap=cap)
	label = " {} ".format(title) if title else ""
	top = glyphs["tl"] + glyphs["h"] * max(0, width - 2) + glyphs["tr"]
	if label and len(label) <= width - 2:
		top = (glyphs["tl"] + glyphs["h"]
			   + label + glyphs["h"] * (width - 3 - len(label)) + glyphs["tr"])
	canvas.draw_text(x, y, truncate(top, width), edge)
	for row in range(1, max(1, height - 1)):
		canvas.draw_text(x, y + row, glyphs["v"], edge)
		canvas.draw_text(x + width - 1, y + row, glyphs["v"], edge)
	bottom = glyphs["bl"] + glyphs["h"] * max(0, width - 2) + glyphs["br"]
	canvas.draw_text(x, y + height - 1, truncate(bottom, width), edge)


def theme_entries():
	"""Load-popup rows: `{slug, display, error, label, active}` per file.

	Never raises: an unreadable or invalid file becomes an `!` row with the
	engine's reason, so one broken file cannot break the list.
	"""
	active = theme_engine.selection()[0]
	entries = []
	for slug in theme_engine.list_themes():
		try:
			document = theme_engine.load_theme(slug)
			display = str(document.get("display") or slug)
			error = None
		except Exception as exc:  # a bad file is a row, never a crash
			display, error = slug, str(exc)
		if error:
			label = "! {} ({}.json) - invalid".format(slug, slug)
		else:
			marker = "*" if slug == active else " "
			label = "{} {} ({}.json)".format(marker, display, slug)
		entries.append({"slug": slug, "display": display, "error": error,
						"label": label, "active": slug == active and not error})
	return entries


def valid_slug(value):
	"""TextField validator for the Save popup: a legal theme slug."""
	text = slug_of(value)
	if not _SLUG.match(text):
		return "use a-z, 0-9 and -"
	return True


def slug_of(value):
	"""Drop a typed `.json` suffix; the file extension is implied."""
	text = str(value).strip().lower()
	return text[:-5] if text.endswith(".json") else text
