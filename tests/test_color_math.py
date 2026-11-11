# Colour math tests: hex/RGB/HSV conversions, WCAG helpers, the grid cell scale
"""
			COLOUR MATH
			===========
Coverage for `tui/color_math.py`: the pure conversions (hex <-> RGB, RGB <->
HSV including the hue wrap), the WCAG luminance/contrast pair with the AA
threshold, and `cell_index`, the 0-1 component -> 16-column mapping. The
picker's popup behaviour lives in `test_tui_colorpicker.py`; the last case here
pins the compatibility shim, so the moved names still resolve through
`tui.colorpicker` and `tui`.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

import tui  # noqa: E402
from tui import color_math, colorpicker  # noqa: E402
from tui.color_math import (STEPS, WCAG_AA, cell_index, contrast_ratio,  # noqa: E402
							hex_to_rgb, hsv_to_rgb, luminance, rgb_to_hex,
							rgb_to_hsv)


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


class CompatibilityTests(unittest.TestCase):
	"""The split must not move a name off its old path (re-export shim)."""

	def test_the_moved_names_still_resolve_through_the_picker_and_the_package(self):
		# `STEPS`/`cell_index` were only ever `colorpicker` attributes; the rest
		# are also re-exported by the package.
		for name in ("STEPS", "cell_index"):
			self.assertIs(getattr(colorpicker, name), getattr(color_math, name))
		for name in ("WCAG_AA", "contrast_ratio", "hex_to_rgb", "hsv_to_rgb",
					 "luminance", "rgb_to_hex", "rgb_to_hsv"):
			moved = getattr(color_math, name)
			self.assertIs(getattr(colorpicker, name), moved)
			self.assertIs(getattr(tui, name), moved)

	def test_import_is_inert(self):
		# No printing, no terminal access, no third-party import: the module
		# only needs `colorsys` from the standard library.
		self.assertEqual(color_math.__name__, "tui.color_math")
		self.assertTrue(callable(color_math.hex_to_rgb))


if __name__ == "__main__":
	unittest.main()
