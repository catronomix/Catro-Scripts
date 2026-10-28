# Editor mouse: press/double and wheel routing for the panes and previews
"""
			EDITOR MOUSE
			============
The mouse half of `tui.editor`: a press selects the preview, row or Action
button under the pointer; the wheel scrolls the hovered pane. A second press on
the same cell is a `double` and opens what the press selected: picker, draft or
theme (`tui.editor_keys` dispatches both, Load included, and the Load rows live
in `tui.editor_load_mouse`).
"""

from . import editoractions, editorviews, theme_engine
from .editor_load_mouse import load_mouse  # noqa: F401  (re-exported seam)
from .mouse import DOUBLE


def mouse(editor, kind, x, y, modifiers=()):
	"""Route one decoded mouse event through the session's click tracker."""
	kind = editor.clicks.push(kind, x, y, modifiers)
	panel = editor._panel_at(x, y)
	if kind.startswith("wheel-"):
		if panel in (3, 4):
			scroll(editor, panel, -3 if kind == "wheel-up" else 3)
		return True
	if kind not in ("press", DOUBLE):
		return False
	consumed = press(editor, x, y)
	if kind != DOUBLE:
		return consumed
	if panel == 3 and _select_row(editor, 3, y):
		return editoractions.begin_property_edit(editor)
	if panel == 4 and editor.picker is None and _select_row(editor, 4, y):
		return editoractions.open_picker(editor) is not None
	return consumed


def press(editor, x, y):
	"""A press selects the preview/row under the pointer or presses a button."""
	for index in range(3):
		rect = editor.rects.get(index)
		if rect and _hit(rect, x, y):
			editor.look_index = index
			return True
	panel = editor._panel_at(x, y)
	if panel in (3, 4):
		# A Colours row opens the picker on the first press; once it is open,
		# `editor_keys` routes everything to `picker_key`, so this can only
		# fire on a fresh press and never reopens or double-handles it.
		if _select_row(editor, panel, y) and panel == 4 \
				and editor.picker is None:
			return editoractions.open_picker(editor) is not None
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
	attr = "property_offset" if panel == 3 else "colour_offset"
	offset = getattr(editor, attr)
	setattr(editor, attr, max(0, min(len(keys) - visible, offset + delta)))


def _select_row(editor, panel, y):
	"""Focus that pane and select the row under the pointer, if it is a row."""
	top = editor.rects[panel][1] + 1
	offset = getattr(editor, ("property_offset", "colour_offset")[panel - 3])
	if not top <= y < top + editor._visible(panel):
		return False
	index = min(offset + y - top, len(editor._rows(panel)) - 1)
	if panel == 3:
		editor.focus, editor.property_index = 0, index
	else:
		editor.focus, editor.colour_index = 1, index
	return True


def _hit(rect, x, y):
	return (rect[0] <= x < rect[0] + rect[2]
			and rect[1] <= y < rect[1] + rect[3])
