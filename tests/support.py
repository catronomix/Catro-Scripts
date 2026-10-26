# Shared environment hygiene for tests that spawn children
"""
			TEST ENVIRONMENT HYGIENE
			========================
Child processes and layout assertions must describe the repository, not the
developer's shell. `tui.caps` treats an explicit colour request as permission to
style a pipe (`plain` follows `FORCE_COLOR`/`CLICOLOR_FORCE`/`CATRO_COLOR`), so
an exported switch would turn a child's TAB records into a styled table and make
layout tests fail for a reason that has nothing to do with the code.

Build child environments through `clean_env()`; the names below are the ones a
shell can set that change colour, theme or glyph decisions.

The checkout itself is another environment input: `tui.config` and
`tui.theme_engine` read `config.ini`/`theme.ini` from the project folder, so an
operator who selects contrast-light there would change the bytes every default
look test pins. `isolate_checkout_config()` redirects those two seams at empty
files in a temp folder for the duration of a test module, so the suite describes
the code, not the checkout.
"""

import os
import shutil
import tempfile
from pathlib import Path

SCRUBBED = (
	"NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "CATRO_COLOR",
	"CATRO_ASCII", "CATRO_THEME",
)


def clean_env(**overrides):
	"""`os.environ` minus the colour/theme switches, plus `overrides`."""
	env = {key: value for key, value in os.environ.items()
		   if key not in SCRUBBED}
	env.update(overrides)
	return env


def isolate_checkout_config():
	"""Point the checkout config seams at empty files in a temp folder.

	`tui.config.CONFIG_FILE` and `tui.theme_engine.THEME_FILE` are the supported
	test seams (see their module docstrings); the built-in theme documents are
	left alone, so palette/table tests keep reading the shipped themes. Returns
	a callable that puts the previous seam values back and removes the temp
	folder, so a module can restore the developer's checkout in tearDown.
	"""
	from tui import config, theme_engine

	previous = (config.CONFIG_FILE, theme_engine.THEME_FILE)
	directory = tempfile.mkdtemp(prefix="catro-config-")
	config.CONFIG_FILE = Path(directory) / "config.ini"
	theme_engine.THEME_FILE = Path(directory) / "theme.ini"
	theme_engine._CACHE.clear()

	def restore():
		config.CONFIG_FILE, theme_engine.THEME_FILE = previous
		theme_engine._CACHE.clear()
		shutil.rmtree(directory, ignore_errors=True)

	return restore


def module_isolation():
	"""(setUpModule, tearDownModule) isolating the checkout for one module."""
	state = {}

	def setUpModule():
		state["restore"] = isolate_checkout_config()

	def tearDownModule():
		restore = state.pop("restore", None)
		if restore is not None:
			restore()

	return setUpModule, tearDownModule
