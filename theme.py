# Show and change the shared terminal theme
"""
			CATRO-SCRIPTS THEME
			====================
Shows the terminal preferences this checkout uses and changes them in the
checkout-local `config.ini` (never in the current directory, never per user).

Everything the rest of the collection renders - colour level, Unicode box
glyphs, table style - consults the same file, so one command switches the whole
toolset between the three shipped palettes: dark (house identity), light and
high-contrast.

Features:
	- Shows theme mode, colour level, table style, config path and writability.
	- `theme dark|light|high-contrast|toggle` switches the palette.
	- `theme set <key> <value>` changes one setting; keys are theme.mode,
	  color.level and table.style.
	- Environment overrides still win per run: NO_COLOR, FORCE_COLOR,
	  CATRO_COLOR, CATRO_THEME, CATRO_ASCII.

Usage:
	catro-scripts theme
	catro-scripts theme light
	catro-scripts theme high-contrast
	catro-scripts theme toggle
	catro-scripts theme set color.level 256
"""

import sys

from tui.__main__ import main

if __name__ == "__main__":
	try:
		sys.exit(main())
	except BrokenPipeError:
		# The reader went away; stop quietly instead of writing into the pipe.
		sys.exit(0)
