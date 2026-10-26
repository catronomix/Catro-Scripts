# Project-local terminal configuration (config.ini)
"""
			PROJECT CONFIGURATION
			=====================
Reads and (optionally) writes the checkout-local `config.ini` that holds the
terminal preferences: colour level and table style. Theme selection lives in
`theme.ini` and belongs to `tui.theme_engine`; an old `[theme] mode` value is
still readable here so the engine can migrate it.

Resolution is fixed to the project folder - `Path(__file__).parents[1]` - so it
is one file per checkout, never cwd, %APPDATA% or ~/.config.

Reads never raise: a missing, unreadable or malformed file silently falls back
to the built-in defaults below. Writes are optional and never happen at import
time; `set()` reports failure instead of raising, and the `theme` command turns
that into one line plus exit 1.

Test seam: assign `tui.config.CONFIG_FILE` to a path (str or Path) to redirect
every read and write, so tests never create a `config.ini` in the repository.
Assign `None` back to restore the project-folder behaviour.
"""

import configparser
import io
import os
from pathlib import Path

DEFAULTS = {
	"color": {"level": "auto"},
	"table": {"style": "auto"},
}

# Override for tests; see the module docstring.
CONFIG_FILE = None


def path():
	"""Absolute path of the config file this checkout uses."""
	if CONFIG_FILE is not None:
		return Path(CONFIG_FILE)
	return Path(__file__).resolve().parents[1] / "config.ini"


def _parser():
	"""Built-in defaults layered under whatever the file provides."""
	parser = configparser.ConfigParser()
	for section, values in DEFAULTS.items():
		parser[section] = dict(values)
	try:
		with open(path(), "r", encoding="utf-8") as handle:
			parser.read_file(handle)
	except (OSError, UnicodeDecodeError, configparser.Error):
		pass
	return parser


def get(section, key, default=None):
	"""Read one value; blank, missing or malformed input yields `default`."""
	fallback = DEFAULTS.get(section, {}).get(key, default)
	try:
		value = _parser().get(section, key, fallback=None)
	except (configparser.Error, ValueError):
		return fallback
	if value is None or not str(value).strip():
		return fallback
	return str(value).strip()


def set(section, key, value):  # noqa: A001 - the public name is part of the contract
	"""Write one value; return False when the file cannot be written."""
	parser = _parser()
	if not parser.has_section(section):
		parser.add_section(section)
	parser[section][str(key)] = str(value)
	text = io.StringIO()
	parser.write(text)
	try:
		with open(path(), "w", encoding="utf-8", newline="\n") as handle:
			handle.write(text.getvalue())
	except OSError:
		return False
	return True


def writable():
	"""True when `set()` has a plausible chance of succeeding here."""
	target = path()
	try:
		if target.exists():
			return target.is_file() and os.access(str(target), os.W_OK)
		return target.parent.is_dir() and os.access(str(target.parent), os.W_OK)
	except OSError:
		return False
