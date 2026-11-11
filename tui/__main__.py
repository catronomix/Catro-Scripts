# `python -m tui` / `theme` entrypoint
"""
			THEME COMMAND
			==============
Shows and changes the checkout-local terminal preferences. `theme.py` and
`python -m tui` share this implementation, so both answer the same commands:

	theme                     overview: name, look, level, style, paths, writability
	theme <name>              select themes/<name>.json
	theme soft|default        the default look
	theme light|contrast-light
	theme dark|contrast-dark  the contrast-dark look (the legacy `dark` spelling
	                          is a look here, not the old `soft` alias)
	theme toggle              cycle looks
	theme list                available themes
	theme palette             list the active palette
	theme set <key> <value>   change one setting (theme.name, theme.look,
	                          theme.mode, color.level, table.style)
	theme edit [name]         full-screen editor (needs a terminal)

The listing pages render through `tui.chrome`: a masthead, one `field` per fact
and, for the palette, a swatch painted in each key's own palette colour next to
the readable hex value. Message lines (usage, invalid value, unwritable file)
keep their exact wording and only gain a semantic colour, so piped output and
the pinned exit codes do not move. A broken install (the shipped
`themes/cozypurple.json` missing or unreadable) is the one `ThemeError` no command
can place; `main()` turns it into one error line and exit 2 instead of a
traceback. Nothing here runs at import time, and the
editor is imported only when `edit` actually launches.
"""

from .theme_cli import (USAGE, THEME_ORDER, VALID, _dispatch, _edit,  # noqa: F401
						_error_line, _look_selector, _page, _set,
						_select_theme, _write, _write_look, main,
						palette_rows, summary, theme_rows)

if __name__ == "__main__":
	raise SystemExit(main())
