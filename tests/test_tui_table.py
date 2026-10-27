# Table rendering tests for tui.table
"""
		TABLE BYTES AND LAYOUT
		=======================
Pins the two output modes: the styled Unicode box at a terminal (byte-identical
soft@true escapes to what `list.py` emits) and TAB-separated plain records for
pipes. Also covers the ASCII fallback, wide characters, truncation, ragged rows
and the smaller block helpers.
"""

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, palette, table, table_glyphs  # noqa: E402  (import after sys.path setup)
from tui.text import display_width  # noqa: E402

# soft's truecolor codes, pinned literally: `list.py` itself renders through
# `tui` now, so scraping its source would only ever prove that the library
# agrees with itself.
BORDER = "\033[38;2;163;146;192m"
FG = "\033[38;2;212;200;235m"
BG = "\033[48;2;27;23;38m"
SURFACE = "\033[48;2;41;34;56m"
BOLD = "\033[1m"
RESET = "\033[0m"

TRUE = caps.Capabilities(level="true", unicode=True, width=None,
						 isatty=True, plain=False, reason="test")
ASCII = caps.Capabilities(level="true", unicode=False, width=None,
						  isatty=True, plain=False, reason="test")
PIPE = caps.Capabilities(level="none", unicode=False, width=None,
						 isatty=False, plain=True, reason="pipe")
# Colour off, but still a terminal: the layout must not degrade to a pipe.
MONO = caps.Capabilities(level="none", unicode=True, width=None,
						 isatty=True, plain=False, reason="NO_COLOR")
MONO_ASCII = caps.Capabilities(level="none", unicode=False, width=None,
							   isatty=True, plain=False, reason="NO_COLOR")


class PlainModeTests(unittest.TestCase):
	HEADERS = ["ID", "Script Name", "Size"]
	ROWS = [(1, "list", "4.2 KB"), (2, "theme", "1.0 KB")]

	def test_tab_separated_records(self):
		out = table.render_table(self.HEADERS, self.ROWS, cap=PIPE)
		self.assertEqual(out.split("\n"), [
			"ID\tScript Name\tSize",
			"1\tlist\t4.2 KB",
			"2\ttheme\t1.0 KB",
		])

	def test_plain_output_has_no_ansi_and_no_borders(self):
		out = table.render_table(self.HEADERS, self.ROWS, cap=PIPE)
		for marker in ("\x1b", "\u2500", "\u2502", "\u250c", "|"):
			self.assertNotIn(marker, out)
		self.assertNotIn("  ", out)

	def test_plain_output_never_truncates(self):
		long_text = "x" * 400
		out = table.render_table(["A"], [(long_text,)], cap=PIPE)
		self.assertIn(long_text, out)

	def test_cut_column_contract(self):
		out = table.render_table(self.HEADERS, self.ROWS, cap=PIPE)
		second = [line.split("\t")[1] for line in out.split("\n")[1:]]
		self.assertEqual(second, ["list", "theme"])


class NoColorLayoutTests(unittest.TestCase):
	"""Level "none" removes escapes, not the table: a tty keeps its decor."""

	HEADERS = ["ID", "Script Name", "Size"]
	ROWS = [(1, "list", "4.2 KB"), (2, "theme", "1.0 KB")]

	def test_monochrome_tty_keeps_the_box_and_drops_the_escapes(self):
		out = table.render_table(self.HEADERS, self.ROWS, cap=MONO)
		self.assertNotIn("\x1b", out)
		for glyph in ("\u250c", "\u2500", "\u2502", "\u2514", "\u253c"):
			self.assertIn(glyph, out, "the monochrome table lost {!r}".format(glyph))
		lines = out.split("\n")
		self.assertEqual(len(lines), 6)
		# Padded columns, not TAB-separated fields.
		self.assertEqual(lines[1], "\u2502 ID   \u2502 Script Name \u2502 Size   \u2502")
		self.assertEqual(lines[3],
						 "\u2502 1    \u2502 list        \u2502 4.2 KB \u2502")
		self.assertNotIn("\t", out)

	def test_monochrome_ascii_tty_falls_back_to_ascii_boxes(self):
		out = table.render_table(self.HEADERS, self.ROWS, cap=MONO_ASCII)
		self.assertNotIn("\x1b", out)
		self.assertIn("+", out)
		self.assertIn("|", out)
		self.assertNotIn("\u2500", out)

	def test_level_none_pipe_is_still_plain(self):
		out = table.render_table(self.HEADERS, self.ROWS, cap=PIPE)
		self.assertEqual(out.split("\n")[0], "ID\tScript Name\tSize")
		self.assertNotIn("\x1b", out)
		self.assertNotIn("\t\t", out)

	def test_monochrome_banner_and_sections_have_no_escapes(self):
		for render in (lambda: table.banner("TITLE", cap=MONO),
					   lambda: table.section("HEADING", cap=MONO),
					   lambda: table.key_values("KEYS", [("a", "b")], cap=MONO)):
			out = render()
			self.assertNotIn("\x1b", out)


class GoldenBytesTests(unittest.TestCase):
	"""Rebuild soft's list.py row bytes from the tui primitives."""

	def test_border_row_is_one_border_run(self):
		out = table.render_table(["A"], [["b"]], cap=TRUE, theme="soft")
		border = out.split("\n")[0]
		self.assertEqual(border, BORDER + "\u250c" + "\u2500" * 6 + "\u2510" + RESET)

	def test_header_row_matches_list_py(self):
		out = table.render_table(["A", "B"], [["x", "y"]], cap=TRUE, theme="soft")
		header = out.split("\n")[1]
		# Border colour, leading border, then bold: one span, one reset.
		expected = BORDER + "\u2502" + BOLD + " A    \u2502 B    \u2502" + RESET
		self.assertEqual(header, expected)

	def test_zebra_rows_match_list_py(self):
		out = table.render_table(["A", "B"], [["x", "y"], ["z", "w"]],
								 cap=TRUE, theme="soft")

		def expected(first, second, background):
			cell = FG + background
			return "".join([
				BORDER, "\u2502", cell, " " + first.ljust(4) + " ",
				BORDER, "\u2502", cell, " " + second.ljust(4) + " ",
				RESET, BORDER, "\u2502", RESET,
			])

		lines = out.split("\n")
		self.assertEqual(lines[3], expected("x", "y", BG))
		self.assertEqual(lines[4], expected("z", "w", SURFACE))

	def test_data_row_has_two_resets_only(self):
		row = table.render_table(["A", "B"], [["x", "y"]], cap=TRUE).split("\n")[3]
		self.assertEqual(row.count(RESET), 2)

	def test_divider_and_bottom_use_the_border_colour(self):
		lines = table.render_table(["A", "B"], [["x", "y"]], cap=TRUE).split("\n")
		self.assertTrue(lines[2].startswith(BORDER + "\u251c"))
		self.assertTrue(lines[-1].startswith(BORDER + "\u2514"))
		self.assertIn("\u253c", lines[2])
		self.assertIn("\u2534", lines[-1])


class ForcedWidthTests(unittest.TestCase):
	"""`widths=` pins the layout so a caller can keep exact bytes."""

	def test_widths_are_used_verbatim(self):
		out = table.render_table(["ID", "Name"], [["1", "x" * 20]],
								 widths=[4, 6], truncate=False, cap=TRUE)
		lines = out.split("\n")
		self.assertEqual(display_width(re.sub(r"\x1b\[[0-9;]*m", "", lines[0])),
						 sum([4, 6]) + 3 * 2 + 1)
		self.assertIn("x" * 20, lines[3])

	def test_widths_are_not_shrunk_to_the_terminal(self):
		cap = caps.Capabilities(level="true", unicode=True, width=20,
								isatty=True, plain=False, reason="test")
		out = table.render_table(["A", "B"], [["x", "y"]], widths=[10, 10],
								 cap=cap, theme="soft")
		self.assertEqual(len(re.sub(r"\x1b\[[0-9;]*m", "", out.split("\n")[0])),
						 10 + 10 + 3 * 2 + 1)

	def test_plain_mode_ignores_widths_and_truncation(self):
		out = table.render_table(["A"], [["x" * 90]], widths=[4], truncate=False,
								 cap=PIPE)
		self.assertEqual(out, "A\n" + "x" * 90)

	def test_missing_widths_pad_with_the_minimum_column(self):
		out = table.render_table(["A", "B"], [["x", "y"]], widths=[8], cap=TRUE)
		self.assertIn(" x       ", out.split("\n")[3])
		self.assertIn(" y    ", out.split("\n")[3])


class LayoutTests(unittest.TestCase):
	def test_ascii_variant_uses_plus_and_dash(self):
		out = table.render_table(["A"], [["b"]], cap=ASCII)
		self.assertIn("+", out)
		self.assertIn("-", out)
		for glyph in ("\u2500", "\u2502", "\u250c", "\u2510", "\u2514", "\u2518"):
			self.assertNotIn(glyph, out)

	def test_wide_characters_get_two_cells(self):
		out = table.render_table(["名前"], [["日本"]], cap=TRUE, theme="soft")
		lines = out.split("\n")
		widths = {display_width(re.sub(r"\x1b\[[0-9;]*m", "", line)) for line in lines}
		self.assertEqual(len(widths), 1)
		self.assertIn(" 日本 ", out)

	def test_truncation_fits_the_terminal_width(self):
		cap = caps.Capabilities(level="true", unicode=True, width=30,
								isatty=True, plain=False, reason="test")
		rows = [("short", "d" * 200)]
		out = table.render_table(["a", "b"], rows, cap=cap, theme="soft")
		plain_lines = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in out.split("\n")]
		for line in plain_lines:
			self.assertLessEqual(display_width(line), 30, line)
		self.assertIn("..", out)

	def test_ragged_rows_are_repaired_not_raised(self):
		out = table.render_table(["A", "B"], [("only",), ("one", "two", "extra"), ()], cap=TRUE)
		body = out.split("\n")[3:-1]
		self.assertEqual(len(body), 3)
		for line in body:
			self.assertNotIn("extra", line)

	def test_newlines_in_cells_are_flattened(self):
		out = table.render_table(["A"], [("two\nlines",)], cap=TRUE)
		self.assertEqual(len(out.split("\n")), 5)

	def test_empty_input_still_renders(self):
		self.assertEqual(table.render_table([], [], cap=TRUE), "")

	def test_borderless_variant_aligns_columns(self):
		out = table.render_table(["A", "BB"], [["x", "y"]], box=False, cap=TRUE, theme="soft")
		self.assertNotIn("\u2502", out)
		self.assertIn("x", out)

	def test_style_config_can_force_ascii(self):
		from tui import config
		previous = config.CONFIG_FILE
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			try:
				config.set("table", "style", "ascii")
				out = table.render_table(["A"], [["b"]], cap=TRUE)
				self.assertNotIn("\u2500", out)
			finally:
				config.CONFIG_FILE = previous


class BlockTests(unittest.TestCase):
	def test_print_table_writes_once(self):
		stream = io.StringIO()
		with contextlib.redirect_stdout(stream):
			table.print_table(["A"], [["b"]], cap=PIPE)
		self.assertEqual(stream.getvalue(), "A\nb\n")

	def test_key_values_plain(self):
		self.assertEqual(table.key_values("Title", [("a", 1), ("bb", 2)], cap=PIPE),
						 "Title\na\t1\nbb\t2")

	def test_key_values_aligned(self):
		out = table.key_values("T", [("a", 1), ("bbb", 2)], cap=TRUE, theme="soft")
		lines = out.split("\n")
		self.assertEqual(len(lines), 3)
		plain = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in lines]
		self.assertEqual(plain[1].index("1"), plain[2].index("2"))

	def test_banner_is_a_box_when_styled(self):
		out = table.banner("TITLE", cap=TRUE, theme="soft")
		self.assertEqual(len(out.split("\n")), 3)
		self.assertIn("TITLE", out)
		self.assertIn("\u250c", out)
		self.assertIn(BORDER, out)

	def test_banner_plain_is_the_title(self):
		self.assertEqual(table.banner("TITLE", cap=PIPE), "TITLE")

	def test_section_plain_and_styled(self):
		self.assertEqual(table.section("Part", cap=PIPE), "Part")
		self.assertIn(palette.style("Part", fg="header-fg", bold=True, cap=TRUE, theme="soft"),
					  table.section("Part", cap=TRUE, theme="soft"))

class GlyphShimTests(unittest.TestCase):
	"""The glyph tables moved to `tui.table_glyphs`; old paths must resolve."""

	def test_the_moved_names_still_resolve_through_the_table_module(self):
		for name in ("UNICODE_GLYPHS", "ASCII_GLYPHS", "HEAVY_GLYPHS",
					 "DOUBLE_GLYPHS", "SQUARE_GLYPHS", "SPACE_GLYPHS",
					 "BORDER_GLYPHS", "glyphs_for"):
			with self.subTest(name=name):
				self.assertIs(getattr(table, name), getattr(table_glyphs, name))

	def test_the_shipped_family_is_the_same_object_both_ways(self):
		self.assertIs(table.BORDER_GLYPHS["rounded"], table_glyphs.UNICODE_GLYPHS)


if __name__ == "__main__":
	unittest.main()
