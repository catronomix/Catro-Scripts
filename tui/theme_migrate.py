# Theme migration: schema 1 -> 2 -> 3 key renames, new slots and defaults
"""
			THEME MIGRATION
			===============
Two in-memory steps between an old document on disk and the current schema:
`migrate_doc()` renames a schema-1 document to schema 2 and then derives the
three schema-3 button slots from a slot that already carries the byte a shipped
theme needs; a schema-2 document takes the second step only. Hex case is copied,
never rewritten, and a look key the schema never had rides along (a spelling a
later schema owns is blanked), so `validate_any()` refuses a half-migrated file
instead of a save dropping the bytes.

The maps live in `tui.theme_keys` (not in `tui.theme_engine`, which is at its
budget) and are re-exported here: `tui.palette` publishes current roles only, so
an old name is just an unknown role there. `tui.theme_schema` migrates before it
checks, and an old file is never refused or rewritten by a read.
"""

from .picker_keys import PALETTE_KEYS, V1_PALETTE_KEYS
from .theme_keys import (DERIVED, V1_TO_V2, V2_PALETTE_KEYS, V2_TO_V3)  # noqa: F401

SCHEMA_CURRENT = 3

# Properties the current schema adds (defaults) and retires (dropped).
DEFAULT_PROPERTIES = {"corner-char": "none"}
DROPPED_PROPERTIES = ("selection_style",)


def migrate_doc(document):
	"""`document` as the current schema; a current document is returned as is."""
	if not isinstance(document, dict):
		return document
	schema = document.get("schema")
	if schema == 1:
		schema = 2
		document = _document(document, schema, _look)
	if schema != 2:
		return document
	return _document(document, SCHEMA_CURRENT, _v3_look)


def _document(document, schema, look_step):
	"""One old document as `schema`: v1 properties plus `look_step` per look."""
	migrated = dict(document, schema=schema)
	if schema == 2:
		migrated["properties"] = _properties(document.get("properties"))
	migrated["looks"] = {look: look_step(entry)
						 for look, entry in (document.get("looks") or {}).items()}
	return migrated


def _properties(properties):
	"""v1 properties minus the retired ones, plus the new defaults."""
	values = {key: value for key, value in (properties or {}).items()
			  if key not in DROPPED_PROPERTIES}
	for key, value in DEFAULT_PROPERTIES.items():
		values.setdefault(key, value)
	return values


def _look_step(entry, keys, renames, derived, order):
	"""One old look as the next schema: blank a later spelling, derive, order."""
	extra = {key: None if key in PALETTE_KEYS else value
			 for key, value in entry.items() if key not in keys}
	colours = {renames.get(key, key): entry.get(key) for key in keys}
	colours.update({key: entry.get(source) for key, source in derived.items()})
	result = {key: colours.get(key) for key in order}
	result.update(extra)
	return result


def _look(entry):
	"""One v1 look as a v2 look: the sixteen schema-2 keys, in canonical order."""
	return _look_step(entry, V1_PALETTE_KEYS, V1_TO_V2, DERIVED, V2_PALETTE_KEYS)


def _v3_look(entry):
	"""One v2 look as v3: the three button slots derived, canonical order."""
	return _look_step(entry, V2_PALETTE_KEYS, {}, V2_TO_V3, PALETTE_KEYS)
