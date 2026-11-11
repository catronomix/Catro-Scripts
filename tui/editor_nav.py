# Editor navigation: the look tables, the panel/button captions and the help copy
"""
			EDITOR NAVIGATION
			==================
The label half of `tui.editor`: the three previews and their user-facing
selectors, the panel and button captions the key router and the painter share,
and the two help blocks.

Pure data plus three string helpers - no imports, no canvas, no palette - so
`tui.editorviews` can re-export every name and stays the fan-in leaf: `editor`,
`editorpaint` and `editoractions` import `editorviews`, never this module, and
this module imports nothing at all.

The look ids are the document keys (`default`, `contrast-light`,
`contrast-dark`); the labels are what the header band and the Load popup show.
`LOOK_ORDER` is also the Left/Right cycle order, so the preview titles and the
selection ring cannot drift apart.
"""

# The three previews, in the order Left/Right moves through them.
LOOK_ORDER = ("default", "contrast-light", "contrast-dark")
LOOK_LABELS = {"default": "soft", "contrast-light": "light",
			   "contrast-dark": "dark"}

# Editor chrome shared by the key router, the painter and the action popups.
PANELS = ("Properties", "Colours", "Actions")
BUTTONS = ("Save", "Load", "Quit")
HELP_LINE = "Tab panel  <-/-> look  Enter edit  ^S save  F1 help  Q quit"
HELP_LINES = (
	"THEME EDITOR",
	"",
	"Tab / Shift-Tab   cycle Properties, Colours, Actions",
	"Left / Right      select the look under edit",
	"Up / Down         move inside the focused panel",
	"Enter             edit a property, open the picker, press a button",
	"Ctrl-S            save as themes/<name>.json",
	"F1 / Esc          this help",
	"Delete / Q        quit (asks when unsaved)",
	"",
	"Wheel or PageUp/PageDown scrolls the focused panel.",
)


def look_label(look_id):
	"""User-facing selector for one look id (`default` -> `soft`)."""
	return LOOK_LABELS.get(look_id, "soft")


def preview_title(document, look_id):
	"""`<display> - <selector>` for one preview's header band."""
	display = str(document.get("display") or document.get("name") or "theme")
	return "{} - {}".format(display, look_label(look_id))


def preview_titles(document):
	"""One title per preview, in Left/Right order."""
	return [preview_title(document, look_id) for look_id in LOOK_ORDER]
