# Theme schema data: look ids, palette keys, legal properties, built-ins
"""
			THEME SCHEMA DATA
			=================
The static half of `tui.theme_engine`: look ids, palette key order, the legal
value of every rendering property, the look-selector spellings and the built-in
`cozypurple` document. Pure data, so the engine itself stays well inside the
`tui/` file budget and a reader can check the schema in one screen.

`BUILTIN_LOOKS` is the in-code fallback and the table `tui.palette` publishes as
`SOFT`/`CONTRAST_*`; it mirrors `themes/cozypurple.json` exactly (a test pins
the two together).
"""

DEFAULT_THEME = "cozypurple"
DEFAULT_LOOK = "soft"

# Look ids are the JSON file's keys; selectors are what a user types.
LOOKS = ("default", "contrast-dark", "contrast-light")

PALETTE_KEYS = ("bg", "surface", "fg", "muted", "accent", "success", "warn",
				"error", "border", "header", "zebra_bg")

PROPERTY_VALUES = {
	"header_align": ("left", "center", "right"),
	"border_style": ("rounded", "square", "heavy", "double", "ascii", "none"),
	"button_style": ("filled", "outline", "plain", "underline"),
	"button_decoration": ("none", "brackets", "angles", "braces", "colons",
						  "pipes", "chevron", "ellipsis"),
	"table_style": ("box", "borderless", "compact"),
	"table_zebra": (True, False),
	"focus_style": ("reverse", "accent", "underline"),
	"scrollbar_style": ("block", "line", "ascii"),
	"selection_style": ("accent",),
}

# The default document's properties: every value is what today's renderers
# already produce, so the default look stays byte-identical.
BUILTIN_PROPERTIES = {
	"header_align": "left", "border_style": "rounded",
	"button_style": "filled", "button_decoration": "brackets",
	"table_style": "box", "table_zebra": True, "focus_style": "reverse",
	"scrollbar_style": "block", "selection_style": "accent",
}

# Selector -> look id. `soft`/`light`/`dark` are selectors, never theme names.
SELECTORS = {
	"soft": "default", "default": "default",
	"light": "contrast-light", "contrast-light": "contrast-light",
	"dark": "contrast-dark", "contrast-dark": "contrast-dark",
}

# Look id -> canonical selector, the spelling theme.ini and the CLI write.
SELECTOR_OF = {"default": "soft", "contrast-light": "light",
			   "contrast-dark": "dark"}

# Legacy `config.ini [theme] mode` values. `dark` was the old default name, so it
# maps onto the current default look rather than onto the contrast-dark look.
LEGACY_LOOKS = {
	"soft": "soft", "default": "soft", "cozy": "soft", "dark": "soft",
	"light": "light", "contrast-light": "light", "contrastlight": "light",
	"clight": "light", "contrast-dark": "dark", "contrastdark": "dark",
	"high-contrast": "dark", "highcontrast": "dark", "hc": "dark",
	"cdark": "dark",
}

# The cozypurple hexes in PALETTE_KEYS order, identical to
# themes/cozypurple.json. This is the in-code fallback and the table
# `tui.palette` publishes as SOFT/CONTRAST_*.
_BUILTIN_HEXES = {
	"default":
		"#1B1726 #292238 #D4C8EB #A392C0 #F5CD68 #7FD1A0 #E09F67 #FF6B6B "
		"#A392C0 #F5CD68 #352B49",
	"contrast-light":
		"#FFFFFF #E8F4F8 #000000 #4A4A4A #0000B3 #0A7A2F #8A5A00 #B3261E "
		"#000000 #A0007A #E8F4F8",
	"contrast-dark":
		"#000000 #0A0A0A #FFFFFF #D0D0D0 #00FFFF #00FF66 #FFFF00 #FF4040 "
		"#00FFFF #FFFF00 #1A1A1A",
}
BUILTIN_LOOKS = {look: dict(zip(PALETTE_KEYS, text.split()))
				 for look, text in _BUILTIN_HEXES.items()}

BUILTIN_DOCUMENT = {
	"schema": 1,
	"name": DEFAULT_THEME,
	"display": "Cozy Purple",
	"properties": dict(BUILTIN_PROPERTIES),
	"looks": {look: dict(BUILTIN_LOOKS[look]) for look in LOOKS},
}
