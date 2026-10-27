# editor store
"""
		Editor store
		============
The Save/Load half of the editor (`tui.editor_store`): the seven moved
functions still resolve through `editoractions`, and the popup,
overwrite, slug-validation and dirty-discard paths write through the
engine seams only.

Every test points `THEMES_DIR`/`THEME_FILE` and `config.CONFIG_FILE` at a
temp folder, so the repository never gains a theme or a `theme.ini`.
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

from tui import (caps, config, editor, editor_keys, editor_mouse, editor_nav,
				 editor_overlays, editor_preview, editoractions, editorpaint,
				 editor_store, editorviews, keys, palette, screen, table,
				 theme_engine)  # noqa: E402
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

class StoreSplitShimTests(unittest.TestCase):
	"""The Save/Load half moved to `tui.editor_store`; old paths must resolve."""

	MOVED = ("save_prompt", "save_key", "commit_save", "load_popup",
			 "load_key", "open_document", "confirm_key")

	def test_the_moved_names_still_resolve_through_editoractions(self):
		for name in self.MOVED:
			with self.subTest(name=name):
				self.assertIs(getattr(editoractions, name),
							  getattr(editor_store, name))

	def test_the_pane_half_stayed_in_editoractions(self):
		for name in ("begin_property_edit", "edit_key", "commit_property",
					 "open_picker", "picker_key"):
			with self.subTest(name=name):
				self.assertTrue(hasattr(editoractions, name))
				self.assertFalse(hasattr(editor_store, name))

	def test_the_mouse_half_moved_to_editor_mouse(self):
		for name in ("mouse", "scroll", "_hit"):
			with self.subTest(name=name):
				self.assertTrue(hasattr(editor_mouse, name))
				self.assertFalse(hasattr(editoractions, name))
				self.assertFalse(hasattr(editor_store, name))

	def test_editor_store_does_not_import_editoractions_or_its_importers(self):
		source = (REPO / "tui" / "editor_store.py").read_text(encoding="utf-8")
		imports = [line for line in source.splitlines()
				   if line.startswith("from .") or line.startswith("import ")]
		self.assertTrue(imports)
		for line in imports:
			for blocked in ("editoractions", "editorimport", "editorpaint",
							"editor_store"):
				self.assertNotIn(blocked, line)

	def test_editor_store_does_not_import_the_editor_itself(self):
		source = (REPO / "tui" / "editor_store.py").read_text(encoding="utf-8")
		imports = [line.strip() for line in source.splitlines()
				   if line.startswith("from .") or line.startswith("import ")]
		self.assertNotIn("from . import editor", imports)
		self.assertNotIn("from .editor import", " ".join(imports))


class SaveTests(EditorTestCase):
	def test_save_prompt_is_preseeded_and_ctrl_s_opens_it(self):
		ed = self.make()
		ed.handle("ctrl-s")
		self.assertEqual(ed.prompt, "save")
		self.assertEqual(ed.save_prompt(), "cozypurple")

	def test_enter_writes_the_theme_and_selects_it(self):
		ed = self.make()
		ed.save_prompt()
		ed.save_field.value = "fresh"
		ed.pump(["enter"])
		self.assertIsNone(ed.prompt)
		self.assertFalse(ed.dirty)
		target = theme_engine.themes_dir() / "fresh.json"
		self.assertTrue(target.exists())
		self.assertEqual(ed.document["name"], "fresh")
		self.assertEqual(theme_engine.selection(), ("fresh", "soft"))
		self.assertIn(str(target), ed.message[1])

	def test_a_bad_slug_stays_in_the_popup_with_the_validator_error(self):
		ed = self.make()
		ed.save_prompt()
		ed.save_field.value = "Not A Name!"
		ed.pump(["enter"])
		self.assertEqual(ed.prompt, "save")
		self.assertTrue(ed.save_field.editing)
		self.assertIn("error", ed.message[0])
		self.assertEqual(list(theme_engine.themes_dir().glob("*.json")),
						 [theme_engine.themes_dir() / "cozypurple.json"])

	def test_an_existing_other_file_asks_before_overwriting(self):
		ed = self.make()
		other = theme_engine.document()
		other["name"], other["display"] = "other", "Other"
		theme_engine.save_theme(other)
		target = theme_engine.themes_dir() / "other.json"
		before = target.read_bytes()
		ed.save_prompt()
		ed.save_field.value = "other"
		ed.pump(["enter"])
		self.assertEqual(ed.prompt, "overwrite")
		self.assertIn("overwrite? y/n", ed.message[1])
		# `n` leaves the other file byte-identical and writes no temp file.
		ed.pump(["n"])
		self.assertIsNone(ed.prompt)
		self.assertEqual(target.read_bytes(), before)
		self.assertEqual(list(theme_engine.themes_dir().glob("*.tmp")), [])
		self.assertEqual(ed.document["name"], "cozypurple")
		self.assertEqual(theme_engine.selection()[0], "cozypurple")
		# `y` rewrites that file atomically with the edited document.
		ed.save_prompt()
		ed.save_field.value = "other"
		ed.pump(["enter", "y"])
		self.assertIsNone(ed.prompt)
		self.assertNotEqual(target.read_bytes(), before)
		self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["name"],
						 "other")
		self.assertEqual(list(theme_engine.themes_dir().glob("*.tmp")), [])
		self.assertEqual(ed.document["name"], "other")
		self.assertFalse(ed.dirty)
		self.assertEqual(theme_engine.selection()[0], "other")


class LoadTests(EditorTestCase):
	def test_popup_lists_the_active_theme_and_an_invalid_file(self):
		(theme_engine.themes_dir() / "broken.json").write_text(
			"{not json", encoding="utf-8")
		ed = self.make()
		labels = ed.load_popup()
		self.assertEqual(labels, ["! broken (broken.json) - invalid",
								  "* Cozy Purple (cozypurple.json)"])
		self.assertEqual(ed.prompt, "load")

	def test_loading_an_invalid_file_keeps_the_list_and_reports_the_error(self):
		(theme_engine.themes_dir() / "broken.json").write_text(
			"{not json", encoding="utf-8")
		ed = self.make()
		ed.load_popup()
		ed.pump(["home", "enter"])
		self.assertEqual(ed.message[0], "error")
		self.assertIn("broken", ed.message[1])
		self.assertEqual(ed.prompt, "load")
		self.assertEqual(ed.load_box.selected, 0)

	def test_loading_a_valid_theme_switches_the_document_and_selection(self):
		other = theme_engine.document()
		other["name"], other["display"] = "other", "Other"
		theme_engine.save_theme(other)
		ed = self.make()
		ed.load_popup()
		ed.pump(["down", "enter"])
		self.assertEqual(ed.document["name"], "other")
		self.assertFalse(ed.dirty)
		self.assertEqual(theme_engine.selection()[0], "other")
		self.assertIn("loaded other", ed.message[1])

	def test_an_invalid_row_keeps_the_list_and_a_valid_one_loads_after_it(self):
		(theme_engine.themes_dir() / "broken.json").write_text(
			"{not json", encoding="utf-8")
		other = theme_engine.document()
		other["name"], other["display"] = "other", "Other"
		theme_engine.save_theme(other)
		ed = self.make()
		labels = ed.load_popup()
		self.assertEqual(labels, ["! broken (broken.json) - invalid",
								  "* Cozy Purple (cozypurple.json)",
								  "  Other (other.json)"])
		# The broken row reports and leaves the popup open...
		ed.pump(["home", "enter"])
		self.assertEqual(ed.message[0], "error")
		self.assertEqual(ed.prompt, "load")
		self.assertEqual(ed.document["name"], "cozypurple")
		# ...and a valid row after it still loads.
		ed.pump(["end", "enter"])
		self.assertIsNone(ed.prompt)
		self.assertEqual(ed.document["name"], "other")
		self.assertEqual(theme_engine.selection()[0], "other")

	def test_loading_while_dirty_asks_first(self):
		other = theme_engine.document()
		other["name"], other["display"] = "other", "Other"
		theme_engine.save_theme(other)
		ed = self.make()
		ed.dirty = True
		ed.load_popup()
		ed.pump(["down", "enter"])
		self.assertEqual(ed.prompt, "discard-load")
		ed.pump(["n"])
		self.assertEqual(ed.document["name"], "cozypurple")
		self.assertTrue(ed.dirty)

if __name__ == "__main__":
	unittest.main()
