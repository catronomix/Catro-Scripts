# Editor Load-modal mouse: a row press or double opens that theme
"""
			EDITOR LOAD MOUSE
			=================
The Load popup's mouse half, split out of `tui.editor_mouse` so the pane
router stays inside its file budget. It owns nothing else: the click tracker
still lives on the editor, the row click on the `ListBox`, and the load flow
(validation, the dirty confirm, the engine write) in `tui.editor_store` via
`tui.editoractions.load_key`.

`tui.editor_mouse` re-exports `load_mouse`, so `editor_mouse.load_mouse(...)`
and the dispatch in `tui.editor_keys` keep resolving at their old path.
"""

from . import editoractions
from .mouse import DOUBLE


def load_mouse(editor, kind, x, y, modifiers=()):
	"""Load popup: a press selects a row, a double opens it (Enter's flow)."""
	kind = editor.clicks.push(kind, x, y, modifiers)
	if kind not in ("press", DOUBLE) or editor.load_box is None:
		return False
	if not editor.load_box.click(x, y):
		return False
	if kind == DOUBLE:
		return editoractions.load_key(editor, "enter")
	return True
