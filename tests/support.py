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

Test seams: assign `THEME_FILE` / `THEMES_DIR` / `CONFIG_FILE` to redirect reads
and writes (tests never touch the repository); `None` restores the project
folder. `isolate_checkout_config()` redirects all three at a seeded temp
checkout, so a palette test reads the shipped documents without pointing a
write seam at the checkout.

The checkout itself is another environment input: `tui.config` and
`tui.theme_engine` read `config.ini`/`theme.ini` from the project folder, so an
operator who selects contrast-light there would change the bytes every default
look test pins. `install_repo_write_guard()` is the net under that:
`tests/conftest.py` installs it for the whole pytest run, so any write a test
funnels into the checkout - through a seam left at `None` or through a raw
`Path.write_text`/`open(..., "w")` - raises `AssertionError` naming the target
instead of changing the working tree. Plain `unittest` runs install the same
guard with `install_test_guard()`.

`SgrTerminal`/`replay()`/`repaint_errors()` are the repaint oracle: they replay
a canvas frame through an independent SGR state machine, so a regression can
assert each cell's *effective* style instead of the bytes a painter emitted.
"""

import contextlib
import hashlib
import os
import re
import shutil
import tempfile
import unittest
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


REPO_ROOT = Path(__file__).resolve().parents[1]


def isolate_checkout_config():
	"""Point all three checkout seams at a seeded temp folder; returns restore.

	`tui.config.CONFIG_FILE`, `tui.theme_engine.THEME_FILE` and
	`theme_engine.THEMES_DIR` are the supported seams (see their docstrings).
	The temp folder gets copies of the shipped `themes/*.json`, so palette tests
	keep reading the same documents while nothing can reach the checkout. The
	returned callable is idempotent, so module cleanups may call it twice.
	"""
	from tui import config, theme_engine

	previous = (config.CONFIG_FILE, theme_engine.THEME_FILE,
				theme_engine.THEMES_DIR)
	directory = tempfile.mkdtemp(prefix="catro-config-")
	themes = Path(directory) / "themes"
	themes.mkdir()
	for source in sorted((REPO_ROOT / "themes").glob("*.json")):
		shutil.copyfile(source, themes / source.name)

	def restore():
		if state.pop("done", None):
			return
		(config.CONFIG_FILE, theme_engine.THEME_FILE,
		 theme_engine.THEMES_DIR) = previous
		theme_engine._CACHE.clear()
		shutil.rmtree(directory, ignore_errors=True)

	state = {}
	try:
		config.CONFIG_FILE = Path(directory) / "config.ini"
		theme_engine.THEME_FILE = Path(directory) / "theme.ini"
		theme_engine.THEMES_DIR = themes
		theme_engine._CACHE.clear()
	except BaseException:
		restore()  # a half-applied seam is worse than none
		raise
	return restore


def module_isolation():
	"""(setUpModule, tearDownModule) isolating the checkout for one module."""
	state = {}

	def setUpModule():
		restore = isolate_checkout_config()
		state["restore"] = restore
		# Module cleanups run even if this hook raises, so a broken isolation
		# cannot leak a repo-pointing or deleted-temp seam into the next module.
		unittest.addModuleCleanup(restore)

	def tearDownModule():
		restore = state.pop("restore", None)
		if restore is not None:
			restore()

	return setUpModule, tearDownModule


# -- repository write guard ---------------------------------------------------
#
# Issue #39: THEMES_DIR / THEME_FILE / CONFIG_FILE default to None, which means
# the tracked checkout, and tests write through whatever path they resolve to.
# A leaked seam therefore writes themes/*.json, theme.ini or config.ini into the
# developer's tree. The guard makes that impossible inside the test process:
# every writer a test can reach checks its resolved target and raises
# AssertionError naming it. Production runs never install it, so a real
# `cs theme ...` still writes the project's own files.

# Tool-managed caches are not checkout content: pytest and the import system
# write them during any run. Everything else inside the repository is refused
# unless a scoped `allow_repo_writes()` says otherwise.
CACHE_DIRS = ("__pycache__", ".pytest_cache", ".git")

_ALLOWED = []
_UNINSTALL = None


class RepositoryWriteError(AssertionError):
	"""A test process tried to write inside the checkout."""


def _is_write_mode(mode):
	return any(flag in str(mode) for flag in "wax+")


def check_repo_write(target):
	"""Raise unless `target` may be written: temp paths and cache dirs only."""
	try:
		resolved = Path(os.fsdecode(target)).resolve()
	except (TypeError, ValueError, OSError):
		return target
	# Resolve the root at check time and decide containment positively: a
	# short-spelled or `..`-spelled root must not turn a failure to relativise
	# into "outside the checkout" (issue #39).
	root = Path(REPO_ROOT).resolve()
	if not resolved.is_relative_to(root):
		return target
	relative = resolved.relative_to(root)
	allowed = (relative.parts and relative.parts[0] in CACHE_DIRS) or any(
		prefix == Path(".") or relative == prefix or prefix in relative.parents
		for prefix in _ALLOWED)
	if not allowed:
		raise RepositoryWriteError(
			"the test process must not write the checkout: {}".format(resolved))
	return target


@contextlib.contextmanager
def allow_repo_writes(path):
	"""Permit writes under one checkout subtree (fixture regeneration only)."""
	_ALLOWED.append(
		Path(path).resolve().relative_to(Path(REPO_ROOT).resolve()))
	try:
		yield
	finally:
		_ALLOWED.pop()


def install_repo_write_guard():
	"""Refuse in-process writes into the checkout; returns the uninstall."""
	global _UNINSTALL
	if _UNINSTALL is not None:
		return _UNINSTALL
	import builtins
	import pathlib

	from tui import theme_engine

	# `Path.write_text`/`write_bytes` go through `self.open`, so wrapping these
	# three entry points covers every writer the suite uses, including the
	# engine's atomic save and `config.set`.
	saved = (builtins.open, pathlib.Path.open, theme_engine._atomic_write)

	def open_hook(file, mode="r", *args, **kwargs):
		if _is_write_mode(mode):
			check_repo_write(file)
		return saved[0](file, mode, *args, **kwargs)

	def path_open_hook(self, mode="r", *args, **kwargs):
		if _is_write_mode(mode):
			check_repo_write(self)
		return saved[1](self, mode, *args, **kwargs)

	def atomic_hook(target, text, make_dir=False):
		check_repo_write(target)
		return saved[2](target, text, make_dir)

	def uninstall():
		global _UNINSTALL
		if _UNINSTALL is None:
			return
		_UNINSTALL = None
		builtins.open, pathlib.Path.open, theme_engine._atomic_write = saved

	builtins.open, pathlib.Path.open, theme_engine._atomic_write = (
		open_hook, path_open_hook, atomic_hook)
	_UNINSTALL = uninstall
	return uninstall


def guard_installed():
	"""True while `install_repo_write_guard()` is in force."""
	return _UNINSTALL is not None


# Checkout data the suite must leave as found: theme documents, the two
# per-checkout selection/config files and every committed fixture.
GUARDED_GLOBS = ("themes/*.json", "theme.ini", "config.ini",
				 "tests/fixtures/*", "tests/fixtures/**/*")


def snapshot_checkout(root=None):
	"""{path: (sha256, mtime_ns)} for the checkout data files.

	Absent `theme.ini`/`config.ini` are recorded as `None`, so creating one is a
	change too. `root` lets the checker itself be tested on a temp tree.
	"""
	root = Path(root).resolve() if root is not None else Path(REPO_ROOT).resolve()
	state = {name: None for name in ("theme.ini", "config.ini")}
	for pattern in GUARDED_GLOBS:
		for entry in root.glob(pattern):
			if entry.is_file():
				state[entry.relative_to(root).as_posix()] = (
					hashlib.sha256(entry.read_bytes()).hexdigest(),
					entry.stat().st_mtime_ns)
	return state


def assert_checkout_unchanged(before, root=None):
	"""Raise listing every checkout data file that is not as it was found."""
	after = snapshot_checkout(root)
	changed = sorted(name for name in set(before) | set(after)
					 if before.get(name) != after.get(name))
	if changed:
		raise AssertionError(
			"the suite changed the checkout: {}".format(", ".join(changed)))
	return after


def install_test_guard():
	"""Guard + as-found check for plain `unittest` runs (`check()` last).

	`python -m unittest` has no session hook, so a module run that way installs
	this in `setUpModule` and calls `check()` in `tearDownModule`; pytest users
	get it from `tests/conftest.py`.
	"""
	before = snapshot_checkout()
	uninstall = install_repo_write_guard()

	def check():
		uninstall()
		assert_checkout_unchanged(before)

	return check


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
