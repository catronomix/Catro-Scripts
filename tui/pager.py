# Paged output
"""
			PAGER
			======
`page()` shows long output one screen at a time on a tty (space/enter/n/pgdn
forward, b/p/pgup back, q/ESC exits) and prints everything unchanged when the
stream is not a tty. The interactive loop runs in `keys.raw_mode()` so keys
arrive one at a time (no Enter needed), and both the alternate screen and the
terminal settings are always restored, including on an exception.
"""

import sys

from . import keys
from .screen import Screen, terminal_size

_FORWARD = ("space", "enter", "n", "pagedown", "down")
_BACK = ("b", "p", "pageup", "up")
_EXIT = ("q", "esc", "ctrl-c")


def page(lines, page_size=None, stream=None):
	"""Show `lines`; returns when the reader is done or from a non-tty stream."""
	stream = sys.stdout if stream is None else stream
	lines = [str(line) for line in lines]
	if not _isatty(stream):
		for line in lines:
			stream.write(line + "\n")
		stream.flush()
		return
	size = int(page_size or max(1, terminal_size(stream)[1] - 1))
	offset = 0
	with Screen(stream) as screen, keys.raw_mode():
		while True:
			screen.clear()
			visible = lines[offset:offset + size]
			stream.write("\n".join(visible) + "\n")
			if offset + size < len(lines):
				stream.write("-- more ({} left) -- ".format(len(lines) - offset - size))
			stream.flush()
			key = keys.read_key()
			if key in _EXIT or (key is None and not lines[offset:offset + size]):
				return
			if key in _BACK:
				offset = max(0, offset - size)
			elif key in _FORWARD or key is None:
				offset += size
			if offset >= len(lines):
				return


def _isatty(stream):
	try:
		return bool(stream.isatty())
	except (AttributeError, ValueError, OSError):
		return False
