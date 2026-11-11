# editor keys
"""
		Editor keys
		===========
The token router that moved to `tui.editor_keys` as the `EditorKeys`
mixin: the moved methods resolve through `ThemeEditor`, the session
keeps its own, the MRO stays single and the mixin imports neither the
editor nor a painter.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import editor_keys  # noqa: E402
from tui.editor import ThemeEditor  # noqa: E402
from tui.editor_keys import EditorKeys  # noqa: E402

class KeySplitShimTests(unittest.TestCase):
	"""The token router moved to `tui.editor_keys` as a mixin; paths must hold."""

	MOVED = ("handle", "_move", "_activate", "_small", "_small_key", "_escape",
			 "_property_field", "_field_for", "_field_value")

	SESSION = ("__init__", "_initial", "_initial_look", "open", "_layout",
			   "_visible", "_window", "_panel_at", "pump", "_current_look",
			   "_look_colours", "quit", "save_prompt", "load_popup", "draw",
			   "run", "preview_titles")

	def test_the_moved_methods_resolve_to_the_mixin(self):
		for name in self.MOVED:
			with self.subTest(name=name):
				self.assertIs(getattr(ThemeEditor, name),
							  getattr(EditorKeys, name))

	def test_the_session_methods_stay_on_the_editor(self):
		for name in self.SESSION:
			with self.subTest(name=name):
				self.assertIn(name, ThemeEditor.__dict__)
				self.assertNotIn(name, EditorKeys.__dict__)

	def test_the_mixin_comes_first_in_a_single_mro(self):
		self.assertEqual([cls.__name__ for cls in ThemeEditor.__mro__],
						 ["ThemeEditor", "EditorKeys", "object"])

	def test_editor_keys_does_not_import_the_editor_or_a_painter(self):
		source = (REPO / "tui" / "editor_keys.py").read_text(encoding="utf-8")
		imports = [line for line in source.splitlines()
				   if line.startswith("from .") or line.startswith("import ")]
		self.assertTrue(imports)
		for line in imports:
			for blocked in ("editorpaint", "editor_store", "editorimport"):
				self.assertNotIn(blocked, line)
		self.assertNotIn("from . import editor", imports)
		self.assertNotIn("from .editor import", " ".join(imports))


if __name__ == "__main__":
	unittest.main()
