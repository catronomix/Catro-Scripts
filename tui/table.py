# Styled tables, banners and key/value blocks
"""
			TABLE AND BLOCK RENDERING
			==========================
One renderer for the house table: Unicode box borders at a terminal, and one
TAB-separated record per line when the stream is a pipe (`cap.plain`), where
`catro-scripts list | cut -f2` becomes a supported use. `widths=` forces exact
columns (no measuring, no terminal fitting) so a caller can keep a fixed layout
and therefore exact bytes; such a caller normally passes `truncate=False` and
applies its own truncation rule. Rendering never prints, never raises on ragged
rows (short rows pad, extra cells are dropped) and never truncates plain
output. Cell values are str()-ified and their newlines flattened to spaces.

The frame alphabets and `glyphs_for()` live in `tui.table_glyphs` and are
re-exported here, so `tui.table.glyphs_for()`/`BORDER_GLYPHS` keep resolving.
"""

from . import caps, palette
from . import table_rows
from .table_glyphs import (ASCII_GLYPHS, BORDER_GLYPHS, DOUBLE_GLYPHS,  # noqa: F401
						   HEAVY_GLYPHS, SPACE_GLYPHS, SQUARE_GLYPHS,
						   UNICODE_GLYPHS, glyphs_for)
from .text import display_width, pad

MIN_COLUMN = 4


def render_table(headers, rows, *, box=None, zebra=None, truncate=True,
				 widths=None, cap=None, theme=None):
	"""Render a table; returns text without a trailing newline.

	`box`/`zebra` default to `None` = "ask the active theme": `table_style`
	picks the frame (`box`, `borderless` or `compact`) and `table_zebra` the row
	shading. An explicit caller argument always wins. `widths` forces exact
	column widths and skips both auto-sizing and terminal fitting, which is how
	`list` keeps its fixed 4/25/10/50 layout (and its exact bytes); a caller with
	its own truncation rule passes `truncate=False` and pre-truncates.
	"""
	cap = cap or caps.detect()
	theme = palette.theme(theme)
	props = palette.properties()
	table_style = props.get("table_style", "box")
	compact = box is None and table_style == "compact"
	if box is None:
		box = table_style != "borderless"
	if zebra is None:
		zebra = bool(props.get("table_zebra", True))
	labels = [_flat(value) for value in headers]
	data = [_normalise(row, len(labels)) for row in rows]
	if not labels:
		return ""

	if cap.plain:
		lines = ["\t".join(labels)]
		lines += ["\t".join(cells) for cells in data]
		return "\n".join(lines)

	if widths is None:
		widths = _column_widths(labels, data)
		if cap.width:
			widths = _fit(widths, cap.width)
	else:
		widths = _explicit_widths(widths, len(labels))
	glyphs = glyphs_for(cap)
	if not box:
		return "\n".join(table_rows.bare_rows(labels, data, widths, cap, theme,
											  zebra))
	if compact:
		lines = [table_rows.bare_line(labels, widths, cap, theme,
									  fg="header-fg", bold=True)]
		lines.append(table_rows.span_rule(glyphs, widths, cap, theme))
		for index, cells in enumerate(data):
			lines.append(table_rows.bare_line(
				cells, widths, cap, theme,
				bg=table_rows.zebra_bg(index, zebra)))
		lines.append(table_rows.span_rule(glyphs, widths, cap, theme))
		return "\n".join(lines)

	lines = [table_rows.rule(glyphs, widths, "tl", "tm", "tr", cap, theme)]
	lines.append(table_rows.header_row(glyphs, widths, labels, cap, theme))
	lines.append(table_rows.rule(glyphs, widths, "ml", "mm", "mr", cap, theme))
	for index, cells in enumerate(data):
		lines.append(table_rows.row(glyphs, widths, cells, cap, theme,
									bg=table_rows.zebra_bg(index, zebra),
									truncate_cells=truncate))
	lines.append(table_rows.rule(glyphs, widths, "bl", "bm", "br", cap, theme))
	return "\n".join(lines)


def print_table(headers, rows, **kw):
	"""Print `render_table(...)` to stdout."""
	print(render_table(headers, rows, **kw))


def key_values(title, pairs, *, cap=None, theme=None):
	"""Aligned key/value block, or `key<TAB>value` lines when piped."""
	cap = cap or caps.detect()
	items = [(_flat(key), _flat(value)) for key, value in pairs]
	lines = []
	if cap.plain:
		if title:
			lines.append(_flat(title))
		lines.extend("{}\t{}".format(key, value) for key, value in items)
		return "\n".join(lines)
	if title:
		lines.append(palette.style(_flat(title), fg="header-fg", bold=True,
								   cap=cap, theme=theme))
	width = max([display_width(key) for key, _ in items] or [0])
	for key, value in items:
		lines.append("{}  {}".format(
			palette.style(pad(key, width), fg="fg-muted", cap=cap, theme=theme),
			palette.style(value, fg="fg", cap=cap, theme=theme)))
	return "\n".join(lines)


def banner(title, width=60, *, cap=None, theme=None):
	"""Boxed, centred title - the keygen/help header shape."""
	cap = cap or caps.detect()
	label = _flat(title)
	if cap.plain:
		return label
	glyphs = glyphs_for(cap)
	inner = max(int(width), display_width(label) + 4)
	left = (inner - display_width(label)) // 2
	right = inner - display_width(label) - left
	return "\n".join([
		palette.style(glyphs["tl"] + glyphs["h"] * inner + glyphs["tr"],
					  fg="border-fg", cap=cap, theme=theme),
		palette.style(glyphs["v"] + " " * left + label + " " * right + glyphs["v"],
					  fg="header-fg", bold=True, cap=cap, theme=theme),
		palette.style(glyphs["bl"] + glyphs["h"] * inner + glyphs["br"],
					  fg="border-fg", cap=cap, theme=theme),
	])


def section(title, *, cap=None, theme=None):
	"""Section heading; plain text when piped."""
	cap = cap or caps.detect()
	label = _flat(title)
	if cap.plain:
		return label
	return palette.style(label, fg="header-fg", bold=True, cap=cap, theme=theme)


def _flat(value):
	"""str() with newlines flattened: a cell is always one line."""
	return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _normalise(row, count):
	cells = [_flat(value) for value in list(row)[:count]]
	return cells + [""] * (count - len(cells))


def _column_widths(labels, data):
	widths = [display_width(label) for label in labels]
	for cells in data:
		for index, cell in enumerate(cells):
			widths[index] = max(widths[index], display_width(cell))
	return [max(MIN_COLUMN, width) for width in widths]


def _explicit_widths(widths, count):
	"""Caller-supplied widths: exact, never measured, never fitted."""
	forced = [max(0, int(width)) for width in list(widths)[:count]]
	return forced + [MIN_COLUMN] * (count - len(forced))


def _fit(widths, limit):
	"""Shrink the widest columns until the box fits `limit` cells."""
	widths = list(widths)
	while sum(widths) + 3 * len(widths) + 1 > limit:
		widest = max(range(len(widths)), key=lambda index: widths[index])
		if widths[widest] <= MIN_COLUMN:
			break
		widths[widest] -= 1
	return widths

