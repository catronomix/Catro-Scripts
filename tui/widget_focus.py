# Widget focus ground: the self-contained prefix for a focused row
"""
			WIDGET FOCUS
			============
The focus prefix split out of `tui.widgetkit`: one function, kept apart so the
widget kit stays inside its file budget. `tui.widgetkit` (and therefore
`tui.widgets`) re-exports it, so `from tui.widgets import focus_prefix` keeps
working.

The prefix re-asserts `fg`/`bg` before the theme's focus attribute: a canvas
cell carries no state of its own, so a prefix that only had the attribute would
inherit whatever ground the previously drawn cell left behind.
"""

from . import caps, palette


def focus_prefix(focused, cap=None, *, fg="fg", bg="bg-inside-active"):
	"""A self-contained focus-visible cell colour, or None when not focused.

	The theme's `focus_style` picks the attribute (`reverse` by default,
	`accent` fg, or `underline`), but `fg`/`bg` are re-asserted first: two
	adjacent focused rows therefore cannot bleed into each other.
	"""
	if not focused:
		return None
	cap = cap or caps.detect()
	if cap.level == "none":
		return None
	style = palette.properties().get("focus_style")
	if style == "accent":
		return palette.prefix(fg="fg-accent", bg=bg, cap=cap) or None
	if style == "underline":
		return palette.prefix(fg=fg, bg=bg, underline=True, cap=cap) or None
	return palette.prefix(fg=fg, bg=bg, reverse=True, cap=cap) or None
