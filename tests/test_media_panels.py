# Regression tests for the media group's boxed result blocks
"""
			MEDIA RESULT PANELS
			===================
Issue 0041 batch B1 moved the media group's block-shaped result/summary output
onto `tui.panel`: the audio splitter's completion note, the extractor's `Done.`
line, the two settings blocks, the joined/saved/tweaked result lines and the
frame-extraction summary. Per-item progress lines ("Processing: ...",
"Saved: ...") stay inline status lines.

Each probe drives the script's own block-producing path with FFmpeg, Decord,
Pillow and Pydub stubbed out, so no media is decoded and no binary is required.
The four cases pin the degradation axes the contract keeps apart:

	- `true` on a tty frames the block and emits truecolor,
	- level `16` frames it without truecolor,
	- level `none` keeps the frame and drops every escape,
	- a pipe prints the exact same bytes as before the sweep (no frame, no
	  escapes, no padding), pinned literally so a regression cannot slip in.

Run with:
	python -m unittest tests.test_media_panels -v
"""
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)

# A box frame's top-left glyph; a framed block must carry one.
FRAME = "\u250c"
BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"

# The path the join probe writes to, spelled for this platform.
_JOINED = os.path.join(".", "out.mp4")

# The plain bytes each script printed at the batch-A tip, before the panels.
PLAIN_EXPECTED = {
	"audiosplit.py":
		"Targeting\t1 files\n\nProcessing complete.\n",
	"getaudio.py":
		"[info] Found 1 file(s). Starting...\n\n[ok] Done.\n",
	"videofade.py":
		"\nFADE SETTINGS\nFade In\t1.0s\nFade Out\t1.0s\n"
		"Mode\tStandard\nCurve\tesin\n\n"
		"[info] Processing: clip.mp4...\n[ok] Saved as clip_faded.mp4\n",
	"videoframes.py":
		"Extracting frame 0 from clip.mp4...\n"
		"[ok] Frame saved as: clip_frame_0.png\n",
	"videojoin.py":
		"\nAnalyzing 1 inputs in '.'...\n\n"
		"[info] Executing FFmpeg for out.mp4...\n\n"
		"[ok] Joined video saved as " + _JOINED + "\n",
	"videoloop.py":
		"\nLOOP SETTINGS\nFade Time\t1.0s\nShift\t0%\nCurve\tesin\n\n"
		"[warn] Fade duration is very long for clip.mp4. Reducing overlap.\n"
		"[info] Processing: clip.mp4...\n[ok] Loop saved as clip_seamless.mp4\n",
	"videotweak.py":
		"Tweaking: clip.mp4...\n[ok] Saved to clip_tweak.mp4\n",
}


# --- Stubs: no FFmpeg, Decord, Pillow or Pydub ever runs ---------------------

class _Completed:
	"""`subprocess.run` result with a parseable FFmpeg version banner."""

	def __init__(self, returncode=0):
		self.returncode = returncode
		self.stdout = "ffmpeg version 4.4\n"
		self.stderr = ""


class _Frame:
	"""One fake decoded frame; only the shapes Pillow sees matter."""

	shape = (8, 8, 3)

	def asnumpy(self):
		return self


class _Reader:
	"""Fake `decord.VideoReader`: 48 frames at 24 fps."""

	def __init__(self, path, *args, **kwargs):
		self.path = path

	def get_avg_fps(self):
		return 24.0

	def __len__(self):
		return 48

	def __getitem__(self, index):
		return _Frame()


class _Image:
	"""Fake `PIL.Image` module: `fromarray(...).save(...)` writes nothing."""

	@staticmethod
	def fromarray(frame):
		return _Image()

	def save(self, path):
		pass


def _cpu(index=0):
	return index


def _decord():
	"""A stand-in `decord` module for the scripts' lazy import."""
	module = types.ModuleType("decord")
	module.VideoReader = _Reader
	module.cpu = _cpu
	return module


def _pydub():
	module = types.ModuleType("pydub")
	module.AudioSegment = object()
	return module


@contextlib.contextmanager
def _workdir():
	"""Run inside a scratch folder so output paths stay deterministic."""
	previous = os.getcwd()
	with tempfile.TemporaryDirectory() as folder:
		os.chdir(folder)
		try:
			yield folder
		finally:
			os.chdir(previous)


def _touch(name):
	Path(name).write_bytes(b"")


# --- Probes: one per script, driving only its block-producing path -----------

def probe_audiosplit(cap):
	import audiosplit

	with _workdir():
		_touch("song.wav")
		with mock.patch.dict(sys.modules, {"pydub": _pydub()}), \
				mock.patch.object(audiosplit, "check_ffmpeg", lambda: True), \
				mock.patch.object(audiosplit, "split_audio_file",
								  lambda *a, **k: True), \
				mock.patch.object(sys, "argv", ["audiosplit.py", "song.wav"]):
			audiosplit.main()


def probe_getaudio(cap):
	import getaudio

	with _workdir():
		_touch("clip.mp4")
		with mock.patch.object(getaudio, "check_requirements",
							   lambda cap=None: True), \
				mock.patch.object(getaudio, "process_file",
								  lambda *a, **k: True):
			getaudio.main(["clip.mp4"])


def probe_videofade(cap):
	import videofade

	with _workdir():
		_touch("clip.mp4")
		with mock.patch.dict(sys.modules, {"decord": _decord()}), \
				mock.patch.object(videofade, "has_audio", lambda path: False), \
				mock.patch.object(videofade.subprocess, "run",
								  lambda *a, **k: _Completed()), \
				mock.patch.object(sys, "argv", ["videofade.py", "clip.mp4"]):
			videofade.main()


def probe_videoframes(cap):
	import videoframes

	with _workdir():
		_touch("clip.mp4")
		with mock.patch.object(videoframes, "check_ffmpeg", lambda: True), \
				mock.patch.object(videoframes, "VideoReader", _Reader), \
				mock.patch.object(videoframes, "Image", _Image), \
				mock.patch.object(videoframes, "cpu", _cpu):
			videoframes.extract_frames("clip.mp4", cap, frame_id="first")


def probe_videojoin(cap):
	import videojoin

	with _workdir():
		_touch("clip.mp4")
		with mock.patch.object(videojoin, "check_ffmpeg", lambda: True), \
				mock.patch.object(videojoin, "VideoReader", _Reader), \
				mock.patch.object(videojoin, "has_audio", lambda path: False), \
				mock.patch.object(videojoin.subprocess, "run",
								  lambda *a, **k: _Completed()):
			videojoin.run_ffmpeg_join(
				["clip.mp4"], False, "libx264",
				{"width": 8, "height": 8, "method": "fit", "quant": 2},
				"out.mp4", cap, working_dir=".")


def probe_videoloop(cap):
	import videoloop

	with _workdir():
		_touch("clip.mp4")
		with mock.patch.dict(sys.modules, {"decord": _decord()}), \
				mock.patch.object(videoloop, "has_audio", lambda path: False), \
				mock.patch.object(videoloop.subprocess, "run",
								  lambda *a, **k: _Completed()), \
				mock.patch.object(sys, "argv", ["videoloop.py", "clip.mp4"]):
			videoloop.main()


def probe_videotweak(cap):
	import videotweak

	with _workdir():
		_touch("clip.mp4")
		with mock.patch.object(videotweak, "VideoReader", _Reader), \
				mock.patch.object(videotweak, "has_audio", lambda path: False), \
				mock.patch.object(videotweak.subprocess, "run",
								  lambda *a, **k: _Completed()):
			videotweak.process_video("clip.mp4", 6, None, None, "libx264",
									 ".mp4", None, cap)


PROBES = (
	("audiosplit.py", probe_audiosplit),
	("getaudio.py", probe_getaudio),
	("videofade.py", probe_videofade),
	("videoframes.py", probe_videoframes),
	("videojoin.py", probe_videojoin),
	("videoloop.py", probe_videoloop),
	("videotweak.py", probe_videotweak),
)

# The summary text each panel must still show, whatever the level.
SUMMARY = {
	"audiosplit.py": "Processing complete.",
	"getaudio.py": "[ok] Done.",
	"videofade.py": "FADE SETTINGS",
	"videoframes.py": "Frame saved as: clip_frame_0.png",
	"videojoin.py": "Joined video saved as",
	"videoloop.py": "LOOP SETTINGS",
	"videotweak.py": "Saved to clip_tweak.mp4",
}

TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=70, isatty=True,
							plain=False, reason="test")
TTY_16 = tui.Capabilities(level="16", unicode=True, width=70, isatty=True,
						  plain=False, reason="test")
TTY_NONE = tui.Capabilities(level="none", unicode=True, width=70, isatty=True,
							plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


def render(probe, cap, theme="soft"):
	"""Run one probe with `cap` resolved for the script and capture stdout."""
	buffer = io.StringIO()
	with mock.patch.dict(os.environ, {"CATRO_THEME": theme}), \
			mock.patch.object(tui, "detect", lambda: cap), \
			mock.patch.object(tui, "init_ansi"), \
			contextlib.redirect_stdout(buffer):
		probe(cap)
	return buffer.getvalue()


def plain_outputs():
	"""`{script: plain bytes}` for every probe; used to pin the pipe contract."""
	return {name: render(probe, PIPE) for name, probe in PROBES}


class BlockPanelTest(unittest.TestCase):
	"""One result panel per script, degrading by level and by pipe."""

	def test_true_colour_frames_the_block(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				out = render(probe, TTY_TRUE)
				self.assertIn(FRAME, out,
							  "{} drew no panel frame:\n{}".format(name, out))
				self.assertIn("\x1b[38;2;", out,
							  "{} emitted no truecolor:\n{}".format(name, out))
				self.assertIn(SUMMARY[name], tui.strip_ansi(out),
							  "{} lost its summary text:\n{}".format(name, out))

	def test_level_16_frames_without_truecolor(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				out = render(probe, TTY_16)
				self.assertIn(FRAME, out,
							  "{} drew no panel frame at level 16".format(name))
				self.assertIn("\x1b[", out)
				self.assertNotIn("38;2;", out,
								 "{} emitted truecolor at level 16".format(name))
				self.assertNotIn("48;2;", out,
								 "{} emitted truecolor at level 16".format(name))

	def test_level_none_keeps_the_frame_and_drops_the_escapes(self):
		for name, probe in PROBES:
			with self.subTest(script=name):
				out = render(probe, TTY_NONE)
				self.assertIn(FRAME, out,
							  "{} lost its frame at level none:\n{}".format(
								  name, out))
				self.assertNotIn("\x1b", out,
								 "{} kept escapes at level none".format(name))

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		for name, out in plain_outputs().items():
			with self.subTest(script=name):
				self.assertIn(name, PLAIN_EXPECTED,
							  "no pinned plain output for {}".format(name))
				self.assertNotIn("\x1b", out,
								 "{} sent escapes down a pipe".format(name))
				for glyph in BOX_GLYPHS:
					self.assertNotIn(glyph, out,
									 "{} drew a frame on a pipe".format(name))
				self.assertEqual(PLAIN_EXPECTED[name], out,
								 "{} changed its plain output".format(name))


class PromptSeamTest(unittest.TestCase):
	"""No media script reads input() directly; prompts come from tui.prompts."""

	def test_no_bare_input_in_the_seven_scripts(self):
		for name, _probe in PROBES:
			with self.subTest(script=name):
				source = (REPO / name).read_text(encoding="utf-8")
				self.assertNotIn("input(", source,
								 "{} still calls input() directly".format(name))

	def test_settings_blocks_use_a_tui_panel(self):
		for name, _probe in PROBES:
			with self.subTest(script=name):
				source = (REPO / name).read_text(encoding="utf-8")
				self.assertIn("tui.panel(", source,
							  "{} draws no result panel".format(name))


if __name__ == "__main__":
	unittest.main()
