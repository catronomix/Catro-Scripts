# `python -m tui` / `theme` command implementation
"""
			THEME COMMAND
			==============
Shows and changes the checkout-local terminal preferences. `theme.py` and
`python -m tui` share this implementation, so both answer the same commands:

	theme                     show mode/level/style, config path and writability
	theme dark|light|high-contrast|toggle
	                          change theme.mode (aliases: highcontrast, hc)
	theme set <key> <value>   change one setting
	theme palette             list the active palette

Writes are optional: when config.ini cannot be written this prints one line
naming the path and exits 1. Nothing here runs at import time.
"""

import sys

from . import caps, config, palette

USAGE = ("usage: theme [show|dark|light|high-contrast|toggle|"
		 "set <key> <value>|palette]")

THEME_ORDER = ("dark", "light", "high-contrast")
MODES = ", ".join(THEME_ORDER)

VALID = {
	"theme.mode": THEME_ORDER,
	"color.level": ("auto", "none", "16", "256", "true"),
	"table.style": ("auto", "unicode", "ascii"),
}


def summary(stream=None):
	"""The `theme` overview, one line per fact."""
	cap = caps.detect(stream)
	return [
		"theme.mode   {}".format(palette.theme()),
		"color.level  {} (effective {})".format(
			config.get("color", "level", "auto"), cap.level),
		"table.style  {}".format(config.get("table", "style", "auto")),
		"unicode      {}".format("yes" if cap.unicode else "ascii fallback"),
		"config       {}".format(config.path()),
		"writable     {}".format("yes" if config.writable() else "no"),
	]


def main(argv=None):
	"""Run one command; returns the process exit code."""
	args = list(sys.argv[1:] if argv is None else argv)
	out = sys.stdout
	command = args[0].lower() if args else "show"
	if command in ("show", "status"):
		out.write("\n".join(summary(out)) + "\n")
		return 0
	if command in ("-h", "--help", "help"):
		out.write(USAGE + "\n")
		return 0
	if command in palette.THEME_ALIASES:
		return _write("theme.mode", palette.normalize(command))
	if command == "toggle":
		index = THEME_ORDER.index(palette.theme())
		return _write("theme.mode", THEME_ORDER[(index + 1) % len(THEME_ORDER)])
	if command == "set":
		if len(args) != 3:
			out.write(USAGE + "\n")
			return 2
		key, value = args[1].strip().lower(), args[2].strip().lower()
		if key == "theme.mode" and value in palette.THEME_ALIASES:
			value = palette.normalize(value)
		if key not in VALID or value not in VALID[key]:
			if key == "theme.mode":
				out.write("invalid theme.mode: {} (valid: {})\n".format(
					args[2].strip(), MODES))
			else:
				out.write("invalid setting: {} {}\n".format(key, value))
			return 2
		return _write(key, value)
	if command == "palette":
		for key, value in palette.palette().items():
			out.write("{:<10} {}\n".format(key, value))
		return 0
	out.write(USAGE + "\n")
	return 2


def _write(key, value):
	section, name = key.split(".", 1)
	if config.set(section, name, value):
		return 0
	sys.stdout.write("config.ini is not writable here: {}\n".format(config.path()))
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
