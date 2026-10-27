# editor run
"""
		Editor run
		==========
`run()`'s real-terminal wiring, without a terminal: raw mode and the
alternate screen are entered and left on a clean quit, and both are
restored when the injected token source raises.
"""

# Full-screen theme editor tests
"""
		THEME EDITOR (HEADLESS)
		=======================
The editor's headless seam: construct against a `Canvas` and an injected token
sequence, so open/preview-titles/navigation/Save/Load/quit all run without a
tty. The real `Screen`/`KeyReader`/mouse wiring is `run()`'s business and is not
exercised here.

Every test points the engine seams (`THEMES_DIR`, `THEME_FILE`) and
`config.CONFIG_FILE` at a temp folder, so the repository never gains a theme or
a `theme.ini` and the developer's checkout never leaks into the assertions.
"""

import contextlib
import copy
import io
import json
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from types import SimpleNamespace

from tui import (caps, config, editor, editor_keys, editor_nav, editor_overlays,
				 editor_preview, editoractions, editorpaint, editor_store,
				 editorviews, keys, palette, screen, table, theme_engine)  # noqa: E402
from tui.editor import ThemeEditor  # noqa: E402
from tui.editor_keys import EditorKeys  # noqa: E402
from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

SHIPPED = REPO / "themes" / "cozypurple.json"


def make_cap(unicode=True, level="true"):
	return caps.Capabilities(level=level, unicode=unicode, width=None,
							isatty=False, plain=False, reason="test")

class EditorTestCase(unittest.TestCase):
	"""Temp seams plus a document and a 90x24 canvas for every test."""

	def setUp(self):
		self._config_file = config.CONFIG_FILE
		self._theme_file = theme_engine.THEME_FILE
		self._themes_dir = theme_engine.THEMES_DIR
		self._td = tempfile.TemporaryDirectory()
		root = Path(self._td.name)
		config.CONFIG_FILE = root / "config.ini"
		theme_engine.THEME_FILE = root / "theme.ini"
		theme_engine.THEMES_DIR = root / "themes"
		theme_engine.THEMES_DIR.mkdir()
		# The shipped document is the built-in fallback, so a temp checkout
		# needs its own copy of it (issue #33).
		shutil.copyfile(SHIPPED, theme_engine.THEMES_DIR / "cozypurple.json")
		theme_engine._CACHE.clear()
		document = theme_engine.document()
		document["name"] = "cozypurple"
		theme_engine.save_theme(document, overwrite=True)
		self.cap = make_cap()

	def tearDown(self):
		config.CONFIG_FILE = self._config_file
		theme_engine.THEME_FILE = self._theme_file
		theme_engine.THEMES_DIR = self._themes_dir
		theme_engine._CACHE.clear()
		self._td.cleanup()

	def make(self, width=90, height=24, cap=None):
		"""A freshly opened editor on an explicit canvas."""
		return editor.ThemeEditor(canvas=screen.Canvas(width, height),
								  cap=cap or self.cap).open()

	def lines(self, ed):
		"""The canvas as plain rows, for content assertions."""
		return ["".join(row) for row in ed.canvas._buffer]

	def colours(self, ed):
		"""Every non-None cell colour currently on the canvas."""
		return {colour for row in ed.canvas._colors for colour in row
				if colour is not None}

class RunTests(EditorTestCase):
	"""`run()` wiring, with the terminal classes faked and no real tty."""

	def fake_terminal(self, tokens=(), error=None):
		calls = []

		@contextlib.contextmanager
		def raw_mode():
			calls.append("raw-enter")
			try:
				yield
			finally:
				calls.append("raw-exit")

		class FakeScreen:
			def __init__(self, stream):
				self.stream = stream

			def enter(self):
				calls.append("screen-enter")

			def exit(self):
				calls.append("screen-exit")

			def poll_resize(self):
				return False

		class FakeCanvas:
			width, height = 90, 24

			def __init__(self, stream=None):
				pass

			def render(self, full=False):
				calls.append("render")

		class FakeReader:
			def __init__(self, *args, **kwargs):
				self.tokens = list(tokens)

			def start(self):
				calls.append("reader-start")

			def stop(self):
				calls.append("reader-stop")

			def wait(self, timeout=None):
				if error is not None:
					raise error
				return self.tokens.pop(0) if self.tokens else "q"

		return calls, raw_mode, FakeScreen, FakeCanvas, FakeReader

	def run_faked(self, tokens=(), error=None):
		calls, raw_mode, screen_cls, canvas_cls, reader_cls = \
			self.fake_terminal(tokens, error)
		ed = self.make()
		with mock.patch.object(editor.keyio, "raw_mode", raw_mode), \
				mock.patch.object(editor.mouse, "reporting",
								  lambda stream: contextlib.nullcontext()), \
				mock.patch.object(editor.screen, "Screen", screen_cls), \
				mock.patch.object(editor.screen, "Canvas", canvas_cls), \
				mock.patch.object(editor.keyio, "KeyReader", reader_cls):
			result = ed.run(stream=io.StringIO())
		return calls, result

	def test_run_enters_and_leaves_raw_mode_on_a_clean_quit(self):
		calls, result = self.run_faked(tokens=["q"])
		self.assertEqual(result, 0)
		self.assertIn("raw-enter", calls)
		self.assertIn("raw-exit", calls)
		self.assertLess(calls.index("raw-enter"), calls.index("screen-enter"))
		self.assertLess(calls.index("screen-exit"), calls.index("raw-exit"))

	def test_run_restores_raw_mode_and_the_screen_on_an_exception(self):
		calls, raw_mode, screen_cls, canvas_cls, reader_cls = \
			self.fake_terminal(error=RuntimeError("boom"))
		ed = self.make()
		with mock.patch.object(editor.keyio, "raw_mode", raw_mode), \
				mock.patch.object(editor.mouse, "reporting",
								  lambda stream: contextlib.nullcontext()), \
				mock.patch.object(editor.screen, "Screen", screen_cls), \
				mock.patch.object(editor.screen, "Canvas", canvas_cls), \
				mock.patch.object(editor.keyio, "KeyReader", reader_cls):
			with self.assertRaises(RuntimeError):
				ed.run(stream=io.StringIO())
		self.assertIn("raw-exit", calls)
		self.assertIn("screen-exit", calls)

if __name__ == "__main__":
	unittest.main()
