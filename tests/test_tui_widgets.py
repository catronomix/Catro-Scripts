# Widget tests: focus ring, buttons, fields, list, scrollbar
"""
			INTERACTIVE WIDGETS
			====================
Smoke coverage for `tui/widgets.py`: the shared rectangle/hit-test seam, each
widget's keys and click mapping, focus cycling, the disabled button rule, the
clip proxy behind `Panel` and the small-terminal fallback. Drawing is checked
against the same `chrome` seams the widgets wrap, so a restyle cannot silently
change a hit box. Pinned capabilities keep the checkout's `config.ini` out of
the assertions.

The helpers (`Widget`, `Panel`, `Clip`, `cells`, `focus_prefix`, the
small-terminal pair) moved to `tui/widgetkit.py`, so this module also pins the
re-export and the self-contained focus ground.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, chrome, palette, screen, widgets  # noqa: E402

CAP = caps.Capabilities(level="16", unicode=True, width=120, isatty=True,
						plain=False, reason="test")


class FakeStream:
	"""A stream that is a tty only when a test says so."""

	def __init__(self, tty=False):
		self._tty = tty

	def isatty(self):
		return self._tty

	def write(self, text):
		return len(text)

	def flush(self):
		return None


def new_canvas(width=60, height=12):
	return screen.Canvas(width, height, stream=FakeStream())


def rows(canvas, x, y, width, height):
	return canvas.region(x, y, width, height)


class SeamTests(unittest.TestCase):
	def test_hit_test_is_the_rectangle(self):
		widget = widgets.Widget(2, 3, 5, 2, cap=CAP)
		self.assertTrue(widget.hit_test(2, 3))
		self.assertTrue(widget.hit_test(6, 4))
		self.assertFalse(widget.hit_test(7, 4))
		self.assertFalse(widget.hit_test(6, 5))
		self.assertFalse(widget.hit_test(1, 3))

	def test_cells_splits_lead_colour_from_text(self):
		colour, text = widgets.cells(palette.style("Save", fg="warn", cap=CAP))
		self.assertTrue(colour.startswith("\x1b["))
		self.assertEqual(text, "Save")
		self.assertEqual(widgets.cells("plain"), (None, "plain"))

	def test_focus_prefix_follows_visibility(self):
		self.assertIsNone(widgets.focus_prefix(False, CAP))
		self.assertIsNotNone(widgets.focus_prefix(True, CAP))
		self.assertIsNone(widgets.focus_prefix(
			True, caps.Capabilities(level="none", unicode=False, width=80,
									isatty=True, plain=False, reason="test")))


class ModuleSplitTests(unittest.TestCase):
	"""`tui/widgetkit.py` owns the helpers; `tui/widgets.py` re-exports them."""

	def test_helpers_are_the_widgetkit_objects(self):
		from tui import widgetkit  # noqa: E402  (the split is the assertion)
		for name in ("Widget", "Panel", "Clip", "cells", "focus_prefix",
					 "small_terminal", "resize_notice", "MIN_WIDTH",
					 "MIN_HEIGHT", "SMALL_TERMINAL"):
			with self.subTest(name=name):
				self.assertIs(getattr(widgets, name), getattr(widgetkit, name))

	def test_widgets_keep_the_public_import_surface(self):
		from tui.widgets import (Clip, Panel, Widget, cells,  # noqa: F401
								 focus_prefix, resize_notice, small_terminal)
		self.assertTrue(callable(cells))
		self.assertTrue(callable(focus_prefix))
		self.assertTrue(issubclass(Panel, Widget))
		self.assertIsNotNone(Clip)

	def test_no_duplicated_ansi_table(self):
		from tui import widgetkit
		self.assertFalse(hasattr(widgetkit, "_SGR"))
		self.assertFalse(hasattr(widgets, "_SGR"))
		self.assertEqual(widgetkit.cells("\x1b[31mred\x1b[0m"), ("\x1b[31m", "red"))


class FocusGroundTests(unittest.TestCase):
	"""A focused cell must carry its own ground, never inherit one."""

	class Recorder:
		def __init__(self):
			self.cells = {}

		def draw_char(self, x, y, char, color=None):
			self.cells[(int(x), int(y))] = (char, color)

		def draw_text(self, x, y, text, color=None):
			for offset, char in enumerate(str(text)):
				self.draw_char(x + offset, y, char, color)

	def true_cap(self):
		return caps.Capabilities(level="true", unicode=True, width=120,
								 isatty=True, plain=False, reason="test")

	def test_two_focused_rows_cannot_bleed(self):
		cap = self.true_cap()
		recorder = self.Recorder()
		widgets.CheckField(0, 0, "one", cap=cap).draw(recorder, focused=True)
		widgets.CheckField(0, 1, "two", cap=cap).draw(recorder, focused=True)
		grounds = []
		for row in (0, 1):
			colours = {colour for (x, y), (char, colour)
					   in recorder.cells.items() if y == row}
			self.assertEqual(len(colours), 1)
			ground = colours.pop()
			self.assertRegex(ground, "\x1b\\[38;2;")
			self.assertRegex(ground, "\x1b\\[48;2;")
			grounds.append(ground)
		self.assertEqual(grounds[0], grounds[1])

	def test_focus_prefix_is_self_contained(self):
		cap = self.true_cap()
		prefix = widgets.focus_prefix(True, cap)
		self.assertIn("\x1b[38;2;", prefix)
		self.assertIn("\x1b[48;2;", prefix)
		self.assertEqual(widgets.focus_prefix(True, cap, fg="warn"),
						 widgets.focus_prefix(True, cap, fg="warn"))


class ButtonTests(unittest.TestCase):
	def test_width_matches_the_chrome_render(self):
		button = widgets.Button(0, 0, "Save", cap=CAP)
		visible = widgets.cells(chrome.button("Save", cap=CAP))[1]
		self.assertEqual(button.width, len(visible))

	def test_enter_space_and_click_activate(self):
		fired = []
		button = widgets.Button(0, 0, "Save", on_activate=fired.append, cap=CAP)
		self.assertTrue(button.key("enter"))
		self.assertTrue(button.key("space"))
		self.assertTrue(button.click(0, 0))
		self.assertTrue(button.activated)
		self.assertEqual(fired, [button, button, button])
		self.assertFalse(button.key("q"))

	def test_disabled_button_never_activates(self):
		fired = []
		button = widgets.Button(0, 0, "Save", disabled=True,
								on_activate=fired.append, cap=CAP)
		self.assertFalse(button.key("enter"))
		self.assertFalse(button.click(0, 0))
		self.assertFalse(button.activated)
		self.assertEqual(fired, [])

	def test_disabled_draw_is_the_muted_chrome_cell(self):
		canvas = new_canvas()
		button = widgets.Button(1, 1, "Save", disabled=True, cap=CAP)
		button.draw(canvas)
		expected = widgets.cells(chrome.button("Save", disabled=True, cap=CAP))
		self.assertEqual(rows(canvas, 1, 1, button.width, 1), [expected[1]])


class TextFieldTests(unittest.TestCase):
	def test_typing_backspace_and_delete(self):
		field = widgets.TextField(0, 0, cap=CAP)
		field.key("enter")
		for token in ("a", "b", "c"):
			field.key(token)
		self.assertEqual(field.value, "abc")
		field.key("left")
		field.key("backspace")
		self.assertEqual((field.value, field.cursor), ("ac", 1))
		field.key("delete")
		self.assertEqual((field.value, field.cursor), ("a", 1))

	def test_home_end_and_space(self):
		field = widgets.TextField(0, 0, "ab", cap=CAP)
		field.begin()
		field.key("home")
		field.key("space")
		self.assertEqual(field.value, " ab")
		field.key("end")
		self.assertEqual(field.cursor, 3)
		field.key("right")
		self.assertEqual(field.cursor, 3)

	def test_enter_commits_and_esc_restores(self):
		field = widgets.TextField(0, 0, "keep", cap=CAP)
		field.key("enter")
		field.key("x")
		self.assertTrue(field.commit())
		self.assertEqual((field.value, field.editing), ("keepx", False))
		field.key("enter")
		field.key("y")
		field.key("esc")
		self.assertEqual((field.value, field.editing), ("keepx", False))

	def test_validator_rejects_then_accepts(self):
		field = widgets.TextField(0, 0, "ab", cap=CAP,
								  validator=lambda value: len(value) > 2)
		field.begin()
		field.key("enter")
		self.assertTrue(field.editing)
		self.assertEqual(field.error, "invalid")
		field.key("c")
		field.key("enter")
		self.assertFalse(field.editing)
		self.assertIsNone(field.error)

	def test_validator_message_is_shown(self):
		field = widgets.TextField(0, 0, "x", cap=CAP,
								  validator=lambda value: "too short")
		field.begin()
		field.key("enter")
		self.assertEqual(field.error, "too short")

	def test_click_edits_at_the_pointer(self):
		field = widgets.TextField(3, 2, "abcdef", width=10, cap=CAP)
		self.assertTrue(field.click(5, 2))
		self.assertTrue(field.editing)
		self.assertEqual(field.cursor, 2)
		self.assertFalse(field.click(3, 4))

	def test_draw_stays_inside_its_width(self):
		canvas = new_canvas()
		field = widgets.TextField(0, 0, "0123456789abcdef", width=6, cap=CAP)
		field.draw(canvas)
		self.assertEqual(rows(canvas, 0, 0, 6, 1), ["012345"])
		self.assertEqual(canvas.region(6, 0, 4, 1), ["    "])


class SelectFieldTests(unittest.TestCase):
	def test_cycling_wraps_both_ways(self):
		field = widgets.SelectField(0, 0, ["soft", "light", "dark"], cap=CAP)
		self.assertEqual(field.selected(), "soft")
		self.assertEqual(field.key("right") and field.selected(), "light")
		self.assertEqual(field.key("enter") and field.selected(), "dark")
		self.assertEqual(field.key("right") and field.selected(), "soft")
		self.assertEqual(field.key("left") and field.selected(), "dark")
		self.assertFalse(field.key("q"))

	def test_click_cycles(self):
		field = widgets.SelectField(0, 0, ["a", "b"], cap=CAP)
		self.assertTrue(field.click(0, 0))
		self.assertEqual(field.selected(), "b")
		self.assertFalse(field.click(0, 2))


class CheckFieldTests(unittest.TestCase):
	def test_toggle_by_key_and_click(self):
		field = widgets.CheckField(0, 0, "zebra", cap=CAP)
		self.assertTrue(field.key("space"))
		self.assertTrue(field.value)
		self.assertTrue(field.click(0, 0))
		self.assertFalse(field.value)
		self.assertFalse(field.key("q"))

	def test_draw_marks_the_value(self):
		canvas = new_canvas()
		widgets.CheckField(0, 0, "zebra", True, cap=CAP).draw(canvas)
		self.assertEqual(rows(canvas, 0, 0, 8, 1), ["[x] zebr"])
		self.assertEqual(canvas.region(8, 0, 2, 1)[0].strip(), "a")


class ListBoxTests(unittest.TestCase):
	def rows(self, count=20, height=4):
		return widgets.ListBox(0, 0, [str(index) for index in range(count)],
							   width=4, height=height, cap=CAP)

	def test_arrows_and_paging_move_the_window(self):
		box = self.rows()
		box.key("pagedown")
		self.assertEqual((box.selected, box.offset), (4, 1))
		box.key("down")
		self.assertEqual((box.selected, box.offset), (5, 2))
		box.key("up")
		self.assertEqual((box.selected, box.offset), (4, 2))
		box.key("pageup")
		self.assertEqual((box.selected, box.offset), (0, 0))

	def test_home_end_clamp_at_the_edges(self):
		box = self.rows()
		box.key("end")
		self.assertEqual((box.selected, box.offset), (19, 16))
		box.key("down")
		self.assertEqual(box.selected, 19)
		box.key("home")
		self.assertEqual((box.selected, box.offset), (0, 0))
		self.assertFalse(box.key("q"))

	def test_click_selects_the_row_under_the_pointer(self):
		box = self.rows()
		self.assertTrue(box.click(0, 2))
		self.assertEqual(box.selected, 2)
		box.key("end")
		self.assertTrue(box.click(0, 0))
		self.assertEqual((box.selected, box.offset), (16, 16))
		self.assertFalse(box.click(0, 9))

	def test_empty_list_is_harmless(self):
		box = widgets.ListBox(0, 0, [], height=3, cap=CAP)
		self.assertEqual(box.move(2), 0)
		self.assertEqual((box.selected, box.offset), (0, 0))
		self.assertEqual(box.visible(), [])


class ScrollBarTests(unittest.TestCase):
	def test_content_that_fits_is_all_thumb(self):
		bar = widgets.ScrollBar(0, 0, 6, total=6, cap=CAP)
		self.assertEqual(bar.geometry(), (0, 6))
		self.assertEqual(bar.offset_for(3), 0)

	def test_geometry_follows_the_offset(self):
		bar = widgets.ScrollBar(0, 0, 10, total=50, offset=0, cap=CAP)
		start, length = bar.geometry()
		self.assertEqual(length, 2)
		self.assertEqual(start, 0)
		bar.offset = 20
		self.assertGreater(bar.geometry()[0], 0)
		self.assertEqual(bar.offset_for(bar.geometry()[0]), 20)

	def test_press_grabs_the_thumb_and_drag_moves_it(self):
		bar = widgets.ScrollBar(0, 0, 10, total=50, offset=0, cap=CAP)
		self.assertEqual(bar.press(0, 0), "thumb")
		self.assertEqual(bar.drag(0, 5), 25)
		bar.release()
		self.assertEqual(bar.press(0, 9), "jump")
		self.assertGreater(bar.offset, 0)
		self.assertIsNone(bar.press(4, 0))

	def test_wheel_clamps_to_the_span(self):
		bar = widgets.ScrollBar(0, 0, 5, total=10, cap=CAP)
		self.assertEqual(bar.wheel(-3), 0)
		self.assertEqual(bar.wheel(2), 2)
		self.assertEqual(bar.wheel(20), 5)

	def test_draw_uses_the_chrome_column(self):
		canvas = new_canvas()
		bar = widgets.ScrollBar(2, 1, 4, total=4, cap=CAP)
		bar.draw(canvas)
		expected = [widgets.cells(cell)[1]
					for cell in chrome.scrollbar(4, offset=0, total=4, cap=CAP)]
		self.assertEqual(rows(canvas, 2, 1, 1, 4), expected)


class FocusRingTests(unittest.TestCase):
	def ring(self):
		return widgets.FocusRing([
			widgets.Button(0, 0, "one", cap=CAP),
			widgets.CheckField(0, 2, "two", cap=CAP),
			widgets.Button(20, 0, "three", cap=CAP)])

	def test_tab_and_shift_tab_wrap(self):
		ring = self.ring()
		self.assertIs(ring.current(), ring.widgets[0])
		ring.key("tab")
		self.assertIs(ring.current(), ring.widgets[1])
		ring.key("shift-tab")
		self.assertIs(ring.current(), ring.widgets[0])
		ring.key("shift-tab")
		self.assertIs(ring.current(), ring.widgets[2])
		ring.key("tab")
		self.assertIs(ring.current(), ring.widgets[0])

	def test_keys_go_to_the_focused_widget_only(self):
		ring = self.ring()
		ring.key("tab")
		self.assertFalse(ring.widgets[0].activated)
		self.assertTrue(ring.key("space"))
		self.assertTrue(ring.widgets[1].value)
		self.assertFalse(ring.widgets[2].activated)

	def test_click_focuses_and_activates(self):
		ring = self.ring()
		self.assertTrue(ring.click(20, 0))
		self.assertIs(ring.current(), ring.widgets[2])
		self.assertTrue(ring.widgets[2].activated)
		self.assertFalse(ring.click(40, 9))

	def test_draw_marks_only_the_focused_widget(self):
		ring = self.ring()
		ring.key("tab")
		canvas = new_canvas()
		ring.draw(canvas)
		self.assertEqual(rows(canvas, 0, 2, 3, 1), ["[ ]"])


class PanelTests(unittest.TestCase):
	def test_children_are_clipped_to_the_panel(self):
		canvas = new_canvas()
		panel = widgets.Panel(1, 1, 4, 2, cap=CAP)
		panel.children.append(widgets.Button(0, 0, "outside", cap=CAP))
		panel.draw(canvas)
		self.assertEqual(canvas.region(0, 0, 60, 12),
						 [" " * 60] * 12)

	def test_visible_child_is_focused_first(self):
		canvas = new_canvas()
		panel = widgets.Panel(0, 0, 20, 2, cap=CAP)
		button = widgets.Button(0, 0, "ok", cap=CAP)
		panel.children.append(button)
		panel.draw(canvas, focused=True)
		self.assertIn("ok", rows(canvas, 0, 0, button.width, 1)[0])


class SmallTerminalTests(unittest.TestCase):
	def test_notice_below_the_minimum(self):
		notice = widgets.resize_notice(widgets.MIN_WIDTH - 1, 10, cap=CAP)
		self.assertIn(widgets.SMALL_TERMINAL, widgets.cells(notice)[1])
		self.assertTrue(widgets.small_terminal(89, 24))
		self.assertTrue(widgets.small_terminal(None, 24))

	def test_no_notice_at_the_minimum(self):
		self.assertIsNone(widgets.resize_notice(widgets.MIN_WIDTH,
												widgets.MIN_HEIGHT, cap=CAP))
		self.assertFalse(widgets.small_terminal(120, 40))


if __name__ == "__main__":
	unittest.main()
