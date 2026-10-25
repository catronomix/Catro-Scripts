# Table rendering tests for tui.table
"""
		TABLE BYTES AND LAYOUT
		=======================
Pins the two output modes: the styled Unicode box at a terminal (byte-identical
dark@true escapes to what `list.py` emits) and TAB-separated plain records for
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

from tui import caps, palette, table  # noqa: E402  (import after sys.path setup)
from tui.text import display_width  # noqa: E402

LIST_SOURCE = (REPO / "list.py").read_text(encoding="utf-8")

TRUE = caps.Capabilities(level="true", unicode=True, width=None,
						 isatty=True, plain=False, reason="test")
ASCII = caps.Capabilities(level="true", unicode=False, width=None,
						  isatty=True, plain=False, reason="test")
PIPE = caps.Capabilities(level="none", unicode=False, width=None,
						 isatty=False, plain=True, reason="pipe")


def list_code(name):
	"""The escape sequence `Colors.<name>` holds in list.py today."""
	match = re.search(name + r"\s*=\s*'([^']+)'", LIST_SOURCE)
	return match.group(1).encode("latin-1").decode("unicode_escape")


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


class GoldenBytesTests(unittest.TestCase):
	"""Rebuild list.py's exact row strings from the tui primitives."""

	purple = list_code("PURPLE")
	light_blue = list_code("LIGHT_BLUE")
	bold = list_code("BOLD")
	reset = list_code("END")
	bg_black = list_code("BG_BLACK")
	bg_grey = list_code("BG_GREY")

	def test_border_row_is_one_purple_run(self):
		out = table.render_table(["A"], [["b"]], cap=TRUE, theme="dark")
		border = out.split("\n")[0]
		self.assertEqual(border, self.purple + "\u250c" + "\u2500" * 6 + "\u2510" + self.reset)

	def test_header_row_matches_list_py(self):
		out = table.render_table(["A"], [["b"]], cap=TRUE, theme="dark")
		header = out.split("\n")[1]
		expected = "".join([
			self.purple, "\u2502", self.reset,
			self.purple, self.bold, " A    ", self.reset,
			self.purple, "\u2502", self.reset,
		])
		self.assertEqual(header, expected)

	def test_zebra_rows_match_list_py(self):
		out = table.render_table(["A"], [["x"], ["y"]], cap=TRUE, theme="dark")

		def expected(cell, background):
			return "".join([
				self.purple, "\u2502", self.reset,
				self.light_blue, background, cell, self.reset,
				self.purple, "\u2502", self.reset,
			])

		self.assertEqual(out.split("\n")[3], expected(" x    ", self.bg_black))
		self.assertEqual(out.split("\n")[4], expected(" y    ", self.bg_grey))

	def test_divider_and_bottom_use_the_border_colour(self):
		lines = table.render_table(["A", "B"], [["x", "y"]], cap=TRUE).split("\n")
		self.assertTrue(lines[2].startswith(self.purple + "\u251c"))
		self.assertTrue(lines[-1].startswith(self.purple + "\u2514"))
		self.assertIn("\u253c", lines[2])
		self.assertIn("\u2534", lines[-1])


class LayoutTests(unittest.TestCase):
	def test_ascii_variant_uses_plus_and_dash(self):
		out = table.render_table(["A"], [["b"]], cap=ASCII)
		self.assertIn("+", out)
		self.assertIn("-", out)
		for glyph in ("\u2500", "\u2502", "\u250c", "\u2510", "\u2514", "\u2518"):
			self.assertNotIn(glyph, out)

	def test_wide_characters_get_two_cells(self):
		out = table.render_table(["名前"], [["日本"]], cap=TRUE, theme="dark")
		lines = out.split("\n")
		widths = {display_width(re.sub(r"\x1b\[[0-9;]*m", "", line)) for line in lines}
		self.assertEqual(len(widths), 1)
		self.assertIn(" 日本 ", out)

	def test_truncation_fits_the_terminal_width(self):
		cap = caps.Capabilities(level="true", unicode=True, width=30,
								isatty=True, plain=False, reason="test")
		rows = [("short", "d" * 200)]
		out = table.render_table(["a", "b"], rows, cap=cap, theme="dark")
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
		out = table.render_table(["A", "BB"], [["x", "y"]], box=False, cap=TRUE, theme="dark")
		self.assertNotIn("\u2502", out)
		self.assertIn("x", out)

	def test_style_config_can_force_ascii(self):
		from tui import config
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			try:
				config.set("table", "style", "ascii")
				out = table.render_table(["A"], [["b"]], cap=TRUE)
				self.assertNotIn("\u2500", out)
			finally:
				config.CONFIG_FILE = None


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
		out = table.key_values("T", [("a", 1), ("bbb", 2)], cap=TRUE, theme="dark")
		lines = out.split("\n")
		self.assertEqual(len(lines), 3)
		plain = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in lines]
		self.assertEqual(plain[1].index("1"), plain[2].index("2"))

	def test_banner_is_a_box_when_styled(self):
		out = table.banner("TITLE", cap=TRUE, theme="dark")
		self.assertEqual(len(out.split("\n")), 3)
		self.assertIn("TITLE", out)
		self.assertIn("\u250c", out)
		self.assertIn(list_code("PURPLE"), out)

	def test_banner_plain_is_the_title(self):
		self.assertEqual(table.banner("TITLE", cap=PIPE), "TITLE")

	def test_section_plain_and_styled(self):
		self.assertEqual(table.section("Part", cap=PIPE), "Part")
		self.assertIn(palette.style("Part", fg="header", bold=True, cap=TRUE, theme="dark"),
					  table.section("Part", cap=TRUE, theme="dark"))


if __name__ == "__main__":
	unittest.main()
