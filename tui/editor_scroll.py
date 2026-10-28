# Editor pane scrolling: wheel selection movement and the overflow marker
"""
			EDITOR SCROLL
			=============
The scrolling half of `tui.editor`'s Properties/Colours panes, split out of
`tui.editor_mouse` and `tui.editorpaint` so both stay inside their budgets.

`scroll()` is the wheel's model: it moves the pane *selection* by the delta and
lets the window follow through `ThemeEditor._window` - the same rule the arrow
keys use - because the next paint re-derives the offset from the index, so an
offset-only delta would be discarded. `mark_overflow()` is the matching view: a
one-column scrollbar on the pane's right inner edge when the key list is longer
than the visible band. It imports `editorviews`, `theme_engine` and `widgets`
only; never `editor`, `editor_mouse` or `editorpaint`.
"""

from . import editorviews, theme_engine, widgets


def scroll(editor, panel, delta):
	"""Move the Properties (3) or Colours (4) selection by `delta` rows."""
	keys = editorviews.PROPERTY_KEYS if panel == 3 else theme_engine.PALETTE_KEYS
	visible = editor._visible(panel)
	index_attr, offset_attr = (("property_index", "property_offset")
							   if panel == 3
							   else ("colour_index", "colour_offset"))
	index = max(0, min(len(keys) - 1, getattr(editor, index_attr) + delta))
	offset = editor._window(index, getattr(editor, offset_attr), len(keys),
							visible)
	setattr(editor, index_attr, index)
	setattr(editor, offset_attr, offset)


def mark_overflow(canvas, editor, panel, cap):
	"""A scrollbar column on the right edge when the pane hides rows.

	It reuses `widgets.ScrollBar`, so the glyphs come from chrome's
	`scrollbar_style` table (with its ASCII fallback) and the thumb position
	from the same offset `_window` just clamped - no second marker table.
	"""
	rect = editor.rects[panel]
	rows, visible = len(editor._rows(panel)), editor._visible(panel)
	if rows <= visible:
		return
	offset = editor.property_offset if panel == 3 else editor.colour_offset
	widgets.ScrollBar(rect[0] + rect[2] - 2, rect[1] + 1, visible,
					  total=rows, offset=offset, cap=cap).draw(canvas)
