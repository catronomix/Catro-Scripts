# JSON theme engine: themes/*.json, theme.ini selection, look resolution
"""
			THEME ENGINE
			============
One JSON file per theme under `themes/`, one selection file per checkout
(`theme.ini`) and the rules that tie them to the palettes. This module owns the
data; `tui.palette` stays the public styling API and delegates here.

A document is `{schema, name, display, properties, looks}`: exactly the three
looks `default`, `contrast-dark`, `contrast-light` with the eleven palette keys
as `#rrggbb` strings, plus the nine rendering properties. Validation is
all-or-nothing, so a typo can never ship a half-theme.

Reads never raise: a missing, unreadable or invalid theme file, and a malformed
`theme.ini`, fall back to the built-in `cozypurple` default look. Only the paths
a user asks for - `load_theme()`, `set_selection()`, `save_theme()` - raise
`ThemeError`, so the CLI can print one line and exit 2.

Precedence is override, then `CATRO_THEME` (both in `tui.palette`), then
`theme.ini`, then the migrated legacy `config.ini [theme] mode`, then the
built-in default. The legacy value is migrated in memory on read and persisted
by the first write, so a plain render never creates files.

Test seams: assign `THEME_FILE` / `THEMES_DIR` to redirect reads and writes (tests
never touch the repository); `None` restores the project folder. Import is inert:
no printing, no write, no terminal mode change, no third-party or platform import.
"""

import configparser
import copy
import json
import os
import re
from pathlib import Path

from . import config

# The schema tables live in their own module; re-exported here so callers
# and tests keep using the engine namespace.
from .theme_schema import (BUILTIN_DOCUMENT, BUILTIN_LOOKS,  # noqa: F401
						   BUILTIN_PROPERTIES, DEFAULT_LOOK, DEFAULT_THEME,
						   LEGACY_LOOKS, LOOKS, PALETTE_KEYS, PROPERTY_VALUES,
						   SELECTOR_OF, SELECTORS)


# Overrides for tests; see the module docstring.
THEME_FILE = None
THEMES_DIR = None

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
_CACHE = {}


class ThemeError(Exception):
	"""A theme file or the selection could not be read, validated or written."""


def fold(name):
	"""Fold a spelling before lookup: lowercase, spaces/underscores to "-"."""
	return "-".join(str(name).strip().lower().replace("_", " ").split())


def theme_file():
	"""Absolute path of the selection file this checkout uses."""
	if THEME_FILE is not None:
		return Path(THEME_FILE)
	return Path(__file__).resolve().parents[1] / "theme.ini"


def themes_dir():
	"""Absolute path of the directory that holds the theme documents."""
	if THEMES_DIR is not None:
		return Path(THEMES_DIR)
	return Path(__file__).resolve().parents[1] / "themes"


def list_themes():
	"""Sorted theme slugs in `themes/`; [] when the directory is absent."""
	try:
		return sorted(entry.stem for entry in themes_dir().glob("*.json")
					  if entry.is_file())
	except OSError:
		return []


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
	if not isinstance(name, str) or not _SLUG.match(name):
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


def _ordered(document, lower=True):
	"""Copy in the pinned order; `lower=False` keeps the file's hex spelling."""
	return {
		"schema": 1,
		"name": str(document["name"]).strip().lower(),
		"display": str(document["display"]).strip(),
		"properties": {key: document["properties"][key]
					   for key in PROPERTY_VALUES},
		"looks": {look: {key: canonical_hex(document["looks"][look][key], lower)
						 for key in PALETTE_KEYS}
				  for look in LOOKS},
	}


def _copy(document):
	"""Copy so callers cannot mutate the cache or the built-in document."""
	return copy.deepcopy(document)


def _path_for(name):
	return themes_dir() / "{}.json".format(name)


def _cache_key(target):
	try:
		stat = target.stat()
	except OSError:
		return None
	return (str(target), stat.st_mtime_ns, stat.st_size)


def load_theme(name=None):
	"""The validated document for `name`; raises `ThemeError`."""
	name = str(name if name is not None else DEFAULT_THEME).strip().lower()
	if not _SLUG.match(name):
		raise ThemeError("invalid theme name: {!r}".format(name))
	target = _path_for(name)
	key = _cache_key(target)
	cached = _CACHE.get(key)
	if cached is not None:
		return _copy(cached)
	try:
		with open(target, "r", encoding="utf-8") as handle:
			document = json.load(handle)
	except (OSError, UnicodeDecodeError, ValueError) as exc:
		raise ThemeError("cannot read {}: {}".format(target, exc))
	errors = validate(document)
	if errors:
		raise ThemeError("invalid theme: {}: {}".format(
			target, "; ".join(errors)))
	if str(document.get("name")).strip().lower() != name:
		raise ThemeError("theme name {!r} does not match {}".format(
			document.get("name"), target.name))
	normalized = _ordered(document, lower=False)
	_CACHE.clear()
	if key is not None:
		_CACHE[key] = normalized
	return _copy(normalized)


def selection():
	"""(theme name, look selector) this checkout selects, legacy value migrated."""
	name, selector = _read_selection_file()
	if selector is None:
		legacy = _legacy_selection()
		selector = legacy[1] if legacy is not None else DEFAULT_LOOK
	return (name or DEFAULT_THEME), selector


def _read_selection_file():
	parser = configparser.ConfigParser()
	try:
		with open(theme_file(), "r", encoding="utf-8") as handle:
			parser.read_file(handle)
	except (OSError, UnicodeDecodeError, configparser.Error):
		return None, None
	name = str(parser.get("theme", "name", fallback="")).strip().lower()
	selector = fold(parser.get("theme", "look", fallback=""))
	if selector not in SELECTORS:
		selector = None
	return (name if _SLUG.match(name) else None), selector


def _legacy_selection():
	"""(DEFAULT_THEME, selector) for an old `config.ini [theme] mode`, or None."""
	try:
		mode = config.get("theme", "mode", None)
	except (configparser.Error, ValueError):
		return None
	if mode is None or not str(mode).strip():
		return None
	return DEFAULT_THEME, LEGACY_LOOKS.get(fold(mode), DEFAULT_LOOK)


def _selector_for(look):
	"""Canonical selector for a selector or look id, or None when unknown."""
	look_id = SELECTORS.get(fold(look))
	return SELECTOR_OF[look_id] if look_id is not None else None


def resolve(name=None, look=None):
	"""(theme name, look id) for a call; never raises, falls back to built-in."""
	selected_name, selected_selector = selection()
	candidate = DEFAULT_THEME if name is None or not str(name).strip() \
		else str(name).strip().lower()
	try:
		load_theme(candidate)
	except (ThemeError, OSError):
		return DEFAULT_THEME, "default"
	if look is not None and str(look).strip():
		return candidate, SELECTORS.get(fold(look), "default")
	if candidate == selected_name:
		return candidate, SELECTORS.get(selected_selector, "default")
	return candidate, "default"


def look_palette(name=None, look=None):
	"""Copy of one look's eleven hexes; never raises."""
	theme_name, look_id = resolve(name, look)
	try:
		return dict(load_theme(theme_name)["looks"][look_id])
	except (ThemeError, KeyError, OSError):
		return dict(BUILTIN_LOOKS[look_id])


def document(name=None):
	"""The active (or named) validated document, or the built-in equivalent."""
	try:
		return load_theme(resolve(name)[0])
	except (ThemeError, OSError):
		return _copy(BUILTIN_DOCUMENT)


def properties(name=None):
	"""Copy of the document's rendering properties; never raises."""
	return dict(document(name)["properties"])


def set_selection(name=None, look=None):
	"""Write theme.ini; False when unwritable, `ThemeError` on a bad value."""
	candidate, selector = selection()
	if name is not None and str(name).strip():
		candidate = str(name).strip().lower()
		if not _SLUG.match(candidate):
			raise ThemeError("invalid theme name: {!r}".format(name))
		if not _path_for(candidate).is_file():
			raise ThemeError("no theme file: {}".format(_path_for(candidate)))
	if look is not None and str(look).strip():
		selector = _selector_for(look)
		if selector is None:
			raise ThemeError("invalid look: {!r}".format(look))
	return _write_selection(candidate, selector)


def migrate():
	"""Persist a legacy `config.ini [theme] mode` into theme.ini, once."""
	if theme_file().exists():
		return True
	legacy = _legacy_selection()
	return True if legacy is None else _write_selection(*legacy)


def _write_selection(name, selector):
	"""Atomic write of theme.ini; False when the file cannot be written."""
	try:
		_atomic_write(theme_file(), (
			"# catro-scripts theme selection (project-local; gitignored).\n"
			"[theme]\nname = {}\nlook = {}\n".format(name, selector)))
	except OSError:
		return False
	return True


def save_theme(document, overwrite=False):
	"""Validate and atomically write `themes/<name>.json`; returns the path."""
	errors = validate(document)
	if errors:
		raise ThemeError("invalid theme: {}".format("; ".join(errors)))
	canonical = _ordered(document)
	target = _path_for(canonical["name"])
	if target.exists() and not overwrite:
		raise ThemeError("theme file exists: {}".format(target))
	try:
		_atomic_write(target, json.dumps(canonical, indent=2) + "\n", True)
	except OSError as exc:
		raise ThemeError("cannot write {}: {}".format(target, exc))
	_CACHE.clear()
	return str(target)


def _atomic_write(target, text, make_dir=False):
	"""Write through a sibling temp file + `os.replace`; re-raises `OSError`."""
	temp = target.with_name(target.name + ".tmp")
	try:
		if make_dir:
			target.parent.mkdir(parents=True, exist_ok=True)
		with open(temp, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(text)
		os.replace(str(temp), str(target))
	except OSError:
		try:
			os.unlink(str(temp))
		except OSError:
			pass
		raise
