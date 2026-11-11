# editor nav
"""
		Editor nav
		==========
The caption tables that moved from `tui.editorviews` to
`tui.editor_nav`: the old paths still resolve through the views and the
leaf imports nothing back.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import editor_nav, editorviews  # noqa: E402

class NavSplitShimTests(unittest.TestCase):
	"""The caption tables moved to `tui.editor_nav`; old paths must resolve."""

	def test_the_moved_names_still_resolve_through_editorviews(self):
		for name in ("LOOK_ORDER", "LOOK_LABELS", "PANELS", "BUTTONS",
					 "HELP_LINE", "HELP_LINES", "look_label", "preview_title",
					 "preview_titles"):
			with self.subTest(name=name):
				self.assertIs(getattr(editorviews, name), getattr(editor_nav, name))

	def test_editor_nav_does_not_import_the_views_or_their_importers(self):
		source = (REPO / "tui" / "editor_nav.py").read_text(encoding="utf-8")
		body = source.split('"""', 2)[2]
		self.assertNotIn("import", body)
		self.assertNotIn("editorviews", body)

if __name__ == "__main__":
	unittest.main()
