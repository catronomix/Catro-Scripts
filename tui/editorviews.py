# Editor views: look previews, panel frames and the theme list
"""
			EDITOR VIEWS
			=============
The drawing half of `tui.editor`: three kitchen-sink look previews, the panel
frame used for the Properties/Colours/Actions panes, the Load popup's theme
rows and the small-terminal notice. Everything paints onto a `Canvas` through
`palette.prefix()`, so the editor emits no private ANSI and every colour still
degrades through the normal four levels.

A preview is drawn for the document under edit, not for whatever `theme.ini`
currently selects, so it passes the document's own `#rrggbb` values to
`palette.prefix()`. The chrome roles (button decoration/style and scrollbar
glyphs) come from `tui.chrome`'s tables and the frame glyphs from
`tui.table.glyphs_for()`, so the editor does not grow a second style engine.
"""

import re

from . import (chrome, editorframe, palette, progress, table, theme_engine,
			   widgets)
from .text import pad, truncate

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The three previews, in the order Left/Right moves through them.
LOOK_ORDER = ("default", "contrast-light", "contrast-dark")
LOOK_LABELS = {"default": "soft", "contrast-light": "light",
			   "contrast-dark": "dark"}

# Editor chrome shared by the key router, the painter and the action popups.
PANELS = ("Properties", "Colours", "Actions")
BUTTONS = ("Save", "Load", "Quit")
HELP_LINE = "Tab panel  <-/-> look  Enter edit  ^S save  F1 help  Q quit"
HELP_LINES = (
	"THEME EDITOR",
	"",
	"Tab / Shift-Tab   cycle Properties, Colours, Actions",
	"Left / Right      select the look under edit",
	"Up / Down         move inside the focused panel",
	"Enter             edit a property, open the picker, press a button",
	"Ctrl-S            save as themes/<name>.json",
	"F1 / Esc          this help",
	"Delete / Q        quit (asks when unsaved)",
	"",
	"Wheel or PageUp/PageDown scrolls the focused panel.",
)
# Properties panel rows, in schema order, and the key column width.
PROPERTY_KEYS = tuple(theme_engine.PROPERTY_VALUES)
PROPERTY_WIDTH = max(len(key) for key in PROPERTY_KEYS)


def look_label(look_id):
	"""User-facing selector for one look id (`default` -> `soft`)."""
	return LOOK_LABELS.get(look_id, "soft")


def preview_title(document, look_id):
	"""`<display> - <selector>` for one preview's header band."""
	display = str(document.get("display") or document.get("name") or "theme")
	return "{} - {}".format(display, look_label(look_id))


def preview_titles(document):
	"""One title per preview, in Left/Right order."""
	return [preview_title(document, look_id) for look_id in LOOK_ORDER]


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


def fill_rect(canvas, x, y, width, height, *, fg="fg", bg="surface", cap=None):
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
	canvas.draw_text(0, 1, hint, palette.prefix(fg="muted", cap=cap))
	return visible


def frame(canvas, x, y, width, height, title=None, cap=None):
	"""A box frame with an optional title cut into the top rule."""
	glyphs = table.glyphs_for(cap)
	edge = palette.prefix(fg="border", cap=cap)
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


def glyphs_for(properties, cap):
	"""Border glyphs for the document's `border_style`, like `table.glyphs_for`."""
	return editorframe.glyphs_for(properties, cap)


def button_text(label, properties, colours, *, focused=False, disabled=False,
				cap=None):
	"""One styled button for a preview, using chrome's decoration/style tables."""
	decorations = (chrome.BUTTON_DECORATIONS if cap.unicode
				   else chrome.ASCII_DECORATIONS)
	left, right = decorations.get(
		str(properties.get("button_decoration", "brackets")),
		chrome.BUTTON_DECORATIONS["brackets"])
	text = left + str(label) + right
	attributes = dict(chrome.BUTTON_STYLES.get(
		str(properties.get("button_style", "filled")),
		chrome.BUTTON_STYLES["filled"]))
	if focused:
		focus = str(properties.get("focus_style", "reverse"))
		if focus == "accent":
			attributes.pop("bg", None)
			attributes["fg"] = "accent"
		elif focus == "underline":
			attributes["underline"] = True
		else:
			attributes["reverse"] = True
	if disabled:
		attributes = {"fg": "muted"}
	fg = colours.get(attributes.pop("fg", "fg"))
	bg = colours.get(attributes.pop("bg", ""), None)
	return palette.style(text, fg=fg, bg=bg, cap=cap, **attributes)


def draw_preview(canvas, x, y, width, height, document, look_id, *, cap,
				 active=False):
	"""One kitchen-sink preview: frame, table, buttons, fields, status, bar.

	The frame carries the document's own `border_style` glyphs (`none` draws
	no frame at all, only the content) and its title sits in the top rule,
	which is what keeps the whole kitchen sink inside a 12-row band at 90x24.
	The progress bar is always the last inner row, so a short band drops
	content from the middle instead of losing the bar.
	"""
	colours = dict(document["looks"][look_id])
	properties = document["properties"]
	glyphs = glyphs_for(properties, cap)
	framed = editorframe.framed(glyphs) and width >= 4 and height >= 4
	inner_x, inner_y = x, y
	inner_w, inner_h = width, height
	if framed:
		editorframe.draw(canvas, x, y, width, height, glyphs,
						 preview_title(document, look_id),
						 editorframe.edge(colours, cap))
		inner_x, inner_y = x + 1, y + 1
		inner_w, inner_h = width - 2, height - 2

	def ink(role):
		return colours.get(role, role)

	rows = []
	if not framed:
		# `none` keeps the old borderless band: header row, table rule, then
		# the same rows. The frame's top rule replaces both when a frame is
		# drawn, so the space is spent on content there.
		rows.append(("header", "header"))
		rows.append(("rule", "border"))
	rows += [("name", "border"), ("alpha", "fg"), ("beta", "fg")]
	rows.append(("buttons", None))
	rows += [("field", "fg"), ("look", "fg"), ("preview", "accent"),
			 ("menu", "fg"), ("ready", "success")]
	# One row is reserved for the progress bar; the closing table rule is
	# therefore the first thing a 12-row band gives up.
	if inner_h > len(rows) + 1:
		rows.insert(3 if framed else 5, ("rule", "border"))
	while len(rows) + 1 > inner_h:
		drop = next((name for name in ("rule", "header", "name", "alpha",
									   "beta", "buttons", "field", "look",
									   "preview", "menu", "ready")
					 if any(row[0] == name for row in rows)), None)
		if drop is None:
			break
		rows = [row for row in rows if row[0] != drop]

	table_style = str(properties.get("table_style", "box"))
	borderless = table_style == "borderless"
	zebra = "zebra_bg" if properties.get("table_zebra") else None
	mark = " *" if active else ""
	texts = {
		"name": " name            value",
		"alpha": " alpha            yes",
		"beta": " beta             no",
		"field": " field: hello___",
		"look": " look  < {} >{}".format(look_label(look_id), mark),
		"preview": "> 1. preview",
		"menu": " 2. menu row",
		"ready": "[ok] ready",
	}
	row = 0
	for kind, role in rows:
		if row >= max(0, inner_h - 1):
			break
		top = inner_y + row
		if kind == "header":
			header = " " + preview_title(document, look_id) + mark + " "
			align = str(properties.get("header_align", "left"))
			if align == "center":
				header = header.center(inner_w)
			elif align == "right":
				header = header.rjust(inner_w)
			canvas.draw_text(inner_x, top, pad(truncate(header, inner_w),
											   inner_w),
							 palette.prefix(fg=ink("header"),
											bg=ink("surface"), bold=True,
											cap=cap))
		elif kind == "rule":
			glyph = " " if borderless else glyphs["h"]
			canvas.draw_text(inner_x, top, truncate(glyph * inner_w, inner_w),
							 palette.prefix(fg=ink("border"), cap=cap))
		elif kind == "buttons":
			column = 1
			for label, focused, disabled in (("OK", False, False),
											 ("Save", True, False),
											 ("Off", False, True)):
				styled = button_text(label, properties, colours,
									 focused=focused, disabled=disabled,
									 cap=cap)
				colour, visible = widgets.cells(styled)
				visible = visible[:max(0, inner_w - column - 1)]
				canvas.draw_text(inner_x + column, top, visible, colour)
				column += len(visible) + 1
		else:
			text = texts[kind]
			background = zebra if kind in ("alpha", "preview") else None
			canvas.draw_text(inner_x, top, pad(truncate(text, inner_w),
											   inner_w),
							 palette.prefix(fg=ink(role),
											bg=ink(background) if background
											else None,
											bold=kind in ("name", "preview"),
											cap=cap))
		row += 1

	bar = progress.bar(3, 5, max(5, min(10, inner_w - 12)), cap=cap)
	canvas.draw_text(inner_x, inner_y + max(0, inner_h - 1),
					 truncate(" build {} 60%".format(bar), inner_w),
					 palette.prefix(fg=ink("accent"), cap=cap))
	_draw_scrollbar(canvas, inner_x + inner_w - 1,
					inner_y + (0 if not framed else 1),
					max(1, inner_h - (2 if framed else 3)),
					properties, colours, cap)


def _draw_scrollbar(canvas, x, y, height, properties, colours, cap):
	"""The preview's scrollbar column from chrome's glyph table."""
	thumb, track, ascii_thumb, ascii_track = chrome.SCROLLBAR_GLYPHS.get(
		str(properties.get("scrollbar_style", "block")),
		chrome.SCROLLBAR_GLYPHS["block"])
	if not cap.unicode:
		thumb, track = ascii_thumb, ascii_track
	stop = max(1, height // 3)
	for row in range(height):
		active = row < stop
		glyph = thumb if active else track
		canvas.draw_char(x, y + row, glyph, palette.prefix(
			fg=colours.get("accent" if active else "muted"), cap=cap))


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
