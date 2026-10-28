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
from .editor_nav import preview_title
from .preview_plan import rows as plan_rows, texts as plan_texts
from .preview_plan import title_label
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
		if focus == "accent" and "bg" in attributes:
			attributes["bg"] = "button-bg-active"
		elif focus == "accent":
			attributes["fg"] = "fg-accent"
		elif focus == "underline":
			attributes["underline"] = True
		else:
			attributes["reverse"] = True
	if disabled:
		attributes = {"fg": "fg-muted"}
	fg = colours.get(palette.role(attributes.pop("fg", "fg")))
	bg = colours.get(palette.role(attributes.pop("bg", "")), None)
	return palette.style(text, fg=fg, bg=bg, cap=cap, **attributes)


def draw_preview(canvas, x, y, width, height, document, look_id, *, cap,
				 active=False):
	"""One kitchen-sink preview: frame, table, buttons, fields, status, bar.

	The frame carries the document's own `border_style` glyphs; `none` is the
	space family, which is painted as coloured spaces so the preview keeps the
	same footprint. Its title sits in the top rule, and the progress bar is
	always the last inner row, so a short band drops content from the middle
	instead of losing the bar.
	"""
	colours = dict(document["looks"][look_id])
	properties = document["properties"]
	glyphs = glyphs_for(properties, cap)
	framed = width >= 4 and height >= 4
	inner_x, inner_y = x, y
	inner_w, inner_h = width, height
	if framed:
		editorframe.draw(canvas, x, y, width, height, glyphs,
						 title_label(preview_title(document, look_id), width,
									 properties),
						 editorframe.edge(colours, cap))
		inner_x, inner_y = x + 1, y + 1
		inner_w, inner_h = width - 2, height - 2

	def ink(role):
		return colours.get(palette.role(role), role)

	rows = plan_rows(inner_h)
	texts = plan_texts(look_id, active)
	table_style = str(properties.get("table_style", "box"))
	borderless = table_style == "borderless"
	zebra = "bg-stripe" if properties.get("table_zebra") else None
	row = 0
	for kind, role in rows:
		if row >= max(0, inner_h - 1):
			break
		top = inner_y + row
		if kind == "rule":
			glyph = " " if borderless else glyphs["h"]
			canvas.draw_text(inner_x, top, truncate(glyph * inner_w, inner_w),
							 palette.prefix(fg=ink("border-fg"), cap=cap))
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
					 palette.prefix(fg=ink("fg-accent"), cap=cap))
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
			fg=colours.get(palette.role("fg-accent" if active else "fg-muted")),
			cap=cap))
