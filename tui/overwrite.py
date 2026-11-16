# Overwrite decisions for reruns of the batch video tools
"""
			OVERWRITE PROMPT
			================
One question asked when a target file already exists, so a rerun cannot replace
a file behind the user's back: `y` overwrites this target, `n` skips it, `Y`
overwrites every later target without asking, `a` aborts the run.

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
"""

import sys

from . import caps, keys, palette, text

QUESTION = "File exists! Overwrite?"
HINT = "([y]es, [n]o, [Y]es to all, [a]bort): "
PROMPT = QUESTION + " " + HINT

_ANSWERS = {"y": "yes", "n": "no", "Y": "all", "a": "abort"}
_ERASE = "\r\x1b[2K"


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
	"""One run's y/n/Y/a policy; `allow()` is True when a target may be replaced."""

	def __init__(self, cap=None, box=None, *, stream=None, reader=None):
		self.cap = cap or caps.detect()
		self.box = box
		if stream is None and box is not None:
			stream = box.stream
		self.stream = sys.stdout if stream is None else stream
		self._reader = reader or keys.read_key
		self.overwrite_all = False
		self.aborted = False

	@property
	def interactive(self):
		"""True when the run can ask without ever waiting on a pipe."""
		return bool(self.cap.isatty and not self.cap.plain and _stdin_tty())

	@property
	def transient(self):
		"""True when the painted row can be erased (escapes are available)."""
		return self.interactive and self.cap.level != "none"

	def allow(self):
		"""True replaces the existing target; False skips it (see `aborted`)."""
		if self.aborted:
			return False
		if self.overwrite_all:
			return True
		if not self.interactive:
			return False
		if not self.transient:
			return self._apply(self._read_line())
		while True:
			self._paint()
			try:
				key = self._read_key()
			finally:
				self._erase()
			if key == "esc":
				key = "a"
			answer = _ANSWERS.get(key)
			if answer is not None:
				return self._apply(key)

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

	def _apply(self, key):
		answer = _ANSWERS.get(key)
		if answer is None:
			return False
		if answer == "all":
			self.overwrite_all = True
		if answer == "abort":
			self.aborted = True
		return answer in ("yes", "all")

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
