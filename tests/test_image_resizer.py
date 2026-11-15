# Regression tests for image_resizer's large-source handling
"""
			IMAGE RESIZER LARGE SOURCE TESTS
			=================================
Pins the two fixes for poster-sized artwork (200+ Mpixel PNG/TIFFs):

	- Pillow's decompression-bomb guard is raised above the sizes this script
	  is expected to shrink, so large print files are processed instead of
	  rejected as attacks;
	- sources above the prescale budget are box-reduced before the final
	  resample, but never below the requested target (no accidental upscale).

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import image_resizer  # noqa: E402

try:
	from PIL import Image
except ImportError:  # pillow is optional for the suite
	Image = None


class BombGuardTest(unittest.TestCase):
	def test_guard_clears_the_artwork_that_failed(self):
		"""The reported 279 Mpixel PNGs must sit well under the guard."""
		self.assertGreater(image_resizer.MAX_SOURCE_PIXELS, 279_565_632)


@unittest.skipIf(Image is None, "pillow is not installed")
class PrescaleSourceTest(unittest.TestCase):
	def test_small_source_is_returned_untouched(self):
		with Image.new("RGB", (40, 30)) as img:
			self.assertIs(image_resizer._prescale_source(img, 10, 10), img)

	def test_oversized_source_is_reduced_to_the_budget(self):
		with Image.new("RGB", (200, 100)) as img, \
				mock.patch.object(image_resizer, "PRESCALE_PIXEL_BUDGET", 1000):
			reduced = image_resizer._prescale_source(img, 10, 10)
		# 20000 / 1000 = 20 -> isqrt() = 4
		self.assertEqual(reduced.size, (50, 25))

	def test_reduce_never_drops_below_the_target(self):
		with Image.new("RGB", (200, 100)) as img, \
				mock.patch.object(image_resizer, "PRESCALE_PIXEL_BUDGET", 1000):
			# A target this close to the source leaves no room to shrink.
			reduced = image_resizer._prescale_source(img, 190, 95)
		self.assertEqual(reduced.size, (200, 100))


if __name__ == "__main__":
	unittest.main()
