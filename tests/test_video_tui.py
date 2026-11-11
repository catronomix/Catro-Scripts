# Regression tests for the video tools' tui migration
"""
			VIDEO TOOLS ON TUI
			==================
The five video scripts print their chrome through `tui`: no private escape
sequence survives in the source, a piped run stays plain text with no box
glyphs, and the capabilities resolved once in `main()` are what the helpers
style with instead of each call re-detecting the terminal.

These checks never invoke FFmpeg for real: every case either misses its input
file or stops at the optional-dependency check, and only the presentation is
asserted.

Run with:
	python -m unittest discover -s tests -v
"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))

import tui  # noqa: E402  (import after sys.path setup)
from support import clean_env  # noqa: E402  (test helper, not production)

VIDEO_SCRIPTS = ("videofade.py", "videoframes.py", "videojoin.py",
				 "videoloop.py", "videotweak.py")

# argparse argv that lands on an error/notice path without touching a video.
PLAIN_ARGS = {
	"videofade.py": ["missing-video.mp4"],
	"videoframes.py": ["missing-video.mp4", "first"],
	"videojoin.py": ["missing-video.mp4"],
	"videoloop.py": ["missing-video.mp4"],
	"videotweak.py": ["missing-video.mp4"],
}

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"


def child_env():
	"""Colour switches scrubbed; output pinned to UTF-8 for the child."""
	env = clean_env()
	env["PYTHONIOENCODING"] = "utf-8"
	return env


class NoPrivateAnsiTest(unittest.TestCase):
	"""The five scripts style only through tui."""

	def test_no_private_escape_sequence(self):
		for name in VIDEO_SCRIPTS:
			with self.subTest(script=name):
				source = (REPO / name).read_text(encoding="utf-8")
				self.assertNotIn("\\033", source,
								 "{} still hardcodes an escape sequence".format(name))
				self.assertNotIn("\\x1b", source,
								 "{} still hardcodes an escape sequence".format(name))
				self.assertNotIn("class Colors", source,
								 "{} still has a private colour helper".format(name))


class PlainPipeOutputTest(unittest.TestCase):
	"""A non-tty run emits plain text only, on every error/notice path."""

	def run_script(self, name, args):
		return subprocess.run(
			[sys.executable, "-B", str(REPO / name), *args],
			cwd=str(REPO),
			env=child_env(),
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			timeout=120,
		)

	def test_missing_input_stays_plain(self):
		for name in VIDEO_SCRIPTS:
			with self.subTest(script=name):
				proc = self.run_script(name, PLAIN_ARGS[name])
				out = proc.stdout.decode("utf-8", "replace")
				self.assertTrue(out.strip(), "{} printed nothing".format(name))
				self.assertNotIn("\x1b", out,
								 "{} styled a piped run: {!r}".format(name, out[:400]))
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, out,
									 "{} drew a box glyph on a pipe".format(name))

	def test_help_needs_no_third_party_import(self):
		# --help must work with decord/pillow absent, so the dependency import
		# has to stay inside main().
		code = (
			"import builtins, runpy, sys\n"
			"real_import = builtins.__import__\n"
			"def guard(name, *args, **kwargs):\n"
			"    if name.split('.')[0] in ('decord', 'PIL'):\n"
			"        raise ImportError('blocked: ' + name)\n"
			"    return real_import(name, *args, **kwargs)\n"
			"builtins.__import__ = guard\n"
			"sys.argv = [sys.argv[1], '--help']\n"
			"runpy.run_path(sys.argv[0], run_name='__main__')\n"
		)
		for name in VIDEO_SCRIPTS:
			with self.subTest(script=name):
				proc = subprocess.run(
					[sys.executable, "-B", "-c", code, str(REPO / name)],
					cwd=str(REPO),
					env=child_env(),
					stdin=subprocess.DEVNULL,
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE,
					timeout=120,
				)
				self.assertEqual(proc.returncode, 0,
								 "{} --help failed without its optional deps: {}".format(
									 name, proc.stderr.decode("utf-8", "replace")[-600:]))


class CapabilityHandoffTest(unittest.TestCase):
	"""Helpers style with the cap they are given, not one they resolve."""

	plain_cap = tui.Capabilities(level="none", unicode=False, width=None,
								 isatty=False, plain=True, reason="test")
	tty_cap = tui.Capabilities(level="16", unicode=True, width=None,
							   isatty=True, plain=False, reason="test")

	def test_ffmpeg_notice_follows_the_capabilities(self):
		import videoframes
		plain = videoframes.get_ffmpeg_instructions(self.plain_cap)
		styled = videoframes.get_ffmpeg_instructions(self.tty_cap)
		self.assertNotIn("\x1b", plain)
		self.assertIn("\x1b", styled)
		self.assertIn("FFmpeg is missing or not found.",
					  tui.strip_ansi(styled))


if __name__ == "__main__":
	unittest.main()
