# Display-width text helpers
"""
			TERMINAL TEXT METRICS
			=====================
Width-aware helpers shared by the table, prompt and pager code. East Asian wide
and fullwidth glyphs count as two cells, combining marks as zero. ANSI escapes
are not measured: `strip_ansi()` removes them first, and no helper here guesses
whether a string already contains styling.
"""

import re
import unicodedata

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ZERO_WIDTH_CATEGORIES = ("Mn", "Me", "Cf")


def char_width(char):
	"""Cells occupied by one character: 0, 1 or 2."""
	if unicodedata.combining(char) or unicodedata.category(char) in _ZERO_WIDTH_CATEGORIES:
		return 0
	return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def display_width(text):
	"""Visible width of `text`, ignoring escape sequences it may contain."""
	total = 0
	for char in _ANSI.sub("", str(text)):
		total += char_width(char)
	return total


def truncate(text, width, marker=".."):
	"""Cut `text` to `width` cells, appending `marker` when it had to shrink."""
	text = str(text)
	if width <= 0:
		return ""
	if display_width(text) <= width:
		return text
	keep = width - display_width(marker)
	if keep <= 0:
		return _head(marker, width)[0]
	return _head(text, keep)[0] + marker


def pad(text, width):
	"""Right-pad `text` with spaces to `width` cells (never truncates)."""
	text = str(text)
	return text + " " * max(0, width - display_width(text))


def wrap(text, width):
	"""Greedy word wrap; words wider than `width` are split."""
	if width <= 0:
		return []
	lines = []
	for paragraph in str(text).splitlines() or [""]:
		line = ""
		for word in paragraph.split():
			candidate = word if not line else "{} {}".format(line, word)
			if display_width(candidate) <= width:
				line = candidate
				continue
			if line:
				lines.append(line)
				line = ""
			while display_width(word) > width:
				head, word = _head(word, width)
				lines.append(head)
			line = word
		lines.append(line)
	return lines


def strip_ansi(text):
	"""`text` without ANSI escape sequences."""
	return _ANSI.sub("", str(text))


def _head(text, width):
	"""(prefix within `width` cells, remainder) - always consumes something."""
	out = []
	used = 0
	for index, char in enumerate(text):
		size = char_width(char)
		if used + size > width:
			if not out:
				# A single over-wide glyph: emit it whole instead of looping.
				return char, text[index + 1:]
			return "".join(out), text[index:]
		out.append(char)
		used += size
	return "".join(out), ""
