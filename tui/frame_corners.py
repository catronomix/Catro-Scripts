# Frame corners: the theme's `corner-char` override for a border glyph set
"""
			FRAME CORNERS
			=============
`apply_corners()` is the one seam that puts a theme's `corner-char` on a box
frame. `none` (the default), an unknown value and the all-space `none` border
family all return the family untouched, so a shipped theme draws exactly the
bytes it always has; the six characters replace the four corner cells only,
never the tees or the rules.

Callers degrade for the console first (`cap.unicode` false hands over the ASCII
family), then this override lands on top, so a custom corner is always the byte
the theme asked for.
"""

from .picker_keys import CORNER_CHARS

CORNERS = ("tl", "tr", "bl", "br")


def apply_corners(glyphs, cap, properties):
	"""`glyphs` with `corner-char` on its corners; the same dict when `none`."""
	char = str((properties or {}).get("corner-char", "none")).strip()
	if char not in CORNER_CHARS or char == "none" or glyphs.get("h") == " ":
		return glyphs
	corners = dict(glyphs)
	for key in CORNERS:
		corners[key] = char
	return corners
