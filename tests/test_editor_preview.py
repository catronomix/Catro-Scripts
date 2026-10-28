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
				 editorviews, keys, palette, preview_plan, screen, table,
				 theme_engine)  # noqa: E402
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
								bg=document["looks"][look]["border-bg"],
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
							  bg=document["looks"]["default"]["border-bg"],
							  cap=self.cap)

		def edge_cells(canvas):
			return sum(1 for row in canvas._colors[2:2 + 12]
					   for cell in row[1:1 + 29] if cell == edge)

		# The painted space frame costs exactly the cells a drawn one does.
		self.assertEqual(edge_cells(none_canvas), edge_cells(framed_canvas))

	def test_header_align_moves_the_framed_title(self):
		_, document, left = self.preview("rounded", header_align="left")
		_, _, center = self.preview("rounded", header_align="center")
		_, _, right = self.preview("rounded", header_align="right")
		title = editorviews.preview_title(document, "default")

		def column(band):
			return band[0].index(title)

		self.assertEqual(column(left), 3)
		self.assertGreater(column(center), column(left))
		self.assertGreater(column(right), column(center))
		# Right aligns the label's trailing space against the closing corner.
		self.assertEqual(column(right) + len(title), 27)

	def test_the_framed_title_is_a_border_pair_heading(self):
		# A preview title is a real panel heading: border-fg as the ground and
		# border-bg as the ink, not the frame's own pair.
		canvas, document, band = self.preview("rounded")
		look = document["looks"]["default"]
		title = editorviews.preview_title(document, "default")
		column = band[0].index(title) + 1
		heading = palette.prefix(fg=look["border-bg"], bg=look["border-fg"],
								 bold=True, cap=self.cap)
		self.assertEqual(canvas._colors[2][column], heading)

	def test_the_90x24_preview_shows_a_table_header_and_the_modal(self):
		ed = self.make()
		x, y, width, height = ed.rects[0]
		lines = self.lines(ed)
		band = "\n".join(row[x:x + width] for row in lines[y:y + height])
		self.assertEqual((y, height), (2, 14))
		self.assertIn("ID", band)
		self.assertIn("alpha", band)
		self.assertIn("beta", band)
		self.assertIn("dialog - overwrite?", band)
		self.assertIn("[ Cancel ]", band)
		self.assertIn("60%", band)

	def test_the_taller_preview_keeps_the_90x24_frame_inside_the_canvas(self):
		ed = self.make()
		lines = self.lines(ed)
		x, y, width, height = ed.rects[5]
		self.assertEqual((y, height), (16, 6))
		self.assertLessEqual(y + height, 22)
		# The Actions frame closes above the two status rows, unharmed.
		self.assertEqual(lines[y + height - 1][x], "\u2514")
		self.assertIn("Tab panel", lines[22])
		self.assertIn("Tab panel", lines[23])

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

	def test_the_plan_lists_the_twelve_content_rows_in_display_order(self):
		kinds = [kind for kind, _, _ in preview_plan.rows(13)]
		self.assertEqual(kinds, [
			"rule_top", "thead", "trow_a", "trow_b", "rule_bot", "buttons",
			"field", "look", "menu", "modal_t", "modal_b", "ready"])
		# The bar is never a plan row: the painter always keeps the last
		# inner row for it.
		self.assertNotIn("bar", kinds)

	def test_a_90x24_band_drops_only_the_table_bottom_rule(self):
		kinds = [kind for kind, _, _ in preview_plan.rows(12)]
		self.assertEqual(kinds, [
			"rule_top", "thead", "trow_a", "trow_b", "buttons", "field",
			"look", "menu", "modal_t", "modal_b", "ready"])

	def test_the_drop_order_keeps_the_bar_last(self):
		# Every band from four inner rows up keeps a bar-sized tail and never
		# leaves the modal behind the table.
		for inner_h in range(4, 14):
			with self.subTest(inner_h=inner_h):
				kinds = [kind for kind, _, _ in preview_plan.rows(inner_h)]
				self.assertLessEqual(len(kinds), inner_h - 1)
				if inner_h >= 4:
					self.assertTrue(kinds)

	def test_the_plan_rows_carry_a_role_and_a_ground(self):
		rows = {kind: (role, bg) for kind, role, bg in preview_plan.rows(13)}
		self.assertEqual(rows["rule_top"], ("border-fg", "border-bg"))
		self.assertEqual(rows["rule_bot"], ("border-fg", "border-bg"))
		self.assertEqual(rows["thead"], ("header-fg", "bg-inside"))
		self.assertEqual(rows["trow_a"], ("fg", "bg"))
		self.assertEqual(rows["trow_b"], ("fg", "bg-stripe"))
		self.assertEqual(rows["field"], ("fg", "bg-inside"))
		self.assertEqual(rows["ready"], ("fg-success", "bg-inside"))

	def test_the_modal_rows_paint_in_the_loop_not_an_overlay(self):
		self.assertFalse(hasattr(editor_preview, "_draw_modal"))
		_, document, band = self.preview("rounded")
		text = "\n".join(band)
		self.assertIn("dialog - overwrite?", text)
		self.assertIn("[ Cancel ]", text)
		# Both rows are full-width on the inside ground, like every other row.
		title_row = band.index(next(row for row in band
									if "dialog - overwrite?" in row))
		self.assertEqual(len(band[title_row]), 29)
		self.assertEqual(len(band[title_row + 1]), 29)

	def test_the_inner_band_is_filled_every_row_every_column(self):
		canvas, _, _ = self.preview("rounded")
		# Outer band is rows 2..13, columns 1..29: the inner 27x10 must all
		# carry a colour, otherwise the terminal shows through the preview.
		for row in range(3, 12):
			for col in range(2, 28):
				with self.subTest(row=row, col=col):
					self.assertIsNotNone(canvas._colors[row][col])

	def test_the_preview_ground_is_the_inside_ground(self):
		canvas, document, _ = self.preview("rounded")
		ground = palette.prefix(bg=document["looks"]["default"]["bg-inside"],
								cap=self.cap)
		# The bar row and a plain content row both sit on it.
		self.assertIn(ground, canvas._colors[12][2])
		self.assertIn(ground, canvas._colors[8][2])

	def test_the_rules_paint_glyphs_on_the_border_ground(self):
		canvas, document, band = self.preview("rounded", height=14)
		look = document["looks"]["default"]
		rule = palette.prefix(fg=look["border-fg"], bg=look["border-bg"],
							  cap=self.cap)
		self.assertEqual(canvas._colors[3][1], rule)
		self.assertTrue(set(band[1][1:-1]) <= {"\u2500"}, band[1])

	def test_the_preview_scrollbar_keeps_the_inside_ground(self):
		canvas, document, _ = self.preview("rounded")
		look = document["looks"]["default"]
		ground = palette.prefix(bg=look["bg-inside"], cap=self.cap)
		column = [canvas._colors[row][28] for row in range(3, 12)]
		for colour in column:
			self.assertIn(ground, colour)

	def test_the_preview_height_is_capped_at_fifteen(self):
		ed = self.make(90, 40)
		self.assertEqual(ed.rects[0][3], 15)
		self.assertEqual(ed.rects[0][1], 2)
		band = "\n".join(row[1:1 + ed.rects[0][2]]
						 for row in self.lines(ed)[2:17])
		self.assertIn("dialog - overwrite?", band)
		self.assertIn("60%", band)

	def test_the_twelve_row_band_keeps_the_bar_and_drops_the_rules(self):
		_, document, band = self.preview("rounded")
		title = editorviews.preview_title(document, "default")
		self.assertEqual(len(band), 12)
		self.assertEqual(band[0].count(title), 1)  # title lives in the top rule
		self.assertEqual(band[0][0], "\u250c")
		self.assertEqual(band[-1][0], "\u2514")
		self.assertIn("60%", band[-2])
		# A twelve-row band drops the table's top and bottom rules and the
		# second stripe, keeping the header, one body row and the modal.
		self.assertFalse(any("\u2500" in row for row in band[1:-1]))
		self.assertIn("alpha", "\n".join(band))
		self.assertNotIn("beta", "\n".join(band))

	def test_a_short_preview_never_drops_the_progress_bar(self):
		for height in range(6, 14):
			with self.subTest(height=height):
				_, _, band = self.preview("rounded", height=height)
				self.assertIn("60%", band[-2], "bar dropped at height %d" % height)
				self.assertEqual(band[-1][0], "\u2514")

if __name__ == "__main__":
	unittest.main()
