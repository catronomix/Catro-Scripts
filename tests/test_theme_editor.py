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

from tui import (caps, config, editor, editorviews, keys, palette, screen,
				 table, theme_engine)  # noqa: E402
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


class PreviewFrameTests(EditorTestCase):
	"""Item 2: the document's border_style frames every preview look."""

	def preview(self, style, look="default", *, width=29, height=12, cap=None):
		"""Paint one preview band on a fresh 90x24 canvas; returns canvas, doc."""
		document = copy.deepcopy(self.make().document)
		document["properties"]["border_style"] = style
		canvas = screen.Canvas(90, 24)
		editorviews.draw_preview(canvas, 1, 2, width, height, document, look,
								 cap=cap or self.cap)
		lines = ["".join(row) for row in canvas._buffer]
		return canvas, document, [line[1:1 + width] for line in lines[2:2 + height]]

	def test_every_border_style_frames_every_look_with_its_own_glyphs(self):
		for style in ("rounded", "square", "heavy", "double", "ascii", "none"):
			glyphs = table.BORDER_GLYPHS[style]
			for look in editorviews.LOOK_ORDER:
				with self.subTest(style=style, look=look):
					canvas, document, band = self.preview(style, look)
					if style == "none":
						# No frame at all: the header keeps the first row.
						self.assertEqual(band[0][0], " ")
						self.assertIn(editorviews.preview_title(document, look),
									  band[0])
					else:
						self.assertEqual(band[0][0], glyphs["tl"])
						self.assertEqual(band[0][-1], glyphs["tr"])
						self.assertEqual(band[-1][0], glyphs["bl"])
						self.assertEqual(band[-1][-1], glyphs["br"])
						self.assertIn(editorviews.preview_title(document, look),
									  band[0])
						# The edge uses the look's own border hex, not the
						# selected theme's: all three previews stay accurate.
						self.assertEqual(
							canvas._colors[2][1],
							palette.prefix(
								fg=document["looks"][look]["border"],
								cap=self.cap))

	def test_ascii_console_degrades_the_frame_but_keeps_the_band(self):
		canvas, _, band = self.preview("heavy", cap=make_cap(unicode=False))
		self.assertEqual(band[0][0], "+")
		self.assertEqual(band[0][-1], "+")
		self.assertEqual(band[-1][0], "+")
		self.assertEqual(band[1][0], "|")
		self.assertIn("-", band[0])
		self.assertIn("60%", band[-2])

	def test_the_twelve_row_band_keeps_the_bar_and_drops_the_closing_rule(self):
		_, document, band = self.preview("rounded")
		title = editorviews.preview_title(document, "default")
		self.assertEqual(len(band), 12)
		self.assertEqual(band[0].count(title), 1)  # title lives in the top rule
		self.assertEqual(band[0][0], "\u250c")
		self.assertEqual(band[-1][0], "\u2514")
		self.assertIn("60%", band[-2])
		# The table's own closing rule never fits at this budget.
		self.assertFalse(any("\u2500" in row for row in band[1:-1]))

	def test_a_short_preview_never_drops_the_progress_bar(self):
		for height in range(6, 13):
			with self.subTest(height=height):
				_, _, band = self.preview("rounded", height=height)
				self.assertIn("60%", band[-2], "bar dropped at height %d" % height)
				self.assertEqual(band[-1][0], "\u2514")


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


class EditingTests(EditorTestCase):
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
		self.assertEqual(ed.look_index, 1)  # editing is over, looks switch again

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
