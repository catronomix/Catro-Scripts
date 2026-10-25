# `python -m tui` / `theme` command implementation
"""
			THEME COMMAND
			==============
Shows and changes the checkout-local terminal preferences. `theme.py` and
`python -m tui` share this implementation, so both answer the same commands:

	theme                     show mode/level/style, config path and writability
	theme dark|light|toggle   change theme.mode
	theme set <key> <value>   change one setting
	theme palette             list the active palette

Writes are optional: when config.ini cannot be written this prints one line
naming the path and exits 1. Nothing here runs at import time.
"""

import sys

from . import caps, config, palette

USAGE = "usage: theme [show|dark|light|toggle|set <key> <value>|palette]"

VALID = {
	"theme.mode": ("dark", "light"),
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
	if command in ("dark", "light"):
		return _write("theme.mode", command)
	if command == "toggle":
		return _write("theme.mode", "light" if palette.theme() == "dark" else "dark")
	if command == "set":
		if len(args) != 3:
			out.write(USAGE + "\n")
			return 2
		key, value = args[1].strip().lower(), args[2].strip().lower()
		if key not in VALID or value not in VALID[key]:
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
