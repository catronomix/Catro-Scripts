# Failing video runs report a non-zero exit (#25, #26)
"""
			VIDEO TOOL FAILURES
			===================
A failing video run must be visible to a caller: a missing input, an unreadable
clip or a rejected duration answer exits non-zero, while a completed run stays
0. `videotweak.parse_duration` pins its accepted grammar and refuses zero,
negative, exponent, trailing-junk and clock-form answers.

Nothing here invokes FFmpeg: every case fails before a real encode.

Run with:
	python -m unittest tests.test_video_failures
"""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))

import videotweak  # noqa: E402  (import after sys.path setup)
from support import clean_env  # noqa: E402  (test helper, not production)

# Missing input is the cheapest failing path for every script.
MISSING_INPUT_ARGS = {
	"videofade.py": ["missing-video.mp4"],
	"videoframes.py": ["missing-video.mp4", "first"],
	"videojoin.py": ["missing-video.mp4"],
	"videoloop.py": ["missing-video.mp4"],
	"videotweak.py": ["missing-video.mp4"],
}


class FailingPathExitCodeTest(unittest.TestCase):
	"""Each failing path leaves the process non-zero."""

	def test_missing_input_exits_non_zero(self):
		for name, args in MISSING_INPUT_ARGS.items():
			with self.subTest(script=name):
				proc = subprocess.run(
					[sys.executable, "-B", str(REPO / name), *args],
					cwd=str(REPO),
					env=clean_env(),
					stdin=subprocess.DEVNULL,
					stdout=subprocess.PIPE,
					stderr=subprocess.PIPE,
					timeout=120,
				)
				self.assertNotEqual(
					proc.returncode, 0,
					"{} exited 0 on a missing input".format(name))


def installed(name):
	"""True when the child interpreter (`sys.executable`) can import it."""
	return importlib.util.find_spec(name) is not None


class VideoFramesFailureMarkerTest(unittest.TestCase):
	"""videoframes reports the missing input from its own frame extractor.

	The exit code alone cannot tell the two failing paths apart: without
	decord/pillow videoframes exits at the dependency guard before any input
	is read, so the code passes for the wrong reason. Pinning the marker text
	proves `extract_frames` ran; on a host without the dependencies the test
	skips and the missing-input loop above still proves the exit code.
	"""

	def test_missing_input_reports_the_extract_frames_marker(self):
		if not (installed("decord") and installed("PIL")):
			self.skipTest("decord/pillow not installed: videoframes exits at "
						  "the dependency guard, not extract_frames")
		proc = subprocess.run(
			[sys.executable, "-B", str(REPO / "videoframes.py"),
			 "missing-video.mp4", "first"],
			cwd=str(REPO),
			env=clean_env(),
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			timeout=120,
		)
		both = (proc.stdout + proc.stderr).decode("utf-8", "replace")
		self.assertNotEqual(
			proc.returncode, 0,
			"videoframes exited 0 on a missing input\n" + both)
		self.assertIn(
			"File 'missing-video.mp4' not found.", both,
			"videoframes did not reach extract_frames:\n" + both)


class ParseDurationTest(unittest.TestCase):
	"""The duration grammar is stated, and junk is refused by name."""

	REJECTED = ("0", "-5", "1e3", "junk", "12abc", "1:2:3")
	ACCEPTED = (("90", 90.0), ("12.5", 12.5), ("1m30s", 90.0),
				("2m", 120.0), ("45s", 45.0))

	def test_rejected_answers_return_none(self):
		for text in self.REJECTED:
			with self.subTest(answer=text):
				self.assertIsNone(videotweak.parse_duration(text))

	def test_accepted_answers_return_seconds(self):
		for text, expected in self.ACCEPTED:
			with self.subTest(answer=text):
				self.assertEqual(videotweak.parse_duration(text), expected)


if __name__ == "__main__":
	unittest.main()
