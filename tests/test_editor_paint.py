# editor painter
"""
		Editor painter
		==============
The redraw budget of the frame painter: one keystroke paints only the
rows it owns, an unchanged redraw writes nothing, the status rows lose
the previous tail and `_layout` runs only when the canvas size changes.

Every test points the engine seams and `config.CONFIG_FILE` at a temp
folder, so the checkout never leaks into the assertions.
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

class RedrawBudgetTests(EditorTestCase):
	"""Item 1: one keystroke is a small batched diff, not a full repaint."""

	def setUp(self):
		super().setUp()
		self.stream = io.StringIO()
		self.ed = editor.ThemeEditor(
			canvas=screen.Canvas(90, 24, stream=self.stream),
			cap=self.cap).open()
		self.ed.canvas.render()
		self.full = len(self.frame())

	def frame(self):
		"""Drain everything the last render wrote."""
		value = self.stream.getvalue()
		self.stream.seek(0)
		self.stream.truncate()
		return value

	def test_an_unchanged_redraw_writes_nothing(self):
		self.ed.draw(full=False)
		self.ed.canvas.render(full=False)
		self.assertEqual(self.frame(), "")

	def test_one_keyframe_is_a_small_diff_of_its_own_panel_rows(self):
		self.ed.handle("down")
		self.ed.draw(full=False)
		self.ed.canvas.render(full=False)
		frame = self.frame()
		self.assertLess(len(frame), self.full // 2)
		moves = re.findall(r"\033\[(\d+);\d+H", frame)
		rows = {int(row) - 1 for row in moves}
		x, y, width, height = self.ed.rects[3]
		self.assertTrue(rows, "the focused row move painted nothing")
		self.assertTrue(all(y <= row < y + height for row in rows), rows)
		self.assertLessEqual(len(rows), 4)

	def test_one_event_paints_and_writes_in_under_thirty_ms(self):
		samples = []
		for index in range(15):
			start = time.perf_counter()
			self.ed.handle("down" if index % 2 == 0 else "up")
			self.ed.draw(full=False)
			self.ed.canvas.render(full=False)
			samples.append((time.perf_counter() - start) * 1000)
			self.frame()
		samples.sort()
		median = samples[len(samples) // 2]
		self.assertLess(median, 30.0,
						"median event {:.1f} ms: {}".format(median, samples))

	def test_layout_runs_only_when_the_canvas_size_changes(self):
		with mock.patch.object(self.ed, "_layout",
							   wraps=self.ed._layout) as layout:
			self.ed.draw(full=False)
			layout.assert_not_called()
			self.ed.canvas = screen.Canvas(100, 30, stream=self.stream)
			self.ed.draw(full=True)
			layout.assert_called_once()

	def assert_incremental_matches_a_full_repaint(self):
		"""The incremental canvas must equal a full repaint of the same state."""
		self.ed.draw(full=False)
		incremental = ["".join(row) for row in self.ed.canvas._buffer]
		fresh = editor.ThemeEditor(canvas=screen.Canvas(90, 24),
								  cap=self.cap).open()
		fresh.message = self.ed.message
		fresh.dirty = self.ed.dirty
		fresh.draw(full=True)
		full = ["".join(row) for row in fresh.canvas._buffer]
		self.assertEqual(incremental, full)

	def test_shorter_status_message_clears_the_previous_tail(self):
		self.ed.message = ("info", "saved " * 12)
		self.ed.dirty = True
		self.ed.draw(full=True)
		self.ed.canvas.render()
		self.frame()
		self.ed.message = ("info", "ok")
		self.assert_incremental_matches_a_full_repaint()
		self.assertNotIn("saved", "".join(self.ed.canvas._buffer[-2]))
		self.assertIn("* unsaved", "".join(self.ed.canvas._buffer[-1]))

	def test_clearing_dirty_removes_the_unsaved_prefix(self):
		self.ed.message = ("info", "ok")
		self.ed.dirty = True
		self.ed.draw(full=True)
		self.ed.canvas.render()
		self.frame()
		self.ed.dirty = False
		self.assert_incremental_matches_a_full_repaint()
		self.assertNotIn("* unsaved", "".join(self.ed.canvas._buffer[-1]))

if __name__ == "__main__":
	unittest.main()
