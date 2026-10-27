# Colour level tests: rgb()/index() numeric twin and the xterm tables
"""
		COLOUR LEVELS
		=============
Pins `tui/color_levels.py`: `rgb()` resolves a semantic key, hex or tuple the
same way `style()` does, and `index()` returns the exact nearest colour the
256/16 downgrade emits - so a curses consumer never needs a second table. The
shim case keeps `tui.palette.rgb()/index()` and the private helpers resolving at
their old path after the split.

The look tables themselves, the SGR emission order and the degradation matrix
stay in `tests/test_tui_palette.py`.
"""

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, color_levels, palette  # noqa: E402

SHIPPED = REPO / "themes" / "cozypurple.json"


def shipped_looks():
	"""The three looks as the shipped document writes them (one source)."""
	return json.loads(SHIPPED.read_text(encoding="utf-8"))["looks"]


LEVEL256 = caps.Capabilities(level="256", unicode=True, width=None,
							 isatty=True, plain=False, reason="test")
LEVEL16 = caps.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")


class IndexSeamTests(unittest.TestCase):
	"""`palette.index()` is the numeric twin of the 256/16 downgrade.

	It exists so a curses consumer can ask for the same nearest colour the
	escape-code renderer would pick, instead of keeping a second table.
	"""

	def test_index_matches_the_256_escape(self):
		for key in palette.SOFT:
			with self.subTest(key=key):
				out = palette.style("x", fg=key, cap=LEVEL256)
				match = re.match(r"^\x1b\[38;5;(\d+)mx\x1b\[0m$", out)
				self.assertIsNotNone(match, repr(out))
				self.assertEqual(int(match.group(1)), palette.index(key))
				self.assertEqual(palette.index(key), palette.index(palette.SOFT[key]))

	def test_index_matches_the_16_escape(self):
		for key in palette.SOFT:
			with self.subTest(key=key):
				out = palette.style("x", fg=key, cap=LEVEL16)
				match = re.match(r"^\x1b\[(3[0-7]|9[0-7])mx\x1b\[0m$", out)
				self.assertIsNotNone(match, repr(out))
				code = int(match.group(1))
				index = code - 30 if code < 90 else code - 90 + 8
				self.assertEqual(index, palette.index(key, level="16"))
				self.assertTrue(0 <= index <= 15)

	def test_index_accepts_rgb_tuples_and_other_themes(self):
		accent = shipped_looks()["default"]["accent"]
		self.assertEqual(palette.index(palette.rgb(accent)),
						 palette.index(accent))
		for name in palette.THEMES:
			with self.subTest(theme=name):
				value = palette.index("accent", theme=name)
				self.assertTrue(0 <= value <= 255)
				self.assertEqual(value, palette.index(
					palette.THEMES[name]["accent"], theme=name))
		self.assertNotEqual(palette.index("bg", theme="soft"),
							palette.index("bg", theme="contrast-light"))


class CompatibilityTests(unittest.TestCase):
	"""The split must not move a name off its old path (re-export shim)."""

	def test_the_moved_names_still_resolve_through_the_palette(self):
		for name in ("rgb", "index", "_rgb", "_hex", "_sgr", "_nearest",
					 "_NEAREST", "_XTERM256", "_CUBE", "_BASE16"):
			with self.subTest(name=name):
				self.assertIs(getattr(palette, name), getattr(color_levels, name))

	def test_the_nearest_cache_is_one_object(self):
		# A second copy of the cache would silently double the table work and
		# let the two modules disagree about a colour.
		color_levels._nearest((1, 2, 3), 0)
		self.assertIn(((1, 2, 3), 0, None), palette._NEAREST)
		self.assertIs(palette._NEAREST, color_levels._NEAREST)

	def test_the_numeric_twin_reads_and_never_writes_the_look(self):
		self.assertEqual(color_levels.rgb("#0a0b0c"), (10, 11, 12))
		self.assertEqual(color_levels.rgb((1, 2, 3)), (1, 2, 3))
		self.assertEqual(color_levels.index("#0a0b0c"),
						 color_levels.index((10, 11, 12)))


if __name__ == "__main__":
	unittest.main()
