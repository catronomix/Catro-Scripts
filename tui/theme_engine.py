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
all-or-nothing, so a typo can never ship a half-theme. The tables and their
checker live in `tui.theme_schema` and are re-exported here, so this module
stays the public surface while `theme_schema` owns what "valid" means.

Reads never raise for a bad theme *name*: a missing, unreadable or invalid
theme file, and a malformed `theme.ini`, fall back to the shipped
`themes/cozypurple.json` default look. That file is the only copy of the shipped
palette, so it is loaded on first fallback use (never at import) and a missing
or unreadable one raises `ThemeError` at that point - a broken install must not
be masked by an embedded table. Only the paths a user asks for - `load_theme()`,
`set_selection()`, `save_theme()` - otherwise raise `ThemeError`, so the CLI can
print one line and exit 2.

Precedence is override, then `CATRO_THEME` (both in `tui.palette`), then
`theme.ini`, then the migrated legacy `config.ini [theme] mode`, then the
built-in default. The legacy value is migrated in memory on read and persisted
by the first write, so a plain render never creates files.

Reads are memoized: the document cache is keyed by the theme file's path, mtime
and size, and the selection memo by the same triple for `theme.ini` (plus
`config.ini`, which only matters while a legacy value is being migrated). One
directory save, one `theme.ini` write and one `config.ini` edit therefore
invalidate exactly what changed, while a hot renderer can resolve a look palette
hundreds of times per frame without touching the disk.

Test seams: assign `THEME_FILE` / `THEMES_DIR` to redirect reads and writes (tests
never touch the repository); `None` restores the project folder. Import is inert:
no printing, no write, no terminal mode change, no third-party or platform import.
"""

import configparser
import copy
import json
import os
from pathlib import Path

from . import config

# The schema tables and validation live in their own module; re-exported here so
# callers and tests keep using the engine namespace.
from .theme_schema import (DEFAULT_LOOK, DEFAULT_THEME, DOCUMENT_KEYS,  # noqa: F401
						   LEGACY_LOOKS, LOOKS, PALETTE_KEYS, PROPERTY_VALUES,
						   SELECTOR_OF, SELECTORS, SLUG,
						   canonical_hex, validate)


# Overrides for tests; see the module docstring.
THEME_FILE = None
THEMES_DIR = None

# The project folder, resolved once: `themes_dir()`/`theme_file()` are on the
# per-frame path, and `Path.resolve()` is a syscall per call.
_PROJECT = Path(__file__).resolve().parents[1]

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
	return _PROJECT / "theme.ini"


def themes_dir():
	"""Absolute path of the directory that holds the theme documents."""
	if THEMES_DIR is not None:
		return Path(THEMES_DIR)
	return _PROJECT / "themes"


def list_themes():
	"""Sorted theme slugs in `themes/`; [] when the directory is absent."""
	try:
		return sorted(entry.stem for entry in themes_dir().glob("*.json")
					  if entry.is_file())
	except OSError:
		return []


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
	# `os.stat` on the str form, not `Path.stat()`: this runs once per colour
	# resolution on the editor's hot path.
	try:
		info = os.stat(str(target))
	except OSError:
		return None
	return (str(target), info.st_mtime_ns, info.st_size)


def load_theme(name=None):
	"""The validated document for `name`; raises `ThemeError`.

	Returns a fresh copy: the cached document is shared, so a caller that edits
	an editor draft can never change what the next read hands out.
	"""
	name = str(name if name is not None else DEFAULT_THEME).strip().lower()
	if not SLUG.match(name):
		raise ThemeError("invalid theme name: {!r}".format(name))
	return _copy(_document_for(name))


def _cached_document(name):
	"""The cached document for `name`; internal callers only, never mutate it.

	Everything below (`resolve`, `look_palette`, `properties`) reads through
	this, so a hot renderer costs one stat and no copy per colour.
	"""
	name = str(name).strip().lower()
	if not SLUG.match(name):
		raise ThemeError("invalid theme name: {!r}".format(name))
	key = _cache_key(_path_for(name))
	cached = _CACHE.get(key)
	if cached is not None:
		return cached
	return _document_for(name)


def _document_for(name):
	"""Read, validate and cache `themes/<name>.json`; raises `ThemeError`."""
	target = _path_for(name)
	key = _cache_key(target)
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
	return normalized


def builtin_document():
	"""Fresh copy of the shipped default document; raises `ThemeError`.

	`themes/cozypurple.json` is the only copy of the shipped palette: the
	built-in fallback *is* that file, read on first use (lazily, once per file
	version, cached like any other document). No hex table is embedded here, so
	a deliberate theme change is a one-file commit and a missing or unreadable
	shipped file surfaces as one `ThemeError` instead of a second source that
	could silently drift.
	"""
	try:
		return _copy(_cached_document(DEFAULT_THEME))
	except ThemeError as exc:
		raise ThemeError(
			"shipped default theme is unavailable: {}".format(exc))


def builtin_looks():
	"""Copy of the shipped document's looks (look id -> eleven hexes)."""
	return builtin_document()["looks"]


def builtin_properties():
	"""Copy of the shipped document's rendering properties."""
	return builtin_document()["properties"]


def selection():
	"""(theme name, look selector) this checkout selects, legacy value migrated.

	Memoized by the mtime/size of `theme.ini` and `config.ini`, so a frame that
	resolves hundreds of colours reads the selection files once.
	"""
	key = ("selection", _cache_key(theme_file()), _cache_key(config.path()))
	cached = _CACHE.get(key)
	if cached is not None:
		return cached
	name, selector = _read_selection_file()
	if selector is None:
		legacy = _legacy_selection()
		selector = legacy[1] if legacy is not None else DEFAULT_LOOK
	value = (name or DEFAULT_THEME), selector
	_CACHE[key] = value
	return value


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
	return (name if SLUG.match(name) else None), selector


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
	"""(theme name, look id) for a call; never raises, falls back to built-in.

	No `name` means the theme `theme.ini` selects, so `document()`,
	`properties()` and `look_palette()` follow the selection instead of always
	describing `cozypurple`. An unreadable selected theme still falls back to
	the built-in pair.
	"""
	selected_name, selected_selector = selection()
	if name is None or not str(name).strip():
		candidate = selected_name or DEFAULT_THEME
	else:
		candidate = str(name).strip().lower()
	try:
		_cached_document(candidate)
	except (ThemeError, OSError):
		return DEFAULT_THEME, "default"
	if look is not None and str(look).strip():
		return candidate, SELECTORS.get(fold(look), "default")
	if candidate == selected_name:
		return candidate, SELECTORS.get(selected_selector, "default")
	return candidate, "default"


def look_palette(name=None, look=None):
	"""Copy of one look's eleven hexes; never raises for a bad theme name.

	The fallback is the shipped `cozypurple` look, so it raises `ThemeError`
	only when the shipped file itself is missing or unreadable.
	"""
	theme_name, look_id = resolve(name, look)
	try:
		return dict(_cached_document(theme_name)["looks"][look_id])
	except (ThemeError, KeyError, OSError):
		return builtin_looks()[look_id]


def document(name=None):
	"""The active (or named) validated document, or the shipped equivalent."""
	try:
		return _copy(_cached_document(resolve(name)[0]))
	except (ThemeError, OSError):
		return builtin_document()


def properties(name=None):
	"""Copy of the document's rendering properties; never raises for a bad name."""
	try:
		return dict(_cached_document(resolve(name)[0])["properties"])
	except (ThemeError, KeyError, OSError):
		return builtin_properties()


def set_selection(name=None, look=None):
	"""Write theme.ini; False when unwritable, `ThemeError` on a bad value."""
	candidate, selector = selection()
	if name is not None and str(name).strip():
		candidate = str(name).strip().lower()
		if not SLUG.match(candidate):
			raise ThemeError("invalid theme name: {!r}".format(name))
		# Selecting is a user request: an invalid or corrupt file must surface
		# here (CLI exit 2) rather than be selected and silently ignored.
		load_theme(candidate)
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
	# The file mtime is the cache key, but a same-tick rewrite could keep it, so
	# the write itself drops every selection memo it just invalidated.
	for key in [key for key in _CACHE if isinstance(key, tuple)
				and key and key[0] == "selection"]:
		_CACHE.pop(key, None)
	return True


def save_theme(document, overwrite=False):
	"""Validate and atomically write `themes/<name>.json`; returns the path.

	The write is canonical in structure (key order, 2-space indent, one
	trailing LF, a `#` on every hex) but keeps the document's own hex case, so
	an already-canonical document round-trips byte-identically and a
	non-canonical one is canonicalised exactly once. `theme edit` therefore
	only ever shows the lines the user actually changed.
	"""
	errors = validate(document)
	if errors:
		raise ThemeError("invalid theme: {}".format("; ".join(errors)))
	canonical = _ordered(document, lower=False)
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
