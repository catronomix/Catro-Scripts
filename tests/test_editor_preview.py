# editor preview
"""
		Editor preview
		==============
The preview painter split out of `tui.editorviews` into
`tui.editor_preview`: the four moved names still resolve through the
views, the module does not import them back, and the border matrix
still frames every look with the document's own glyphs.
"""

import contextlib
import copy
import io
import json
import re
import shutil
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

from tui import (caps, config, editor, editor_keys, editor_nav, editor_overlays,
				 editor_preview, editoractions, editorpaint, editor_store,
				 editorviews, keys, palette, screen, table, theme_engine)  # noqa: E402
from tui.editor import ThemeEditor  # noqa: E402
from tui.editor_keys import EditorKeys  # noqa: E402
from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

SHIPPED = REPO / "themes" / "cozypurple.json"


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
		# The shipped document is the built-in fallback, so a temp checkout
		# needs its own copy of it (issue #33).
		shutil.copyfile(SHIPPED, theme_engine.THEMES_DIR / "cozypurple.json")
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

class PreviewSplitShimTests(unittest.TestCase):
	"""The preview painter moved to `tui.editor_preview`; old paths must resolve."""

	def test_the_moved_names_still_resolve_through_editorviews(self):
		for name in ("draw_preview", "glyphs_for", "button_text",
					 "_draw_scrollbar"):
			with self.subTest(name=name):
				self.assertIs(getattr(editorviews, name),
							  getattr(editor_preview, name))

	def test_editor_preview_does_not_import_the_views_or_their_importers(self):
		source = (REPO / "tui" / "editor_preview.py").read_text(encoding="utf-8")
		imports = [line for line in source.splitlines()
				   if line.startswith("from .") or line.startswith("import ")]
		self.assertTrue(imports)
		for line in imports:
			self.assertNotIn("editorviews", line)
			self.assertNotIn("editorpaint", line)
			self.assertNotIn("editoractions", line)
			self.assertNotIn("editorimport", line)


class PreviewFrameTests(EditorTestCase):
	"""Item 2: the document's border_style frames every preview look."""

	def preview(self, style, look="default", *, width=29, height=12, cap=None,
				**properties):
		"""Paint one preview band on a fresh 90x24 canvas; returns canvas, doc."""
		document = copy.deepcopy(self.make().document)
		document["properties"]["border_style"] = style
		document["properties"].update(properties)
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
								fg=document["looks"][look]["border-fg"],
								cap=self.cap))

	def test_ascii_console_degrades_the_frame_but_keeps_the_band(self):
		canvas, _, band = self.preview("heavy", cap=make_cap(unicode=False))
		self.assertEqual(band[0][0], "+")
		self.assertEqual(band[0][-1], "+")
		self.assertEqual(band[-1][0], "+")
		self.assertEqual(band[1][0], "|")
		self.assertIn("-", band[0])
		self.assertIn("60%", band[-2])

	def test_the_documents_corner_char_lands_on_the_preview(self):
		for char in ("@", "x", "#", "+", "o", "*"):
			with self.subTest(char=char):
				_, _, band = self.preview("rounded", **{"corner-char": char})
				self.assertEqual([band[0][0], band[0][-1],
								  band[-1][0], band[-1][-1]], [char] * 4)

	def test_corner_none_keeps_the_family_corners_byte_identical(self):
		_, _, band = self.preview("double", **{"corner-char": "none"})
		glyphs = table.BORDER_GLYPHS["double"]
		self.assertEqual([band[0][0], band[0][-1], band[-1][0], band[-1][-1]],
						 [glyphs["tl"], glyphs["tr"],
						  glyphs["bl"], glyphs["br"]])

	def test_an_ascii_console_keeps_ascii_corners_unless_one_is_asked_for(self):
		ascii_cap = make_cap(unicode=False)
		_, _, plain = self.preview("heavy", cap=ascii_cap)
		self.assertEqual([plain[0][0], plain[0][-1],
						  plain[-1][0], plain[-1][-1]], ["+"] * 4)
		_, _, custom = self.preview("heavy", cap=ascii_cap,
									**{"corner-char": "@"})
		self.assertEqual([custom[0][0], custom[0][-1],
						  custom[-1][0], custom[-1][-1]], ["@"] * 4)
		self.assertEqual(custom[1][0], "|")
		self.assertIn("-", custom[0])

	def test_a_borderless_preview_gains_no_corner(self):
		_, _, band = self.preview("none", **{"corner-char": "@"})
		self.assertEqual(band[0][0], " ")
		self.assertEqual(band[-1][0], " ")

	def test_border_style_none_keeps_the_preview_footprint(self):
		# `none` is a space frame, not a dropped frame: same outer box, the
		# same one-cell inset and the same row plan as a drawn frame.
		none_canvas, _, none_band = self.preview("none")
		framed_canvas, document, framed_band = self.preview("rounded")
		self.assertEqual(len(none_band), len(framed_band))
		for row in range(1, len(none_band) - 1):
			self.assertEqual(none_band[row][1:-1], framed_band[row][1:-1])
		self.assertEqual(none_band[0][0], " ")
		self.assertEqual(none_band[-1][0], " ")
		edge = palette.prefix(fg=document["looks"]["default"]["border-fg"],
							  cap=self.cap)

		def edge_cells(canvas):
			return sum(1 for row in canvas._colors[2:2 + 12]
					   for cell in row[1:1 + 29] if cell == edge)

		# The painted space frame costs exactly the cells a drawn one does.
		self.assertEqual(edge_cells(none_canvas), edge_cells(framed_canvas))

	def test_a_filled_preview_button_paints_the_button_tokens(self):
		document = copy.deepcopy(self.make().document)
		look = document["looks"]["default"]
		look["button-fg"], look["button-bg"] = "#010203", "#040506"
		out = editor_preview.button_text("OK", document["properties"], look,
										 cap=self.cap)
		self.assertTrue(out.startswith(palette.prefix(
			fg="#010203", bg="#040506", cap=self.cap)), out)
		# The mirror follows chrome's focus branch: accent focus moves the ground.
		document["properties"]["focus_style"] = "accent"
		look["button-bg-active"] = "#070809"
		out = editor_preview.button_text("OK", document["properties"], look,
										 focused=True, cap=self.cap)
		self.assertTrue(out.startswith(palette.prefix(
			fg="#010203", bg="#070809", cap=self.cap)), out)

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

if __name__ == "__main__":
	unittest.main()
