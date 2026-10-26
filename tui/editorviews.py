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

from . import chrome, palette, progress, table, theme_engine, widgets
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
	glyphs = table.BORDER_GLYPHS.get(
		str(properties.get("border_style", "rounded")),
		table.UNICODE_GLYPHS)
	if not cap.unicode and glyphs is not table.SPACE_GLYPHS:
		return table.ASCII_GLYPHS
	return glyphs


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
	"""One kitchen-sink preview: header, table, buttons, fields, status, bar."""
	colours = dict(document["looks"][look_id])
	properties = document["properties"]
	glyphs = glyphs_for(properties, cap)
	row = 0

	def ink(role):
		return colours.get(role, role)

	def put(text, role="fg", bg=None, bold=False):
		nonlocal row
		if row >= height:
			return
		colour = palette.prefix(fg=ink(role), bg=ink(bg) if bg else None,
								bold=bold, cap=cap)
		visible = pad(truncate(str(text), width), width)[:width]
		canvas.draw_text(x, y + row, visible, colour)
		row += 1

	mark = "*" if active else " "
	header = " " + preview_title(document, look_id) + " " + mark
	align = str(properties.get("header_align", "left"))
	if align == "center":
		header = header.center(width)
	elif align == "right":
		header = header.rjust(width)
	put(header, "header", bg="surface", bold=True)
	table_style = str(properties.get("table_style", "box"))
	rule = " " * width if table_style == "borderless" else glyphs["h"] * width
	compact = table_style == "compact"
	if not compact:
		put(rule, "border")
	put(" name            value", "border", bold=True)
	zebra = "zebra_bg" if properties.get("table_zebra") else None
	put(" alpha            yes", "fg", bg=zebra)
	put(" beta             no", "fg")
	if not compact:
		put(rule, "border")

	# Buttons: normal, focused and disabled share one row.
	if row < height:
		column = 1
		for label, focused, disabled in (("OK", False, False),
										 ("Save", True, False),
										 ("Off", False, True)):
			styled = button_text(label, properties, colours, focused=focused,
								 disabled=disabled, cap=cap)
			colour, visible = widgets.cells(styled)
			visible = visible[:max(0, width - column - 1)]
			canvas.draw_text(x + column, y + row, visible, colour)
			column += len(visible) + 1
		row += 1

	put(" field: hello___", "fg")
	put(" look  < {} >".format(look_label(look_id)), "fg")
	if row < height:
		colour = palette.prefix(fg=ink("accent"), bg=ink(zebra) if zebra else None,
								bold=True, cap=cap)
		labelled = pad(truncate("> 1. preview", width), width)[:width]
		canvas.draw_text(x, y + row, labelled, colour)
		row += 1
	put(" 2. menu row", "fg")
	put("[ok] ready", "success")
	bar = progress.bar(3, 5, max(5, min(10, width - 12)), cap=cap)
	put(" build {} 60%".format(bar), "accent")
	_draw_scrollbar(canvas, x + width - 1, y + 2, max(1, height - 3),
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
