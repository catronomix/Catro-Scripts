# Colour picker tests: conversions, sync, keys, mouse and drawing
"""
			COLOUR PICKER
			==============
Coverage for `tui/colorpicker.py`: the WCAG conversion helpers, the popup's
single-model sync between the hex box, the `h,s,v` box and the three sliders,
key and mouse routing through the stage-3 widgets, the commit/cancel result
seam and the small-terminal fallback. Canvases write to a fake stream, so no
test needs a terminal or the checkout's `config.ini`.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, colorpicker, screen  # noqa: E402
from tui.colorpicker import (WCAG_AA, ColorPicker, contrast_ratio,  # noqa: E402
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


class TrackTests(unittest.TestCase):
	def test_keep_clamps_and_ignores_unrelated_keys(self):
		track = colorpicker._Slider(0, 0, 11, 100, cap=CAP)
		self.assertEqual(track.keep(-5), 0)
		self.assertEqual(track.keep(42.6), 43)
		self.assertEqual(track.keep(500), 100)
		self.assertFalse(track.key("enter"))
		self.assertEqual(track.value, 100)

	def test_keys_step_by_one_and_ten(self):
		track = colorpicker._Slider(0, 0, 11, 360, cap=CAP)
		track.keep(200)
		self.assertTrue(track.key("right"))
		self.assertEqual(track.value, 201)
		self.assertTrue(track.key("left"))
		self.assertEqual(track.value, 200)
		self.assertTrue(track.key("pagedown"))
		self.assertEqual(track.value, 190)
		self.assertTrue(track.key("pageup"))
		self.assertEqual(track.value, 200)
		self.assertTrue(track.key("home"))
		self.assertEqual(track.value, 0)
		self.assertTrue(track.key("end"))
		self.assertEqual(track.value, 360)

	def test_draw_falls_back_to_ascii(self):
		canvas = new_canvas()
		track = colorpicker._Slider(0, 0, 8, 100, cap=ASCII)
		track.keep(50)
		track.draw(canvas, focused=False)
		self.assertEqual(row(canvas, 0, 0, 8), "----#---")


class PickerTests(unittest.TestCase):
	def test_initial_views_share_one_model(self):
		popup = picker("3366cc")
		self.assertEqual(popup.value, "#3366cc")
		self.assertEqual(popup.hex_field.value, "#3366cc")
		self.assertEqual(popup.hsv_field.value, "220,75,80")
		self.assertEqual([track.value for track in popup.sliders], [220, 75, 80])

	def test_hex_box_edit_updates_every_view(self):
		popup = picker()
		popup.ring.focus(0)
		popup.key("enter")
		popup.hex_field.value = "#ff0000"
		self.assertTrue(popup.key("enter"))
		self.assertFalse(popup.hex_field.editing)
		self.assertEqual(popup.value, "#ff0000")
		self.assertEqual(popup.hsv_field.value, "0,100,100")
		self.assertEqual([track.value for track in popup.sliders], [0, 100, 100])

	def test_hsv_box_edit_updates_every_view(self):
		popup = picker()
		popup.ring.focus(4)
		popup.key("enter")
		popup.hsv_field.value = "120,100,100"
		self.assertTrue(popup.key("enter"))
		self.assertEqual(popup.value, "#00ff00")
		self.assertEqual(popup.hex_field.value, "#00ff00")

	def test_invalid_hex_shows_error_and_blocks_commit(self):
		popup = picker()
		popup.ring.focus(0)
		popup.key("enter")
		popup.hex_field.value = "#12345"
		self.assertFalse(popup.key("enter"))
		self.assertTrue(popup.hex_field.editing)
		self.assertEqual(popup.hex_field.error, "need #rrggbb")
		self.assertFalse(popup.commit())
		self.assertFalse(popup.closed)
		self.assertEqual(popup.value, "#3366cc")

	def test_invalid_hsv_shows_error_and_blocks_commit(self):
		popup = picker()
		popup.ring.focus(4)
		popup.key("enter")
		popup.hsv_field.value = "400,100,100"
		self.assertFalse(popup.key("enter"))
		self.assertTrue(popup.hsv_field.editing)
		self.assertEqual(popup.hsv_field.error, "need h,s,v")
		self.assertFalse(popup.commit())

	def test_tab_and_backtab_cycle_focus(self):
		popup = picker()
		self.assertIs(popup.ring.current(), popup.hex_field)
		self.assertTrue(popup.key("tab"))
		self.assertIs(popup.ring.current(), popup.sliders[0])
		self.assertTrue(popup.key("backtab"))
		self.assertIs(popup.ring.current(), popup.hex_field)

	def test_slider_keys_move_the_model(self):
		popup = picker()
		popup.ring.focus(1)
		self.assertTrue(popup.key("right"))
		self.assertEqual(popup.sliders[0].value, 221)
		self.assertEqual(popup.hex_field.value, "#3363cc")
		self.assertEqual(popup.hsv_field.value, "221,75,80")
		self.assertTrue(popup.key("pageup"))
		self.assertEqual(popup.sliders[0].value, 231)

	def test_mouse_press_and_drag_set_the_track(self):
		popup = picker()
		track = popup.sliders[0]
		midpoint = track.x + track.width // 2
		self.assertTrue(popup.key("mouse:press:{}:{}".format(midpoint, track.y)))
		self.assertIs(popup.ring.current(), track)
		expected = round((track.width // 2) * 360 / (track.width - 1))
		self.assertEqual(track.value, expected)
		self.assertEqual(popup.hex_field.value,
						 rgb_to_hex(hsv_to_rgb((expected, 0.75, 0.8))))
		popup.key("mouse:release:{}:{}".format(track.x, track.y))
		self.assertEqual(track.value, expected)

	def test_wheel_and_move_never_change_the_colour(self):
		popup = picker()
		track = popup.sliders[1]
		before = (popup.value, popup.hex_field.value, popup.hsv_field.value, track.value)
		for kind in ("mouse:wheel-down", "mouse:wheel-up", "mouse:move"):
			popup.key("{}:{}:{}".format(kind, track.x + 2, track.y))
		self.assertEqual((popup.value, popup.hex_field.value,
						  popup.hsv_field.value, track.value), before)
		self.assertEqual(track.value, 75)

	def test_drag_moves_only_the_grabbed_slider(self):
		popup = picker()
		hue, saturation, brightness = popup.sliders
		self.assertTrue(popup.key("mouse:press:{}:{}".format(
			saturation.x + 5, saturation.y)))
		low = saturation.value
		# one row above the 1-cell track: only the grabbed slider follows x
		self.assertTrue(popup.key("mouse:drag:{}:{}".format(
			saturation.x + saturation.width - 1, saturation.y - 1)))
		self.assertEqual(saturation.value, 100)
		self.assertGreater(saturation.value, low)
		self.assertEqual((hue.value, brightness.value), (220, 80))
		self.assertEqual(popup.hex_field.value, "#0044cc")
		self.assertEqual(popup.hsv_field.value, "220,100,80")

	def test_drag_without_a_press_and_after_release_is_ignored(self):
		popup = picker()
		track = popup.sliders[2]
		far = "{}:{}".format(track.x + track.width - 1, track.y)
		self.assertFalse(popup.key("mouse:drag:" + far))
		self.assertEqual(popup.value, "#3366cc")
		popup.key("mouse:press:{}:{}".format(track.x, track.y))
		held = track.value
		popup.key("mouse:release:{}:{}".format(track.x, track.y))
		self.assertFalse(popup.key("mouse:drag:" + far))
		self.assertEqual(track.value, held)

	def test_ok_click_and_enter_commit(self):
		popup = picker()
		self.assertTrue(popup.key("mouse:press:{}:{}".format(popup.ok.x, popup.ok.y)))
		self.assertTrue(popup.closed)
		self.assertEqual(popup.result, "#3366cc")
		other = picker()
		other.ring.focus(5)
		self.assertTrue(other.key("enter"))
		self.assertTrue(other.closed)
		self.assertEqual(other.result, "#3366cc")

	def test_esc_and_cancel_restore_the_original(self):
		popup = picker()
		popup.ring.focus(1)
		popup.key("right")
		self.assertTrue(popup.key("esc"))
		self.assertIsNone(popup.result)
		self.assertEqual(popup.value, "#3366cc")
		other = picker()
		other.ring.focus(1)
		other.key("right")
		self.assertTrue(other.key("mouse:press:{}:{}".format(
			other.cancel.x, other.cancel.y)))
		self.assertIsNone(other.result)
		self.assertEqual(other.value, "#3366cc")

	def test_run_consumes_the_injected_queue(self):
		popup = picker(keys=["tab", "right", "esc"])
		self.assertIsNone(popup.run())
		self.assertTrue(popup.closed)
		self.assertEqual(popup.value, "#3366cc")

	def test_commit_waits_for_a_box_mid_edit(self):
		popup = picker()
		popup.ring.focus(0)
		popup.key("enter")
		self.assertFalse(popup.commit())
		self.assertFalse(popup.closed)

	def test_tab_away_commits_a_valid_draft(self):
		popup = picker()
		popup.key("enter")
		popup.hex_field.value = "#ff0000"
		self.assertTrue(popup.key("tab"))
		self.assertFalse(popup.hex_field.editing)
		self.assertEqual(popup.value, "#ff0000")
		self.assertIs(popup.ring.current(), popup.sliders[0])
		self.assertTrue(popup.commit())
		self.assertEqual(popup.result, "#ff0000")

	def test_tab_away_keeps_focus_when_the_draft_is_invalid(self):
		popup = picker()
		popup.key("enter")
		popup.hex_field.value = "#12345"
		self.assertTrue(popup.key("tab"))
		self.assertIs(popup.ring.current(), popup.hex_field)
		self.assertTrue(popup.hex_field.editing)
		self.assertEqual(popup.hex_field.error, "need #rrggbb")
		self.assertEqual(popup.value, "#3366cc")
		self.assertFalse(popup.commit())
		self.assertFalse(popup.closed)

	def test_ok_click_commits_a_valid_draft_like_enter(self):
		popup = picker()
		popup.key("enter")
		popup.hex_field.value = "#ff0000"
		self.assertTrue(popup.key("mouse:press:{}:{}".format(
			popup.ok.x, popup.ok.y)))
		self.assertTrue(popup.closed)
		self.assertEqual(popup.result, "#ff0000")

	def test_cancel_click_restores_an_invalid_draft(self):
		popup = picker()
		popup.key("enter")
		popup.hex_field.value = "#12345"
		self.assertTrue(popup.key("mouse:press:{}:{}".format(
			popup.cancel.x, popup.cancel.y)))
		self.assertTrue(popup.closed)
		self.assertIsNone(popup.result)
		self.assertFalse(popup.hex_field.editing)
		self.assertIsNone(popup.hex_field.error)
		self.assertEqual(popup.hex_field.value, "#3366cc")

	def test_esc_mid_edit_closes_with_clean_boxes(self):
		popup = picker()
		popup.key("enter")
		popup.hex_field.value = "#12345"
		self.assertTrue(popup.key("esc"))
		self.assertTrue(popup.closed)
		self.assertFalse(popup.hex_field.editing)
		self.assertIsNone(popup.hex_field.error)
		self.assertEqual(popup.hex_field.value, "#3366cc")


class DrawTests(unittest.TestCase):
	def test_full_draw_shows_title_hex_and_contrast(self):
		popup = picker()
		self.assertIs(popup.draw(), popup)
		self.assertIn("Colour picker", row(popup.canvas, 2, 1, 20))
		self.assertIn("#3366cc", row(popup.canvas, 6, 2, 12))
		self.assertIn("bg", row(popup.canvas, 2, 8, 40))

	def test_low_contrast_warns_but_never_blocks(self):
		popup = picker("#777777", colours={"bg": "#666666", "zebra_bg": "#666666"})
		popup.draw()
		self.assertIn("below AA 4.5:1", row(popup.canvas, 2, 9, 20))
		self.assertTrue(popup.commit())
		self.assertEqual(popup.result, "#777777")

	def test_high_contrast_and_ascii_draw_without_glyphs(self):
		popup = picker("#ffffff", colours={"bg": "#000000", "zebra_bg": "#000000"},
					   cap=ASCII)
		popup.draw()
		text = "\n".join(popup.canvas.region(0, 0, 90, 24))
		self.assertNotIn("below AA", text)
		self.assertNotIn("\u2588", text)
		self.assertNotIn("\u2500", text)
		self.assertIn("#ffffff", text)

	def test_small_terminal_shows_the_resize_notice(self):
		canvas = new_canvas(60, 12)
		popup = ColorPicker(canvas, "#3366cc", cap=CAP, colours=COLOURS)
		popup.draw()
		self.assertIn("too small", "\n".join(canvas.region(0, 0, 60, 12)))

	def test_draw_without_background_colours_skips_the_warning(self):
		popup = ColorPicker(new_canvas(), "#3366cc", cap=CAP,
							colours={"fg": "#000000"})
		self.assertIs(popup.draw(), popup)
		text = "\n".join(popup.canvas.region(0, 0, 90, 24))
		self.assertNotIn("below AA", text)
		self.assertNotIn("bg", text)
