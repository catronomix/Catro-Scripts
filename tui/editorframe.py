# Preview frame: the document's own border_style drawn around a preview
"""
			PREVIEW FRAME
			=============
The frame a kitchen-sink preview wears: the glyph family the document's
`border_style` selects, the same table `tui.table.glyphs_for()` uses, drawn as
one rectangle around the preview band. Keeping it here (rather than in
`tui.editorviews`) is what lets the preview carry a per-document frame without
pushing `editorviews.py` past its budget, and without a second style engine.

`none` is the space glyph set: the frame is painted as coloured spaces, so the
preview keeps its footprint and only the glyphs vanish. A console without
Unicode degrades to `+ - |` first, then the document's `corner-char` lands on
the four corners, exactly like a table.

The edge colour is the look's own `border-fg` hex (the document under edit,
whatever `theme.ini` selects), so all three previews stay theme-accurate.
"""

from . import frame_corners, palette, table


def glyphs_for(properties, cap):
	"""Border glyphs for the document's `border_style`, like `table.glyphs_for`."""
	glyphs = table.BORDER_GLYPHS.get(
		str(properties.get("border_style", "rounded")),
		table.UNICODE_GLYPHS)
	if not cap.unicode and glyphs is not table.SPACE_GLYPHS:
		glyphs = table.ASCII_GLYPHS
	return frame_corners.apply_corners(glyphs, cap, properties)


def framed(glyphs):
	"""False for the `none` style: its frame is spaces, not glyphs."""
	return glyphs is not table.SPACE_GLYPHS


def draw(canvas, x, y, width, height, glyphs, title=None, colour=None):
	"""Draw one preview frame, the space family included, on every edge."""
	if width < 2 or height < 2:
		return None
	top = glyphs["tl"] + glyphs["h"] * (width - 2) + glyphs["tr"]
	label = " {} ".format(title) if title else ""
	if label and len(label) <= width - 2:
		top = (glyphs["tl"] + glyphs["h"] + label
			   + glyphs["h"] * (width - 3 - len(label)) + glyphs["tr"])
	canvas.draw_text(x, y, top[:width], colour)
	for row in range(1, height - 1):
		canvas.draw_char(x, y + row, glyphs["v"], colour)
		canvas.draw_char(x + width - 1, y + row, glyphs["v"], colour)
	bottom = glyphs["bl"] + glyphs["h"] * (width - 2) + glyphs["br"]
	canvas.draw_text(x, y + height - 1, bottom[:width], colour)
	return None


def edge(colours, cap=None):
	"""The SGR prefix for a preview frame: the look's own border hexes."""
	return palette.prefix(fg=colours.get(palette.role("border-fg"),
										 "border-fg"),
						  bg=colours.get(palette.role("border-bg"),
										 "border-bg"), cap=cap)
