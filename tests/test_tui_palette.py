# Palette and styling tests for tui.palette
"""
		PALETTE TABLES AND STYLING
		==========================
Pins the final theme set: exactly soft (default), contrast-light and
contrast-dark, each with the contract's eleven semantic keys. The soft truecolor
escapes are spelled out literally so the fixed emission order (foreground,
background, attributes, text, reset) cannot drift; the table renderer and the
golden fixture both depend on it.

Also pins the alias/legacy map (old `dark` configs resolve to soft), the WCAG AA
gate recomputed from the hexes for all three themes, and the degradation paths
(16-colour, pipe, NO_COLOR on a tty).
"""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import caps, config, palette, table  # noqa: E402  (import after sys.path setup)

# soft's truecolor codes, byte for byte: border #A392C0, fg #D4C8EB,
# bg #1B1726, surface #292238.
BORDER = "\033[38;2;163;146;192m"
FG = "\033[38;2;212;200;235m"
BG = "\033[48;2;27;23;38m"
SURFACE = "\033[48;2;41;34;56m"
ACCENT = "\033[38;2;245;205;104m"
BOLD = "\033[1m"
RESET = "\033[0m"

TRUE = caps.Capabilities(level="true", unicode=True, width=None,
						 isatty=True, plain=False, reason="test")
LEVEL256 = caps.Capabilities(level="256", unicode=True, width=None,
							 isatty=True, plain=False, reason="test")
LEVEL16 = caps.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")
NONE = caps.Capabilities(level="none", unicode=False, width=None,
						 isatty=False, plain=True, reason="test")
# Colour off on a real terminal: escapes go, the box stays.
MONO_TTY = caps.Capabilities(level="none", unicode=True, width=None,
							 isatty=True, plain=False, reason="NO_COLOR")
PIPE = caps.Capabilities(level="none", unicode=False, width=None,
						 isatty=False, plain=True, reason="pipe")


def rgb_of(escape):
	match = re.search(r"[34]8;2;(\d+);(\d+);(\d+)", escape)
	if match is None:
		raise AssertionError("not a truecolor escape: {!r}".format(escape))
	return tuple(int(part) for part in match.groups())


class SoftByteTests(unittest.TestCase):
	"""style() at level true spells soft's codes, in the pinned order."""

	def style(self, text="x", **kw):
		kw.setdefault("cap", TRUE)
		kw.setdefault("theme", "soft")
		return palette.style(text, **kw)

	def test_border_header_and_accent_codes(self):
		self.assertEqual(self.style(fg="border"), BORDER + "x" + RESET)
		self.assertEqual(self.style(fg="header"), ACCENT + "x" + RESET)
		self.assertEqual(self.style(fg="accent"), ACCENT + "x" + RESET)
		self.assertEqual(self.style(fg="header", bold=True),
						 ACCENT + BOLD + "x" + RESET)

	def test_zebra_row_codes(self):
		odd = FG + BG + "x" + RESET
		even = FG + SURFACE + "x" + RESET
		self.assertEqual(self.style(fg="fg", bg="bg"), odd)
		self.assertEqual(self.style(fg="fg", bg="surface"), even)

	def test_emission_order_is_fg_bg_attrs_text_reset(self):
		expected = FG + SURFACE + BOLD + "x" + RESET
		self.assertEqual(self.style(fg="fg", bg="surface", bold=True), expected)

	def test_soft_palette_values_match_the_pinned_bytes(self):
		self.assertEqual(rgb_of(BORDER), (163, 146, 192))
		self.assertEqual(palette.SOFT["border"], "#A392C0")
		self.assertEqual(palette.SOFT["muted"], "#A392C0")
		self.assertEqual(rgb_of(ACCENT), (245, 205, 104))
		self.assertEqual(palette.SOFT["header"], "#F5CD68")
		self.assertEqual(palette.SOFT["accent"], "#F5CD68")
		self.assertEqual(rgb_of(FG), (212, 200, 235))
		self.assertEqual(palette.SOFT["fg"], "#D4C8EB")
		self.assertEqual(rgb_of(BG), (27, 23, 38))
		self.assertEqual(palette.SOFT["bg"], "#1B1726")
		self.assertEqual(rgb_of(SURFACE), (41, 34, 56))
		self.assertEqual(palette.SOFT["surface"], "#292238")
		self.assertEqual(palette.SOFT["zebra_bg"], "#352B49")


class PrefixSeamTests(unittest.TestCase):
	"""`prefix()` is the SGR-only half of `style()`; the two cannot drift."""

	def test_style_is_prefix_plus_text_plus_reset(self):
		for kw in ({"fg": "fg", "bg": "surface"}, {"fg": "border", "bold": True},
				   {"fg": "error", "reverse": True, "dim": True}):
			with self.subTest(kw=kw):
				self.assertEqual(palette.style("abc", cap=TRUE, theme="soft", **kw),
								 palette.prefix(cap=TRUE, theme="soft", **kw)
								 + "abc" + palette.RESET)

	def test_prefix_emits_no_text_and_no_reset(self):
		lead = palette.prefix(fg="fg", bg="bg", cap=TRUE, theme="soft")
		self.assertEqual(lead, FG + BG)
		self.assertNotIn(RESET, lead)

	def test_prefix_is_empty_without_a_colour_or_attribute(self):
		self.assertEqual(palette.prefix(cap=TRUE, theme="soft"), "")

	def test_prefix_is_empty_at_level_none(self):
		self.assertEqual(palette.prefix(fg="fg", bg="bg", bold=True, cap=NONE), "")


class ThemeTests(unittest.TestCase):
	def tearDown(self):
		config.CONFIG_FILE = None

	def test_default_is_soft(self):
		with mock.patch.dict(os.environ, {}, clear=True):
			self.assertEqual(palette.theme(), "soft")

	def test_env_beats_config(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("theme", "mode", "contrast-dark")
			with mock.patch.dict(os.environ, {"CATRO_THEME": "light"}, clear=True):
				self.assertEqual(palette.theme(), "contrast-light")

	def test_override_beats_env(self):
		with mock.patch.dict(os.environ, {"CATRO_THEME": "light"}, clear=True):
			self.assertEqual(palette.theme("dark"), "soft")

	def test_config_supplies_the_mode(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("theme", "mode", "contrast-light")
			with mock.patch.dict(os.environ, {}, clear=True):
				self.assertEqual(palette.theme(), "contrast-light")

	def test_unknown_theme_falls_back_to_soft(self):
		with mock.patch.dict(os.environ, {"CATRO_THEME": "neon"}, clear=True):
			self.assertEqual(palette.theme(), "soft")

	def test_palette_returns_a_copy(self):
		first = palette.palette("soft")
		first["bg"] = "#123456"
		self.assertEqual(palette.palette("soft")["bg"], "#1B1726")
		self.assertEqual(palette.palette("nope")["bg"], "#1B1726")


class ThreeThemeTests(unittest.TestCase):
	"""The three contract tables, verbatim."""

	EXPECTED = {
		"soft": {
			"bg": "#1B1726", "surface": "#292238", "fg": "#D4C8EB",
			"muted": "#A392C0", "accent": "#F5CD68", "success": "#7FD1A0",
			"warn": "#E09F67", "error": "#FF6B6B", "border": "#A392C0",
			"header": "#F5CD68", "zebra_bg": "#352B49",
		},
		"contrast-light": {
			"bg": "#FFFFFF", "surface": "#E8F4F8", "fg": "#000000",
			"muted": "#4A4A4A", "accent": "#0000B3", "success": "#0A7A2F",
			"warn": "#8A5A00", "error": "#B3261E", "border": "#000000",
			"header": "#A0007A", "zebra_bg": "#E8F4F8",
		},
		"contrast-dark": {
			"bg": "#000000", "surface": "#0A0A0A", "fg": "#FFFFFF",
			"muted": "#D0D0D0", "accent": "#00FFFF", "success": "#00FF66",
			"warn": "#FFFF00", "error": "#FF4040", "border": "#00FFFF",
			"header": "#FFFF00", "zebra_bg": "#1A1A1A",
		},
	}

	def test_theme_set_is_exactly_three(self):
		self.assertEqual(set(palette.THEMES), set(self.EXPECTED))

	def test_every_theme_has_the_same_eleven_keys(self):
		keys = set(self.EXPECTED["soft"])
		self.assertEqual(len(keys), 11)
		for name, table in palette.THEMES.items():
			self.assertEqual(set(table), keys, name)

	def test_tables_are_the_contract_values(self):
		for name, expected in self.EXPECTED.items():
			with self.subTest(theme=name):
				self.assertEqual(palette.THEMES[name], expected)

	def test_contrast_dark_true_accent_is_cyan(self):
		self.assertEqual(
			palette.style("x", fg="accent", cap=TRUE, theme="contrast-dark"),
			"\x1b[38;2;0;255;255mx\x1b[0m")

	def test_every_theme_downgrades_at_16_without_raising(self):
		for name, colours in palette.THEMES.items():
			for key in colours:
				with self.subTest(theme=name, key=key):
					out = palette.style("x", fg=key, cap=LEVEL16, theme=name)
					self.assertRegex(out, r"^\x1b\[(3[0-7]|9[0-7])mx\x1b\[0m$")


def _luminance(colour):
	"""WCAG 2.x relative luminance for a #rrggbb colour."""
	def channel(value):
		value = value / 255.0
		return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
	r, g, b = (int(colour[index:index + 2], 16) for index in (1, 3, 5))
	return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(first, second):
	high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
	return (high + 0.05) / (low + 0.05)


class ContrastGateTests(unittest.TestCase):
	"""Every theme clears WCAG AA on both backgrounds, recomputed from hexes."""

	FOREGROUND = ("fg", "muted", "accent", "success", "warn", "error",
				  "border", "header")

	def test_all_three_themes_clear_wcag_aa(self):
		for name, colours in palette.THEMES.items():
			for key in self.FOREGROUND:
				for backdrop in ("bg", "zebra_bg"):
					ratio = _contrast(colours[key], colours[backdrop])
					self.assertGreaterEqual(
						ratio, 4.5, "{} {} on {} is {:.2f}:1".format(
							name, key, backdrop, ratio))


class ThemeAliasTests(unittest.TestCase):
	def tearDown(self):
		config.CONFIG_FILE = None

	MATRIX = {
		"soft": ("soft", "default", "cozy", " SOFT ", "Soft"),
		"contrast-light": ("contrast-light", "contrastlight", "contrast light",
						   "contrast_light", "Contrast Light", "light", "clight"),
		"contrast-dark": ("contrast-dark", "contrastdark", "contrast dark",
						  "contrast_dark", "high-contrast", "highcontrast",
						  "high_contrast", "hc", " HC ", "cdark"),
	}

	def test_alias_matrix(self):
		for expected, spellings in self.MATRIX.items():
			for alias in spellings:
				with self.subTest(alias=alias):
					self.assertEqual(palette.theme(alias), expected)
					self.assertEqual(palette.normalize(alias), expected)

	def test_legacy_dark_resolves_to_soft(self):
		self.assertEqual(palette.normalize("dark"), "soft")
		self.assertEqual(palette.theme("dark"), "soft")
		with mock.patch.dict(os.environ, {"CATRO_THEME": "dark"}, clear=True):
			self.assertEqual(palette.theme(), "soft")

	def test_legacy_config_value_resolves_to_soft(self):
		with tempfile.TemporaryDirectory() as td:
			target = Path(td) / "config.ini"
			target.write_text("[theme]\nmode = dark\n", encoding="utf-8")
			config.CONFIG_FILE = target
			with mock.patch.dict(os.environ, {}, clear=True):
				self.assertEqual(palette.theme(), "soft")

	def test_unknown_theme_falls_back_to_soft(self):
		self.assertEqual(palette.theme("neon"), "soft")
		self.assertEqual(palette.normalize(""), "soft")
		self.assertEqual(palette.normalize("   "), "soft")
		self.assertEqual(palette.normalize(None), "soft")

	def test_env_and_config_use_the_same_normalizer(self):
		with mock.patch.dict(os.environ, {"CATRO_THEME": "HC"}, clear=True):
			self.assertEqual(palette.theme(), "contrast-dark")
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("theme", "mode", "Contrast_Light")
			with mock.patch.dict(os.environ, {}, clear=True):
				self.assertEqual(palette.theme(), "contrast-light")


class DowngradeTests(unittest.TestCase):
	def test_256_mapping_is_deterministic_and_total(self):
		samples = ("#F5CD68", "#1B1726", "#292238", "#D4C8EB", "#FFFFFF", "#123456")
		for value in samples:
			with self.subTest(colour=value):
				first = palette.style("x", fg=value, cap=LEVEL256)
				second = palette.style("x", fg=value, cap=LEVEL256)
				self.assertEqual(first, second)
				match = re.match(r"^\x1b\[38;5;(\d+)mx\x1b\[0m$", first)
				self.assertIsNotNone(match, repr(first))
				self.assertTrue(0 <= int(match.group(1)) <= 255)

	def test_16_mapping_stays_in_the_basic_range(self):
		for value in ("#F5CD68", "#1B1726", "#D4C8EB", "#FFFFFF"):
			with self.subTest(colour=value):
				fore = palette.style("x", fg=value, cap=LEVEL16)
				back = palette.style("x", bg=value, cap=LEVEL16)
				self.assertRegex(fore, r"^\x1b\[(3[0-7]|9[0-7])mx\x1b\[0m$")
				self.assertRegex(back, r"^\x1b\[(4[0-7]|10[0-7])mx\x1b\[0m$")

	def test_16_keeps_attributes(self):
		out = palette.style("x", fg="fg", bold=True, dim=True,
							reverse=True, cap=LEVEL16)
		self.assertRegex(
			out, r"^\x1b\[(3[0-7]|9[0-7])m\x1b\[1m\x1b\[2m\x1b\[7mx\x1b\[0m$")

	def test_custom_hex_and_rgb(self):
		self.assertEqual(palette.style("x", fg="#0A0B0C", cap=TRUE),
						 "\x1b[38;2;10;11;12mx\x1b[0m")
		self.assertEqual(palette.style("x", bg=(1, 2, 3), cap=TRUE),
						 "\x1b[48;2;1;2;3mx\x1b[0m")

	def test_invalid_colour_falls_back_to_semantic_default(self):
		self.assertEqual(palette.style("x", fg="#zzzzzz", cap=TRUE),
						 palette.style("x", fg="fg", cap=TRUE))
		self.assertEqual(palette.style("x", bg="not-a-colour", cap=TRUE),
						 palette.style("x", bg="bg", cap=TRUE))

	def test_none_returns_bare_text(self):
		self.assertEqual(palette.style("x", fg="error", bg="bg", bold=True, cap=NONE), "x")

	def test_no_colour_requested_returns_bare_text(self):
		self.assertEqual(palette.style("x", cap=TRUE), "x")


class DegradationTests(unittest.TestCase):
	"""Every theme keeps working when colour, glyphs or the tty go away."""

	HEADERS = ["ID", "Name"]
	ROWS = [["1", "list"], ["2", "theme"]]

	def test_every_theme_degrades_to_tab_records_on_a_pipe(self):
		for name in palette.THEMES:
			with self.subTest(theme=name):
				out = table.render_table(self.HEADERS, self.ROWS,
										 cap=PIPE, theme=name)
				self.assertNotIn("\x1b", out)
				self.assertEqual(out.split("\n")[0], "ID\tName")
				self.assertEqual(out.split("\n")[1], "1\tlist")

	def test_every_theme_keeps_the_box_but_drops_escapes_at_no_color(self):
		for name in palette.THEMES:
			with self.subTest(theme=name):
				out = table.render_table(self.HEADERS, self.ROWS,
										 cap=MONO_TTY, theme=name)
				self.assertNotIn("\x1b", out)
				for glyph in ("\u250c", "\u2500", "\u2502", "\u2514"):
					self.assertIn(glyph, out)
				self.assertNotIn("\t", out)


if __name__ == "__main__":
	unittest.main()
