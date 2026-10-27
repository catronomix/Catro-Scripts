# Shared environment hygiene for tests that spawn children
"""
			TEST ENVIRONMENT HYGIENE
			========================
Child processes and layout assertions must describe the repository, not the
developer's shell. `tui.caps` treats an explicit colour request as permission to
style a pipe (`plain` follows `FORCE_COLOR`/`CLICOLOR_FORCE`/`CATRO_COLOR`), so
an exported switch would turn a child's TAB records into a styled table and make
layout tests fail for a reason that has nothing to do with the code.

Build child environments through `clean_env()`; the names below are the ones a
shell can set that change colour, theme or glyph decisions.

The checkout itself is another environment input: `tui.config` and
`tui.theme_engine` read `config.ini`/`theme.ini` from the project folder, so an
operator who selects contrast-light there would change the bytes every default
look test pins. `isolate_checkout_config()` redirects those two seams at empty
files in a temp folder for the duration of a test module, so the suite describes
the code, not the checkout.

`SgrTerminal`/`replay()`/`repaint_errors()` are the repaint oracle: they replay
a canvas frame through an independent SGR state machine, so a regression can
assert each cell's *effective* style instead of the bytes a painter emitted.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

SCRUBBED = (
	"NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "CATRO_COLOR",
	"CATRO_ASCII", "CATRO_THEME",
)


def clean_env(**overrides):
	"""`os.environ` minus the colour/theme switches, plus `overrides`."""
	env = {key: value for key, value in os.environ.items()
		   if key not in SCRUBBED}
	env.update(overrides)
	return env


def isolate_checkout_config():
	"""Point the checkout config seams at empty files in a temp folder.

	`tui.config.CONFIG_FILE` and `tui.theme_engine.THEME_FILE` are the supported
	test seams (see their module docstrings); the built-in theme documents are
	left alone, so palette/table tests keep reading the shipped themes. Returns
	a callable that puts the previous seam values back and removes the temp
	folder, so a module can restore the developer's checkout in tearDown.
	"""
	from tui import config, theme_engine

	previous = (config.CONFIG_FILE, theme_engine.THEME_FILE)
	directory = tempfile.mkdtemp(prefix="catro-config-")
	config.CONFIG_FILE = Path(directory) / "config.ini"
	theme_engine.THEME_FILE = Path(directory) / "theme.ini"
	theme_engine._CACHE.clear()

	def restore():
		config.CONFIG_FILE, theme_engine.THEME_FILE = previous
		theme_engine._CACHE.clear()
		shutil.rmtree(directory, ignore_errors=True)

	return restore


def module_isolation():
	"""(setUpModule, tearDownModule) isolating the checkout for one module."""
	state = {}

	def setUpModule():
		state["restore"] = isolate_checkout_config()

	def tearDownModule():
		restore = state.pop("restore", None)
		if restore is not None:
			restore()

	return setUpModule, tearDownModule


# -- repaint oracle -----------------------------------------------------------
#
# A canvas frame is only correct if the terminal it lands on dresses every cell
# the way that cell's own colour says. The leak this models is cumulative SGR:
# a run that omits an attribute still inherits it from the run before it. The
# machine below is an independent reading of the escape codes, so a regression
# test compares the *effective* style of each cell, not the bytes a painter
# happened to emit.

_HOME = re.compile(r"\033\[H")
_CUP = re.compile(r"\033\[(\d+);(\d+)H")
_SGR = re.compile(r"\033\[([0-9;]*)m")


class SgrTerminal:
	"""The SGR state a terminal holds after replaying some codes."""

	def __init__(self):
		self.reset()

	def reset(self):
		"""Back to the state a fresh terminal starts in."""
		self.fg = self.bg = None
		self.attrs = set()

	def feed(self, codes):
		"""Apply one SGR parameter string (`"38;2;1;2;3"`); returns the state."""
		params = [int(part or 0) for part in str(codes).split(";")]
		while params:
			code = params.pop(0)
			if code == 0:
				self.reset()
			elif code in (1, 2, 4, 7):
				self.attrs.add(code)
			elif code == 22:
				self.attrs -= {1, 2}
			elif code in (24, 27):
				self.attrs.discard(code - 20)
			elif 30 <= code <= 37 or 90 <= code <= 97:
				self.fg = code
			elif code == 39:
				self.fg = None
			elif 40 <= code <= 47 or 100 <= code <= 107:
				self.bg = code
			elif code == 49:
				self.bg = None
			elif code in (38, 48):
				size = 4 if params and params[0] == 2 else 2
				value = (code,) + tuple(params[:size])
				del params[:size]
				if code == 38:
					self.fg = value
				else:
					self.bg = value
		return self.state()

	def state(self):
		"""(fg, bg, attrs) as a hashable snapshot."""
		return (self.fg, self.bg, frozenset(self.attrs))


def cell_style(colour):
	"""The state one cell colour leaves, applied to a reset terminal."""
	terminal = SgrTerminal()
	for codes in _SGR.findall(str(colour or "")):
		terminal.feed(codes)
	return terminal.state()


def replay(frame):
	"""{ (x, y): (char, effective state) } for one emitted frame."""
	terminal = SgrTerminal()
	cells, x, y, index = {}, 0, 0, 0
	while index < len(frame):
		match = _HOME.match(frame, index)
		if match:
			x = y = 0
			index = match.end()
			continue
		match = _CUP.match(frame, index)
		if match:
			y, x = int(match.group(1)) - 1, int(match.group(2)) - 1
			index = match.end()
			continue
		match = _SGR.match(frame, index)
		if match:
			terminal.feed(match.group(1))
			index = match.end()
			continue
		if frame[index] == "\n":
			y, x = y + 1, 0
		else:
			cells[(x, y)] = (frame[index], terminal.state())
			x += 1
		index += 1
	return cells


def repaint_errors(canvas, frame):
	"""Cells whose effective style or character differs from the canvas buffer.

	An empty list is the invariant: a repaint may leave no cell dressed by the
	cell painted before it.
	"""
	errors = []
	for (x, y), (char, state) in replay(frame).items():
		expected_char = canvas._buffer[y][x]
		expected = cell_style(canvas._colors[y][x])
		if char != expected_char or state != expected:
			errors.append((x, y, char, expected_char, state, expected))
	return errors
