# Rendering-property tests: border/table/header/button/scrollbar seams
"""
		RENDERING PROPERTIES (THEME ENGINE, STAGE 2)
		============================================
The theme document's `properties` shape what the renderers emit: the table
frame (`border_style`), the table layout (`table_style`, `table_zebra`), the
masthead (`header_align`), the `chrome.button` and `chrome.scrollbar` seams and
the additive `underline` attribute on `palette.prefix()/style()`.

Two rules are pinned here, in this order:

	- the default look does not move: `rounded`/`box`/zebra/left reproduce the
		shipped bytes (the golden fixture in `test_list_golden.py` and the exact
		spans in `test_tui_table.py`/`test_tui_chrome.py` keep owning that);
	- every legal property value is exercised, and explicit caller arguments
		(`box=`, `zebra=`) still beat the theme.

Every test points `THEMES_DIR`/`THEME_FILE`/`CONFIG_FILE` at a temporary
directory, so the repository never gains a theme, a selection or a config.
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import caps, chrome, config, palette, table, theme_engine  # noqa: E402
from tui.text import display_width, strip_ansi  # noqa: E402

SHIPPED = REPO / "themes" / "cozypurple.json"

# soft's truecolor codes, pinned literally (same values as the other tui tests).
BORDER = "\033[38;2;163;146;192m"
HEADER = "\033[38;2;245;205;104m"
FG = "\033[38;2;212;200;235m"
BG = "\033[48;2;27;23;38m"
SURFACE = "\033[48;2;41;34;56m"
STRIPE = "\033[48;2;53;43;73m"
ACCENT = "\033[38;2;245;205;104m"
MUTED = BORDER
BOLD = "\033[1m"
REVERSE = "\033[7m"
UNDERLINE = "\033[4m"
RESET = "\033[0m"


def capabilities(level="true", unicode=True, plain=False, isatty=True):
	return caps.Capabilities(level=level, unicode=unicode, width=None,
							 isatty=isatty, plain=plain, reason="test")


TRUE = capabilities()
SIXTEEN = capabilities(level="16")
MONO = capabilities(level="none")
CAP_NONE = MONO
ASCII = capabilities(unicode=False)
PIPE = capabilities(level="none", unicode=False, plain=True, isatty=False)

HEADERS = ["ID", "Name"]
ROWS = [("1", "list"), ("2", "theme")]


class PropertyCase(unittest.TestCase):
	"""A temporary checkout whose theme carries the properties under test."""

	def setUp(self):
		self._temp = tempfile.TemporaryDirectory()
		self.root = Path(self._temp.name)
		self.themes = self.root / "themes"
		self.themes.mkdir()
		shutil.copyfile(SHIPPED, self.themes / "cozypurple.json")
		theme_engine.THEMES_DIR = self.themes
		theme_engine.THEME_FILE = self.root / "theme.ini"
		config.CONFIG_FILE = self.root / "config.ini"
		theme_engine._CACHE.clear()
		self._environ = mock.patch.dict(os.environ, {}, clear=True)
		self._environ.start()

	def tearDown(self):
		self._environ.stop()
		theme_engine.THEMES_DIR = None
		theme_engine.THEME_FILE = None
		config.CONFIG_FILE = None
		theme_engine._CACHE.clear()
		self._temp.cleanup()

	def theme(self):
		"""The temp document, safe to mutate."""
		return json.loads((self.themes / "cozypurple.json").read_text(encoding="utf-8"))

	def write(self, document):
		(self.themes / "cozypurple.json").write_text(
			json.dumps(document, indent=2) + "\n", encoding="utf-8")
		theme_engine._CACHE.clear()

	def set_properties(self, **overrides):
		document = self.theme()
		document["properties"].update(overrides)
		self.write(document)
		return document

	def render(self, **kw):
		return table.render_table(HEADERS, ROWS, cap=kw.pop("cap", TRUE),
								  theme="soft", **kw)


class BorderStyleTests(PropertyCase):
	"""`border_style` picks the frame; `table.style` still overrides it."""

	def test_default_is_the_shipped_rounded_set(self):
		self.assertEqual(palette.properties()["border_style"], "rounded")
		self.assertIs(table.glyphs_for(TRUE), table.UNICODE_GLYPHS)

	def test_every_border_style_has_its_own_glyph_family(self):
		families = [table.BORDER_GLYPHS[value]
					for value in theme_engine.PROPERTY_VALUES["border_style"]]
		self.assertEqual(len(families), 6)
		self.assertEqual(len({id(family) for family in families}), 6,
						 "two border styles share one glyph set")

	def test_each_style_reaches_the_frame(self):
		for value in theme_engine.PROPERTY_VALUES["border_style"]:
			with self.subTest(border_style=value):
				self.set_properties(border_style=value)
				glyphs = table.BORDER_GLYPHS[value]
				self.assertIs(table.glyphs_for(TRUE), glyphs)
				top = strip_ansi(self.render().split("\n")[0])
				self.assertTrue(top.startswith(glyphs["tl"]), repr(top))

	def test_none_keeps_the_layout_and_drops_the_borders(self):
		rounded = [display_width(strip_ansi(line))
				   for line in self.render().split("\n")]
		self.set_properties(border_style="none")
		out = self.render()
		for glyph in ("\u2500", "\u2502", "\u250c", "\u2510", "\u2514", "\u2518"):
			self.assertNotIn(glyph, strip_ansi(out))
		self.assertEqual([display_width(strip_ansi(line))
						  for line in out.split("\n")], rounded)
		self.assertIn("list", strip_ansi(out))

	def test_table_style_ascii_forces_ascii_whatever_the_border_style(self):
		self.set_properties(border_style="heavy")
		config.set("table", "style", "ascii")
		self.assertIs(table.glyphs_for(TRUE), table.ASCII_GLYPHS)
		self.assertIn("|", self.render())

	def test_table_style_unicode_keeps_the_engine_glyphs(self):
		self.set_properties(border_style="double")
		config.set("table", "style", "unicode")
		self.assertIs(table.glyphs_for(TRUE), table.DOUBLE_GLYPHS)

	def test_a_non_unicode_capability_degrades_every_family_but_none(self):
		for value in ("rounded", "square", "heavy", "double"):
			with self.subTest(border_style=value):
				self.set_properties(border_style=value)
				self.assertIs(table.glyphs_for(ASCII), table.ASCII_GLYPHS)
		self.set_properties(border_style="none")
		self.assertIs(table.glyphs_for(ASCII), table.SPACE_GLYPHS)


class TableStyleTests(PropertyCase):
	"""`table_style`/`table_zebra` apply only where the caller says nothing."""

	def test_box_is_the_default_and_matches_an_explicit_box(self):
		default = self.render()
		explicit = self.render(box=True, zebra=True)
		self.assertEqual(default, explicit)
		self.assertEqual(len(default.split("\n")), 6)

	def test_borderless_is_rules_and_verticals_off_cells_padded(self):
		self.set_properties(table_style="borderless")
		out = self.render()
		self.assertNotIn("\u2502", out)
		self.assertNotIn("\u250c", out)
		lines = out.split("\n")
		self.assertEqual(len(lines), 3)
		self.assertIn("list", lines[1])
		self.assertEqual(display_width(strip_ansi(lines[1])),
						 display_width(strip_ansi(lines[0])))

	def test_compact_is_one_rule_under_the_header_and_one_at_the_bottom(self):
		self.set_properties(table_style="compact")
		lines = self.render().split("\n")
		self.assertEqual(len(lines), 5)
		self.assertNotIn("\u2502", "\n".join(lines))
		for index in (1, 4):
			self.assertTrue(set(strip_ansi(lines[index])) <= {"\u2500"},
							repr(strip_ansi(lines[index])))
		self.assertIn("list", lines[2])

	def test_zebra_off_drops_the_alternating_bands(self):
		self.assertIn(BG, self.render())
		self.set_properties(table_zebra=False)
		out = self.render()
		# The header and every rule still sit on the inside ground; only the
		# data rows lose the zebra pair.
		data = out.split("\n")[3:5]
		for row in data:
			self.assertNotIn(BG, row)
			self.assertNotIn(STRIPE, row)
		self.assertNotIn(STRIPE, out)
		self.assertIn(SURFACE, out)
		self.assertIn(FG, out)

	def test_an_explicit_caller_argument_beats_the_property(self):
		self.set_properties(table_style="borderless", table_zebra=False)
		self.assertIn("\u250c", self.render(box=True))
		self.assertIn(BG, self.render(zebra=True))

	def test_piped_output_ignores_the_layout_properties(self):
		self.set_properties(table_style="borderless", table_zebra=False)
		self.assertEqual(self.render(cap=PIPE).split("\n")[0], "ID\tName")


class HeaderAlignTests(PropertyCase):
	"""`header_align` moves the label inside the same `surface` band."""

	def bands(self, width=20):
		self.set_properties(header_align="left")
		return chrome.header("TITLE", "sub", width=width, cap=TRUE).split("\n")

	def test_left_is_the_shipped_shape(self):
		self.assertEqual(self.bands()[0],
						 HEADER + SURFACE + BOLD + " TITLE" + " " * 14 + RESET)

	def test_center_and_right_keep_the_width_and_move_the_label(self):
		left = self.bands()[0]
		self.set_properties(header_align="center")
		center = chrome.header("TITLE", "sub", width=20, cap=TRUE).split("\n")[0]
		self.set_properties(header_align="right")
		right = chrome.header("TITLE", "sub", width=20, cap=TRUE).split("\n")[0]
		for line in (center, right):
			self.assertEqual(display_width(strip_ansi(line)), 20)
		self.assertEqual(strip_ansi(center), "       TITLE        ")
		self.assertEqual(strip_ansi(right), "              TITLE ")
		self.assertNotEqual(left, center)
		self.assertNotEqual(center, right)

	def test_the_subtitle_follows_the_same_alignment(self):
		self.set_properties(header_align="right")
		lines = chrome.header("TITLE", "sub", width=20, cap=CAP_NONE).split("\n")
		self.assertEqual(lines[0], "              TITLE ")
		self.assertEqual(lines[1], "                sub ")

	def test_plain_and_monochrome_paths_carry_no_alignment_escapes(self):
		self.set_properties(header_align="center")
		self.assertEqual(chrome.header("TITLE", width=20, cap=PIPE), "TITLE")
		self.assertEqual(chrome.header("TITLE", width=10, cap=MONO),
						 "  TITLE   \n" + "\u2500" * 10)


class ButtonTests(PropertyCase):
	"""`chrome.button` decorates, styles and focuses one label."""

	def test_default_is_a_filled_bracketed_button(self):
		self.assertEqual(chrome.button("OK", cap=TRUE),
						 "\033[38;2;27;23;38m" + "\033[48;2;245;205;104m"
						 + "[ OK ]" + RESET)

	def test_every_decoration_wraps_the_label(self):
		expected = {
			"none": " OK ", "brackets": "[ OK ]", "angles": "< OK >",
			"braces": "{ OK }", "colons": ": OK :", "pipes": "| OK |",
			"chevron": "\u00ab OK \u00bb", "ellipsis": "\u2026 OK \u2026",
		}
		self.assertEqual(set(expected), set(theme_engine.PROPERTY_VALUES[
			"button_decoration"]))
		for value, text in expected.items():
			with self.subTest(button_decoration=value):
				self.set_properties(button_decoration=value)
				self.assertEqual(chrome.button("OK", cap=MONO), text)
				styled = chrome.button("OK", cap=TRUE)
				self.assertEqual(strip_ansi(styled), text)
				# The pad is painted, not dropped: the whole label keeps the
				# filled ground and the trailing reset.
				self.assertTrue(styled.startswith(
					"\033[38;2;27;23;38m\033[48;2;245;205;104m"), styled)
				self.assertTrue(styled.endswith(RESET), styled)
		# `none` is a painted pad, not a collapse: the button keeps a footprint
		# of label + one cell each side.
		self.set_properties(button_decoration="none")
		self.assertEqual(display_width(strip_ansi(chrome.button("OK", cap=TRUE))),
						 len("OK") + 2)

	def test_unicode_less_decoration_uses_the_ascii_spelling(self):
		for value, text in (("chevron", "<< OK >>"), ("ellipsis", "... OK ...")):
			with self.subTest(button_decoration=value):
				self.set_properties(button_decoration=value)
				self.assertEqual(strip_ansi(chrome.button("OK", cap=ASCII)), text)

	def test_every_style_paints_the_label_its_own_way(self):
		cases = {
			"filled": "\033[38;2;27;23;38m" + "\033[48;2;245;205;104m",
			"outline": BORDER,
			"plain": FG,
			"underline": FG + UNDERLINE,
		}
		self.assertEqual(set(cases), set(theme_engine.PROPERTY_VALUES[
			"button_style"]))
		for value, lead in cases.items():
			with self.subTest(button_style=value):
				self.set_properties(button_style=value)
				self.assertEqual(chrome.button("OK", cap=TRUE),
								 lead + "[ OK ]" + RESET)

	def test_every_focus_style_restyles_a_focused_button(self):
		self.set_properties(button_style="plain")
		for value, tail in (("reverse", REVERSE), ("underline", UNDERLINE)):
			with self.subTest(focus_style=value):
				self.set_properties(focus_style=value)
				self.assertEqual(chrome.button("OK", focused=True, cap=TRUE),
								 FG + tail + "[ OK ]" + RESET)
		self.set_properties(focus_style="accent")
		self.assertEqual(chrome.button("OK", focused=True, cap=TRUE),
						 ACCENT + "[ OK ]" + RESET)

	def test_disabled_forces_muted_and_wins_over_focus(self):
		self.set_properties(focus_style="accent")
		self.assertEqual(chrome.button("OK", focused=True, disabled=True, cap=TRUE),
						 MUTED + "[ OK ]" + RESET)

	def test_every_level_degrades_without_losing_the_decoration(self):
		self.assertEqual(chrome.button("OK", cap=MONO), "[ OK ]")
		self.assertEqual(chrome.button("OK", cap=PIPE), "[ OK ]")
		self.assertNotIn("38;2", chrome.button("OK", cap=SIXTEEN))
		self.assertIn("[ OK ]", chrome.button("OK", cap=SIXTEEN))


class ScrollbarTests(PropertyCase):
	"""`chrome.scrollbar` is one single-column cell per row."""

	def column(self, cap=TRUE, **kw):
		return chrome.scrollbar(kw.pop("height", 6), cap=cap, **kw)

	def test_every_style_has_its_own_glyph_pair(self):
		self.assertEqual(set(theme_engine.PROPERTY_VALUES["scrollbar_style"]),
						 set(chrome.SCROLLBAR_GLYPHS))
		expected = {"block": ("\u2588", "\u2591"), "line": ("\u2503", "\u2502"),
					"ascii": ("#", "|")}
		for value, (thumb, track) in expected.items():
			with self.subTest(scrollbar_style=value):
				self.set_properties(scrollbar_style=value)
				rows = self.column(total=60)
				self.assertEqual(len(rows), 6)
				for row in rows:
					self.assertEqual(display_width(strip_ansi(row)), 1)
				self.assertIn(thumb, "".join(rows))
				self.assertIn(track, "".join(rows))

	def test_the_thumb_tracks_the_offset(self):
		self.set_properties(scrollbar_style="ascii")
		self.assertTrue(self.column(height=8, total=80, offset=0)[0].endswith("#" + RESET))
		self.assertTrue(self.column(height=8, total=80, offset=500)[-1].endswith("#" + RESET))
		middle = self.column(height=8, total=80, offset=40)
		self.assertEqual(strip_ansi(middle[0]), "|")
		self.assertEqual(strip_ansi(middle[-1]), "|")

	def test_colours_are_accent_over_muted(self):
		rows = self.column(height=4, total=40)
		self.assertEqual(rows[0], ACCENT + "\u2588" + RESET)
		self.assertEqual(rows[-1], MUTED + "\u2591" + RESET)

	def test_no_content_no_height_and_nothing_to_scroll(self):
		self.assertEqual(self.column(height=0, total=40), [])
		self.assertEqual([strip_ansi(row) for row in self.column(total=0)],
						 ["\u2591"] * 6)
		self.assertEqual([strip_ansi(row) for row in self.column(total=None)],
						 ["\u2588"] * 6)

	def test_pipe_and_ascii_capability_use_ascii_glyphs(self):
		plain = self.column(cap=PIPE, total=40)
		self.assertTrue(all(row in ("#", ".") for row in plain), plain)
		self.assertNotIn("\x1b", "".join(plain))
		ascii_rows = [strip_ansi(row) for row in self.column(cap=ASCII, total=40)]
		self.assertTrue(all(row in ("#", ".") for row in ascii_rows), ascii_rows)

	def test_sixteen_and_none_keep_the_layout(self):
		self.assertNotIn("38;2", "".join(self.column(cap=SIXTEEN, total=40)))
		self.assertEqual([strip_ansi(row) for row in self.column(cap=MONO, total=40)],
						 [strip_ansi(row) for row in self.column(total=40)])


class UnderlineAttributeTests(unittest.TestCase):
	"""`underline` is the additive attribute the button/focus seams need."""

	def test_style_is_prefix_plus_text_plus_reset(self):
		self.assertEqual(palette.style("x", fg="fg", underline=True, cap=TRUE,
									   theme="soft"),
						 FG + UNDERLINE + "x" + palette.RESET)
		self.assertEqual(palette.prefix(fg="fg", underline=True, cap=TRUE,
										theme="soft"), FG + UNDERLINE)

	def test_it_comes_after_reverse(self):
		self.assertEqual(palette.prefix(reverse=True, underline=True, cap=TRUE),
						 REVERSE + UNDERLINE)

	def test_none_level_returns_bare_text(self):
		self.assertEqual(palette.style("x", underline=True, cap=MONO), "x")
		self.assertEqual(palette.prefix(underline=True, cap=MONO), "")


class FallbackTests(PropertyCase):
	"""A bad theme still renders; a broken install surfaces, it is not masked."""

	def test_a_corrupt_selected_theme_falls_back_to_the_shipped_one(self):
		(self.themes / "mint.json").write_text("{not json", encoding="utf-8")
		theme_engine.theme_file().write_text(
			"[theme]\nname = mint\nlook = soft\n", encoding="utf-8")
		theme_engine._CACHE.clear()
		self.assertEqual(palette.properties()["border_style"], "rounded")
		self.assertIn("\u250c", self.render())

	def test_a_missing_themes_directory_raises_at_the_point_of_use(self):
		# The shipped document is the only fallback (issue #33): with no themes
		# directory at all there is nothing to render and no embedded copy to
		# hide a broken install, so the read raises instead of guessing.
		shutil.rmtree(self.themes)
		theme_engine._CACHE.clear()
		with self.assertRaises(theme_engine.ThemeError):
			palette.properties()
