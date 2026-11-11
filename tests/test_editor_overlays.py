# editor overlays
"""
		Editor overlays
		===============
The popup painters that moved to `tui.editor_overlays`: the four moved
names still resolve through `editorpaint`, the band painters stayed
there, and the overlay module imports neither the painter nor the
editor.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import editor_overlays, editorpaint  # noqa: E402

class OverlaySplitShimTests(unittest.TestCase):
	"""The popup painters moved to `tui.editor_overlays`; old paths must resolve."""

	MOVED = ("_overlay", "_draw_help", "_draw_save", "_draw_load")

	def test_the_moved_names_still_resolve_through_editorpaint(self):
		for name in self.MOVED:
			with self.subTest(name=name):
				self.assertIs(getattr(editorpaint, name),
							  getattr(editor_overlays, name))

	def test_the_band_painters_stayed_in_editorpaint(self):
		for name in ("draw", "_paint", "_draw_title", "_draw_properties",
					 "_draw_colours", "_draw_actions", "_draw_status", "_blit"):
			with self.subTest(name=name):
				self.assertTrue(hasattr(editorpaint, name))
				self.assertFalse(hasattr(editor_overlays, name))

	def test_editor_overlays_does_not_import_the_painter_or_the_editor(self):
		source = (REPO / "tui" / "editor_overlays.py").read_text(encoding="utf-8")
		imports = [line for line in source.splitlines()
				   if line.startswith("from .") or line.startswith("import ")]
		self.assertTrue(imports)
		for line in imports:
			for blocked in ("editorpaint", "editoractions", "editorimport",
							"editor_store"):
				self.assertNotIn(blocked, line)
		self.assertNotIn("from . import editor", imports)

if __name__ == "__main__":
	unittest.main()
