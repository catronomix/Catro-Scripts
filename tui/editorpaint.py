# Editor painter: the frame, the three panels, overlays and the status line
"""
			EDITOR PAINTER
			==============
The drawing half of `tui.editor`, split out so the editor stays inside the
`tui/` file budget. Every function takes the editor, paints one part of the
frame and returns nothing; `draw()` composes them in order (title, previews,
panels, status, then help/save/load/picker overlays on top).

The three popup overlays - help, Save and Load, with the centred box they share
- live in `tui.editor_overlays` and are re-exported here, so
`editorpaint._draw_save(...)` and the old attribute paths keep resolving. The
band painters (title, the three panels, status and the run-splitting `_blit`)
stay in this module.

All colour comes from `palette.prefix()`/`chrome.status()`, so the editor emits
no private ANSI; the preview shell itself lives in `tui.editorviews`.
"""

from . import caps, chrome, editor_scroll, editorviews, palette, theme_engine, widgets
from .editor_overlays import (_draw_help, _draw_load, _draw_save,  # noqa: F401
							  _overlay)
from .text import pad, truncate
from .widgetkit import cells


def draw(editor, full=True):
	"""Paint one frame onto the injected canvas; returns `editor`.

	`full` is a *terminal* decision, not a canvas one: the grid is always
	repainted in full, so the buffer a diff compares against is complete. On an
	incremental frame the only cells that need erasing are the overlay a
	previous frame left behind (an overlay repaints its own box), because every
	other painter writes the whole band it owns.
	"""
	canvas = editor.canvas
	if canvas is None:
		return editor
	# One paint, one colour resolution: `begin_frame` keeps the look palette,
	# the selection and the properties from being re-resolved per cell.
	palette.begin_frame()
	try:
		_paint(editor, canvas, full)
	finally:
		palette.end_frame()
	return editor


def _paint(editor, canvas, full):
	cap = editor.cap or caps.detect()
	previous = getattr(editor, "_overlay_rect", None)
	if full:
		editorviews.clear(canvas)
	elif previous is not None:
		editorviews.blank_rect(canvas, *previous)
	editor._overlay_rect = None
	if widgets.small_terminal(canvas.width, canvas.height):
		editorviews.notice(canvas, cap)
		return editor
	if (canvas.width, canvas.height) != getattr(editor, "_layout_size", None):
		editor._layout()
	_draw_title(editor, canvas, cap)
	for index, look_id in enumerate(editorviews.LOOK_ORDER):
		rect = editor.rects[index]
		editorviews.draw_preview(
			canvas, rect[0], rect[1], rect[2], rect[3], editor.document,
			look_id, cap=cap, active=index == editor.look_index)
	_draw_properties(editor, canvas, cap)
	_draw_colours(editor, canvas, cap)
	_draw_actions(editor, canvas, cap)
	_draw_status(editor, canvas, cap)
	if editor.help:
		editor._overlay_rect = _draw_help(editor, canvas, cap)
	if editor.prompt == "save":
		editor._overlay_rect = _draw_save(editor, canvas, cap)
	if editor.prompt == "load":
		editor._overlay_rect = _draw_load(editor, canvas, cap)
	if editor.picker is not None:
		# A resize swaps the editor's canvas; retarget the popup so it is
		# painted again on the new grid instead of the discarded one.
		editor.picker.canvas = canvas
		editor.picker.cap = editor.cap
		editor.picker.draw()
		editor._overlay_rect = editor.picker.rect()
	return editor


def _draw_title(editor, canvas, cap):
	name = editor.document.get("name") or "theme"
	display = editor.document.get("display") or name
	dirty = " * unsaved" if editor.dirty else ""
	text = " Theme editor - {} ({}){}".format(display, name, dirty)
	canvas.draw_text(0, 0, pad(truncate(text, canvas.width), canvas.width),
					 palette.prefix(fg="header-fg", bg="header-bg", bold=True,
									cap=cap))


def _draw_properties(editor, canvas, cap):
	x, y, width, height = editor.rects[3]
	editorviews.frame(canvas, x, y, width, height, "Properties", cap,
					  active=editor.focus == 0)
	editorviews.fill_rect(canvas, x + 1, y + 1, width - 2, height - 2, cap=cap)
	keys = editorviews.PROPERTY_KEYS
	visible = editor._visible(3)
	editor.property_offset = editor._window(
		editor.property_index, editor.property_offset, len(keys), visible)
	for row, key in enumerate(keys[editor.property_offset:
								   editor.property_offset + visible]):
		index = editor.property_offset + row
		top = y + 1 + row
		focused = editor.focus == 0 and index == editor.property_index
		canvas.draw_text(x + 2, top, pad(key, editorviews.PROPERTY_WIDTH),
						 widgets.focus_prefix(focused, cap)
						 or palette.prefix(fg="fg", bg="bg-inside", cap=cap))
		field = editor._field_for(key)
		field.x, field.y = x + 2 + editorviews.PROPERTY_WIDTH, top
		field.width = max(4, width - editorviews.PROPERTY_WIDTH - 4)
		field.draw(canvas, focused=focused)
	editor_scroll.mark_overflow(canvas, editor, 3, cap)


def _draw_colours(editor, canvas, cap):
	x, y, width, height = editor.rects[4]
	title = "Colours - {}".format(
		editorviews.look_label(editor._current_look()))
	editorviews.frame(canvas, x, y, width, height, title, cap,
					  active=editor.focus == 1)
	editorviews.fill_rect(canvas, x + 1, y + 1, width - 2, height - 2, cap=cap)
	colours = editor._look_colours()
	keys = theme_engine.PALETTE_KEYS
	visible = editor._visible(4)
	editor.colour_offset = editor._window(
		editor.colour_index, editor.colour_offset, len(keys), visible)
	for row, key in enumerate(keys[editor.colour_offset:
								   editor.colour_offset + visible]):
		index = editor.colour_offset + row
		top = y + 1 + row
		focused = editor.focus == 1 and index == editor.colour_index
		canvas.draw_text(x + 2, top, "\u25a0\u25a0" if cap.unicode else "##",
						 palette.prefix(fg=colours.get(key), bg="bg-inside",
										cap=cap))
		ink = (widgets.focus_prefix(focused, cap)
			   or palette.prefix(fg="fg", bg="bg-inside", cap=cap))
		text = pad(key, editorviews.COLOUR_WIDTH) + " " + str(colours.get(key, ""))
		canvas.draw_text(x + 5, top, truncate(text, max(1, width - 7)), ink)
	editor_scroll.mark_overflow(canvas, editor, 4, cap)



def _draw_actions(editor, canvas, cap):
	rect = editor.rects[5]
	editorviews.frame(canvas, rect[0], rect[1], rect[2], rect[3],
					  "Actions", cap, active=editor.focus == 2)
	editorviews.fill_rect(canvas, rect[0] + 1, rect[1] + 1, rect[2] - 2,
						  rect[3] - 2, cap=cap)
	for index, button in enumerate(editor.buttons):
		button.cap = editor.cap
		button.draw(canvas, focused=editor.focus == 2
					and index == editor.button_index)


def _draw_status(editor, canvas, cap):
	kind, text = editor.message
	# Both status rows are cleared first: on the incremental path a shorter
	# message (or losing the `* unsaved` prefix) would otherwise leave the tail
	# of the previous text behind, because nothing else paints these rows.
	editorviews.blank_rect(canvas, 1, canvas.height - 2, canvas.width - 2, 2)
	_blit(canvas, 1, canvas.height - 2,
		  chrome.status(kind, text, cap=cap), canvas.width - 2)
	hint = editorviews.HELP_LINE
	if editor.dirty:
		hint = "* unsaved  " + hint
	canvas.draw_text(1, canvas.height - 1, truncate(hint, canvas.width - 2),
					 palette.prefix(fg="fg-muted", cap=cap))


def _blit(canvas, x, y, styled, width):
	"""Draw a styled line run by run, keeping each run's leading colour.

	`chrome.status()` paints its marker and its text separately, so splitting
	on the palette reset preserves that: the alarm colour stays on the marker
	while the message keeps the body colour.
	"""
	column = 0
	for run in str(styled).split(palette.RESET):
		colour, visible = cells(run)
		if not visible or column >= width:
			continue
		visible = truncate(visible, width - column)
		canvas.draw_text(x + column, y, visible, colour)
		column += len(visible)
