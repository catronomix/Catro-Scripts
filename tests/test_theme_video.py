# Theme regression tests for the five video tools
"""
			VIDEO TOOLS FOLLOW THE THEME
			============================
The video tools render their page chrome through `tui`, so `CATRO_THEME` has to
change the bytes they emit: the masthead/menu title, the status markers and the
settings fields all resolve their colours from the active palette. These tests
call one chrome-producing function per script with a forced capability and two
themes, and pin the two axes the contract keeps apart:

	- a styled terminal gets different bytes per theme, with the same visible
	  text once the escapes are stripped;
	- a pipe stays plain: no escapes, no box glyphs, and the same bytes under
	  every theme.

No FFmpeg runs here: `videoframes` stops at its missing-input check and the
other four call their menu functions, which only read one default answer.

Run with:
	python -m unittest discover -s tests -v
"""
import contextlib
import io
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)

import videofade  # noqa: E402
import videoframes  # noqa: E402
import videojoin  # noqa: E402
import videoloop  # noqa: E402
import videotweak  # noqa: E402

VIDEO_SCRIPTS = ("videofade.py", "videoframes.py", "videojoin.py",
				 "videoloop.py", "videotweak.py")

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518"

# One chrome-producing call per script: a menu for four of them, the notice path
# for `videoframes` (it has no menu).
CHROME_CALLS = {
	"videofade.py": videofade.get_codec_choice,
	"videoframes.py": lambda cap: videoframes.extract_frames(
		str(REPO / "missing-video.mp4"), cap),
	"videojoin.py": videojoin.get_codec_choice,
	"videoloop.py": videoloop.get_codec_choice,
	"videotweak.py": videotweak.get_effect_choice,
}

# The semantic role each script's chrome must actually emit: a menu title is a
# `header` band, a notice line is a status `error` marker.
EXPECTED_ROLE = {
	"videofade.py": "header",
	"videoframes.py": "error",
	"videojoin.py": "header",
	"videoloop.py": "header",
	"videotweak.py": "header",
}

TTY = tui.Capabilities(level="true", unicode=True, width=70, isatty=True,
					   plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


def true_fg(role, theme):
	"""The `38;2` foreground code the named palette role resolves to."""
	return "\033[38;2;{};{};{}m".format(*tui.palette.rgb(role, theme))


def render(call, cap, theme):
	"""Run one chrome call under `theme`, capturing stdout as text."""
	buffer = io.StringIO()
	with mock.patch.dict(os.environ, {"CATRO_THEME": theme}), \
			mock.patch("builtins.input", return_value="1"), \
			contextlib.redirect_stdout(buffer):
		call(cap)
	return buffer.getvalue()


class ThemeSwapTest(unittest.TestCase):
	"""`CATRO_THEME` visibly changes the bytes, per script."""

	def test_each_script_follows_the_theme(self):
		for name in VIDEO_SCRIPTS:
			with self.subTest(script=name):
				call = CHROME_CALLS[name]
				soft = render(call, TTY, "soft")
				dark = render(call, TTY, "contrast-dark")
				self.assertIn("\x1b", soft,
							  "{} printed no escapes on a true-colour tty".format(name))
				self.assertIn("\x1b", dark,
							  "{} printed no escapes on a true-colour tty".format(name))
				self.assertNotEqual(soft, dark,
									"{} ignored CATRO_THEME".format(name))
				self.assertEqual(tui.strip_ansi(soft), tui.strip_ansi(dark),
								 "{} changed its visible text with the theme".format(name))
				self.assertIn(true_fg(EXPECTED_ROLE[name], "contrast-dark"), dark,
							  "{} did not use the {} role".format(
								  name, EXPECTED_ROLE[name]))


class PlainPipeTest(unittest.TestCase):
	"""A pipe keeps today's plain text: no escapes, no glyphs, no theme drift."""

	def test_pipe_output_is_plain_and_theme_independent(self):
		for name in VIDEO_SCRIPTS:
			with self.subTest(script=name):
				call = CHROME_CALLS[name]
				soft = render(call, PIPE, "soft")
				dark = render(call, PIPE, "contrast-dark")
				self.assertTrue(soft.strip(),
								"{} printed nothing on a pipe".format(name))
				self.assertEqual(soft, dark,
								 "{} styled a pipe differently per theme".format(name))
				self.assertNotIn("\x1b", soft,
								 "{} styled a piped run".format(name))
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, soft,
									 "{} drew a frame on a pipe".format(name))


class SemanticColourOnlyTest(unittest.TestCase):
	"""No script carries a hex colour literal: roles come from the palette."""

	def test_no_hex_colour_in_the_video_scripts(self):
		pattern = re.compile(r"#[0-9A-Fa-f]{6}\b")
		for name in VIDEO_SCRIPTS:
			with self.subTest(script=name):
				source = (REPO / name).read_text(encoding="utf-8")
				self.assertIsNone(pattern.search(source),
								  "{} hardcodes a hex colour".format(name))


if __name__ == "__main__":
	unittest.main()
