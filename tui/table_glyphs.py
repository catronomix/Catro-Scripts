# Box glyph tables: the six border families and the border_style selector
"""
			TABLE GLYPH TABLES
			==================
The frame alphabets the table renderer, the page chrome and the editor preview
draw with, plus `glyphs_for()`, the one place that decides which family a run
uses: the `table.style` override first, then the theme's `border_style`, then
the capability probe (`cap.unicode` False degrades every family but `none` to
ASCII), then the theme's `corner-char`, which `tui.frame_corners` stamps on the
corners of the winner; the tables live here so callers skip the renderer.

Every set has the same eleven keys (`tl`, `tm`, `tr`, `ml`, `mm`, `mr`, `bl`,
`bm`, `br`, `h`, `v`); `rounded` is the shipped default and is byte-pinned by
the golden fixture, so it must not move between families.
"""

from . import config, frame_corners, palette

UNICODE_GLYPHS = {
	"tl": "\u250c", "tm": "\u252c", "tr": "\u2510",
	"ml": "\u251c", "mm": "\u253c", "mr": "\u2524",
	"bl": "\u2514", "bm": "\u2534", "br": "\u2518",
	"h": "\u2500", "v": "\u2502",
}

ASCII_GLYPHS = {
	"tl": "+", "tm": "+", "tr": "+", "ml": "+", "mm": "+", "mr": "+",
	"bl": "+", "bm": "+", "br": "+", "h": "-", "v": "|",
}

# Heavy frame: the `heavy` border style.
HEAVY_GLYPHS = {
	"tl": "\u250f", "tm": "\u2533", "tr": "\u2513",
	"ml": "\u2523", "mm": "\u254b", "mr": "\u252b",
	"bl": "\u2517", "bm": "\u253b", "br": "\u251b",
	"h": "\u2501", "v": "\u2503",
}

# Double frame: the `double` border style.
DOUBLE_GLYPHS = {
	"tl": "\u2554", "tm": "\u2566", "tr": "\u2557",
	"ml": "\u2560", "mm": "\u256c", "mr": "\u2563",
	"bl": "\u255a", "bm": "\u2569", "br": "\u255d",
	"h": "\u2550", "v": "\u2551",
}

# `square`: Unicode has no second single-line square family (U+250C is the only
# one, and `rounded` keeps it so the default bytes cannot drift), so the crisp
# alternate is the mixed frame: light verticals with double horizontals.
SQUARE_GLYPHS = {
	"tl": "\u2552", "tm": "\u2564", "tr": "\u2555",
	"ml": "\u255e", "mm": "\u256a", "mr": "\u2561",
	"bl": "\u2558", "bm": "\u2567", "br": "\u255d",
	"h": "\u2550", "v": "\u2502",
}

# `none`: every frame cell is a space, so the borders vanish while the padding,
# the column widths and the row height stay exactly where they were.
SPACE_GLYPHS = {key: " " for key in UNICODE_GLYPHS}

# border_style -> glyph set. `rounded` is the shipped set (byte pin); `ascii`
# is the same table the capability probe falls back to.
BORDER_GLYPHS = {
	"rounded": UNICODE_GLYPHS,
	"square": SQUARE_GLYPHS,
	"heavy": HEAVY_GLYPHS,
	"double": DOUBLE_GLYPHS,
	"ascii": ASCII_GLYPHS,
	"none": SPACE_GLYPHS,
}


def glyphs_for(cap, theme=None):
	"""Box glyphs honouring the theme's `border_style` and `table.style`.

	Order: the `table.style` run override wins when it is explicitly set
	(`ascii` forces `+ - |`; `unicode` keeps the theme's glyphs when the
	capability probe allows Unicode), otherwise the theme's `border_style`
	picks a family, with `cap.unicode` False degrading everything but `none`
	to ASCII so a cp1252 console still renders a frame.
	"""
	style = str(config.get("table", "style", "auto")).strip().lower()
	if style == "ascii":
		glyphs = ASCII_GLYPHS
	else:
		border = str(palette.properties().get("border_style", "rounded"))
		glyphs = BORDER_GLYPHS.get(border, UNICODE_GLYPHS)
		if not cap.unicode and glyphs is not SPACE_GLYPHS:
			glyphs = ASCII_GLYPHS
	return frame_corners.apply_corners(glyphs, cap, palette.properties())
