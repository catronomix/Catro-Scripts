# OSC 8 hyperlinks: the one place that spells the escape
"""
			OSC 8 HYPERLINKS
			================
A terminal that understands OSC 8 turns a wrapped run of text into a clickable
link without changing a single visible column, so a reader can keep painting the
same styled text and only the bytes around it change.

`wrap()` is the single source of the byte shape (empty params, ST terminator):
`\\x1b]8;;URL\\x1b\\\\ text \\x1b]8;;\\x1b\\\\`. `supported()` is the single
support decision and reads only the capability record `tui.caps.detect()`
already built; `is_openable()` gates the URL itself, so a weird or relative
destination degrades to plain text instead of being embedded raw.

`paint()` is the curses seam: a curses window counts every byte given to
`addstr` as a cell, so an embedded sequence is painted as literal `^[]8;;...`
and can be clipped. Instead the visible run is drawn normally and re-emitted
here through the terminal's raw channel (`putp`), positioned with terminfo's own
cursor-address and coloured from the cell's pair, so the terminal sees
open + text + close in one undroppable write while the cell grid never sees a
byte of it.
"""

import os

from . import caps

_OPEN = "\x1b]8;;{}\x1b\\"
_CLOSE = "\x1b]8;;\x1b\\"

# Only destinations a terminal can hand to a browser/ mail client. Relative
# paths, anchors and custom schemes stay plain text.
_SCHEMES = ("http://", "https://", "mailto:")

# True on a real Windows host; tests patch it. The raw re-emission below is only
# proven through a POSIX pty (ncurses writes it unmodified); a Windows console
# path through PDCurses has no such evidence, so it degrades to plain text.
_IS_WINDOWS = os.name == "nt"


def supported(cap=None):
	"""True when this terminal is expected to honour OSC 8."""
	cap = caps.detect() if cap is None else cap
	if cap.level == "none" or cap.plain:
		return False
	return not _IS_WINDOWS


def wrap(url, text, cap=None):
	"""`text` as an OSC 8 link to `url`, or `text` unchanged when unsupported."""
	if not is_openable(url) or not supported(cap):
		return text
	return _OPEN.format(url) + text + _CLOSE


def paint(y, x, text, url, attr=0, pair=0, cap=None):
	"""Re-emit `text` at cell (y, x) wrapped in its link, outside curses' grid.

	The run must already be on screen at that spot (curses painted it); this
	rewrites the same characters with the pair's colours and `attr`'s
	attributes, between the open and close sequences, in one raw write. It
	returns False, emitting nothing, when the terminal or the colour/attribute
	capabilities cannot carry the run, so the visible text simply stays.
	"""
	if not text or not supported(cap) or not is_openable(url):
		return False
	import curses

	move = curses.tigetstr("cup")
	setaf = curses.tigetstr("setaf")
	setab = curses.tigetstr("setab")
	done = curses.tigetstr("sgr0")
	if not (move and setaf and setab and done):
		return False
	attributes = _attributes(curses, attr)
	if attributes is None:
		return False
	fg, bg = curses.pair_content(pair)
	colours = curses.tparm(setaf, fg) if fg >= 0 else b""
	if bg >= 0:
		colours += curses.tparm(setab, bg)
	curses.putp(curses.tparm(move, y, x) + colours + attributes
				+ _OPEN.format(url).encode("utf-8") + text.encode("utf-8")
				+ _CLOSE.encode("ascii") + done)
	return True


def _attributes(curses, attr):
	"""Capability strings for the set attributes, or None when any is missing."""
	parts = []
	for name, bit in (("bold", curses.A_BOLD), ("dim", curses.A_DIM),
					  ("sitm", curses.A_ITALIC), ("smul", curses.A_UNDERLINE)):
		if not attr & bit:
			continue
		value = curses.tigetstr(name)
		if value is None:
			return None
		parts.append(value)
	return b"".join(parts)


def is_openable(url):
	"""True for a non-empty absolute http/https/mailto destination."""
	if not isinstance(url, str) or not url:
		return False
	if any(ord(char) <= 32 or ord(char) == 127 for char in url):
		return False
	return url.lower().startswith(_SCHEMES)
