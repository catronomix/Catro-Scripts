# Editor overlays: the help, save and load popup painters
"""
			EDITOR OVERLAYS
			===============
The popup painters of `tui.editor`: the shared `surface()` box (filled and
framed at an explicit origin), the centred `_overlay()` built on it, and the
three overlays drawn on top of the frame - the F1 help page, the Save prompt
with its filename field and inline error, and the Load list with its hint row.

They live apart from the band painters in `tui.editorpaint` because they are a
separate concern: a popup owns a rectangle of its own, repaints it whole and
reports that rectangle back so the incremental frame can erase it. `editor`
re-exports these four names, so `editorpaint._draw_save(...)` and the old
attribute paths keep resolving. This module imports `editorviews` and `palette`
only, never `editorpaint`.

All colour goes through `palette.prefix()`, so the overlay inherits the four
levels and three themes like the rest of the editor.
"""

from . import editorviews, palette
from .text import truncate


def surface(canvas, cap, x, y, width, height, title=None):
	"""A popup surface at an explicit origin; returns (x, y, width, height).

	The shared seam for a bordered block that owns its rectangle: the fill
	first (so the box hides what is behind it), then the frame. `_overlay()`
	centres one; the colour picker places its own.
	"""
	editorviews.fill_rect(canvas, x, y, width, height, cap=cap)
	editorviews.frame(canvas, x, y, width, height, title, cap)
	return x, y, width, height


def _overlay(canvas, cap, width, height, title):
	"""A centred surface box; returns its (x, y, width, height)."""
	width = min(max(20, width), canvas.width - 2)
	height = min(max(4, height), canvas.height - 2)
	x = max(1, (canvas.width - width) // 2)
	y = max(1, (canvas.height - height) // 2)
	return surface(canvas, cap, x, y, width, height, title)


def _draw_help(editor, canvas, cap):
	width = min(64, canvas.width - 2)
	x, y, width, height = _overlay(canvas, cap, width,
								   len(editorviews.HELP_LINES) + 2,
								   "Help - F1/Esc closes")
	for row, line in enumerate(editorviews.HELP_LINES):
		canvas.draw_text(x + 2, y + 1 + row, truncate(line, width - 4),
						 palette.prefix(fg="fg", bg="surface", cap=cap))
	return x, y, width, height


def _draw_save(editor, canvas, cap):
	x, y, width, height = _overlay(canvas, cap, 46, 6, "Save theme")
	canvas.draw_text(x + 2, y + 2, "name",
					 palette.prefix(fg="muted", bg="surface", cap=cap))
	editor.save_field.x, editor.save_field.y = x + 8, y + 2
	editor.save_field.width = max(6, width - 10)
	editor.save_field.cap = editor.cap
	editor.save_field.draw(canvas, focused=True)
	note = ".json is added; Enter saves, Esc cancels"
	canvas.draw_text(x + 2, y + 3, truncate(note, width - 4),
					 palette.prefix(fg="muted", bg="surface", cap=cap))
	if editor.save_field.error:
		canvas.draw_text(x + 2, y + 4, truncate(editor.save_field.error,
												width - 4),
						 palette.prefix(fg="error", bg="surface", cap=cap))
	return x, y, width, height


def _draw_load(editor, canvas, cap):
	height = min(14, 4 + len(editor.load_box.items))
	x, y, width, _ = _overlay(canvas, cap, 56, height, "Load theme")
	editor.load_box.x, editor.load_box.y = x + 2, y + 2
	editor.load_box.width = max(10, width - 4)
	editor.load_box.cap = editor.cap
	editor.load_box.draw(canvas, focused=True)
	hint = "Enter loads, Esc cancels - ! marks an unreadable file"
	canvas.draw_text(x + 2, y + height - 2, truncate(hint, width - 4),
					 palette.prefix(fg="muted", bg="surface", cap=cap))
	return x, y, width, height
