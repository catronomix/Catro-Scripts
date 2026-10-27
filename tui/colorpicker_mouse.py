# Colour picker mouse: select, drag and release on the swatch grid
"""
			COLOUR PICKER MOUSE
			===================
The mouse half of `tui.colorpicker`: a press selects the cell under the pointer
and grabs it, a drag follows the pointer (clamping past an edge to the grabbed
row) and a release drops the grab. The popup owns the grid; this module only
turns a decoded event into grid operations, so the popup's drawing and colour
model stay in one place.
"""

from .color_math import STEPS
from .mouse import DOUBLE


def mouse(picker, kind, x, y, modifiers=()):
	"""Route one decoded mouse event; a double selects the cell and commits."""
	kind = picker.clicks.push(kind, x, y, modifiers)
	if kind == DOUBLE:
		cell = picker.cell_at(x, y)
		if cell is None:
			return False
		picker.select(*cell)
		return picker.commit()
	if kind == "press":
		cell = picker.cell_at(x, y)
		if cell is None:
			return False
		picker._grab = cell
		picker.select(*cell)
		return True
	if kind == "drag" and picker._grab is not None:
		cell = picker.cell_at(x, y)
		if cell is not None:
			picker._grab = cell
			picker.select(*cell)
			return True
		# Dragging past the edge clamps to the grabbed row's last cell.
		from .colorpicker import CELL  # the grid's cell width, owned there
		offset = min(CELL * STEPS - 1, max(0, int(x) - picker.grid_x))
		picker._grab = (picker.row, offset // CELL)
		picker.select(picker.row, offset // CELL)
		return True
	if kind == "release":
		picker._grab = None
		return True
	return False
