# Theme schema data and validation: look ids, palette keys, legal properties
"""
			THEME SCHEMA DATA
			=================
The static half of `tui.theme_engine`: look ids, palette key order, the legal
value of every rendering property, the look-selector spellings and the built-in
`cozypurple` document. It also owns validation - the tables above are the only
place that knows what a valid document looks like, so the checks live next to
them and the engine only calls `validate()`.

`theme_engine` re-exports `canonical_hex` and `validate`, so callers keep using
the engine namespace. Pure data plus pure functions: no I/O, no terminal, no
third-party import, which keeps the engine well inside the `tui/` file budget
and lets a reader check the whole schema in one screen.

`BUILTIN_LOOKS` is the in-code fallback and the table `tui.palette` publishes as
`SOFT`/`CONTRAST_*`; it mirrors `themes/cozypurple.json` exactly (a test pins
the two together).
"""

import re

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

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def canonical_hex(value, lower=True):
	"""`#rrggbb` for a hex string, or None when invalid.

	`lower=False` keeps the file's own spelling, which is what a load hands out so
	the shipped uppercase document renders exactly the bytes it always has.
	"""
	if not isinstance(value, str):
		return None
	match = _HEX.match(value.strip())
	if match is None:
		return None
	return "#" + (match.group(1).lower() if lower else match.group(1))


def validate(document):
	"""Every reason `document` is not a valid theme; [] when it is valid."""
	if not isinstance(document, dict):
		return ["theme document must be a JSON object"]
	errors = []
	schema = document.get("schema")
	if isinstance(schema, bool) or schema != 1:
		errors.append("schema must be 1")
	name = document.get("name")
	if not isinstance(name, str) or not SLUG.match(name):
		errors.append("name must be a slug matching [a-z0-9][a-z0-9-]*")
	display = document.get("display")
	if not isinstance(display, str) or not display.strip():
		errors.append("display must be non-empty text")
	errors.extend(_property_errors(document.get("properties")))
	errors.extend(_look_errors(document.get("looks")))
	return errors


def _property_errors(properties):
	if not isinstance(properties, dict):
		return ["properties must be an object"]
	errors = []
	for key, allowed in PROPERTY_VALUES.items():
		if key not in properties:
			errors.append("properties is missing {}".format(key))
		elif not any(properties[key] == value and
					 type(properties[key]) is type(value) for value in allowed):
			errors.append("invalid property {}: {!r}".format(
				key, properties[key]))
	unknown = sorted(set(properties) - set(PROPERTY_VALUES))
	if unknown:
		errors.append("unknown properties: {}".format(", ".join(unknown)))
	return errors


def _look_errors(looks):
	if not isinstance(looks, dict):
		return ["looks must be an object"]
	errors = []
	for look in LOOKS:
		entry = looks.get(look)
		if not isinstance(entry, dict):
			errors.append("looks is missing {}".format(look))
			continue
		errors.extend("looks.{} has no valid {} colour".format(look, key)
					  for key in PALETTE_KEYS
					  if canonical_hex(entry.get(key)) is None)
		unknown = sorted(set(entry) - set(PALETTE_KEYS))
		if unknown:
			errors.append("looks.{} has unknown keys: {}".format(
				look, ", ".join(unknown)))
	unknown = sorted(set(looks) - set(LOOKS))
	if unknown:
		errors.append("unknown looks: {}".format(", ".join(unknown)))
	return errors
