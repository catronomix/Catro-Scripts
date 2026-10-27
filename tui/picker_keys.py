# Palette key tables: the canonical v2 keys, the schema-1 spellings, corners
"""
			PALETTE KEY TABLES
			==================
Pure data shared by the theme schema, the migration and the corner seam: the
canonical schema-2 palette keys in document order, the schema-1 keys they
replaced, and the one-character corner overrides a theme may pick.

The lists live here rather than in `tui.theme_schema` so the checker, the
migration map and `tui.frame_corners` can share them without importing each
other. `tui.keys` is keyboard decoding only and owns no key-list data, so no
split out of it is needed.
"""

PALETTE_KEYS = ("bg", "bg-inside", "bg-inside-active", "bg-stripe", "fg",
				"fg-muted", "fg-accent", "fg-success", "fg-warn", "fg-error",
				"border-bg", "border-fg", "border-bg-active",
				"border-fg-active", "header-fg", "header-bg")

# The schema-1 spelling of the same document, kept so a v1 file keeps loading.
V1_PALETTE_KEYS = ("bg", "surface", "fg", "muted", "accent", "success", "warn",
				   "error", "border", "header", "zebra_bg")

# Valid `corner-char` values: `none` keeps the border family's own corners.
CORNER_CHARS = ("none", "@", "x", "#", "+", "o", "*")
