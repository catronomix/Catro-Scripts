# Palette and styling tests for tui.palette
"""
		PALETTE AND BYTE IDENTITY
		==========================
The dark palette has to reproduce the bytes the old per-script `Colors` class in
`list.py` emitted, so this module reads those escape codes straight out of
`list.py` instead of trusting a copy. It also pins the fixed emission order
(foreground, background, attributes, text, reset), the 256/16 downgrade
determinism, custom colours and the level-"none" bare-text path.
"""

import io
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

from tui import caps, config, palette  # noqa: E402  (import after sys.path setup)

LIST_SOURCE = (REPO / "list.py").read_text(encoding="utf-8")

TRUE = caps.Capabilities(level="true", unicode=True, width=None,
						 isatty=True, plain=False, reason="test")
LEVEL256 = caps.Capabilities(level="256", unicode=True, width=None,
							 isatty=True, plain=False, reason="test")
LEVEL16 = caps.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")
NONE = caps.Capabilities(level="none", unicode=False, width=None,
						 isatty=False, plain=True, reason="test")


def list_code(name):
	"""(actual escape sequence) for `Colors.<name>` in list.py."""
	match = re.search(name + r"\s*=\s*'([^']+)'", LIST_SOURCE)
	if match is None:
		raise AssertionError("list.py no longer defines Colors.{}".format(name))
	return match.group(1).encode("latin-1").decode("unicode_escape")


def rgb_of(escape):
	match = re.search(r"[34]8;2;(\d+);(\d+);(\d+)", escape)
	if match is None:
		raise AssertionError("not a truecolor escape: {!r}".format(escape))
	return tuple(int(part) for part in match.groups())


class DarkByteIdentityTests(unittest.TestCase):
	"""style() at level true must spell list.py's escape codes, in order."""

	def style(self, text="x", **kw):
		kw.setdefault("cap", TRUE)
		kw.setdefault("theme", "dark")
		return palette.style(text, **kw)

	def test_border_and_header_codes_match_list_py(self):
		purple, sgr_reset = list_code("PURPLE"), list_code("END")
		self.assertEqual(self.style(fg="border"), purple + "x" + sgr_reset)
		self.assertEqual(self.style(fg="header"), purple + "x" + sgr_reset)
		self.assertEqual(self.style(fg="accent"), purple + "x" + sgr_reset)
		self.assertEqual(self.style(fg="header", bold=True),
						 purple + list_code("BOLD") + "x" + sgr_reset)

	def test_zebra_row_codes_match_list_py(self):
		fg, reset = list_code("LIGHT_BLUE"), list_code("END")
		odd = fg + list_code("BG_BLACK") + "x" + reset
		even = fg + list_code("BG_GREY") + "x" + reset
		self.assertEqual(self.style(fg="fg", bg="bg"), odd)
		self.assertEqual(self.style(fg="fg", bg="surface"), even)

	def test_emission_order_is_fg_bg_attrs_text_reset(self):
		expected = (list_code("LIGHT_BLUE") + list_code("BG_GREY")
					+ list_code("BOLD") + "x" + list_code("END"))
		self.assertEqual(self.style(fg="fg", bg="surface", bold=True), expected)

	def test_dark_palette_values_match_list_py_bytes(self):
		self.assertEqual(rgb_of(list_code("PURPLE")), (170, 0, 255))
		self.assertEqual(palette.DARK["border"], "#AA00FF")
		self.assertEqual(palette.DARK["header"], "#AA00FF")
		self.assertEqual(palette.DARK["accent"], "#AA00FF")
		self.assertEqual(rgb_of(list_code("LIGHT_BLUE")), (173, 216, 230))
		self.assertEqual(palette.DARK["fg"], "#ADD8E6")
		self.assertEqual(rgb_of(list_code("BG_BLACK")), (0, 0, 0))
		self.assertEqual(palette.DARK["bg"], "#000000")
		self.assertEqual(rgb_of(list_code("BG_GREY")), (45, 45, 45))
		self.assertEqual(palette.DARK["surface"], "#2D2D2D")
		self.assertEqual(palette.DARK["zebra_bg"], "#2D2D2D")


class ThemeTests(unittest.TestCase):
	def tearDown(self):
		config.CONFIG_FILE = None

	def test_default_is_dark(self):
		with mock.patch.dict(os.environ, {}, clear=True):
			self.assertEqual(palette.theme(), "dark")

	def test_env_beats_config(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("theme", "mode", "dark")
			with mock.patch.dict(os.environ, {"CATRO_THEME": "light"}, clear=True):
				self.assertEqual(palette.theme(), "light")

	def test_override_beats_env(self):
		with mock.patch.dict(os.environ, {"CATRO_THEME": "light"}, clear=True):
			self.assertEqual(palette.theme("dark"), "dark")

	def test_config_supplies_the_mode(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			config.set("theme", "mode", "light")
			with mock.patch.dict(os.environ, {}, clear=True):
				self.assertEqual(palette.theme(), "light")

	def test_unknown_theme_falls_back_to_dark(self):
		with mock.patch.dict(os.environ, {"CATRO_THEME": "neon"}, clear=True):
			self.assertEqual(palette.theme(), "dark")

	def test_light_palette_is_complete_and_distinct(self):
		self.assertEqual(set(palette.LIGHT), set(palette.DARK))
		for key, value in palette.LIGHT.items():
			self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$")
			self.assertNotEqual(value, palette.DARK[key], key)

	def test_palette_returns_a_copy(self):
		first = palette.palette("dark")
		first["bg"] = "#123456"
		self.assertEqual(palette.palette("dark")["bg"], "#000000")
		self.assertEqual(palette.palette("nope")["bg"], "#000000")


class DowngradeTests(unittest.TestCase):
	def test_256_mapping_is_deterministic_and_total(self):
		samples = ("#AA00FF", "#000000", "#2D2D2D", "#ADD8E6", "#FFFFFF", "#123456")
		for value in samples:
			with self.subTest(colour=value):
				first = palette.style("x", fg=value, cap=LEVEL256)
				second = palette.style("x", fg=value, cap=LEVEL256)
				self.assertEqual(first, second)
				match = re.match(r"^\x1b\[38;5;(\d+)mx\x1b\[0m$", first)
				self.assertIsNotNone(match, repr(first))
				self.assertTrue(0 <= int(match.group(1)) <= 255)

	def test_16_mapping_stays_in_the_basic_range(self):
		for value in ("#AA00FF", "#000000", "#ADD8E6", "#FFFFFF"):
			with self.subTest(colour=value):
				fore = palette.style("x", fg=value, cap=LEVEL16)
				back = palette.style("x", bg=value, cap=LEVEL16)
				self.assertRegex(fore, r"^\x1b\[(3[0-7]|9[0-7])mx\x1b\[0m$")
				self.assertRegex(back, r"^\x1b\[(4[0-7]|10[0-7])mx\x1b\[0m$")

	def test_16_keeps_attributes(self):
		self.assertEqual(palette.style("x", fg="fg", bold=True, dim=True,
									   reverse=True, cap=LEVEL16),
						 "\x1b[37m\x1b[1m\x1b[2m\x1b[7mx\x1b[0m")

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


if __name__ == "__main__":
	unittest.main()
