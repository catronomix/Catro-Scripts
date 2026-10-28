# Table row builders: the frame, header and zebra cells one row at a time
"""
			TABLE ROWS
			==========
The row-level half of `tui.table`: the rules, the header span, the zebra data
row, the borderless line and the compact span rule. Split out of `table.py` for
budget headroom; `tui.table` imports these and keeps `render_table` as the only
public entry point.

Every helper returns one string and never prints. Colours go through
`palette.prefix()`/`palette.style()` with the caller's cap and theme, so a pipe
still gets plain text and a themed terminal gets the palette's own escapes.
"""

from . import palette
from .text import pad, truncate as _truncate


def reset(cap):
	"""The reset code, or "" when the caller asked for no styling at all."""
	return "" if cap.level == "none" else palette.RESET


def rule(glyphs, widths, left, middle, right, cap, theme):
	body = glyphs[middle].join(glyphs["h"] * (width + 2) for width in widths)
	return palette.style(glyphs[left] + body + glyphs[right], fg="border-fg",
						 bg="border-bg", cap=cap, theme=theme)


def header_row(glyphs, widths, labels, cap, theme):
	"""One span over the whole row: border, then the first border, then bold.

	This keeps the pre-migration `list.py` escape order (border colour and
	ground once, the leading `|` inside it, then one styled span for the rest):
	only the header ink and its ground are new. The header's body sits on
	`bg-inside` in `header-fg`, so the band has no terminal-coloured hole
	between its inner borders and matches the editor preview's `thead` row.
	"""
	body = glyphs["v"].join(" " + pad(cell, width) + " "
							for cell, width in zip(labels, widths))
	return (palette.prefix(fg="border-fg", bg="border-bg", cap=cap,
						   theme=theme) + glyphs["v"]
			+ palette.prefix(fg="header-fg", bg="bg-inside", bold=True,
							 cap=cap, theme=theme)
			+ body + glyphs["v"] + reset(cap))


def row(glyphs, widths, cells, cap, theme, bg=None, truncate_cells=False):
	"""Zebra data row, composed exactly like the old `list.py` row.

	Each cell re-asserts its own colours after the border (`border | cell-style
	text`), and only the closing border is preceded by a reset, so the row
	carries the same escapes in the same order as the hand-built table did.
	"""
	border = palette.prefix(fg="border-fg", cap=cap, theme=theme)
	cell_style = palette.prefix(fg="fg", bg=bg, cap=cap, theme=theme)
	tail = reset(cap)
	parts = []
	for index, width in enumerate(widths):
		cell = cells[index]
		if truncate_cells:
			cell = _truncate(cell, width)
		parts.append(border + glyphs["v"] + cell_style)
		parts.append(" " + pad(cell, width) + " ")
	parts.append(tail + border + glyphs["v"] + tail)
	return "".join(parts)


def bare_rows(labels, data, widths, cap, theme, zebra):
	"""Borderless variant: padded columns separated by two spaces."""
	lines = [bare_line(labels, widths, cap, theme, fg="header-fg",
					   bg="bg-inside", bold=True)]
	for index, cells in enumerate(data):
		lines.append(bare_line(cells, widths, cap, theme,
							   bg=zebra_bg(index, zebra)))
	return lines


def zebra_bg(index, zebra):
	"""Palette key for row `index`, or None when zebra shading is off."""
	if not zebra:
		return None
	return "bg" if index % 2 == 0 else "bg-stripe"


def span_rule(glyphs, widths, cap, theme):
	"""One rule as wide as the borderless row (`compact`'s top/bottom edge)."""
	span = sum(widths) + 2 * max(0, len(widths) - 1)
	return palette.style(glyphs["h"] * max(1, span), fg="border-fg",
						 bg="border-bg", cap=cap, theme=theme)


def bare_line(cells, widths, cap, theme, fg="fg", bg=None, bold=False):
	cells = [_truncate(cell, width) for cell, width in zip(cells, widths)]
	body = "  ".join(pad(cell, width) for cell, width in zip(cells, widths))
	return palette.style(body, fg=fg, bg=bg, bold=bold, cap=cap, theme=theme)
