# Theme migration: schema 1 -> schema 2 key renames, new slots and defaults
"""
			THEME MIGRATION
			===============
One in-memory step between a schema-1 document on disk and the schema-2
document the engine hands out. `migrate_doc()` renames the nine palette slots,
derives the five new ones from a slot that already carries the byte a shipped
theme needs, drops the retired `selection_style` property and adds
`corner-char: none`; hex case is copied, never rewritten, so a migrated look
renders exactly the bytes the file spelled.

The map lives here (not in `tui.theme_engine`, which is at its budget) and is
the only reader of a v1 spelling: `tui.palette` publishes schema-2 roles only,
so an old name is just an unknown role there. Validation stays in
`tui.theme_schema`: `validate_any()` migrates first, then the schema-2 checker
runs, and a v1 file is never refused or rewritten by a read.
"""

from .picker_keys import PALETTE_KEYS, V1_PALETTE_KEYS

SCHEMA_CURRENT = 2

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

# Properties the current schema adds (defaults) and retires (dropped).
DEFAULT_PROPERTIES = {"corner-char": "none"}
DROPPED_PROPERTIES = ("selection_style",)


def migrate_doc(document):
	"""`document` as the current schema; a non-v1 document is returned as is."""
	if not isinstance(document, dict) or document.get("schema") != 1:
		return document
	looks = document.get("looks")
	migrated = dict(document)
	migrated["schema"] = SCHEMA_CURRENT
	migrated["properties"] = _properties(document.get("properties"))
	migrated["looks"] = {look: _look(entry)
						 for look, entry in (looks or {}).items()}
	return migrated


def _properties(properties):
	"""v1 properties minus the retired ones, plus the new defaults."""
	values = {key: value for key, value in (properties or {}).items()
			  if key not in DROPPED_PROPERTIES}
	for key, value in DEFAULT_PROPERTIES.items():
		values.setdefault(key, value)
	return values


def _look(entry):
	"""One v1 look as a v2 look: derive, rename, then emit in canonical order."""
	colours = {key: entry.get(key) for key in V1_PALETTE_KEYS}
	for key, source in DERIVED.items():
		colours[key] = entry.get(source)
	for old, new in V1_TO_V2.items():
		colours[new] = colours.pop(old, None)
	return {key: colours.get(key) for key in PALETTE_KEYS}
