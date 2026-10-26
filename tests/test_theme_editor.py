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

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import caps, config, editor, editorviews, screen, theme_engine  # noqa: E402
from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()


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


class HeadlessOpenTests(EditorTestCase):
	def test_open_paints_a_frame_and_three_preview_titles(self):
		ed = self.make()
		self.assertEqual(
			ed.preview_titles(),
			["Cozy Purple - soft", "Cozy Purple - light", "Cozy Purple - dark"])
		self.assertIn("Theme editor", self.lines(ed)[0])
		for title in ("soft", "light", "dark"):
			self.assertTrue(any("Cozy Purple - " + title in row
								for row in self.lines(ed)), title)
		self.assertEqual(sorted(ed.rects), [0, 1, 2, 3, 4, 5])

	def test_every_painted_colour_is_a_palette_prefix(self):
		# No private ANSI: the canvas only ever sees SGR sequences.
		ed = self.make()
		for colour in self.colours(ed):
			self.assertTrue(colour.startswith("\033["), repr(colour))
			self.assertTrue(colour.endswith("m"), repr(colour))

	def test_drawing_never_uses_the_private_clear_that_rereads_the_size(self):
		ed = self.make()
		ed.draw()
		self.assertEqual((ed.canvas.width, ed.canvas.height), (90, 24))

	def test_small_terminal_falls_back_and_still_quits(self):
		ed = self.make(width=60, height=16)
		self.assertIn("too small", self.lines(ed)[0])
		self.assertIn("Q or Delete quits", self.lines(ed)[1])
		ed.handle("q")
		self.assertTrue(ed.closed)

	def test_f1_toggles_the_help_overlay(self):
		ed = self.make()
		ed.handle("f1")
		self.assertTrue(ed.help)
		ed.draw()
		self.assertTrue(any("THEME EDITOR" in row for row in self.lines(ed)))
		ed.handle("esc")
		self.assertFalse(ed.help)


class NavigationTests(EditorTestCase):
	def test_tab_cycles_properties_colours_actions(self):
		ed = self.make()
		self.assertEqual(ed.focus, 0)
		ed.pump(["tab"])
		self.assertEqual(ed.focus, 1)
		self.assertIn("Colours", ed.message[1])
		ed.pump(["tab"])
		self.assertEqual(ed.focus, 2)
		ed.pump(["shift-tab"])
		self.assertEqual(ed.focus, 1)

	def test_left_right_and_clicks_select_the_look(self):
		ed = self.make()
		ed.pump(["right"])
		self.assertEqual(ed.look_index, 1)
		self.assertIn("light", ed.message[1])
		ed.pump(["left", "left"])
		self.assertEqual(ed.look_index, 2)
		ed.handle("mouse:press:1:2")
		self.assertEqual(ed.look_index, 0)

	def test_arrows_and_page_keys_scroll_the_properties_window(self):
		ed = self.make()
		ed.pump(["end"])
		self.assertEqual(ed.property_index,
						 len(editorviews.PROPERTY_KEYS) - 1)
		self.assertGreater(ed.property_offset, 0)
		ed.pump(["home"])
		self.assertEqual((ed.property_index, ed.property_offset), (0, 0))
		ed.pump(["pagedown"])
		self.assertGreater(ed.property_index, 0)

	def test_wheel_scrolls_the_hovered_panel(self):
		ed = self.make()
		# Column 2 is inside the Properties panel; the preview band is not.
		ed.handle("mouse:wheel-down:2:16")
		self.assertGreater(ed.property_offset, 0)


class EditingTests(EditorTestCase):
	def test_enter_cycles_a_select_property_and_marks_the_document_dirty(self):
		ed = self.make()
		first = editorviews.PROPERTY_KEYS[0]
		before = ed.document["properties"][first]
		ed.handle("enter")
		self.assertNotEqual(ed.document["properties"][first], before)
		self.assertTrue(ed.dirty)
		ed.draw()
		self.assertIn("* unsaved", self.lines(ed)[0])

	def test_enter_toggles_the_zebra_check_field(self):
		ed = self.make()
		index = editorviews.PROPERTY_KEYS.index("table_zebra")
		for _ in range(index):
			ed.handle("down")
		before = ed.document["properties"]["table_zebra"]
		ed.handle("enter")
		self.assertEqual(ed.document["properties"]["table_zebra"], not before)
		self.assertTrue(ed.dirty)

	def test_picker_commit_writes_the_selected_look_only(self):
		ed = self.make()
		ed.pump(["tab", "enter"])
		self.assertIsNotNone(ed.picker)
		key = theme_engine.PALETTE_KEYS[ed.colour_index]
		other = dict(ed.document["looks"]["contrast-dark"])
		# Tab moves off the hex box; Right steps the hue slider; Enter commits.
		ed.pump(["tab", "right", "right", "enter"])
		self.assertIsNone(ed.picker)
		self.assertNotEqual(ed.document["looks"][ed._current_look()][key],
							other[key])
		self.assertEqual(ed.document["looks"]["contrast-dark"], other)
		self.assertTrue(ed.dirty)

	def test_picker_cancel_leaves_the_document_alone(self):
		ed = self.make()
		ed.pump(["tab", "enter", "esc"])
		self.assertIsNone(ed.picker)
		self.assertFalse(ed.dirty)


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
		ed.save_prompt()
		ed.save_field.value = "other"
		ed.pump(["enter"])
		self.assertEqual(ed.prompt, "overwrite")
		self.assertIn("overwrite? y/n", ed.message[1])
		ed.pump(["n"])
		self.assertIsNone(ed.prompt)
		self.assertEqual(ed.document["name"], "cozypurple")
		self.assertEqual(theme_engine.selection()[0], "cozypurple")


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


class QuitTests(EditorTestCase):
	def test_clean_quit_closes_immediately(self):
		ed = self.make()
		ed.handle("q")
		self.assertTrue(ed.closed)
		self.assertFalse(ed.handle("tab"))

	def test_delete_quits_and_esc_just_reports_when_clean(self):
		ed = self.make()
		ed.handle("esc")
		self.assertIn("no unsaved changes", ed.message[1])
		self.assertFalse(ed.closed)
		ed.handle("delete")
		self.assertTrue(ed.closed)

	def test_dirty_quit_asks_and_no_keeps_the_session(self):
		ed = self.make()
		ed.handle("enter")
		self.assertTrue(ed.dirty)
		ed.handle("q")
		self.assertEqual(ed.prompt, "quit")
		self.assertIn("Discard changes? y/n", ed.message[1])
		ed.handle("n")
		self.assertFalse(ed.closed)
		ed.handle("q")
		ed.handle("y")
		self.assertTrue(ed.closed)

	def test_quit_is_implemented_headless(self):
		ed = self.make()
		self.assertTrue(ed.quit())
		self.assertTrue(ed.closed)


if __name__ == "__main__":
	unittest.main()
