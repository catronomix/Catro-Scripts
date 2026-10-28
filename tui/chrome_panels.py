# Page panels: the framed panel and the masthead band painters
"""
			PAGE PANELS
			============
The framed half of `tui.chrome`: `panel()` (a bg-inside box with the title
cut into the top rule) and `_band()`/`_top_frame()`, the single-line and border
painters it is built from. `tui.chrome.header()` keeps the masthead itself but
takes its title/subtitle bands from here, so the masthead and the panel share
one padding rule.

This module sits below `tui.chrome` in the chain (`chrome -> chrome_panels`) and
imports nothing from it, which is why the page-row helpers both halves need -
`_flat()` and `_span()` - live here and are imported back by `chrome`. `panel()`
is re-exported there, so `chrome.panel()` and `tui.panel()` keep resolving.
"""

from . import caps, palette, table
from .text import display_width, pad, truncate as _truncate


def _flat(value):
	"""str() with newlines flattened: a page row is always one line."""
	return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
def _span(width, cap):
	"""Explicit width, else the terminal width, else None (content-sized)."""
	if width is not None:
		try:
			return max(0, int(width))
		except (TypeError, ValueError):
			return None
	return cap.width
def _reset(cap):
	"""The reset code, or "" when the caller asked for no styling at all."""
	return "" if cap.level == "none" else palette.RESET
def _body_lines(body):
	"""The panel body as one flattened string per line; never empty."""
	if isinstance(body, str):
		return body.splitlines() or [""]
	return [_flat(line) for line in body] or [""]
def frame_roles(active=False):
	"""The (fg, bg) palette roles of a frame band, focused or not."""
	if active:
		return "border-fg-active", "border-bg-active"
	return "border-fg", "border-bg"
def panel(title, body, *, width=None, padding=1, cap=None, theme=None,
		  active=False):
	"""Framed box with `bg-inside` interior and the title in the top rule.

	`body` is a string (one line per `\\n`) or an iterable of lines; lines are
	truncated to the interior, never wrapped, never raise. `padding` is the
	spaces between frame and text on each side; a caller `width` wins.
	`active` paints the frame with the focused band roles.
	"""
	cap = cap or caps.detect()
	padding = max(0, int(padding))
	title = "" if title is None else _flat(title)
	body_lines = _body_lines(body)
	if cap.plain:
		lines = ([title] if title else []) + body_lines
		return "\n".join(lines)
	glyphs = table.glyphs_for(cap)
	gutter = " " * padding
	content = max([display_width(line) for line in body_lines] + [0])
	needed = content + 2 * padding + 2
	if title:
		# Room for one rule glyph, " title ", and one more rule glyph.
		needed = max(needed, display_width(title) + 6)
	inner = _span(width, cap)
	if inner is None:
		inner = needed
	inner = max(4, inner)
	lines = [_top_frame(glyphs, inner, title, cap, theme, active)]
	cell = max(0, inner - 2 - 2 * padding)
	edge_fg, edge_bg = frame_roles(active)
	edge = palette.prefix(fg=edge_fg, bg=edge_bg, cap=cap, theme=theme)
	inside = palette.prefix(fg="fg", bg="bg-inside", cap=cap, theme=theme)
	reset = _reset(cap)
	for line in body_lines:
		text = _truncate(line, cell) if display_width(line) > cell else line
		lines.append(edge + glyphs["v"] + inside + gutter + pad(text, cell)
					 + gutter + edge + glyphs["v"] + reset)
	lines.append(palette.style(glyphs["bl"] + glyphs["h"] * (inner - 2)
							   + glyphs["br"], fg=edge_fg, bg=edge_bg,
							   cap=cap, theme=theme))
	return "\n".join(lines)
def _top_frame(glyphs, inner, title, cap, theme, active=False):
	"""Top border with the title cut into it, or a plain rule when untitled.

	The title is a heading band: `border-fg` as its background and `border-bg`
	as its text, bold as before. `header_align` places it inside the top rule,
	so a panel and the masthead follow the document's alignment together.
	"""
	edge_fg, edge_bg = frame_roles(active)
	if not title:
		return palette.style(glyphs["tl"] + glyphs["h"] * (inner - 2)
							 + glyphs["tr"], fg=edge_fg, bg=edge_bg,
							 cap=cap, theme=theme)
	label = title
	if display_width(label) > inner - 6:
		label = _truncate(label, max(0, inner - 6))
	if not label:
		return palette.style(glyphs["tl"] + glyphs["h"] * (inner - 2)
							 + glyphs["tr"], fg=edge_fg, bg=edge_bg,
							 cap=cap, theme=theme)
	align = str(palette.properties(theme).get("header_align", "left"))
	room = max(0, inner - 5 - display_width(label))
	left = room if align == "right" else room // 2 if align == "center" else 0
	rest = room - left
	heading = palette.prefix(fg=edge_bg, bg=edge_fg, bold=True, cap=cap,
							 theme=theme)
	edge = palette.prefix(fg=edge_fg, bg=edge_bg, cap=cap, theme=theme)
	return (edge
			+ glyphs["tl"] + glyphs["h"] * (1 + left)
			+ heading
			+ " " + label + " "
			+ edge
			+ glyphs["h"] * rest + glyphs["tr"] + _reset(cap))
def _band(text, width, *, fg, bold=False, align="left", cap, theme):
	"""One full-width `header-bg` band with the label placed by `align`.

	`left` is the shipped shape: one space, the label, the padding (and one
	trailing space), so the masthead bytes do not move; `center`/`right` only
	move the padding inside those two end spaces.
	"""
	inner = max(0, width - 2)
	label = _truncate(text, inner)
	slack = max(0, inner - display_width(label))
	if align == "center":
		left = slack // 2
	elif align == "right":
		left = slack
	else:
		left = 0
	body = " " + " " * left + label + " " * (slack - left) + " "
	return palette.style(body, fg=fg, bg="header-bg", bold=bold, cap=cap,
						 theme=theme)
