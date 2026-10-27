# Colour picker tests: conversions, the 16x3 grid, keys, mouse and drawing
"""
			COLOUR PICKER
			==============
Coverage for `tui/colorpicker.py`: the WCAG conversion helpers, the 16x3
swatch grid (one hue row, one saturation row, one value row of two-cell cells),
the marker, key and mouse routing, the commit/cancel result seam and the
small-terminal fallback. Canvases write to a fake stream, so no test needs a
terminal or the checkout's `config.ini`.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, colorpicker, palette, screen  # noqa: E402
from tui.colorpicker import (CELL, HEIGHT, STEPS, WIDTH, WCAG_AA,  # noqa: E402
							 ColorPicker, cell_index, contrast_ratio,
							 hex_to_rgb, hsv_to_rgb, luminance, rgb_to_hex,
							 rgb_to_hsv)

CAP = caps.Capabilities(level="16", unicode=True, width=120, isatty=True,
						plain=False, reason="test")
ASCII = caps.Capabilities(level="16", unicode=False, width=120, isatty=True,
						  plain=False, reason="test")
COLOURS = {"bg": "#ffffff", "zebra_bg": "#f4f4f8"}


class FakeStream:
	"""A stream that records writes and is never a tty."""

	def __init__(self):
		self.data = []

	def isatty(self):
		return False

	def write(self, text):
		self.data.append(text)
		return len(text)

	def flush(self):
		return None


def new_canvas(width=90, height=24):
	return screen.Canvas(width, height, stream=FakeStream())


def picker(value="#3366cc", **kwargs):
	"""A popup over a fresh 90x24 canvas, pinned capabilities and colours."""
	kwargs.setdefault("cap", CAP)
	kwargs.setdefault("colours", COLOURS)
	return ColorPicker(new_canvas(), value, **kwargs)


def row(canvas, x, y, width):
	return canvas.region(x, y, width, 1)[0]


def swatch_colour(popup, grid_row, grid_col):
	"""The plain prefix the grid writes for one swatch."""
	return palette.prefix(fg=popup.value_at(grid_row, grid_col), cap=CAP)


def hsv_hex(hue, saturation, value):
	"""The `#rrggbb` an HSV triple spells, for expectations."""
	return rgb_to_hex(hsv_to_rgb((hue, saturation, value)))


class ConversionTests(unittest.TestCase):
	def test_hex_and_rgb_spellings(self):
		self.assertEqual(hex_to_rgb("#3366cc"), (51, 102, 204))
		self.assertEqual(hex_to_rgb("3366CC"), (51, 102, 204))
		self.assertEqual(hex_to_rgb("  #0a0B0c "), (10, 11, 12))
		self.assertEqual(rgb_to_hex((51, 102, 204)), "#3366cc")
		self.assertEqual(rgb_to_hex((0, 0, 0)), "#000000")

	def test_hex_to_rgb_rejects_bad_input(self):
		for value in ("", "#12345", "#1234567", "#gggggg", "red", None):
			with self.assertRaises(ValueError) as caught:
				hex_to_rgb(value)
			self.assertIn("not a #rrggbb colour", str(caught.exception))

	def test_rgb_to_hsv_known_values(self):
		self.assertEqual(rgb_to_hsv((255, 0, 0)), (0.0, 1.0, 1.0))
		self.assertEqual(rgb_to_hsv((255, 255, 255)), (0.0, 0.0, 1.0))
		hue, saturation, value = rgb_to_hsv((51, 102, 204))
		self.assertAlmostEqual(hue, 220.0)
		self.assertAlmostEqual(saturation, 0.75)
		self.assertAlmostEqual(value, 0.8)

	def test_hsv_to_rgb_known_values_and_hue_wrap(self):
		self.assertEqual(hsv_to_rgb((0, 1, 1)), (255, 0, 0))
		self.assertEqual(hsv_to_rgb((120, 1, 1)), (0, 255, 0))
		self.assertEqual(hsv_to_rgb((360, 1, 1)), (255, 0, 0))
		self.assertEqual(hsv_to_rgb((90, 0, 1)), (255, 255, 255))

	def test_round_trip_keeps_the_hex(self):
		for text in ("#000000", "#ffffff", "#3366cc", "#7f3a12", "#00ff7f"):
			again = rgb_to_hex(hsv_to_rgb(rgb_to_hsv(hex_to_rgb(text))))
			self.assertEqual(again, text)

	def test_wcag_luminance_and_contrast(self):
		self.assertAlmostEqual(luminance("#000000"), 0.0)
		self.assertAlmostEqual(luminance("#ffffff"), 1.0)
		self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=2)
		self.assertAlmostEqual(contrast_ratio("#ffffff", "#000000"), 21.0, places=2)
		self.assertAlmostEqual(contrast_ratio("#3366cc", "#3366cc"), 1.0)
		self.assertEqual(WCAG_AA, 4.5)

	def test_the_midpoint_component_reads_as_cell_eight(self):
		# The contract's "value 50%" reading: the 16-step scale has no exact
		# 50% cell, and the midpoint rounds to index 8 of 0-15.
		self.assertEqual(cell_index(0.0), 0)
		self.assertEqual(cell_index(0.5), 8)
		self.assertEqual(cell_index(0.25), 4)
		self.assertEqual(cell_index(1.0), STEPS - 1)


class GridTests(unittest.TestCase):
	def test_geometry_is_a_bordered_sixteen_by_three_grid(self):
		popup = picker()
		x, y, width, height = popup.rect()
		self.assertEqual((width, height), (WIDTH, HEIGHT))
		self.assertEqual((WIDTH, HEIGHT), (36, 8))
		self.assertEqual(popup.grid_x, x + 2)
		self.assertEqual(popup.grid_y, y + 1)
		self.assertEqual(popup.grid_x + CELL * STEPS, x + WIDTH - 2)
		self.assertEqual(popup.cell_at(x, y), None)  # the top border, not a cell
		self.assertEqual(popup.cell_at(popup.grid_x, popup.grid_y), (0, 0))
		self.assertEqual(popup.cell_at(popup.grid_x + CELL * STEPS - 1,
									   popup.grid_y + 2), (2, STEPS - 1))
		self.assertEqual(popup.cell_at(popup.grid_x - 1, popup.grid_y), None)
		self.assertEqual(popup.cell_at(popup.grid_x, popup.grid_y + 3), None)

	def test_row_one_is_a_vivid_hue_ramp_at_full_saturation_and_value(self):
		popup = picker()
		for col in range(STEPS):
			expected = hsv_hex(col / (STEPS - 1) * 360, 1.0, 1.0)
			self.assertEqual(popup.value_at(0, col), expected)
		# The ramp never dims to the current colour: 15% value stays vivid.
		dark = picker("#1b1726")
		for col in range(STEPS):
			self.assertEqual(dark.value_at(0, col), popup.value_at(0, col))
		self.assertEqual(popup.value_at(0, 0), "#ff0000")
		self.assertEqual(popup.value_at(0, STEPS - 1), "#ff0000")

	def test_row_two_is_a_saturation_ramp_at_the_current_hue_and_full_value(self):
		popup = picker()
		self.assertEqual(popup.value_at(1, 0), "#ffffff")
		for col in range(STEPS):
			self.assertEqual(popup.value_at(1, col),
							 hsv_hex(220, col / (STEPS - 1), 1.0))
		self.assertEqual(popup.value_at(1, STEPS - 1), hsv_hex(220, 1, 1))
		dark = picker("#1b1726")
		self.assertEqual(dark.value_at(1, STEPS - 1),
						 hsv_hex(256, 1, 1))

	def test_row_three_walks_the_value_at_the_current_hue_and_saturation(self):
		popup = picker()
		self.assertEqual(popup.value_at(2, 0), "#000000")
		self.assertEqual(popup.value_at(2, STEPS - 1), hsv_hex(220, 0.75, 1))
		# Value 50% is the midpoint cell, index 8 of 0-15 - not a second scale.
		self.assertEqual(popup.value_at(2, cell_index(0.5)), "#224488")

	def test_select_applies_the_cell_component_and_keeps_the_marker(self):
		popup = picker()
		self.assertEqual((popup.row, popup.col), (0, cell_index(220 / 360)))
		self.assertEqual(popup.select(0, 0), "#cc3333")
		self.assertEqual(popup.value, "#cc3333")
		self.assertEqual((popup.row, popup.col), (0, 0))
		popup.select(2, STEPS - 1)
		self.assertEqual(popup.value, hsv_hex(0, 0.75, 1))
		popup.select(2, 0)
		self.assertEqual(popup.value, "#000000")
		other = picker()
		other.select(2, STEPS - 1)
		self.assertEqual(other.value, hsv_hex(220, 0.75, 1))


class KeyTests(unittest.TestCase):
	def test_left_right_wrap_inside_the_row_and_update_the_colour(self):
		popup = picker()
		popup.select(0, 0)
		self.assertTrue(popup.key("right"))
		self.assertEqual((popup.row, popup.col), (0, 1))
		self.assertEqual(popup.value, hsv_hex(1 / (STEPS - 1) * 360, 0.75, 0.8))
		self.assertTrue(popup.key("left"))
		self.assertTrue(popup.key("left"))
		self.assertEqual(popup.col, STEPS - 1)
		self.assertEqual(popup.value, "#cc3333")

	def test_up_down_change_row_and_snap_to_the_current_component(self):
		popup = picker()
		self.assertEqual((popup.row, popup.col), (0, cell_index(220 / 360)))
		self.assertTrue(popup.key("down"))
		self.assertEqual(popup.row, 1)
		self.assertEqual(popup.col, cell_index(0.75))
		self.assertEqual(popup.value, "#3366cc")  # a row move is not an edit
		self.assertTrue(popup.key("down"))
		self.assertEqual(popup.row, 2)
		self.assertEqual(popup.col, cell_index(0.8))
		self.assertTrue(popup.key("up"))
		self.assertEqual(popup.row, 1)

	def test_tab_and_backtab_move_between_rows_like_down_and_up(self):
		popup = picker()
		self.assertTrue(popup.key("tab"))
		self.assertEqual(popup.row, 1)
		self.assertTrue(popup.key("backtab"))
		self.assertEqual(popup.row, 0)

	def test_home_and_end_jump_to_the_row_poles(self):
		popup = picker()
		self.assertTrue(popup.key("end"))
		self.assertEqual((popup.row, popup.col), (0, STEPS - 1))
		self.assertTrue(popup.key("home"))
		self.assertEqual((popup.row, popup.col), (0, 0))
		self.assertTrue(popup.key("down"))
		self.assertTrue(popup.key("end"))
		self.assertEqual(popup.value, hsv_hex(0, 1, 0.8))

	def test_unrelated_keys_are_not_consumed(self):
		popup = picker()
		for token in ("x", "f1", "ctrl-s", "pagedown"):
			self.assertFalse(popup.key(token))
		self.assertFalse(popup.closed)

	def test_enter_applies_the_current_colour_and_space_too(self):
		popup = picker()
		popup.key("right")
		self.assertTrue(popup.key("enter"))
		self.assertTrue(popup.closed)
		self.assertEqual(popup.result, popup.value)
		self.assertNotEqual(popup.result, "#3366cc")
		other = picker()
		other.key("down")
		other.key("left")
		self.assertTrue(other.key("space"))
		self.assertEqual(other.result, other.value)

	def test_esc_cancels_and_restores_the_opening_colour(self):
		popup = picker()
		popup.key("right")
		self.assertNotEqual(popup.value, "#3366cc")
		self.assertTrue(popup.key("esc"))
		self.assertTrue(popup.closed)
		self.assertIsNone(popup.result)
		self.assertEqual(popup.value, "#3366cc")
		self.assertEqual(popup.col, cell_index(220 / 360))

	def test_run_consumes_the_injected_queue(self):
		popup = picker(keys=["down", "right", "esc"])
		self.assertIsNone(popup.run())
		self.assertTrue(popup.closed)
		self.assertEqual(popup.value, "#3366cc")


class MouseTests(unittest.TestCase):
	def test_press_selects_the_cell_and_applies_it(self):
		popup = picker()
		x = popup.grid_x + 3 * CELL + 1
		y = popup.grid_y + 1
		self.assertTrue(popup.key("mouse:press:{}:{}".format(x, y)))
		self.assertEqual((popup.row, popup.col), (1, 3))
		self.assertEqual(popup.value, hsv_hex(220, 3 / (STEPS - 1), 0.8))

	def test_drag_moves_the_selection_inside_the_grid(self):
		popup = picker()
		start = popup.grid_x + 2
		self.assertTrue(popup.key("mouse:press:{}:{}".format(
			start, popup.grid_y + 2)))
		self.assertEqual(popup.value, popup.value_at(2, 1))
		self.assertTrue(popup.key("mouse:drag:{}:{}".format(
			popup.grid_x + 11 * CELL, popup.grid_y + 2)))
		self.assertEqual((popup.row, popup.col), (2, 11))
		self.assertEqual(popup.value, popup.value_at(2, 11))

	def test_drag_past_the_edge_clamps_to_the_grabbed_row(self):
		popup = picker()
		popup.key("mouse:press:{}:{}".format(
			popup.grid_x + 4, popup.grid_y + 1))
		self.assertTrue(popup.key("mouse:drag:{}:{}".format(
			popup.grid_x + 999, popup.grid_y + 1)))
		self.assertEqual((popup.row, popup.col), (1, STEPS - 1))
		self.assertTrue(popup.key("mouse:drag:{}:{}".format(
			popup.grid_x - 50, popup.grid_y + 1)))
		self.assertEqual((popup.row, popup.col), (1, 0))

	def test_release_drops_the_grab_and_outside_presses_are_ignored(self):
		popup = picker()
		self.assertFalse(popup.key("mouse:press:{}:{}".format(
			popup.x, popup.y)))
		self.assertFalse(popup.key("mouse:drag:{}:{}".format(
			popup.grid_x, popup.grid_y)))
		self.assertTrue(popup.key("mouse:press:{}:{}".format(
			popup.grid_x, popup.grid_y)))
		self.assertTrue(popup.key("mouse:release:{}:{}".format(
			popup.grid_x, popup.grid_y)))
		self.assertFalse(popup.key("mouse:drag:{}:{}".format(
			popup.grid_x + CELL * 5, popup.grid_y)))
		self.assertEqual(popup.col, 0)

	def test_wheel_and_move_never_change_the_colour(self):
		popup = picker()
		before = popup.value
		for kind in ("mouse:wheel-down", "mouse:wheel-up", "mouse:move"):
			self.assertFalse(popup.key("{}:{}:{}".format(
				kind, popup.grid_x, popup.grid_y)))
		self.assertEqual(popup.value, before)


class DrawTests(unittest.TestCase):
	def test_full_draw_shows_a_bordered_title_and_three_swatch_rows(self):
		popup = picker()
		popup.key("down")
		self.assertIs(popup.draw(), popup)
		canvas = popup.canvas
		x, y, width, height = popup.rect()
		self.assertIn("Colour picker", row(canvas, x + 2, y, width - 4))
		self.assertIn("\u250c", row(canvas, x, y, width))
		self.assertIn("\u2518", row(canvas, x, y + height - 1, width))
		for grid_row in range(3):
			line = row(canvas, popup.grid_x, popup.grid_y + grid_row,
					   CELL * STEPS)
			self.assertEqual(line.count("\u2588"), CELL * STEPS)
		self.assertIn("#3366cc", "\n".join(
			canvas.region(x, y, width, height)))

	def test_the_selected_swatch_carries_the_reverse_marker(self):
		popup = picker()
		popup.draw()
		grid_row, grid_col = popup.row, popup.col
		cells = popup.canvas._colors[popup.grid_y + grid_row]
		first = popup.grid_x + grid_col * CELL
		self.assertEqual(cells[first],
						 swatch_colour(popup, grid_row, grid_col)
						 + palette.prefix(reverse=True, cap=CAP))
		self.assertNotEqual(cells[popup.grid_x], cells[first])

	def test_ascii_draw_uses_brackets_for_the_marker_and_no_glyphs(self):
		popup = picker(cap=ASCII)
		popup.draw()
		text = "\n".join(popup.canvas.region(0, 0, 90, 24))
		self.assertNotIn("\u2588", text)
		self.assertNotIn("\u2500", text)
		self.assertIn("><", text)
		self.assertIn("+", text)
		self.assertIn("#3366cc", text)

	def test_the_bottom_hint_fits_inside_the_popup(self):
		popup = picker()
		popup.draw()
		x, y, width, height = popup.rect()
		hint = "".join(popup.canvas._buffer[y + height - 2])
		self.assertIn("arrows  Enter apply  Esc cancel", hint)
		self.assertNotIn("..", hint)

	def test_low_contrast_warns_but_never_blocks(self):
		popup = picker("#777777", colours={"bg": "#666666", "zebra_bg": "#666666"})
		popup.draw()
		text = "\n".join(popup.canvas.region(0, 0, 90, 24))
		self.assertIn("below AA 4.5:1", text)
		self.assertTrue(popup.commit())
		self.assertEqual(popup.result, "#777777")

	def test_high_contrast_reports_the_ratio_without_the_warning(self):
		popup = picker("#ffffff", colours={"bg": "#000000", "zebra_bg": "#000000"})
		popup.draw()
		text = "\n".join(popup.canvas.region(0, 0, 90, 24))
		self.assertNotIn("below AA", text)
		self.assertIn("bg 21.0:1", text)

	def test_draw_without_background_colours_skips_the_warning(self):
		popup = ColorPicker(new_canvas(), "#3366cc", cap=CAP,
							colours={"fg": "#000000"})
		self.assertIs(popup.draw(), popup)
		text = "\n".join(popup.canvas.region(0, 0, 90, 24))
		self.assertNotIn("below AA", text)
		self.assertNotIn("bg", text)

	def test_small_terminal_shows_the_resize_notice(self):
		canvas = new_canvas(60, 12)
		popup = ColorPicker(canvas, "#3366cc", cap=CAP, colours=COLOURS)
		popup.draw()
		self.assertIn("too small", "\n".join(canvas.region(0, 0, 60, 12)))
