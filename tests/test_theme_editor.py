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

	def test_small_terminal_ignores_editing_and_popups(self):
		ed = self.make(width=60, height=16)
		before = copy.deepcopy(ed.document)
		ed.pump(["enter", "ctrl-s", "f1", "tab", "right", "space"])
		self.assertEqual(ed.document, before)
		self.assertIsNone(ed.prompt)
		self.assertIsNone(ed.picker)
		self.assertFalse(ed.help)
		self.assertFalse(ed.dirty)
		self.assertFalse(ed.closed)

	def test_small_terminal_still_asks_before_discarding(self):
		ed = self.make(width=60, height=16)
		ed.dirty = True
		ed.handle("q")
		self.assertEqual(ed.prompt, "quit")
		self.assertFalse(ed.closed)
		ed.handle("y")
		self.assertTrue(ed.closed)

	def test_every_preview_shows_the_progress_bar_at_90x24(self):
		ed = self.make()
		rows = self.lines(ed)
		for index in range(3):
			x, y, width, height = ed.rects[index]
			band = "\n".join(row[x:x + width]
							 for row in rows[y:y + height])
			self.assertIn("60%", band)
			self.assertIn("\u2588", band)

	def test_a_one_cell_gutter_separates_the_three_previews(self):
		ed = self.make()
		for index in range(2):
			x, y, width, height = ed.rects[index]
			self.assertEqual(ed.rects[index + 1][0], x + width + 1)
		self.assertGreaterEqual(ed.rects[0][0], 1)
		x, y, width, height = ed.rects[2]
		self.assertLessEqual(x + width, ed.canvas.width - 1)

	def test_actions_buttons_stay_inside_the_frame_at_90x24(self):
		ed = self.make()
		rows = self.lines(ed)
		x, y, width, height = ed.rects[5]
		self.assertEqual(rows[y + height - 1][x], "\u2514")
		self.assertEqual(rows[y + height - 1][x + width - 1], "\u2518")
		for button in ed.buttons:
			self.assertLess(button.y, y + height - 1)
			self.assertGreater(button.y, y)
		self.assertEqual(ed.buttons[-1].y, y + height - 2)

	def test_f1_toggles_the_help_overlay_without_touching_the_document(self):
		ed = self.make()
		before = copy.deepcopy(ed.document)
		ed.handle("f1")
		self.assertTrue(ed.help)
		ed.draw()
		self.assertTrue(any("THEME EDITOR" in row for row in self.lines(ed)))
		ed.handle("esc")
		self.assertFalse(ed.help)
		# Opening the overlay is a view: no value, draft or dirty flag moves.
		self.assertEqual(ed.document, before)
		self.assertFalse(ed.dirty)
		self.assertIsNone(ed.edit)

	def test_overlays_survive_a_resize_and_reopen(self):
		# 90x24 -> 60x16 -> 90x24, with each popup open in turn: the small
		# terminal shows the notice (and swallows editing keys), and the popup
		# is painted again once the terminal is large enough.
		ed = self.make()
		before = copy.deepcopy(ed.document)
		ed.pump(["tab", "enter"])
		self.assertIsNotNone(ed.picker)
		ed.canvas = screen.Canvas(60, 16)
		ed.draw()
		self.assertIn("too small", self.lines(ed)[0])
		self.assertIsNotNone(ed.picker)
		ed.canvas = screen.Canvas(90, 24)
		ed.draw()
		self.assertIsNotNone(ed.picker)
		self.assertTrue(any("Colour picker" in row for row in self.lines(ed)))
		ed.handle("esc")
		self.assertIsNone(ed.picker)

		ed.handle("ctrl-s")
		ed.canvas = screen.Canvas(60, 16)
		ed.draw()
		self.assertIn("too small", self.lines(ed)[0])
		self.assertEqual(ed.prompt, "save")
		ed.canvas = screen.Canvas(90, 24)
		ed.draw()
		self.assertEqual(ed.prompt, "save")
		self.assertTrue(any("Save theme" in row for row in self.lines(ed)))
		ed.handle("esc")

		ed.load_popup()
		ed.canvas = screen.Canvas(60, 16)
		ed.draw()
		self.assertIn("too small", self.lines(ed)[0])
		self.assertEqual(ed.prompt, "load")
		ed.canvas = screen.Canvas(90, 24)
		ed.draw()
		self.assertEqual(ed.prompt, "load")
		self.assertTrue(any("Load theme" in row for row in self.lines(ed)))
		ed.handle("esc")
		self.assertEqual(ed.prompt, None)
		self.assertEqual(ed.document, before)
		self.assertFalse(ed.dirty)


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
		ed.pump(["tab"])  # the look is switched from the Colours pane
		ed.pump(["right"])
		self.assertEqual(ed.look_index, 1)
		self.assertIn("light", ed.message[1])
		ed.pump(["left", "left"])
		self.assertEqual(ed.look_index, 2)
		ed.handle("mouse:press:1:2")
		self.assertEqual(ed.look_index, 0)

	def test_an_esc_led_up_moves_the_focused_panel(self):
		# End to end: the three bytes a VT-enabled Windows console sends for Up
		# decode to one token and move the focused panel's row.
		ed = self.make()
		ed.pump(["down", "down"])
		self.assertEqual(ed.property_index, 2)

		class FakeMsvcrt:
			def __init__(self):
				self._bytes = [b"\x1b", b"[", b"A"]

			def kbhit(self):
				return bool(self._bytes)

			def getch(self):
				return self._bytes.pop(0)

		with mock.patch.dict(sys.modules, {"msvcrt": FakeMsvcrt()}), \
				mock.patch.object(keys, "os", SimpleNamespace(name="nt")):
			token = keys.read_key(timeout=0.2)
		self.assertEqual(token, "up")
		ed.handle(token)
		self.assertEqual(ed.property_index, 1)

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
		ed.handle("mouse:wheel-down:2:16")
		# The wheel moves the selection; the window follows only when the row
		# would leave the visible band (5 of 9 rows at 90x24).
		self.assertGreater(ed.property_index, 0)
		self.assertGreater(ed.property_offset, 0)

	def test_pagekeys_and_wheel_scroll_the_panel_not_the_document(self):
		ed = self.make()
		before = copy.deepcopy(ed.document)
		# Colours panel: PageDown and the wheel both only move its window.
		ed.pump(["tab", "pagedown"])
		self.assertGreater(ed.colour_index, 0)
		ed.handle("mouse:wheel-down:45:16")  # column inside the Colours panel
		self.assertGreater(ed.colour_offset, 0)
		self.assertEqual(ed.document, before)
		self.assertFalse(ed.dirty)

	def test_pagekeys_and_wheel_leave_an_open_draft_alone(self):
		ed = self.make()
		ed.handle("enter")
		key = editorviews.PROPERTY_KEYS[0]
		before = ed.document["properties"][key]
		ed.pump(["pagedown", "pageup", "mouse:wheel-down:2:16"])
		self.assertIsNotNone(ed.edit, "scrolling committed or cancelled the draft")
		self.assertEqual(ed.document["properties"][key], before)
		self.assertFalse(ed.dirty)


class WheelScrollTests(EditorTestCase):
	"""Issue #38 item 8: the wheel moves the selection, not a lost offset."""

	def test_wheel_moves_the_colour_selection_and_survives_the_next_paint(self):
		ed = self.make()  # 90x24: Colours shows 5 of 16 keys
		ed.handle("tab")  # focus Colours
		for _ in range(6):
			ed.handle("mouse:wheel-down:45:16")
		ed.draw()
		self.assertGreater(ed.colour_offset, 0)
		self.assertEqual(ed.colour_index, len(theme_engine.PALETTE_KEYS) - 1)
		x, y, width, height = ed.rects[4]
		rows = self.lines(ed)
		last = theme_engine.PALETTE_KEYS[-1]
		self.assertTrue(any(last in row[x:x + width]
							for row in rows[y:y + height]), last)

	def test_wheel_up_at_the_top_keeps_the_property_window_at_zero(self):
		ed = self.make()
		ed.handle("mouse:wheel-up:2:16")
		self.assertEqual((ed.property_index, ed.property_offset), (0, 0))

	def test_an_overflowing_pane_draws_a_marker_on_its_right_edge(self):
		ed = self.make()
		ed.draw()
		rows = self.lines(ed)
		for panel in (3, 4):
			x, y, width, height = ed.rects[panel]
			self.assertGreater(len(ed._rows(panel)), ed._visible(panel))
			column = [row[x + width - 2]
					  for row in rows[y + 1:y + height - 1]]
			self.assertTrue(all(cell != " " for cell in column), panel)


class SchemaTwoDocumentTests(EditorTestCase):
	"""The flipped document: every v2 token has an editor row and a value."""

	def panel_text(self, ed, index):
		ed.draw()
		x, y, width, height = ed.rects[index]
		rows = self.lines(ed)
		return "\n".join(row[x:x + width] for row in rows[y:y + height])

	def test_the_colours_panel_lists_every_v2_token(self):
		ed = self.make()
		ed.handle("tab")  # focus the Colours panel
		seen = set()
		for _ in range(len(theme_engine.PALETTE_KEYS)):
			seen |= {key for key in theme_engine.PALETTE_KEYS
					 if key in self.panel_text(ed, 4)}
			ed.handle("down")
		self.assertEqual(seen, set(theme_engine.PALETTE_KEYS))
		self.assertNotIn("surface", self.panel_text(ed, 4))

	def test_the_properties_panel_lists_the_surviving_keys(self):
		ed = self.make()
		seen = set()
		for _ in range(len(editorviews.PROPERTY_KEYS) + 1):
			band = self.panel_text(ed, 3)
			seen |= {key for key in editorviews.PROPERTY_KEYS if key in band}
			ed.handle("down")
		self.assertEqual(seen, set(editorviews.PROPERTY_KEYS))
		self.assertIn("corner-char", self.panel_text(ed, 3))


class DoubleClickTests(EditorTestCase):
	"""A second press on the same cell activates it; the first only selects."""

	def test_a_single_press_on_a_palette_row_opens_the_picker(self):
		# Issue #38 item 4: the first press selects the row and opens the
		# picker; a second identical press lands in the open picker and must
		# not replace it (the key path routes it to `picker_key`).
		ed = self.make()
		ed.handle("mouse:press:45:16")  # inside the Colours panel
		self.assertEqual(ed.focus, 1)
		picker = ed.picker
		self.assertIsNotNone(picker)
		ed.handle("mouse:press:45:16")
		self.assertIs(ed.picker, picker)
		self.assertEqual(ed.focus, 1)

	def test_a_double_press_on_a_property_row_opens_its_draft(self):
		ed = self.make()
		ed.handle("mouse:press:2:16")  # inside the Properties panel
		self.assertIsNone(ed.edit)
		ed.handle("mouse:press:2:16")
		self.assertEqual(ed.focus, 0)
		self.assertIsNotNone(ed.edit)
		self.assertEqual(ed.edit["key"], editorviews.PROPERTY_KEYS[0])

	def test_a_double_press_on_a_preview_only_selects_that_look(self):
		ed = self.make()
		ed.pump(["tab"])  # on Colours, a preview click is still explicit
		ed.handle("mouse:press:31:3")  # the second preview
		ed.handle("mouse:press:31:3")
		self.assertEqual(ed.look_index, 1)
		self.assertIsNone(ed.picker)

	def test_a_double_press_on_an_action_button_presses_it(self):
		ed = self.make()
		ed.handle("mouse:press:75:16")  # the Save button
		self.assertEqual(ed.prompt, "save")
		ed.handle("mouse:press:75:16")
		self.assertEqual(ed.prompt, "save")
		self.assertFalse(ed.closed)

	def test_a_double_press_on_a_load_row_opens_that_theme(self):
		ed = self.make()
		ed.load_popup()
		ed.handle("mouse:press:0:0")
		self.assertEqual(ed.prompt, "load")
		self.assertEqual(ed.load_box.selected, 0)
		ed.handle("mouse:press:0:0")
		self.assertIsNone(ed.prompt)
		self.assertIn("loaded", ed.message[1])

	def test_a_double_press_on_an_invalid_load_row_only_selects_it(self):
		(theme_engine.themes_dir() / "broken.json").write_text("{",
															   encoding="utf-8")
		ed = self.make()
		ed.load_popup()
		index = next(index for index, entry in enumerate(ed.entries)
					 if entry["error"])
		token = "mouse:press:0:{}".format(index)
		ed.handle(token)
		ed.handle(token)
		self.assertEqual(ed.prompt, "load")
		self.assertEqual(ed.load_box.selected, index)
		self.assertIn("cannot load", ed.message[1])


class LookScopeTests(EditorTestCase):
	"""Only the Colours pane may switch the active look."""

	def test_pane_moves_never_change_the_look(self):
		ed = self.make()
		for token in ("tab", "tab", "tab", "shift-tab", "shift-tab",
					  "shift-tab"):
			ed.handle(token)
			self.assertEqual(ed.look_index, 0)
		self.assertFalse(ed.dirty)

	def test_colours_is_the_only_pane_that_steps_the_look(self):
		ed = self.make()
		ed.pump(["tab", "right"])
		self.assertEqual(ed.look_index, 1)
		ed.pump(["tab", "right"])  # Actions: consumed, no look change
		self.assertEqual((ed.focus, ed.look_index), (2, 1))
		ed.pump(["tab", "right"])  # Properties: nudges, no look change
		self.assertEqual((ed.focus, ed.look_index), (0, 1))

	def test_actions_arrows_leave_the_document_alone(self):
		ed = self.make()
		before = copy.deepcopy(ed.document)
		ed.pump(["tab", "tab"])
		self.assertTrue(ed.handle("left"))
		self.assertEqual(ed.look_index, 0)
		self.assertTrue(ed.handle("right"))
		self.assertEqual(ed.look_index, 0)
		self.assertEqual(ed.document, before)
		self.assertFalse(ed.dirty)
		self.assertEqual(ed.look_index, 0)

	def test_an_open_picker_never_moves_the_look(self):
		ed = self.make()
		ed.pump(["tab", "enter"])
		self.assertEqual(ed.look_index, 0)
		ed.pump(["left", "right", "down", "right"])
		self.assertIsNotNone(ed.picker)
		self.assertEqual(ed.look_index, 0)


class ScrolledPaneTests(EditorTestCase):
	"""A scrolled pane hits rows in screen space and never past its last key."""

	def test_a_press_on_the_first_visible_colour_row_opens_that_key(self):
		ed = self.make()  # 90x24: Colours shows 5 of 16 keys
		ed.colour_offset = 1
		ed.handle("mouse:press:45:16")
		self.assertEqual((ed.focus, ed.colour_index), (1, 1))
		self.assertIsNotNone(ed.picker)

	def test_a_double_press_on_a_scrolled_property_row_drafts_that_key(self):
		ed = self.make()  # 90x24: Properties shows 5 of 9 keys
		ed.property_offset = 1
		ed.handle("mouse:press:2:16")
		self.assertEqual((ed.focus, ed.property_index), (0, 1))
		self.assertIsNone(ed.edit)
		ed.handle("mouse:press:2:16")
		self.assertIsNotNone(ed.edit)
		self.assertEqual(ed.edit["key"], editorviews.PROPERTY_KEYS[1])

	def test_a_stale_offset_cannot_select_past_the_last_colour_key(self):
		ed = self.make()
		ed.colour_offset = 99
		ed.handle("mouse:press:45:16")
		self.assertEqual(ed.colour_index, len(theme_engine.PALETTE_KEYS) - 1)


class ClickResetTests(EditorTestCase):
	"""A press pair cannot straddle a Load popup or a loaded document."""

	def test_opening_the_load_popup_forgets_an_armed_press(self):
		ed = self.make()
		ed.clicks.push("press", 5, 5)
		ed.load_popup()
		self.assertEqual(ed.clicks.push("press", 5, 5), "press")

	def test_opening_a_document_forgets_an_armed_press(self):
		ed = self.make()
		ed.clicks.push("press", 5, 5)
		editor_store.open_document(ed, "cozypurple")
		self.assertEqual(ed.clicks.push("press", 5, 5), "press")


class EditingTests(EditorTestCase):
	def test_left_right_nudge_the_selected_property_in_place(self):
		ed = self.make()
		key = editorviews.PROPERTY_KEYS[0]
		before = ed.document["properties"][key]
		ed.handle("right")
		self.assertEqual(ed.document["properties"][key],
						 theme_engine.PROPERTY_VALUES[key][1])
		self.assertNotEqual(ed.document["properties"][key], before)
		self.assertTrue(ed.dirty)
		self.assertEqual((ed.look_index, ed.colour_index), (0, 0))
		self.assertIn(key + " = ", ed.message[1])
		ed.handle("left")
		self.assertEqual(ed.document["properties"][key], before)

	def test_a_single_valued_property_nudges_to_nothing(self):
		ed = self.make()
		# No shipped property has one value any more, so pin the seam that
		# still has to handle one (`selection_style` retired in schema 2).
		with mock.patch.dict(theme_engine.PROPERTY_VALUES,
							 {"corner-char": ("none",)}):
			ed.pump(["end"])  # the last row is the single-valued one
			self.assertEqual(ed.property_index,
							 len(editorviews.PROPERTY_KEYS) - 1)
			before = copy.deepcopy(ed.document)
			ed.handle("right")
			ed.handle("left")
			self.assertEqual(ed.document, before)
			self.assertFalse(ed.dirty)
			self.assertIn("only value", ed.message[1])

	def test_zebra_toggles_in_place(self):
		ed = self.make()
		for _ in range(editorviews.PROPERTY_KEYS.index("table_zebra")):
			ed.handle("down")
		before = ed.document["properties"]["table_zebra"]
		ed.handle("right")
		self.assertEqual(ed.document["properties"]["table_zebra"], not before)
		self.assertTrue(ed.dirty)
		ed.handle("right")
		self.assertEqual(ed.document["properties"]["table_zebra"], before)

	def test_enter_drafts_a_property_and_a_second_enter_commits_it(self):
		ed = self.make()
		first = editorviews.PROPERTY_KEYS[0]
		before = ed.document["properties"][first]
		ed.handle("enter")
		self.assertIsNotNone(ed.edit)
		self.assertEqual(ed.document["properties"][first], before)
		self.assertFalse(ed.dirty)
		ed.handle("right")
		self.assertEqual(ed.look_index, 0)  # the look must not switch
		self.assertEqual(ed.document["properties"][first], before)
		ed.handle("enter")
		self.assertIsNone(ed.edit)
		self.assertNotEqual(ed.document["properties"][first], before)
		self.assertTrue(ed.dirty)
		ed.draw()
		self.assertIn("* unsaved", self.lines(ed)[0])

	def test_enter_drafts_the_zebra_check_field_until_committed(self):
		ed = self.make()
		index = editorviews.PROPERTY_KEYS.index("table_zebra")
		for _ in range(index):
			ed.handle("down")
		before = ed.document["properties"]["table_zebra"]
		ed.handle("enter")
		self.assertIsNotNone(ed.edit)
		ed.handle("right")
		self.assertEqual(ed.document["properties"]["table_zebra"], before)
		self.assertFalse(ed.dirty)
		ed.handle("enter")
		self.assertEqual(ed.document["properties"]["table_zebra"], not before)
		self.assertTrue(ed.dirty)

	def test_esc_restores_the_pre_edit_value(self):
		ed = self.make()
		first = editorviews.PROPERTY_KEYS[0]
		before = ed.document["properties"][first]
		ed.handle("enter")
		ed.handle("right")
		self.assertNotEqual(ed._field_value(ed.edit["field"]), before)
		ed.handle("esc")
		self.assertIsNone(ed.edit)
		self.assertEqual(ed.document["properties"][first], before)
		self.assertFalse(ed.dirty)
		ed.handle("right")
		# Editing is over, but Properties nudges in place: the look stays put.
		self.assertEqual(ed.look_index, 0)
		self.assertNotEqual(ed.document["properties"][first], before)
		self.assertTrue(ed.dirty)

	def test_picker_commit_writes_the_selected_look_only(self):
		ed = self.make()
		ed.pump(["tab", "enter"])
		self.assertIsNotNone(ed.picker)
		key = theme_engine.PALETTE_KEYS[ed.colour_index]
		other = dict(ed.document["looks"]["contrast-dark"])
		# Tab moves to the saturation row; Right steps saturation; Enter commits.
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
		ed.pump(["enter", "right", "enter"])
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
