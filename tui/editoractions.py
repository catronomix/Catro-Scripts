# Editor actions: property draft editing, colour picker and mouse routing
"""
			EDITOR ACTIONS
			==============
The pane-editing half of `tui.editor`: the Properties draft edit (Enter keeps
the old value as the Esc target, arrows/space cycle it, Enter commits), the
colour-picker wiring and the mouse/wheel routing.

Every function takes the editor and returns whether it consumed the token, so
`ThemeEditor.handle()` stays a short dispatcher while one editor object keeps
the whole session state. Nothing here touches a terminal and nothing here
writes `themes/` or `theme.ini`: that half - the Save/Load popups, opening a
document and the y/n confirms - lives in `tui.editor_store` and is re-exported
below, so `editoractions.save_prompt(...)` keeps resolving. Keep the boundary
sharp: pane interaction changes land here, persistence changes land there.
"""

from . import colorpicker, editorviews, theme_engine
from .editor_store import (commit_save, confirm_key, load_key,  # noqa: F401
						   load_popup, open_document, save_key, save_prompt)


# -- property draft editing ---------------------------------------------------

def begin_property_edit(editor):
	"""Enter on Properties: keep the old value as the Esc cancel target."""
	key = editorviews.PROPERTY_KEYS[editor.property_index]
	before = editor.document["properties"][key]
	field = editor._property_field(key)
	editor.edit = {"key": key, "before": before, "field": field}
	editor.message = ("info", "{} = {} - arrows change, Enter commits, "
					  "Esc cancels".format(key, editor._field_value(field)))
	return True


def edit_key(editor, token):
	"""Draft edit: arrows/space change it, Enter commits, Esc restores."""
	if token == "esc":
		key = editor.edit["key"]
		before = editor.edit["before"]
		editor.edit = None
		editor.message = ("info", "{} = {} (unchanged)".format(key, before))
		return True
	if token == "enter":
		return commit_property(editor)
	field = editor.edit["field"]
	select = hasattr(field, "selected")
	if token in ("left", "up", "space"):
		if select:
			field.cycle(-1)
		else:
			field.toggle()
	elif token in ("right", "down"):
		if select:
			field.cycle(1)
		else:
			field.toggle()
	else:
		return True
	editor.message = ("warn", "{} -> {} (Enter commits, Esc cancels)".format(
		editor.edit["key"], editor._field_value(field)))
	return True


def commit_property(editor):
	"""Enter while editing: adopt the draft and mark the document dirty."""
	edit, editor.edit = editor.edit, None
	key = edit["key"]
	value = editor._field_value(edit["field"])
	if value != edit["before"]:
		editor.document["properties"][key] = value
		editor.dirty = True
		editor.message = ("ok", "{} = {}".format(key, value))
	else:
		editor.message = ("info", "{} = {} (unchanged)".format(key, value))
	return True


# -- colour picker ------------------------------------------------------------

def open_picker(editor):
	"""Open the picker on the selected palette key of the current look."""
	key = theme_engine.PALETTE_KEYS[editor.colour_index]
	colours = editor._look_colours()
	x = y = 1
	if editor.canvas is not None:
		width, height = colorpicker.WIDTH, colorpicker.HEIGHT
		x = max(1, (editor.canvas.width - width) // 2)
		y = max(1, (editor.canvas.height - height) // 2)
	editor.picker = colorpicker.ColorPicker(
		editor.canvas, colours[key], x=x, y=y, cap=editor.cap, colours=colours)
	editor.message = ("info", "{} - Enter commits, Esc cancels".format(key))
	return editor.picker


def picker_key(editor, token):
	"""Feed one token to the open picker and adopt its result when it closes."""
	editor.picker.key(token)
	if not editor.picker.closed:
		return True
	value = editor.picker.result
	key = theme_engine.PALETTE_KEYS[editor.colour_index]
	if value:
		editor.document["looks"][editor._current_look()][key] = value
		editor.dirty = True
		editor.message = ("ok", "{} = {}".format(key, value))
	else:
		editor.message = ("info", "colour unchanged")
	editor.picker = None
	return True


# -- mouse --------------------------------------------------------------------

def mouse(editor, kind, x, y, modifiers=()):
	"""Wheel scrolls the hovered panel; a press selects a preview/row/button."""
	if kind.startswith("wheel-"):
		panel = editor._panel_at(x, y)
		if panel in (3, 4):
			scroll(editor, panel, -3 if kind == "wheel-up" else 3)
		return True
	if kind != "press":
		return False
	for index in range(3):
		rect = editor.rects.get(index)
		if rect and _hit(rect, x, y):
			editor.look_index = index
			return True
	panel = editor._panel_at(x, y)
	if panel == 3:
		row = editor.rects[3][1] + 1 + editor.property_offset
		if row <= y < row + editor._visible(3):
			editor.focus = 0
			editor.property_index = y - row + editor.property_offset
		return True
	if panel == 4:
		row = editor.rects[4][1] + 1 + editor.colour_offset
		if row <= y < row + editor._visible(4):
			editor.focus = 1
			editor.colour_index = y - row + editor.colour_offset
		return True
	for index, button in enumerate(editor.buttons):
		if button.hit_test(x, y):
			editor.focus, editor.button_index = 2, index
			return editor._activate()
	return False


def scroll(editor, panel, delta):
	"""Scroll the Properties (3) or Colours (4) window by `delta` rows."""
	keys = editorviews.PROPERTY_KEYS if panel == 3 else theme_engine.PALETTE_KEYS
	visible = editor._visible(panel)
	offset = editor.property_offset if panel == 3 else editor.colour_offset
	offset = max(0, min(len(keys) - visible, offset + delta))
	if panel == 3:
		editor.property_offset = offset
	else:
		editor.colour_offset = offset


def _hit(rect, x, y):
	return (rect[0] <= x < rect[0] + rect[2]
			and rect[1] <= y < rect[1] + rect[3])
