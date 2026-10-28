# Preview row plan: the content rows of a kitchen-sink preview and their text
"""
			PREVIEW ROW PLAN
			===============
The rows a kitchen-sink preview paints between its frame and its progress bar,
as data: `rows()` returns the `(kind, palette role, background role)` triples in
display order and `texts()` the sample string each kind carries. Kept out of
`tui.editor_preview` so the painter stays inside its file budget and the plan
can be read - and dropped from - in one place.

The plan is the same for every look; only the colours differ. The progress bar
is not part of the plan: `tui.editor_preview` always keeps the last inner row
for it.
"""

from .preview_texts import texts, title_label  # noqa: F401  (re-exported)


def rows(inner_h):
	"""The content rows that fit an `inner_h`-row band, in display order.

	A short band gives up the table's closing rule first, then its top rule,
	then the second body row, so the bar and the buttons survive.
	"""
	plan = [("rule_top", "border-fg", "border-bg"),
			("thead", "header-fg", "bg-inside"),
			("trow_a", "fg", "bg"),
			("trow_b", "fg", "bg-stripe"),
			("rule_bot", "border-fg", "border-bg"),
			("buttons", None, None),
			("field", "fg", "bg-inside"),
			("look", "fg", "bg-inside"),
			("menu", "fg", "bg-inside"),
			("modal_t", "header-fg", "bg-inside"),
			("modal_b", "fg", "bg-inside"),
			("ready", "fg-success", "bg-inside")]
	# One row is reserved for the progress bar; the bar is not in the plan.
	while len(plan) + 1 > inner_h:
		drop = next((kind for kind in ("rule_bot", "rule_top", "trow_b",
									   "look", "field", "menu", "modal_b",
									   "trow_a", "modal_t", "thead",
									   "buttons", "ready")
					 if any(kind == row[0] for row in plan)), None)
		if drop is None:
			break
		plan = [row for row in plan if row[0] != drop]
	return plan
