# Theme schema data and validation: look ids, palette keys, legal properties
"""
			THEME SCHEMA DATA
			=================
The static half of `tui.theme_engine`: look ids, palette key order, the legal
value of every rendering property and the look-selector spellings. It also owns
validation - the tables above are the only place that knows what a valid
document looks like, so the checks live next to them and the engine only calls
`validate()`.

`validate()` knows one schema: the current one (schema 3). An older document
is read through `tui.theme_migrate` first, so `validate_any()` migrates before
it checks and an old file keeps loading; the strict `validate()` stays the
writer's gate. A schema-2 document that still carries the retired
`selection_style` property is rejected as an unknown key, never silently
dropped.

`theme_engine` re-exports `canonical_hex` and `validate`, so callers keep using
the engine namespace. Pure data plus pure functions: no I/O, no terminal, no
third-party import, which keeps the engine well inside the `tui/` file budget
and lets a reader check the whole schema in one screen.

No shipped palette lives here: `themes/cozypurple.json` is the one source of
truth, and `tui.theme_engine` loads it lazily for the built-in fallback.
"""

import re

from .picker_keys import CORNER_CHARS, PALETTE_KEYS
from .theme_migrate import SCHEMA_CURRENT, migrate_doc

DEFAULT_THEME = "cozypurple"
DEFAULT_LOOK = "soft"

# Look ids are the JSON file's keys; selectors are what a user types.
LOOKS = ("default", "contrast-dark", "contrast-light")

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
	"corner-char": CORNER_CHARS,
}

# The document's top-level keys, in the order `_ordered()` writes them. Anything
# else is rejected rather than dropped by a save.
DOCUMENT_KEYS = ("schema", "name", "display", "properties", "looks")

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
	"""Every reason `document` is not a valid current-schema theme; [] when it is."""
	if not isinstance(document, dict):
		return ["theme document must be a JSON object"]
	errors = []
	# Unknown top-level keys are rejected, not dropped: `_ordered()` only emits
	# DOCUMENT_KEYS, so keeping one would silently lose data on the next save.
	unknown = sorted(set(document) - set(DOCUMENT_KEYS), key=str)
	if unknown:
		errors.append("unknown top-level keys: {}".format(
			", ".join(str(key) for key in unknown)))
	schema = document.get("schema")
	if isinstance(schema, bool) or schema != SCHEMA_CURRENT:
		errors.append("schema must be {}".format(SCHEMA_CURRENT))
	name = document.get("name")
	if not isinstance(name, str) or not SLUG.match(name):
		errors.append("name must be a slug matching [a-z0-9][a-z0-9-]*")
	display = document.get("display")
	if not isinstance(display, str) or not display.strip():
		errors.append("display must be non-empty text")
	errors.extend(_property_errors(document.get("properties")))
	errors.extend(_look_errors(document.get("looks")))
	return errors


def validate_any(document):
	"""`validate()` after the migrate steps: an older file still reads.

	Migration is in memory and only renames or derives; the document then meets
	the same strict current-schema checker the writer uses. A malformed old
	document that migration cannot walk is reported, never raised.
	"""
	try:
		document = migrate_doc(document)
	except (AttributeError, KeyError, TypeError):
		return ["theme document must be a JSON object"]
	return validate(document)


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
