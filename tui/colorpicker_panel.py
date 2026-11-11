# Colour picker preview panel: the solid swatch beside the grid
"""
			COLOUR PICKER PANEL
			===================
The right-hand column of the picker popup: the selected colour as a solid
`PANEL`-wide block, three rows tall, with its hex one row beneath. It is a
separate module so `tui.colorpicker` keeps its line budget and the popup's
geometry has one owner: `panel_x()` decides whether the popup is wide enough
(the grid and its border always win) and `draw()` paints only through
`palette.prefix()`.

No picker imports: the caller passes its own origin, width and grid extent, so
this module stays a leaf of `palette` and `text`.
"""

from . import palette
from .text import truncate

PANEL = 8  # cells in the preview block


def panel_x(x, width, grid_end):
	"""Left edge of the preview panel, or None when the grid leaves no room."""
	left = x + width - PANEL - 1
	return left if left > grid_end else None


def draw(canvas, x, width, grid_end, y, rows, value, glyph, cap):
	"""Paint the selected colour and its hex beside the grid; no-op if narrow."""
	left = panel_x(x, width, grid_end)
	if left is None:
		return
	colour = palette.prefix(fg=value, cap=cap)
	for row in range(rows):
		canvas.draw_text(left, y + row, glyph * PANEL, colour)
	canvas.draw_text(left, y + rows, truncate(value, PANEL),
					 palette.prefix(fg="fg", bg="bg-inside", cap=cap))
