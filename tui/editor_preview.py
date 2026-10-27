# Editor preview: the kitchen-sink look preview and its two paint helpers
"""
			EDITOR PREVIEW
			===============
The painter for one look preview: the frame (or borderless band), the sample
table rows, the three styled buttons, the fields, the status line and the
progress bar, all onto an injected `Canvas`.

It carries `glyphs_for()` and `button_text()` because the painter is their only
caller; keeping them here is what lets this module stay a leaf - it imports the
label helpers from `tui.editor_nav` and never `tui.editorviews`, the module that
re-exports it. Colours come from the document under edit (`colours` mapping plus
`palette.prefix()`), so a preview shows what the file says, not what `theme.ini`
currently selects.
"""

from . import chrome, editorframe, palette, progress, widgets
from .editor_nav import look_label, preview_title
from .text import pad, truncate


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
