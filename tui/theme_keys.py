# Theme migration maps: schema-1 renames, byte-preserving slots, v2 -> v3 slots
"""
			THEME MIGRATION MAPS
			====================
Pure tables read by `tui.theme_migrate`, kept in their own module so that one
holds both migration steps inside its line budget: the nine schema-1 renames,
the five slots schema 2 derived from a schema-1 slot, the three button slots
schema 3 derives from a schema-2 one, and the schema-2 key set a v3 step keeps
as its own. `tui.theme_migrate` re-exports all four and is the only code that
walks them.
"""

from .picker_keys import PALETTE_KEYS

# Schema-1 key -> schema-2 key for the nine renamed palette slots.
V1_TO_V2 = {
	"surface": "bg-inside",
	"zebra_bg": "bg-stripe",
	"muted": "fg-muted",
	"accent": "fg-accent",
	"success": "fg-success",
	"warn": "fg-warn",
	"error": "fg-error",
	"border": "border-fg",
	"header": "header-fg",
}

# The new slots and the schema-1 slot each one starts from (byte-preserving).
DERIVED = {
	"bg-inside-active": "zebra_bg",
	"border-bg": "surface",
	"border-bg-active": "zebra_bg",
	"border-fg-active": "accent",
	"header-bg": "surface",
}

# The schema-3 button slots and the schema-2 slot each one derives from. The
# defaults duplicate a shipped hex, so the default look keeps its exact pixels;
# a focused button is still signalled by the reverse attribute.
V2_TO_V3 = {
	"button-fg": "bg",
	"button-bg": "fg-accent",
	"button-bg-active": "fg-accent",
}

# The sixteen keys a schema-2 look owns, in canonical order: the v3 set less the
# three button slots, which a v2 -> v3 step blanks if a file already spells one.
V2_PALETTE_KEYS = tuple(key for key in PALETTE_KEYS if key not in V2_TO_V3)
