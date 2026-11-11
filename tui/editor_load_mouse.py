# Editor Load-modal mouse: a row press or double opens that theme
"""
			EDITOR LOAD MOUSE
			=================
The Load popup's mouse half, split out of `tui.editor_mouse` so the pane
router stays inside its file budget. It owns nothing else: the click tracker
still lives on the editor, the row click on the `ListBox`, and the load flow
(validation, the dirty confirm, the engine write) in `tui.editor_store` via
`tui.editoractions.load_key`.

A press that hits a row loads it at once, exactly like Enter (`#38` item 10).
A press that misses every row only consumes the event, so an invalid row, the
dirty confirm and the popup staying open on error behave as they always did:
those decisions are `load_key`'s, not this module's.

`tui.editor_mouse` re-exports `load_mouse`, so `editor_mouse.load_mouse(...)`
and the dispatch in `tui.editor_keys` keep resolving at their old path.
"""

from . import editoractions
from .mouse import DOUBLE


def load_mouse(editor, kind, x, y, modifiers=()):
	"""Load popup: a press on a row loads it; a miss only consumes the event."""
	kind = editor.clicks.push(kind, x, y, modifiers)
	if kind not in ("press", DOUBLE) or editor.load_box is None:
		return False
	box = editor.load_box
	row = box.offset + int(y) - box.y
	hits_row = box.hit_test(x, y) and 0 <= row < len(box.items)
	if not box.click(x, y):
		return False
	if hits_row:
		return editoractions.load_key(editor, "enter")
	return True
