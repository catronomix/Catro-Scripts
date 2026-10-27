# Page-chrome tests for tui.chrome
"""
		PAGE CHROME
		============
`tui.chrome` turns the page building blocks into strings: masthead, framed panel,
rule, field, status line, filled band and menu. Nothing prints, so every helper
is checked here as text.

The matrix is the point: the same helper at `true`, `16`, `none`, `plain` and
`unicode=False` (ASCII), plus a CJK run per helper, so the degradation rules
from the contract are pinned rather than assumed:

	- true  -> soft's exact `38;2`/`48;2` bytes
	- 16    -> no `38;2`/`48;2` anywhere, colour still present
	- none  -> layout and glyphs kept, no escapes at all
	- plain -> plain lines, no frame, no escapes, no background fill
	- ASCII -> `+`/`-`/`|` frames instead of box drawing
	- CJK   -> every framed/menu/band line is exactly `width` cells
"""

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import (caps, chrome, chrome_controls, chrome_panels,  # noqa: E402
				 palette, table)  # (import after sys.path setup)
from tui.text import display_width, strip_ansi  # noqa: E402
from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# soft's truecolor codes, pinned literally (same values as the table tests).
BORDER = "\033[38;2;163;146;192m"
HEADER = "\033[38;2;245;205;104m"
FG = "\033[38;2;212;200;235m"
BG = "\033[48;2;27;23;38m"
SURFACE = "\033[48;2;41;34;56m"
# bg-inside-active derives from zebra_bg in the shipped look.
SURFACE_ACTIVE = "\033[48;2;53;43;73m"
SUCCESS = "\033[38;2;127;209;160m"
WARN = "\033[38;2;224;159;103m"
ERROR = "\033[38;2;255;107;107m"
BOLD = "\033[1m"
RESET = "\033[0m"

CJK = "\u65e5\u672c"

# A schema-2 look whose every token is a unique, recognisable hex, so a test can
# prove which token reached the rendered bytes.
V2_LOOK = {
	"bg": "#000001", "bg-inside": "#000002", "bg-inside-active": "#0000aa",
	"bg-stripe": "#0000bb", "fg": "#000003", "fg-muted": "#000004",
	"fg-accent": "#000005", "fg-success": "#000006", "fg-warn": "#000007",
	"fg-error": "#000008", "border-bg": "#0000cc", "border-fg": "#000009",
	"border-bg-active": "#0000dd", "border-fg-active": "#00000a",
	"header-fg": "#00000b", "header-bg": "#0000ee",
}
BG_ACTIVE = "\033[48;2;0;0;170m"
BORDER_BG = "\033[48;2;0;0;204m"
BORDER_FG_ACTIVE = "\033[38;2;0;0;10m"
BORDER_BG_ACTIVE = "\033[48;2;0;0;221m"
HEADER_BG = "\033[48;2;0;0;238m"


def capabilities(level="true", unicode=True, plain=False, isatty=True, width=None):
	return caps.Capabilities(level=level, unicode=unicode, width=width,
							 isatty=isatty, plain=plain, reason="test")


TRUE = capabilities()
SIXTEEN = capabilities(level="16")
MONO = capabilities(level="none")
ASCII = capabilities(unicode=False)
PIPE = capabilities(level="none", unicode=False, plain=True, isatty=False)


class HeaderTests(unittest.TestCase):
	def test_true_paints_title_and_subtitle_on_surface_then_a_border_rule(self):
		lines = chrome.header("TITLE", "subtitle", width=24, cap=TRUE,
							theme="soft").split("\n")
		self.assertEqual(len(lines), 3)
		self.assertEqual(lines[0],
						 HEADER + SURFACE + BOLD + " TITLE" + " " * 18 + RESET)
		self.assertEqual(lines[1], BORDER + SURFACE + " subtitle" + " " * 15 + RESET)
		self.assertEqual(lines[2], BORDER + "\u2500" * 24 + RESET)

	def test_without_a_subtitle_there_are_two_lines(self):
		lines = chrome.header("T", width=10, cap=TRUE).split("\n")
		self.assertEqual(len(lines), 2)
		self.assertEqual(lines[1], BORDER + "\u2500" * 10 + RESET)

	def test_ascii_degrades_the_rule_and_keeps_the_surface_bands(self):
		out = chrome.header("T", width=6, cap=ASCII)
		self.assertIn("-" * 6, out)
		self.assertNotIn("\u2500", out)
		self.assertIn(SURFACE, out)

	def test_level_none_keeps_the_layout_and_drops_the_escapes(self):
		out = chrome.header("TITLE", "subtitle", width=12, cap=MONO)
		self.assertEqual(out.split("\n"), [
			" TITLE      ",
			" subtitle   ",
			"\u2500" * 12,
		])
		self.assertNotIn("\x1b", out)

	def test_plain_is_the_lines_only(self):
		self.assertEqual(chrome.header("TITLE", "sub", width=40, cap=PIPE),
						 "TITLE\nsub")
		self.assertEqual(chrome.header("TITLE", width=40, cap=PIPE), "TITLE")

	def test_cap_width_is_the_default_and_cjk_stays_square(self):
		cap = caps.Capabilities(level="true", unicode=True, width=18, isatty=True,
								plain=False, reason="test")
		lines = chrome.header(CJK, CJK, cap=cap).split("\n")
		for line in lines:
			self.assertEqual(display_width(line), 18, repr(strip_ansi(line)))


class RuleTests(unittest.TestCase):
	def test_true_is_a_border_run(self):
		self.assertEqual(chrome.rule(7, cap=TRUE), BORDER + "\u2500" * 7 + RESET)

	def test_default_width_and_custom_char(self):
		out = chrome.rule(cap=TRUE)
		self.assertEqual(display_width(strip_ansi(out)), chrome.DEFAULT_RULE_WIDTH)
		self.assertEqual(chrome.rule(4, char="=", cap=TRUE),
						 BORDER + "====" + RESET)

	def test_ascii_none_and_plain(self):
		self.assertEqual(chrome.rule(5, cap=ASCII), BORDER + "-----" + RESET)
		self.assertEqual(chrome.rule(5, cap=MONO), "\u2500" * 5)
		self.assertEqual(chrome.rule(5, cap=PIPE), "")

	def test_sixteen_has_no_truecolor_codes(self):
		out = chrome.rule(5, cap=SIXTEEN)
		self.assertIn("\x1b[", out)
		self.assertNotIn("38;2", out)


class PanelTests(unittest.TestCase):
	def test_true_draws_a_square_frame_with_the_title_in_the_top_rule(self):
		lines = chrome.panel("Info", ["first", "second"], width=20, cap=TRUE,
						   theme="soft").split("\n")
		self.assertEqual(len(lines), 4)
		self.assertTrue(lines[0].startswith(BORDER + SURFACE + "\u250c\u2500"))
		self.assertIn(HEADER + SURFACE + BOLD + " Info ", lines[0])
		self.assertTrue(lines[0].endswith("\u2510" + RESET))
		self.assertIn(SURFACE, lines[1])
		self.assertIn(" first", strip_ansi(lines[1]))
		self.assertTrue(lines[-1].startswith(BORDER + SURFACE + "\u2514"))
		for line in lines:
			self.assertEqual(display_width(line), 20, repr(strip_ansi(line)))

	def test_a_string_body_splits_on_newlines(self):
		lines = chrome.panel("T", "a\nb", width=10, cap=MONO).split("\n")
		self.assertEqual(len(lines), 4)
		self.assertEqual(strip_ansi(lines[1]), "\u2502 a      \u2502")

	def test_ascii_frame(self):
		out = chrome.panel("T", "body", width=10, cap=ASCII)
		self.assertIn("+", out)
		self.assertIn("|", out)
		for glyph in ("\u2500", "\u2502", "\u250c", "\u2510", "\u2514", "\u2518"):
			self.assertNotIn(glyph, out)

	def test_level_none_keeps_the_frame_without_escapes(self):
		out = chrome.panel("T", "body", width=10, cap=MONO)
		self.assertNotIn("\x1b", out)
		self.assertEqual(out.split("\n")[0], "\u250c\u2500 T \u2500\u2500\u2500\u2500\u2510")
		self.assertEqual(out.split("\n")[1], "\u2502 body   \u2502")

	def test_plain_drops_the_frame_and_keeps_title_and_body(self):
		self.assertEqual(chrome.panel("T", ["a", "b"], cap=PIPE), "T\na\nb")
		self.assertEqual(chrome.panel(None, "a\nb", cap=PIPE), "a\nb")

	def test_width_wins_and_long_lines_are_truncated_not_wrapped(self):
		out = chrome.panel("T", "x" * 100, width=12, cap=MONO)
		for line in out.split("\n"):
			self.assertEqual(display_width(line), 12)
		self.assertIn("..", out)
		self.assertEqual(len(out.split("\n")), 3)

	def test_a_long_title_is_truncated_to_fit(self):
		out = chrome.panel("a very long panel title", "x", width=12, cap=MONO)
		self.assertEqual(display_width(out.split("\n")[0]), 12)
		self.assertIn("..", out.split("\n")[0])

	def test_padding_widens_the_gutter(self):
		out = chrome.panel("T", "x", width=10, padding=2, cap=MONO)
		self.assertEqual(out.split("\n")[1], "\u2502  x     \u2502")

	def test_cjk_body_keeps_every_line_square(self):
		out = chrome.panel("T", CJK, width=16, cap=TRUE)
		for line in out.split("\n"):
			self.assertEqual(display_width(line), 16, repr(strip_ansi(line)))

	def test_sixteen_has_no_truecolor_codes(self):
		out = chrome.panel("T", "x", width=10, cap=SIXTEEN)
		self.assertNotIn("38;2", out)
		self.assertNotIn("48;2", out)
		self.assertIn("\x1b[", out)


class FieldTests(unittest.TestCase):
	def test_muted_key_and_fg_value(self):
		self.assertEqual(chrome.field("key", "value", width=6, cap=TRUE),
						 BORDER + "key   " + RESET + "  " + FG + "value" + RESET)

	def test_key_column_defaults_to_the_key_width(self):
		self.assertEqual(strip_ansi(chrome.field("key", "v", cap=TRUE)), "key  v")

	def test_a_narrow_column_truncates_the_key(self):
		self.assertEqual(strip_ansi(chrome.field("key", "v", width=2, cap=TRUE)),
						 "..  v")

	def test_plain_is_tab_separated(self):
		self.assertEqual(chrome.field("key", "v", cap=PIPE), "key\tv")

	def test_none_keeps_the_layout_and_ascii_only_changes_the_glyphs(self):
		out = chrome.field("key", CJK, width=6, cap=MONO)
		self.assertNotIn("\x1b", out)
		self.assertEqual(display_width(out), 6 + 2 + 4)
		# The ASCII cap is still a colour cap: same layout, same escapes.
		self.assertEqual(strip_ansi(chrome.field("key", "v", cap=ASCII)),
						 strip_ansi(chrome.field("key", "v", cap=TRUE)))


class StatusTests(unittest.TestCase):
	def test_each_kind_uses_its_palette_colour(self):
		cases = (("ok", SUCCESS), ("warn", WARN), ("error", ERROR), ("info", HEADER))
		for kind, colour in cases:
			out = chrome.status(kind, "text", cap=TRUE)
			self.assertTrue(out.startswith(colour + BOLD
										   + chrome.STATUS_MARKERS[kind] + RESET),
							kind)
			self.assertIn(FG + "text" + RESET, out)

	def test_unknown_kind_degrades_to_info_and_never_raises(self):
		out = chrome.status("exploded", "text", cap=TRUE)
		self.assertIn("[info]", out)
		self.assertIn(HEADER, out)

	def test_plain_keeps_the_ascii_marker(self):
		self.assertEqual(chrome.status("ok", "fine", cap=PIPE), "[ok] fine")
		self.assertEqual(chrome.status("warn", "hmm", cap=PIPE), "[warn] hmm")

	def test_none_keeps_the_marker_and_drops_the_escapes(self):
		self.assertEqual(chrome.status("error", "boom", cap=MONO), "[error] boom")

	def test_width_truncates_the_text_not_the_marker(self):
		out = chrome.status("ok", "x" * 40, width=10, cap=MONO)
		self.assertTrue(out.startswith("[ok] "))
		self.assertEqual(display_width(out), 10)

	def test_cjk_text_is_truncated_in_cells(self):
		out = chrome.status("info", CJK * 4, width=12, cap=MONO)
		self.assertLessEqual(display_width(out), 12)
		self.assertTrue(out.endswith(".."))


class FillTests(unittest.TestCase):
	def test_pads_with_the_background_role(self):
		self.assertEqual(chrome.fill("hi", width=6, cap=TRUE),
						 FG + BG + "hi    " + RESET)

	def test_custom_roles(self):
		self.assertEqual(chrome.fill("hi", width=4, bg="bg-inside", fg="fg-muted", cap=TRUE),
						 BORDER + SURFACE + "hi  " + RESET)

	def test_truncates_rather_than_overflowing(self):
		out = chrome.fill("x" * 30, width=8, cap=MONO)
		self.assertEqual(display_width(out), 8)
		self.assertIn("..", out)

	def test_plain_returns_the_text_unchanged(self):
		self.assertEqual(chrome.fill("band", width=20, cap=PIPE), "band")

	def test_none_pads_without_escapes(self):
		self.assertEqual(chrome.fill("hi", width=5, cap=MONO), "hi   ")

	def test_no_width_anywhere_does_not_pad(self):
		self.assertEqual(chrome.fill("hi", cap=MONO), "hi")

	def test_cjk_band_is_exactly_the_width(self):
		out = chrome.fill(CJK, width=8, cap=TRUE)
		self.assertEqual(display_width(out), 8)


class MenuTests(unittest.TestCase):
	def test_rows_are_numbered_and_the_selected_row_has_the_bar(self):
		lines = chrome.menu(["one", "two"], selected=1, width=12, cap=TRUE,
						  theme="soft").split("\n")
		self.assertEqual(lines[0], FG + "  1. one    " + RESET)
		self.assertEqual(lines[1],
						 HEADER + SURFACE_ACTIVE + BOLD + "> 2. two    " + RESET)
		for line in lines:
			self.assertEqual(display_width(line), 12)

	def test_selected_none_means_no_bar(self):
		out = chrome.menu(["one", "two"], selected=None, width=12, cap=TRUE)
		self.assertNotIn(">", out)
		self.assertNotIn(SURFACE, out)

	def test_title_is_a_header_band(self):
		lines = chrome.menu(["a"], title="Pick", width=10, cap=TRUE).split("\n")
		self.assertTrue(lines[0].startswith(HEADER + SURFACE + BOLD + " Pick"))

	def test_ascii_pointer_and_frame_independence(self):
		out = chrome.menu(["a", "b"], selected=0, cap=ASCII)
		self.assertIn("> 1. a", out)
		self.assertNotIn("\u2500", out)

	def test_level_none_keeps_the_pointer_and_numbers(self):
		lines = chrome.menu(["a", "b"], selected=0, width=8, cap=MONO).split("\n")
		self.assertEqual(lines, ["> 1. a  ", "  2. b  "])
		self.assertNotIn("\x1b", "\n".join(lines))

	def test_plain_keeps_numbers_and_marks_the_selection(self):
		self.assertEqual(chrome.menu(["a", "b"], selected=1, title="Pick", cap=PIPE),
						 "Pick\n1. a\n> 2. b")
		self.assertEqual(chrome.menu(["a"], selected=None, cap=PIPE), "1. a")

	def test_width_defaults_to_the_widest_row_and_cjk_is_square(self):
		out = chrome.menu([CJK, "two"], selected=0, cap=TRUE)
		widths = {display_width(line) for line in out.split("\n")}
		self.assertEqual(len(widths), 1)

	def test_empty_menu_is_empty_not_an_error(self):
		self.assertEqual(chrome.menu([], cap=TRUE), "")
		self.assertEqual(chrome.menu([], cap=PIPE), "")
		self.assertEqual(chrome.menu([], title="T", cap=PIPE), "T")

	def test_long_items_are_truncated_to_the_width(self):
		out = chrome.menu(["x" * 50], selected=0, width=10, cap=MONO)
		self.assertEqual(display_width(out), 10)
		self.assertIn("..", out)


class GlyphSourceTests(unittest.TestCase):
	def test_the_frame_follows_table_glyphs_for(self):
		cap = capabilities(unicode=False)
		self.assertIs(table.glyphs_for(cap), table.ASCII_GLYPHS)
		self.assertIn("+", chrome.panel("T", "x", cap=cap))


class ControlShimTests(unittest.TestCase):
	"""The button/scrollbar seams moved to `tui.chrome_controls`; old paths win."""

	def test_the_moved_names_still_resolve_through_the_chrome_module(self):
		for name in ("button", "scrollbar", "BUTTON_DECORATIONS",
					 "ASCII_DECORATIONS", "BUTTON_STYLES", "SCROLLBAR_GLYPHS"):
			with self.subTest(name=name):
				self.assertIs(getattr(chrome, name), getattr(chrome_controls, name))

	def test_the_ascii_table_derives_from_the_unicode_one(self):
		self.assertEqual(chrome_controls.ASCII_DECORATIONS["chevron"], ("<< ", " >>"))
		self.assertEqual(chrome_controls.BUTTON_DECORATIONS["chevron"],
						 ("\u00ab ", " \u00bb"))

class PanelSplitShimTests(unittest.TestCase):
	"""The panel/masthead painters moved to `tui.chrome_panels`; old paths win."""

	def test_the_moved_names_still_resolve_through_the_chrome_module(self):
		for name in ("panel", "_band", "_flat", "_span"):
			with self.subTest(name=name):
				self.assertIs(getattr(chrome, name), getattr(chrome_panels, name))

	def test_chrome_panels_does_not_import_chrome(self):
		source = (REPO / "tui" / "chrome_panels.py").read_text(encoding="utf-8")
		imports = [line for line in source.splitlines()
				   if line.startswith("from .") or line.startswith("import ")]
		self.assertTrue(imports)
		for line in imports:
			self.assertNotIn(" chrome", line)
			self.assertNotIn("chrome_controls", line)


class NewTokenTests(unittest.TestCase):
	"""The schema-2 tokens with no v1 ancestor must reach the rendered bytes."""

	def render(self, call):
		with mock.patch.object(palette, "palette", return_value=dict(V2_LOOK)):
			return call()

	def test_the_selection_fill_uses_bg_inside_active(self):
		out = self.render(lambda: chrome.menu(["one", "two"], selected=1,
											  width=12, cap=TRUE))
		self.assertIn(BG_ACTIVE, out)

	def test_a_plain_frame_band_uses_border_bg(self):
		out = self.render(lambda: chrome.panel("Info", ["body"], width=16,
											   cap=TRUE))
		self.assertIn(BORDER_BG, out)

	def test_a_focused_frame_uses_the_active_band_roles(self):
		out = self.render(lambda: chrome.panel("Info", ["body"], width=16,
											   cap=TRUE, active=True))
		self.assertIn(BORDER_FG_ACTIVE, out)
		self.assertIn(BORDER_BG_ACTIVE, out)
		self.assertNotIn(BORDER_BG, out)

	def test_the_header_band_uses_header_bg(self):
		out = self.render(lambda: chrome.header("T", width=10, cap=TRUE))
		self.assertIn(HEADER_BG, out)

	def test_frame_roles_are_the_one_seam(self):
		self.assertEqual(chrome_panels.frame_roles(),
						 ("border-fg", "border-bg"))
		self.assertEqual(chrome_panels.frame_roles(True),
						 ("border-fg-active", "border-bg-active"))
		self.assertIs(chrome.frame_roles, chrome_panels.frame_roles)


if __name__ == "__main__":
	unittest.main()
