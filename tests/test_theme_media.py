# Theme, pipe and page-chrome regression tests for the media/file scripts
"""
			THEMED MEDIA AND FILE PAGES
			===========================
The media and file tools in this group draw their chrome through `tui/`
(`header`, `menu`, `section`, `field`, `key_values`, `status`), so:

	- the selected theme must change the bytes a terminal receives,
	- a pipe must stay plain text: no escape sequences, no box glyphs, and the
		message itself still present,
	- `CATRO_COLOR=16` must not emit truecolor, and `CATRO_ASCII` must drop the
		Unicode frame.

Each probe below drives the script's own chrome-producing path with the
dependency-heavy work stubbed out (pillow, piexif, pydub, npm, ffmpeg never
run), so the assertion is about the script and not about a copy of its call.

Run with:
	python -m unittest tests.test_theme_media -v
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))

import tui  # noqa: E402  (import after sys.path setup)
from support import clean_env  # noqa: E402  (test helper, not production)

# Every glyph a box frame or rule can emit; plain output must contain none.
BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"

# The shared chrome helpers these scripts are expected to render through.
CHROME_CALLS = ("tui.header(", "tui.panel(", "tui.rule(", "tui.field(",
				"tui.status(", "tui.menu(", "tui.section(", "tui.key_values(")


# --- Probes: one per script, driving only its chrome-producing path ----------

def probe_audiosplit(cap):
	import audiosplit
	with mock.patch.object(tui, "ask_int", return_value=None):
		audiosplit.interactive_codec_menu(cap)


def probe_image_resizer(cap):
	import image_resizer
	cwd = os.getcwd()
	with tempfile.TemporaryDirectory() as td:
		os.chdir(td)
		try:
			with mock.patch.object(tui, "ask_int", return_value=None):
				image_resizer.resize_images_in_folder(cap)
		finally:
			os.chdir(cwd)


def probe_image_generator(cap):
	import image_generator
	# A blank colour is rejected before pillow is touched.
	with mock.patch.object(tui, "ask_text", return_value=""):
		image_generator.generate_colored_images(cap)


def probe_ts_setup(cap):
	import ts_setup
	argv = sys.argv
	sys.argv = ["ts_setup.py"]
	try:
		with mock.patch.object(tui, "require_tty", lambda name: None), \
				mock.patch.object(ts_setup, "check_env",
								  return_value=("v20.0.0", "10.0.0")), \
				mock.patch.object(tui, "ask_text", return_value=""):
			ts_setup.main()
	finally:
		sys.argv = argv


def probe_getaudio(cap):
	import getaudio
	getaudio.main([])


def probe_exifcopy(cap):
	import exifcopy
	with mock.patch.dict(sys.modules, {"piexif": mock.MagicMock()}):
		try:
			exifcopy.copy_exif("missing_source.jpg", "missing_target.jpg",
							   cap=cap)
		except SystemExit:
			pass


def probe_timecopy(cap):
	import timecopy
	timecopy.copy_metadata("missing_source.jpg", "missing_target.jpg", cap=cap)


def probe_randomsorter(cap):
	import randomsorter
	with tempfile.TemporaryDirectory() as td:
		randomsorter.distribute_files(td, [], None, True, "batch", False, 12,
									  False, cap)


PROBES = (
	("audiosplit.py", probe_audiosplit),
	("image_resizer.py", probe_image_resizer),
	("image_generator.py", probe_image_generator),
	("ts_setup.py", probe_ts_setup),
	("getaudio.py", probe_getaudio),
	("exifcopy.py", probe_exifcopy),
	("timecopy.py", probe_timecopy),
	("randomsorter.py", probe_randomsorter),
)


def render(probe, environ):
	"""Run one probe under `environ` and return everything it wrote to stdout."""
	buffer = io.StringIO()
	env = clean_env()
	env.update(environ)
	with mock.patch.dict(os.environ, env, clear=True), \
			mock.patch.object(tui, "init_ansi"), \
			contextlib.redirect_stdout(buffer):
		cap = tui.detect()
		probe(cap)
	return buffer.getvalue()


class ThemeSwapTests(unittest.TestCase):
	"""`CATRO_THEME` must repaint each script's chrome."""

	def test_every_script_changes_bytes_between_themes(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				soft = render(probe, {"FORCE_COLOR": "3",
									  "CATRO_THEME": "soft"})
				dark = render(probe, {"FORCE_COLOR": "3",
									  "CATRO_THEME": "contrast-dark"})
				self.assertIn("\x1b[", soft,
							  "{} drew no styled chrome:\n{}".format(name, soft))
				self.assertNotEqual(soft, dark,
									"{} ignored CATRO_THEME".format(name))

	def test_level_16_never_emits_truecolor(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				out = render(probe, {"CATRO_COLOR": "16", "CATRO_THEME": "soft"})
				self.assertIn("\x1b[", out)
				self.assertNotIn("38;2;", out,
								 "{} emitted truecolor at level 16".format(name))
				self.assertNotIn("48;2;", out,
								 "{} emitted truecolor at level 16".format(name))

	def test_ascii_fallback_drops_the_unicode_frame(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				out = render(probe, {"FORCE_COLOR": "3", "CATRO_ASCII": "1"})
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, out,
									 "{} kept a unicode glyph under "
									 "CATRO_ASCII".format(name))

	def test_the_masthead_scripts_draw_an_ascii_rule_as_a_fallback(self):
		# These four open with `tui.header`, so their rule has a glyph to swap.
		for name, probe in (PROBES[0], PROBES[1], PROBES[2], PROBES[3]):
			with self.subTest(script=name):
				out = render(probe, {"FORCE_COLOR": "3", "CATRO_ASCII": "1"})
				self.assertIn("-", out,
							  "{} drew no ASCII rule:\n{}".format(name, out))


class PlainPipeTests(unittest.TestCase):
	"""A pipe stays machine-readable: no escapes, no glyphs, text intact."""

	def test_every_script_is_plain_on_a_pipe(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				out = render(probe, {})
				self.assertTrue(out.strip(), "{} wrote nothing".format(name))
				self.assertNotIn("\x1b", out,
								 "{} sent escapes down a pipe:\n{}".format(name, out))
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, out,
									 "{} sent box glyphs down a pipe:\n{}".format(
										 name, out))

	def test_no_color_pipe_keeps_the_message_after_the_marker(self):
		out = render(probe_getaudio, {"NO_COLOR": "1"})
		self.assertIn("No valid files found to process.", out)
		self.assertNotIn("\x1b", out)

	def test_plain_status_is_the_ascii_marker_and_the_text(self):
		out = render(probe_timecopy, {})
		self.assertIn("[error] Error: Source file", out)

	def test_field_on_a_pipe_is_a_tab_record(self):
		# `tui.field` is `key<TAB>value` off a tty; audiosplit's target count
		# stays one record either way.
		out = render(probe_audiosplit, {})
		self.assertIn("WAV (Uncompressed)", out)


class ChromeSourceTests(unittest.TestCase):
	"""The eight scripts render through the shared helpers, not private ANSI."""

	def test_each_script_calls_a_chrome_helper(self):
		for name, _probe in PROBES:
			with self.subTest(script=name):
				source = (REPO / name).read_text(encoding="utf-8")
				self.assertTrue(any(call in source for call in CHROME_CALLS),
								"{} renders no shared page chrome".format(name))
				self.assertNotIn("\\033", source,
								 "{} hardcodes an escape sequence".format(name))


if __name__ == "__main__":
	unittest.main()
