# Theme plumbing for the system and file tools
"""
			SYSTEM AND FILE TOOL THEMES
			===========================
The system/file scripts (gitpush, ts_export, venvreplicator, renamer, alias,
newfile, shutdown, installdeps) render their chrome through the shared page
helpers (`tui.header`, `tui.status`, `tui.field`), so the selected palette has
to reach them without any script owning a colour.

Every probe below is a non-destructive path that still prints the script's own
chrome: a usage error, a validation failure, an unknown flag or the shutdown
masthead. Nothing here pushes, installs, renames or schedules anything.

Pins:
	- `CATRO_THEME` changes the bytes each script emits at a styled level, and
		the change comes from the palette (`38;2` truecolor), not from a private
		escape sequence;
	- a pipe keeps the plain text: no ANSI, no box glyphs, the same message;
	- `CATRO_ASCII` swaps the frame glyphs, `CATRO_COLOR=16` drops truecolor,
		and `NO_COLOR` beats a forced-colour request.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import clean_env  # noqa: E402  (test helper, not production)

TIMEOUT = 60

BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"

# (script, argv, marker that must reach both the styled and the plain output)
PROBES = [
	("gitpush.py", [], 'Usage: gitpush "<commit message>"'),
	("ts_export.py", [], "No 'tsconfig.json' found"),
	("venvreplicator.py", [], "Could not find Python executable"),
	("renamer.py", ["--bogus"], "unrecognized arguments: --bogus"),
	("alias.py", ["bad name"], "Invalid alias name"),
	("newfile.py", ["-z", "x"], "Unknown flag: -z"),
	("shutdown.py", [], "Cross-Platform Shutdown Timer"),
	("installdeps.py", ["-workdir", "no-such-dir"], "does not exist"),
]


def run_probe(script, argv, cwd, env, stdin_text=None):
	"""One probe in a child process with captured streams."""
	kwargs = {"input": stdin_text} if stdin_text is not None else {
		"stdin": subprocess.DEVNULL}
	return subprocess.run(
		[sys.executable, str(REPO / script), *argv],
		cwd=str(cwd),
		env=env,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		timeout=TIMEOUT,
		**kwargs
	)


def output_text(proc):
	return (proc.stdout + proc.stderr).decode("utf-8", "replace")


class ProbeCase(unittest.TestCase):
	"""Shared temporary cwd so no probe can touch the repository."""

	def setUp(self):
		self._temp = tempfile.TemporaryDirectory(prefix="catro-theme-")
		self.addCleanup(self._temp.cleanup)
		self.cwd = Path(self._temp.name)

	def probe(self, script, argv, **overrides):
		env = clean_env(**overrides)
		stdin_text = b"q\n" if script == "shutdown.py" else None
		return output_text(run_probe(script, argv, self.cwd, env, stdin_text))


class ThemeSwapTest(ProbeCase):
	"""`CATRO_THEME` must visibly change each script's output."""

	def test_each_script_swaps_with_the_theme(self):
		for script, argv, marker in PROBES:
			with self.subTest(script=script):
				soft = self.probe(script, argv, FORCE_COLOR="3",
								  CATRO_THEME="soft")
				light = self.probe(script, argv, FORCE_COLOR="3",
								   CATRO_THEME="contrast-light")
				self.assertIn(marker, soft,
							  "{} lost its message: {!r}".format(script, soft[:400]))
				self.assertIn(marker, light,
							  "{} lost its message: {!r}".format(script, light[:400]))
				self.assertIn("\x1b[", soft,
							  "{} printed no styling at a styled level".format(script))
				self.assertIn("\x1b[", light,
							  "{} printed no styling at a styled level".format(script))
				self.assertNotEqual(
					soft, light,
					"{} ignored CATRO_THEME (the two themes are byte-identical)".format(
						script))
				# The difference is palette-driven, not a private escape string.
				self.assertIn("\x1b[38;2", soft + light,
							  "{} emitted no truecolor palette code".format(script))


class PipePlainTest(ProbeCase):
	"""A pipe keeps the plain text: no escapes, no box glyphs, same message."""

	def test_pipe_has_no_ansi_or_glyphs(self):
		for script, argv, marker in PROBES:
			with self.subTest(script=script):
				out = self.probe(script, argv, NO_COLOR="1")
				self.assertIn(marker, out,
							  "{} lost its message: {!r}".format(script, out[:400]))
				self.assertNotIn("\x1b", out,
								 "{} wrote an escape to a pipe: {!r}".format(
									 script, out[:400]))
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, out,
									 "{} drew a box glyph in a pipe".format(script))

	def test_no_color_beats_a_forced_colour_pipe(self):
		for script, argv, marker in PROBES:
			with self.subTest(script=script):
				out = self.probe(script, argv, NO_COLOR="1", FORCE_COLOR="3")
				self.assertIn(marker, out)
				self.assertNotIn("\x1b", out,
								 "{} styled a pipe although NO_COLOR was set".format(
									 script))


class DegradationTest(ProbeCase):
	"""ASCII frames and the 16-colour stop reach the chrome helpers."""

	def test_ascii_swaps_the_header_rule(self):
		out = self.probe("shutdown.py", [], FORCE_COLOR="3", CATRO_ASCII="1")
		self.assertIn("Cross-Platform Shutdown Timer", out)
		self.assertIn("-", out, "the ASCII rule is missing: {!r}".format(out[:200]))
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, out,
							 "CATRO_ASCII left the glyph {!r}".format(glyph))

	def test_16_colour_output_keeps_no_truecolor(self):
		out = self.probe("shutdown.py", [], CATRO_COLOR="16")
		self.assertIn("\x1b[", out)
		self.assertNotIn("\x1b[38;2", out,
						 "16-colour output carried a truecolor code")


if __name__ == "__main__":
	unittest.main()
