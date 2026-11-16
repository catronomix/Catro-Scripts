# Overwrite decisions for reruns of the batch video tools
"""
			OVERWRITE PROMPT
			================
One question asked when a target file already exists, so a rerun cannot replace
a file behind the user's back: `y` overwrites this target, `n` skips it, `r`
writes it under the next free `name (2).ext` instead, `Y` overwrites every later
target without asking, `R` renames every later target the same way, `a` aborts
the run.

On a terminal the question is a transient row painted under the caller's batch
box: the frame is parked with the cursor under its last line, the question is
written there, one key is read in cbreak mode, the row is erased and the box is
repainted in place (`BatchBox.update()` rewinds over its own lines), so no
prompt text survives and the next repaint lands on the top border. Without a box
the row is erased the same way and nothing needs repainting.

A run that cannot ask never waits: a pipe, a forced-colour pipe, or a stdin that
is not a terminal treats an existing target as `n`. A level-`none` terminal
reads a line instead of a key, because erasing and repainting need escapes; the
question is then ordinary output, exactly like the box itself at that level.

`next_free()` is the single source of truth for a renamed target (`name (2).ext`,
`name (3).ext`, ...); `settle()` re-runs that scan just before the write so a
sibling process that claimed the name in the meantime costs the next number, not
the file.
"""

import os
import sys

from . import caps, keys, palette, text

QUESTION = "File exists! Overwrite?"
HINT = "([y]es, [n]o, [r]ename, [Y]es to all, [R]ename all, [a]bort): "
PROMPT = QUESTION + " " + HINT

_ANSWERS = {"y": "yes", "n": "no", "r": "rename", "Y": "all", "R": "rename_all",
			"a": "abort"}
_ERASE = "\r\x1b[2K"


def next_free(path):
	"""The next free `stem (N)ext` for `path`; the zip convention starts at 2."""
	stem, ext = os.path.splitext(path)
	number = 2
	candidate = "{} ({}){}".format(stem, number, ext)
	while os.path.exists(candidate):
		number += 1
		candidate = "{} ({}){}".format(stem, number, ext)
	return candidate


def settle(path, effective, attempts=8):
	"""Re-resolve a decided rename just before the write.

	The `next_free` scan and the FFmpeg run are not atomic: a sibling can claim
	the chosen name in between, so the same scan runs again and the caller
	writes to the number it now returns.
	"""
	for _ in range(attempts):
		fresh = next_free(path)
		if fresh == effective:
			break
		effective = fresh
	return effective


def _stdin_tty():
	try:
		return bool(sys.stdin.isatty())
	except (AttributeError, ValueError, OSError):
		return False


def _question(cap):
	"""The styled question; truncated so the painted row can never wrap."""
	width = cap.width
	if width and text.display_width(PROMPT) > int(width) - 1:
		return palette.style(text.truncate(PROMPT, max(1, int(width) - 1)),
							 fg="fg-warn", cap=cap)
	return (palette.style(QUESTION, fg="fg-warn", cap=cap) + " "
			+ palette.style(HINT, fg="fg-muted", cap=cap))


class OverwriteGate:
	"""One run's y/n/r/Y/R/a policy; `decide()` names the action per target."""

	def __init__(self, cap=None, box=None, *, stream=None, reader=None):
		self.cap = cap or caps.detect()
		self.box = box
		if stream is None and box is not None:
			stream = box.stream
		self.stream = sys.stdout if stream is None else stream
		self._reader = reader or keys.read_key
		self.overwrite_all = False
		self.rename_all = False
		self.aborted = False

	@property
	def interactive(self):
		"""True when the run can ask without ever waiting on a pipe."""
		return bool(self.cap.isatty and not self.cap.plain and _stdin_tty())

	@property
	def transient(self):
		"""True when the painted row can be erased (escapes are available)."""
		return self.interactive and self.cap.level != "none"

	def allow(self, path=None):
		"""Compat shim: True replaces the target; skip, rename and abort do not."""
		return self.decide(path)[0] == "overwrite"

	def decide(self, path):
		"""One answer for `path`: `(action, effective path)`.

		`action` is `overwrite`, `rename`, `skip` or `abort`; a rename returns
		the free name `next_free()` picked as the effective path.
		"""
		if self.aborted:
			return ("abort", path)
		if self.overwrite_all:
			return ("overwrite", path)
		if self.rename_all:
			return ("rename", next_free(path) if path else path)
		if not self.interactive:
			return ("skip", path)
		if not self.transient:
			return self._resolve(self._read_line(), path)
		return self._resolve(self._ask(), path)

	def _ask(self):
		"""Paint and read until a known answer arrives; one question per try."""
		while True:
			self._paint()
			try:
				key = self._read_key()
			finally:
				self._erase()
			if key == "esc":
				key = "a"
			if key in _ANSWERS:
				return key

	def _read_key(self):
		"""One key token; Ctrl-C / closed stdin abort, like pressing `a`."""
		try:
			with keys.raw_mode():
				return self._reader()
		except (EOFError, KeyboardInterrupt):
			return "a"

	def _read_line(self):
		"""One echoed answer line for a level-`none` terminal."""
		while True:
			try:
				raw = input(_question(self.cap))
			except (EOFError, KeyboardInterrupt):
				return "a"
			key = (raw or "").strip()[:1]
			if key in _ANSWERS:
				return key

	def _resolve(self, key, path):
		"""Map an answer key to its `(action, effective)` pair."""
		answer = _ANSWERS[key]
		if answer == "all":
			self.overwrite_all = True
		elif answer == "rename_all":
			self.rename_all = True
		elif answer == "abort":
			self.aborted = True
		if answer in ("yes", "all"):
			return ("overwrite", path)
		if answer in ("rename", "rename_all"):
			return ("rename", next_free(path) if path else path)
		return ("abort" if answer == "abort" else "skip", path)

	def _paint(self):
		"""Write the question on the row under the frame, without a newline."""
		self.stream.write(_question(self.cap))
		self.stream.flush()

	def _erase(self):
		"""Clear the transient row and repaint the box above it."""
		self.stream.write(_ERASE)
		if self.box is not None:
			self.box.update()
		else:
			self.stream.flush()
