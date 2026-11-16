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

Width accounting belongs to the caller: the escapes are zero-width, so it wraps
the visible text it already measured.
"""

from . import caps

_OPEN = "\x1b]8;;{}\x1b\\"
_CLOSE = "\x1b]8;;\x1b\\"

# Only destinations a terminal can hand to a browser/ mail client. Relative
# paths, anchors and custom schemes stay plain text.
_SCHEMES = ("http://", "https://", "mailto:")


def supported(cap=None):
	"""True when this terminal is expected to honour OSC 8."""
	cap = caps.detect() if cap is None else cap
	if cap.level == "none" or cap.plain:
		return False
	# The legacy Windows console has no VT processing: the bytes would show up
	# as text. Windows Terminal and mintty report their own reasons.
	return cap.reason != "windows-legacy-console"


def wrap(url, text, cap=None):
	"""`text` as an OSC 8 link to `url`, or `text` unchanged when unsupported."""
	if not is_openable(url) or not supported(cap):
		return text
	return _OPEN.format(url) + text + _CLOSE


def is_openable(url):
	"""True for a non-empty absolute http/https/mailto destination."""
	if not isinstance(url, str) or not url:
		return False
	if any(ord(char) <= 32 or ord(char) == 127 for char in url):
		return False
	return url.lower().startswith(_SCHEMES)
