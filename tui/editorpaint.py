# Editor painter: the frame, the three panels, overlays and the status line
"""
			EDITOR PAINTER
			==============
The drawing half of `tui.editor`, split out so the editor stays inside the
`tui/` file budget. Every function takes the editor, paints one part of the
frame and returns nothing; `draw()` composes them in order (title, previews,
panels, status, then help/save/load/picker overlays on top).

All colour comes from `palette.prefix()`/`chrome.status()`, so the editor emits
no private ANSI; the preview shell itself lives in `tui.editorviews`.
"""

from . import caps, chrome, editorviews, palette, theme_engine, widgets
from .text import pad, truncate
from .widgetkit import cells


def draw(editor):
	"""Paint one full frame onto the injected canvas; returns `editor`."""
	canvas = editor.canvas
	if canvas is None:
		return editor
	cap = editor.cap or caps.detect()
	editorviews.clear(canvas)
	if widgets.small_terminal(canvas.width, canvas.height):
		editorviews.notice(canvas, cap)
		return editor
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
		_draw_help(editor, canvas, cap)
	if editor.prompt == "save":
		_draw_save(editor, canvas, cap)
	if editor.prompt == "load":
		_draw_load(editor, canvas, cap)
	if editor.picker is not None:
		editor.picker.cap = editor.cap
		editor.picker.draw()
	return editor


def _draw_title(editor, canvas, cap):
	name = editor.document.get("name") or "theme"
	display = editor.document.get("display") or name
	dirty = " * unsaved" if editor.dirty else ""
	text = " Theme editor - {} ({}){}".format(display, name, dirty)
	canvas.draw_text(0, 0, pad(truncate(text, canvas.width), canvas.width),
					 palette.prefix(fg="header", bg="surface", bold=True,
									cap=cap))


def _draw_properties(editor, canvas, cap):
	x, y, width, height = editor.rects[3]
	editorviews.frame(canvas, x, y, width, height, "Properties", cap)
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
						 or palette.prefix(fg="fg", cap=cap))
		field = editor._field_for(key)
		field.x, field.y = x + 2 + editorviews.PROPERTY_WIDTH, top
		field.width = max(4, width - editorviews.PROPERTY_WIDTH - 4)
		field.draw(canvas, focused=focused)


def _draw_colours(editor, canvas, cap):
	x, y, width, height = editor.rects[4]
	title = "Colours - {}".format(
		editorviews.look_label(editor._current_look()))
	editorviews.frame(canvas, x, y, width, height, title, cap)
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
						 palette.prefix(fg=colours.get(key), cap=cap))
		ink = (widgets.focus_prefix(focused, cap)
			   or palette.prefix(fg="fg", cap=cap))
		text = pad(key, 9) + " " + str(colours.get(key, ""))
		canvas.draw_text(x + 5, top, truncate(text, max(1, width - 7)), ink)


def _draw_actions(editor, canvas, cap):
	rect = editor.rects[5]
	editorviews.frame(canvas, rect[0], rect[1], rect[2], rect[3],
					  "Actions", cap)
	for index, button in enumerate(editor.buttons):
		button.x, button.y = rect[0] + 2, rect[1] + 1 + 2 * index
		button.cap = editor.cap
		button.draw(canvas, focused=editor.focus == 2
					and index == editor.button_index)


def _draw_status(editor, canvas, cap):
	kind, text = editor.message
	_blit(canvas, 1, canvas.height - 2,
		  chrome.status(kind, text, cap=cap), canvas.width - 2)
	hint = editorviews.HELP_LINE
	if editor.dirty:
		hint = "* unsaved  " + hint
	canvas.draw_text(1, canvas.height - 1, truncate(hint, canvas.width - 2),
					 palette.prefix(fg="muted", cap=cap))


def _overlay(canvas, cap, width, height, title):
	"""A centred surface box; returns its (x, y, width, height)."""
	width = min(max(20, width), canvas.width - 2)
	height = min(max(4, height), canvas.height - 2)
	x = max(1, (canvas.width - width) // 2)
	y = max(1, (canvas.height - height) // 2)
	editorviews.fill_rect(canvas, x, y, width, height, cap=cap)
	editorviews.frame(canvas, x, y, width, height, title, cap)
	return x, y, width, height


def _draw_help(editor, canvas, cap):
	width = min(64, canvas.width - 2)
	x, y, width, height = _overlay(canvas, cap, width,
								   len(editorviews.HELP_LINES) + 2,
								   "Help - F1/Esc closes")
	for row, line in enumerate(editorviews.HELP_LINES):
		canvas.draw_text(x + 2, y + 1 + row, truncate(line, width - 4),
						 palette.prefix(fg="fg", bg="surface", cap=cap))


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
