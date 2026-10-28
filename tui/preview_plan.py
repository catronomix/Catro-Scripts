# Preview row plan: the content rows of a kitchen-sink preview and their text
"""
			PREVIEW ROW PLAN
			===============
The rows a kitchen-sink preview paints between its frame and its progress bar,
as data: `rows()` returns the `(kind, palette role)` pairs in display order and
`texts()` the sample string each kind carries. Kept out of
`tui.editor_preview` so the painter stays inside its file budget and the plan
can be read - and dropped from - in one place.

The plan is the same for every look; only the colours differ. The progress bar
is not part of the plan: `tui.editor_preview` always keeps the last inner row
for it.
"""

from .editor_nav import look_label


def rows(inner_h):
	"""The content rows that fit an `inner_h`-row band, in display order.

	A short band gives up the closing table rule first, then the table header,
	then the body rows from the top, so the bar and the buttons survive.
	"""
	plan = [("name", "border-fg"), ("alpha", "fg"), ("beta", "fg")]
	plan += [("buttons", None), ("field", "fg"), ("look", "fg"),
			 ("preview", "fg-accent"), ("menu", "fg"), ("ready", "fg-success")]
	# One row is reserved for the progress bar, so the closing table rule
	# only fits once the body plus bar plus rule fit the band.
	if inner_h > len(plan) + 1:
		plan.insert(3, ("rule", "border-fg"))
	while len(plan) + 1 > inner_h:
		drop = next((kind for kind in ("rule", "name", "alpha", "beta",
									   "buttons", "field", "look", "preview",
									   "menu", "ready")
					 if any(kind == row[0] for row in plan)), None)
		if drop is None:
			break
		plan = [row for row in plan if row[0] != drop]
	return plan


def texts(look_id, active=False):
	"""The sample text of every planned row, keyed by kind."""
	mark = " *" if active else ""
	return {
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
