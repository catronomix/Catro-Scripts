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
"""

import os

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
