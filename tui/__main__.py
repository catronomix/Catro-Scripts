# `python -m tui` / `theme` command implementation
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
the pinned exit codes do not move. Nothing here runs at import time, and the
editor is imported only when `edit` actually launches.
"""

import sys

from . import caps, chrome, config, palette, theme_engine

USAGE = ("usage: theme [show|list|palette|edit [name]|toggle|"
		 "soft|contrast-light|contrast-dark|<theme>|set <key> <value>]")

# Look ids in toggle order (also valid selector spellings).
THEME_ORDER = ("soft", "contrast-light", "contrast-dark")
MODES = ", ".join(THEME_ORDER)

VALID = {
	"color.level": ("auto", "none", "16", "256", "true"),
	"table.style": ("auto", "unicode", "ascii"),
}

# Key column of the settings block and the palette/list tables: the widest key
# ("color.level", "table.style") plus one cell, matching the old layout.
KEY_WIDTH = 11
PALETTE_KEY_WIDTH = 10
# ASCII fallback for the palette swatch, so a legacy codepage never raises.
SWATCH_GLYPH = "\u25a0"
SWATCH_ASCII = "#"


def _look_selector(value):
	"""Canonical look selector for a CLI spelling, else None.

	`theme_engine.SELECTORS` wins over `palette.THEME_ALIASES`: both spell
	`dark`, but the engine's table is the contract's (`dark` is the
	contrast-dark look), while the palette table keeps the legacy
	`dark -> soft` meaning for old `config.ini` files only.
	"""
	folded = palette.fold(value)
	look_id = theme_engine.SELECTORS.get(folded)
	if look_id is None:
		look_id = theme_engine.SELECTORS.get(
			palette.THEME_ALIASES.get(folded, ""))
	return theme_engine.SELECTOR_OF.get(look_id)


def summary(stream=None, cap=None):
	"""The `theme` overview, one `field` row per fact."""
	cap = cap or caps.detect(stream)
	return [
		chrome.field("theme.name", palette.theme_name(), width=KEY_WIDTH,
					 cap=cap),
		chrome.field("theme.look", palette.look(), width=KEY_WIDTH, cap=cap),
		# Kept for back-compat: the old row label prints the look id, so
		# scripts that read `theme.mode` keep working unchanged.
		chrome.field("theme.mode", palette.theme(), width=KEY_WIDTH, cap=cap),
		chrome.field(
			"color.level",
			"{} (effective {})".format(
				config.get("color", "level", "auto"), cap.level),
			width=KEY_WIDTH, cap=cap),
		chrome.field("table.style", config.get("table", "style", "auto"),
					 width=KEY_WIDTH, cap=cap),
		chrome.field("unicode", "yes" if cap.unicode else "ascii fallback",
					 width=KEY_WIDTH, cap=cap),
		chrome.field("config", config.path(), width=KEY_WIDTH, cap=cap),
		chrome.field("writable", "yes" if config.writable() else "no",
					 width=KEY_WIDTH, cap=cap),
	]


def theme_rows(cap):
	"""One `field` row per available theme, the selected one marked active."""
	active = theme_engine.selection()[0]
	rows = []
	for slug in theme_engine.list_themes():
		try:
			display = theme_engine.load_theme(slug).get("display") or slug
		except (theme_engine.ThemeError, OSError):
			display = "(invalid)"
		if slug == active:
			display = "{} (active)".format(display)
		rows.append(chrome.field(slug, display, width=KEY_WIDTH, cap=cap))
	return rows


def palette_rows(cap):
	"""One `field` row per palette key, each sample in that key's own colour.

	Piped, only the key and hex value survive (`key<TAB>#rrggbb`): the swatch
	is decoration for a terminal. The hex text is always present, so the page
	stays readable when the swatch downgrades or the theme is monochrome.
	"""
	glyph = SWATCH_GLYPH * 4 if cap.unicode else SWATCH_ASCII * 4
	rows = []
	for key, value in palette.palette().items():
		if cap.plain:
			sample = value
		else:
			sample = "{}  {}".format(
				palette.style(glyph, fg=key, cap=cap),
				palette.style(value, fg="muted", cap=cap))
		rows.append(chrome.field(key, sample, width=PALETTE_KEY_WIDTH,
								 cap=cap))
	return rows


def main(argv=None):
	"""Run one command; returns the process exit code."""
	args = list(sys.argv[1:] if argv is None else argv)
	out = sys.stdout
	cap = caps.detect(out)
	# Windows consoles need the ANSI bootstrap, but only when the page is
	# actually going to emit codes (a pipe or level "none" emits none).
	if not cap.plain and cap.level != "none":
		caps.init_ansi()
	command = palette.fold(args[0]) if args else "show"
	if command in ("show", "status", ""):
		out.write(_page("theme", "terminal preferences", summary(out, cap=cap),
						cap, warn=not config.writable()) + "\n")
		return 0
	if command in ("-h", "--help", "help"):
		out.write(palette.style(USAGE, fg="muted", cap=cap) + "\n")
		return 0
	if command == "list":
		out.write(_page("themes", "available themes", theme_rows(cap),
						cap) + "\n")
		return 0
	if command == "palette":
		out.write(_page("theme palette", palette.theme(), palette_rows(cap),
						cap) + "\n")
		return 0
	if command == "edit":
		return _edit(args[1] if len(args) > 1 else None, cap)
	if command == "toggle":
		index = THEME_ORDER.index(palette.theme())
		return _write_look(THEME_ORDER[(index + 1) % len(THEME_ORDER)], cap)
	if command == "set":
		return _set(args, out, cap)
	selector = _look_selector(command)
	if selector is not None:
		return _write_look(selector, cap)
	# Anything else is a theme name; the contract has no silent fallback.
	return _select_theme(command, out, cap)


def _set(args, out, cap):
	"""`set <key> <value>`, including the `theme.mode` legacy shape."""
	if len(args) != 3:
		out.write(palette.style(USAGE, fg="muted", cap=cap) + "\n")
		return 2
	key, raw = args[1].strip().lower(), args[2].strip()
	value = raw.lower()
	if key in ("theme.mode", "theme.look"):
		if _look_selector(value) is None:
			out.write(palette.style(
				"invalid {}: {} (valid: {})".format(key, raw, MODES),
				fg="error", cap=cap) + "\n")
			return 2
		return _write_look(value, cap)
	if key == "theme.name":
		return _select_theme(value, out, cap)
	if key in VALID and value in VALID[key]:
		return _write(key, value, cap)
	out.write(palette.style("invalid setting: {} {}".format(key, value),
							fg="error", cap=cap) + "\n")
	return 2


def _page(title, subtitle, rows, cap, warn=False):
	"""Masthead plus body rows; `warn` appends one closing status (the show page
	uses it to explain an unwritable config without changing the write-error
	message)."""
	lines = [chrome.header(title, subtitle, cap=cap)]
	lines.extend(row for row in rows if row)
	if warn:
		lines.append(chrome.rule(cap=cap))
		lines.append(chrome.status(
			"warn", "config.ini is not writable here: {}".format(config.path()),
			cap=cap))
	return "\n".join(lines)


def _write(key, value, cap):
	"""Write one config setting; 0 on success, 1 when the file is unwritable."""
	# Any write also performs the one-off legacy migration, so an old
	# `config.ini [theme] mode` lands in theme.ini instead of being shadowed.
	theme_engine.migrate()
	section, name = key.split(".", 1)
	if config.set(section, name, value):
		return 0
	sys.stdout.write(palette.style(
		"config.ini is not writable here: {}".format(config.path()),
		fg="error", cap=cap) + "\n")
	return 1


def _write_look(value, cap):
	"""Select a look in theme.ini; one error line and exit 1 when unwritable."""
	try:
		written = theme_engine.set_selection(look=value)
	except theme_engine.ThemeError as exc:
		sys.stdout.write(palette.style(
			"invalid theme.mode: {} ({})".format(value, exc),
			fg="error", cap=cap) + "\n")
		return 2
	if written:
		return 0
	sys.stdout.write(palette.style(
		"theme.ini is not writable here: {}".format(theme_engine.theme_file()),
		fg="error", cap=cap) + "\n")
	return 1


def _select_theme(name, out, cap):
	"""Select `themes/<name>.json`; a bad or missing file is one line + exit 2."""
	slug = palette.fold(name)
	target = theme_engine.themes_dir() / "{}.json".format(slug)
	try:
		theme_engine.load_theme(slug)
		written = theme_engine.set_selection(name=slug)
	except theme_engine.ThemeError as exc:
		message = str(exc)
		if str(target) not in message:
			message = "{} (expected {})".format(message, target)
		out.write(palette.style(message, fg="error", cap=cap) + "\n")
		return 2
	if written:
		return 0
	out.write(palette.style(
		"theme.ini is not writable here: {}".format(theme_engine.theme_file()),
		fg="error", cap=cap) + "\n")
	return 1


def _edit(name, cap):
	"""Launch the full-screen editor; off a tty `require_tty` exits 2 first."""
	caps.require_tty("theme edit")
	slug = palette.fold(name) if name else None
	try:
		document = (theme_engine.load_theme(slug) if slug
					else theme_engine.document())
	except theme_engine.ThemeError as exc:
		sys.stdout.write(palette.style(str(exc), fg="error", cap=cap) + "\n")
		return 2
	from .editor import ThemeEditor

	return ThemeEditor(slug, document=document, cap=cap).run()


if __name__ == "__main__":
	raise SystemExit(main())
