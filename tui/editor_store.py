# Editor store: the Save and Load popups over the theme engine
"""
			EDITOR STORE
			============
The persistence half of `tui.editor`: the Save popup (filename field, slug
validation, overwrite confirm, atomic write and `theme.ini` update), the Load
popup (theme list with invalid rows and a dirty confirm), opening a document
and the y/n confirm that answers quit / overwrite / discard-load.

Nothing here paints or routes keys on its own: each function takes the editor
and returns whether it consumed the token, exactly like the pane actions in
`tui.editoractions`, which re-exports these names. The split is a boundary, not
a refactor: pane editing lives in `editoractions`, and this module owns every
path that reads or writes `themes/<name>.json` or `theme.ini`. All writes go
through `theme_engine`, whose seams tests already redirect.
"""

import copy

from . import editorviews, theme_engine, widgets


# -- Save popup ---------------------------------------------------------------

def save_prompt(editor):
	"""Open the Save popup; returns the preseeded, editable filename."""
	editor.prompt = "save"
	editor.save_field = widgets.TextField(
		0, 0, str(editor.document.get("name") or ""), width=28,
		validator=editorviews.valid_slug, cap=editor.cap)
	editor.save_field.begin()
	editor.message = ("info", "save as themes/<name>.json - Enter saves")
	return editor.save_field.value


def save_key(editor, token):
	"""Route one key through the Save popup; Enter commits, Esc cancels."""
	if token == "esc":
		editor.prompt, editor.save_field = None, None
		editor.message = ("info", "save cancelled")
		return True
	editor.save_field.key(token)
	if token == "enter" and not editor.save_field.editing:
		slug = editorviews.slug_of(editor.save_field.value)
		editor.save_field, editor.prompt = None, None
		commit_save(editor, slug)
	elif editor.save_field.error:
		editor.message = ("error", editor.save_field.error)
	return True


def commit_save(editor, slug, overwrite=False):
	"""Validate, confirm an existing different file, then save atomically."""
	if not slug:
		editor.message = ("error", "a theme needs a name")
		return False
	target = theme_engine.themes_dir() / "{}.json".format(slug)
	if not overwrite and target.exists() and slug != editor.document.get("name"):
		editor.prompt, editor.pending = "overwrite", slug
		editor.message = ("warn", "{} exists - overwrite? y/n".format(
			target.name))
		return False
	document = copy.deepcopy(editor.document)
	document["name"] = slug
	try:
		path = theme_engine.save_theme(document, overwrite=True)
	except theme_engine.ThemeError as exc:
		editor.message = ("error", str(exc))
		return False
	editor.document, editor.dirty = document, False
	written = theme_engine.set_selection(name=slug)
	editor.message = ("ok", "saved {} (theme.ini {})".format(
		path, "updated" if written else "not writable"))
	return True


# -- Load popup ---------------------------------------------------------------

def load_popup(editor):
	"""Open the Load popup; returns the rows it lists (invalid ones marked)."""
	editor.clicks.reset()
	editor.entries = editorviews.theme_entries()
	labels = [entry["label"] for entry in editor.entries] or ["(no themes yet)"]
	selected = next((index for index, entry in enumerate(editor.entries)
					 if entry["active"]), 0)
	editor.load_box = widgets.ListBox(0, 0, labels, width=50,
									  height=min(12, len(labels)),
									  selected=selected, cap=editor.cap)
	editor.prompt = "load"
	editor.message = ("info", "load theme - Enter loads, Esc cancels")
	return labels


def load_key(editor, token):
	"""Route one key through the Load popup; Enter loads, Esc cancels."""
	if token == "esc":
		editor.prompt, editor.load_box = None, None
		editor.message = ("info", "load cancelled")
		return True
	if token != "enter":
		editor.load_box.key(token)
		return True
	if not editor.entries:
		editor.message = ("warn", "no themes to load")
		return True
	entry = editor.entries[editor.load_box.selected]
	if entry["error"]:
		editor.message = ("error", "cannot load {}: {}".format(
			entry["slug"], entry["error"]))
		return True
	editor.prompt, editor.pending = None, entry["slug"]
	if editor.dirty:
		editor.prompt = "discard-load"
		editor.message = ("warn", "Discard changes? y/n")
	else:
		open_document(editor, entry["slug"])
	return True


def open_document(editor, slug):
	"""Load one theme, switch the look and select it in `theme.ini`."""
	try:
		document = theme_engine.load_theme(slug)
	except theme_engine.ThemeError as exc:
		editor.message = ("error", str(exc))
		return False
	editor.document, editor.dirty = document, False
	editor.clicks.reset()
	selected, selector = theme_engine.selection()
	look_id = theme_engine.SELECTORS.get(selector, "default")
	editor.look_index = (editorviews.LOOK_ORDER.index(look_id)
						 if document.get("name") == selected else 0)
	written = theme_engine.set_selection(name=slug)
	editor._layout()
	editor.message = ("ok", "loaded {} (theme.ini {})".format(
		slug, "updated" if written else "not writable"))
	return True


# -- y/n confirms -------------------------------------------------------------

def confirm_key(editor, token):
	"""Answer the quit / overwrite / discard-load prompt; anything else is a no."""
	yes = token in ("y", "Y")
	no = token in ("n", "N", "esc")
	if editor.prompt == "quit":
		if yes:
			editor.prompt, editor.closed = None, True
		elif no:
			editor.prompt = None
			editor.message = ("info", "changes kept")
		return True
	if editor.prompt == "overwrite":
		if yes:
			editor.prompt = None
			return commit_save(editor, editor.pending, overwrite=True)
		if no:
			editor.prompt = None
			editor.message = ("info", "not saved")
		return True
	if yes:
		editor.prompt = None
		return open_document(editor, editor.pending)
	if no:
		editor.prompt = None
		editor.message = ("info", "load cancelled")
	return True
