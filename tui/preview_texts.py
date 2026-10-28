# Preview texts: the sample strings and frame title of a kitchen-sink preview
"""
			PREVIEW TEXTS
			=============
The strings a preview paints, split out of `tui.preview_plan` for budget
headroom: `texts()` is the sample text of every planned row keyed by kind, and
`title_label()` pads the frame title per the document's `header_align`.

Pure data and string arithmetic: no canvas, no palette, no stream.
"""

from .editor_nav import look_label


def texts(look_id, active=False):
	"""The sample text of every planned row, keyed by kind."""
	mark = " *" if active else ""
	return {
		"header": " NAME            VALUE",
		"name": " name            value",
		"alpha": " alpha            yes",
		"beta": " beta             no",
		"field": " field: hello___",
		"look": " look  < {} >{}".format(look_label(look_id), mark),
		"preview": "> 1. preview",
		"menu": " 2. menu row",
		"ready": "[ok] ready",
	}


def title_label(title, width, properties):
	"""The frame title, padded so it sits per the document's `header_align`.

	`tui.editorframe` wraps the string in one space on each side and draws it
	two cells in from the corners; the leading padding here is what moves it,
	so the frame keeps one formula for every alignment.
	"""
	room = width - 5 - len(title)
	if room < 0:
		return ""
	align = str(properties.get("header_align", "left"))
	if align == "right":
		return " " * room + title
	if align == "center":
		return " " * (room // 2) + title
	return title
