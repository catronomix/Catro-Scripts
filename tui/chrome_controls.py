# Chrome controls: the styled button label and the scrollbar column
"""
			CHROME CONTROLS
			===============
The two interactive chrome seams, split out of `tui.chrome` so the page
furniture does not carry the widget tables: `button()` decorates and paints one
label from the theme's `button_style`/`button_decoration`/`focus_style`, and
`scrollbar()` returns one single-column cell per row for the theme's
`scrollbar_style`.

`tui.widgets` wraps both (`Button` builds its label through `chrome.button`,
`ScrollBar` reads `chrome.scrollbar()` back for its geometry) and `tui.chrome`
re-exports them, so `chrome.button()`/`chrome.scrollbar()` and the four tables
keep resolving at their old path. Nothing here prints, returns a trailing
newline, or reads the terminal: every escape comes from `palette.style()`.
"""

from . import caps, palette
from .chrome_panels import _flat

# button_decoration -> (prefix, suffix) wrapped around the label. `none` is a
# painted pad, not an empty string: an undecorated button still needs its
# footprint and its colours. `chevron` uses the guillemets so it reads as a
# chevron without doubling `angles`.
BUTTON_DECORATIONS = {
	"none": (" ", " "), "brackets": ("[ ", " ]"), "angles": ("< ", " >"),
	"braces": ("{ ", " }"), "colons": (": ", " :"), "pipes": ("| ", " |"),
	"chevron": ("\u00ab ", " \u00bb"), "ellipsis": ("\u2026 ", " \u2026"),
}

# The ASCII spelling of the two decorations a cp1252 console cannot take.
ASCII_DECORATIONS = dict(BUTTON_DECORATIONS, chevron=("<< ", " >>"),
						 ellipsis=("... ", " ..."))

# button_style -> the palette roles and attributes the label is painted with.
BUTTON_STYLES = {
	"filled": {"fg": "bg", "bg": "fg-accent"}, "outline": {"fg": "border-fg"},
	"plain": {"fg": "fg"}, "underline": {"fg": "fg", "underline": True},
}

# scrollbar_style -> (thumb, track, ascii thumb, ascii track).
SCROLLBAR_GLYPHS = {
	"block": ("\u2588", "\u2591", "#", "."),
	"line": ("\u2503", "\u2502", "#", "."),
	"ascii": ("#", "|", "#", "|"),
}


def button(label, *, focused=False, disabled=False, cap=None, theme=None):
	"""One button label, shaped by `button_style`/`button_decoration`.

	The stage-3 widgets wrap this seam, they never re-implement it. The
	decoration always wraps the label, so the whole button carries the style;
	`focused` re-styles per `focus_style` and `disabled` forces `fg-muted` (it
	wins over both). Piped, the decorated label comes back with no escapes.
	"""
	cap = cap or caps.detect()
	properties = palette.properties()
	decorations = BUTTON_DECORATIONS if cap.unicode else ASCII_DECORATIONS
	decoration = str(properties.get("button_decoration", "brackets"))
	left, right = decorations.get(decoration, BUTTON_DECORATIONS["brackets"])
	text = left + _flat(label) + right
	if cap.plain:
		return text
	style = str(properties.get("button_style", "filled"))
	attributes = dict(BUTTON_STYLES.get(style, BUTTON_STYLES["filled"]))
	if focused:
		focus = str(properties.get("focus_style", "reverse"))
		if focus == "accent":
			# Replacing the ground keeps the label legible on the accent.
			attributes.pop("bg", None)
			attributes["fg"] = "fg-accent"
		elif focus == "underline":
			attributes["underline"] = True
		else:
			attributes["reverse"] = True
	if disabled:
		attributes = {"fg": "fg-muted"}
	return palette.style(text, cap=cap, theme=theme, **attributes)


def scrollbar(height, *, offset=0, total=None, cap=None, theme=None):
	"""One single-column cell per row: `fg-accent` thumb over a `fg-muted` track.

	`scrollbar_style` picks the glyph pair (`block` blocks, `line` lines,
	`ascii` `#`/`|`). `total` is the content height (`None` means everything
	fits) and `offset` is clamped to the scrollable span; a zero `height` gives
	an empty column and a zero `total` (or a sub-cell thumb) all track, never
	an error. `cap.unicode` false and `cap.plain` use the ASCII pair.
	"""
	cap = cap or caps.detect()
	height = max(0, int(height))
	if height == 0:
		return []
	name = str(palette.properties().get("scrollbar_style", "block"))
	thumb, track, ascii_thumb, ascii_track = SCROLLBAR_GLYPHS.get(
		name, SCROLLBAR_GLYPHS["block"])
	if not cap.unicode or cap.plain:
		thumb, track = ascii_thumb, ascii_track
	content = height if total is None else max(0, int(total))
	length = start = 0
	if content > 0:
		length = min(height, max(1, int(round(height * height / content))))
		span = max(0, content - height)
		offset = min(max(0, int(offset)), span)
		start = int(round(offset * (height - length) / span)) if span else 0
	last = start + length
	return [palette.style(thumb if start <= row < last else track,
						  fg="fg-accent" if start <= row < last else "fg-muted",
						  cap=cap, theme=theme) for row in range(height)]
