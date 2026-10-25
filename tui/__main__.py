# `python -m tui` / `theme` command implementation
"""
			THEME COMMAND
			==============
Shows and changes the checkout-local terminal preferences. `theme.py` and
`python -m tui` share this implementation, so both answer the same commands:

	theme                     show mode/level/style, config path and writability
	theme soft|contrast-light|contrast-dark|toggle
	                          change theme.mode (aliases: cozy, clight, cdark, hc)
	theme set <key> <value>   change one setting
	theme palette             list the active palette

The two listing pages render through `tui.chrome`: a masthead, one `field` per
fact and, for the palette, a swatch painted in each key's own palette colour
next to the readable hex value. Message lines (usage, invalid value, unwritable
config) keep their exact wording and only gain a semantic colour, so piped
output and the pinned exit codes do not move.

Writes are optional: when config.ini cannot be written this prints one line
naming the path and exits 1. Nothing here runs at import time.
"""

import sys

from . import caps, chrome, config, palette

USAGE = ("usage: theme [show|soft|contrast-light|contrast-dark|toggle|"
		 "set <key> <value>|palette]")

THEME_ORDER = ("soft", "contrast-light", "contrast-dark")
MODES = ", ".join(THEME_ORDER)

VALID = {
	"theme.mode": THEME_ORDER,
	"color.level": ("auto", "none", "16", "256", "true"),
	"table.style": ("auto", "unicode", "ascii"),
}

# Key column of the settings block and the palette table: the widest key
# ("color.level", "table.style") plus one cell, matching the old layout.
KEY_WIDTH = 11
PALETTE_KEY_WIDTH = 10
# ASCII fallback for the palette swatch, so a legacy codepage never raises.
SWATCH_GLYPH = "\u25a0"
SWATCH_ASCII = "#"


def summary(stream=None, cap=None):
	"""The `theme` overview, one `field` row per fact."""
	cap = cap or caps.detect(stream)
	return [
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
	command = args[0].lower() if args else "show"
	if command in ("show", "status"):
		out.write(_page("theme", "terminal preferences", summary(out, cap=cap),
						cap, warn=not config.writable()) + "\n")
		return 0
	if command in ("-h", "--help", "help"):
		out.write(palette.style(USAGE, fg="muted", cap=cap) + "\n")
		return 0
	if palette.fold(command) in palette.THEME_ALIASES:
		return _write("theme.mode", palette.normalize(command), cap)
	if command == "toggle":
		index = THEME_ORDER.index(palette.theme())
		return _write("theme.mode", THEME_ORDER[(index + 1) % len(THEME_ORDER)],
					  cap)
	if command == "set":
		if len(args) != 3:
			out.write(palette.style(USAGE, fg="muted", cap=cap) + "\n")
			return 2
		key, value = args[1].strip().lower(), args[2].strip().lower()
		if key == "theme.mode" and palette.fold(value) in palette.THEME_ALIASES:
			value = palette.normalize(value)
		if key not in VALID or value not in VALID[key]:
			if key == "theme.mode":
				message = "invalid theme.mode: {} (valid: {})".format(
					args[2].strip(), MODES)
			else:
				message = "invalid setting: {} {}".format(key, value)
			out.write(palette.style(message, fg="error", cap=cap) + "\n")
			return 2
		return _write(key, value, cap)
	if command == "palette":
		out.write(_page("theme palette", palette.theme(), palette_rows(cap),
						cap) + "\n")
		return 0
	out.write(palette.style(USAGE, fg="muted", cap=cap) + "\n")
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
	section, name = key.split(".", 1)
	# Any write canonicalises a legacy theme.mode (e.g. `dark` -> `soft`), so the
	# migration completes on `theme set` too, not only on `toggle`.
	current = config.get("theme", "mode", "soft")
	canonical = palette.normalize(current)
	if canonical != str(current).strip().lower():
		config.set("theme", "mode", canonical)
	if config.set(section, name, value):
		return 0
	sys.stdout.write(palette.style(
		"config.ini is not writable here: {}".format(config.path()),
		fg="error", cap=cap) + "\n")
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
