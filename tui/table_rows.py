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
from .text import display_width, pad, truncate as _truncate


def reset(cap):
	"""The reset code, or "" when the caller asked for no styling at all."""
	return "" if cap.level == "none" else palette.RESET


def rule(glyphs, widths, left, middle, right, cap, theme):
	body = glyphs[middle].join(glyphs["h"] * (width + 2) for width in widths)
	return palette.style(glyphs[left] + body + glyphs[right], fg="border-fg",
						 bg="border-bg", cap=cap, theme=theme)


def header_row(glyphs, widths, labels, cap, theme):
	"""One span over the whole row: frame, then the first border, then bold.

	The header body sits on `bg-inside` in `header-fg`, so the band has no
	terminal-coloured hole between its inner borders and matches the editor
	preview's `thead` row. The closing border re-asserts the frame ink and
	ground, so the last vertical glyph never inherits `header-bg`.
	"""
	align = str(palette.properties(theme).get("header_align", "left"))
	body = glyphs["v"].join(" " + _aligned(cell, width, align) + " "
							for cell, width in zip(labels, widths))
	return (palette.prefix(fg="border-fg", bg="border-bg", cap=cap,
						   theme=theme) + glyphs["v"]
			+ palette.prefix(fg="header-fg", bg="bg-inside", bold=True,
							 cap=cap, theme=theme)
			+ body
			+ palette.prefix(fg="border-fg", bg="border-bg", cap=cap,
							 theme=theme)
			+ glyphs["v"] + reset(cap))


def _aligned(cell, width, align):
	"""`cell` padded to `width` cells, placed by `header_align`."""
	cell = str(cell)
	slack = max(0, width - display_width(cell))
	if align == "right":
		return " " * slack + cell
	if align == "center":
		left = slack // 2
		return " " * left + cell + " " * (slack - left)
	return cell + " " * slack


def row(glyphs, widths, cells, cap, theme, bg=None, truncate_cells=False,
		fg="fg", bold=False):
	"""Zebra data row, composed exactly like the old `list.py` row.

	Every vertical border glyph carries the frame ink and ground
	(`border-fg`/`border-bg`), and each cell re-asserts its own colours after it
	(`border | cell-style text`); only the closing border is preceded by a
	reset, so the row carries the same escapes in the same order as the
	hand-built table did. `fg`/`bold` are the per-row ink a caller keeps as data
	(`count`'s rainbow) or uses to emphasise a summary row; they never touch the
	ground.
	"""
	border = palette.prefix(fg="border-fg", bg="border-bg", cap=cap,
							theme=theme)
	cell_style = palette.prefix(fg=fg, bg=bg, bold=bold, cap=cap, theme=theme)
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


def bare_rows(labels, data, widths, cap, theme, zebra, row_styles=None):
	"""Borderless variant: padded columns separated by two spaces."""
	align = str(palette.properties(theme).get("header_align", "left"))
	lines = [bare_line(labels, widths, cap, theme, fg="header-fg",
					   bg="bg-inside", bold=True, align=align)]
	for index, cells in enumerate(data):
		extra = (row_styles[index] if row_styles and index < len(row_styles)
				 else None) or {}
		lines.append(bare_line(cells, widths, cap, theme,
							   bg=zebra_bg(index, zebra),
							   fg=extra.get("fg", "fg"),
							   bold=extra.get("bold", False)))
	return lines


def zebra_bg(index, zebra):
	"""Palette key for row `index`: the zebra pair, else the inside ground.

	Turning shading off must not expose the terminal default, so every data row
	then sits on `bg-inside` (the same ground the panel interior uses).
	"""
	if not zebra:
		return "bg-inside"
	return "bg" if index % 2 == 0 else "bg-stripe"


def span_rule(glyphs, widths, cap, theme):
	"""One rule as wide as the borderless row (`compact`'s top/bottom edge)."""
	span = sum(widths) + 2 * max(0, len(widths) - 1)
	return palette.style(glyphs["h"] * max(1, span), fg="border-fg",
						 bg="border-bg", cap=cap, theme=theme)


def bare_line(cells, widths, cap, theme, fg="fg", bg=None, bold=False,
			  align="left"):
	cells = [_aligned(_truncate(cell, width), width, align)
			 for cell, width in zip(cells, widths)]
	body = "  ".join(cells)
	return palette.style(body, fg=fg, bg=bg, bold=bold, cap=cap, theme=theme)
