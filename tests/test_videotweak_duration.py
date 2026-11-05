# Duration parsing and error propagation for videotweak
"""
			VIDEO TWEAK DURATION VALIDATION
			==============================
Exercise duration inputs and the CLI boundary without media dependencies or
encoding: a synthetic reader supplies metadata and FFmpeg calls are mocked.
"""
import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui
import videotweak

PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


class DurationTest(unittest.TestCase):
	def test_accepted_forms(self):
		for value, expected in (
			("5", 5), ("5.5", 5.5), (".5", .5), ("5.", 5),
			("1m30s", 90), ("2m", 120), ("45s", 45), (" 1M30S ", 90),
			("1:2:3", 3723), ("1:02", 62), ("1:02.5", 62.5),
			("01:02:03.5", 3723.5), ("0:00:00.5", .5),
		):
			with self.subTest(value=value):
				self.assertEqual(videotweak.parse_duration(value), expected)

	def test_rejected_forms(self):
		for value in ("junk", "12abc", "1e3", "1m30sjunk", "1m2m", "5sjunk",
					  "", " ", "nan", "inf", "1_000", "+5", "1:60", "1:60:00",
					  "1:2:60", "1::2", "1:2:3:4", "1.5:02", "9" * 400):
			with self.subTest(value=value):
				with self.assertRaises(ValueError):
					videotweak.parse_duration(value)

	def test_zero_has_a_named_reason(self):
		for value in ("0", "0.0", "0m0s", "00:00", "0:0:0"):
			with self.subTest(value=value):
				with self.assertRaisesRegex(ValueError, "[Zz]ero"):
					videotweak.parse_duration(value)

	def test_negative_has_a_named_reason(self):
		for value in ("-5", "-0.5", "-1m", "-1:00"):
			with self.subTest(value=value):
				with self.assertRaisesRegex(ValueError, "[Nn]egative"):
					videotweak.parse_duration(value)


class DurationCliTest(unittest.TestCase):
	def run_main(self, duration, effect=5, batch=False):
		reader = mock.Mock()
		reader.get_avg_fps.return_value = 30
		reader.__len__ = mock.Mock(return_value=300)
		output, errors = io.StringIO(), io.StringIO()
		with tempfile.TemporaryDirectory() as folder:
			video = Path(folder) / "synthetic.mp4"
			video.touch()
			if batch:
				(Path(folder) / "second.mp4").touch()
			with mock.patch.dict(sys.modules, {"decord": types.SimpleNamespace(
					VideoReader=mock.Mock(return_value=reader))}), \
				 mock.patch.object(sys, "argv", ["videotweak.py", folder if batch else str(video)]), \
				 mock.patch.object(tui, "init_ansi"), \
				 mock.patch.object(tui, "detect", return_value=PIPE), \
				 mock.patch.object(tui, "ask_text", return_value=duration) as ask, \
				 mock.patch.object(tui, "ask_int", return_value=1), \
				 mock.patch.object(videotweak, "get_effect_choice", return_value=effect), \
				 mock.patch.object(videotweak, "has_audio", return_value=False), \
				 mock.patch.object(videotweak.subprocess, "run", return_value=
							   types.SimpleNamespace(returncode=0)) as encode, \
				 contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
				try:
					videotweak.main()
					exit_code = 0
				except SystemExit as exc:
					exit_code = exc.code
		return exit_code, output.getvalue() + errors.getvalue(), encode, ask

	def test_invalid_duration_exits_once_before_encoding(self):
		for value in ("0", "-5", "1e3", "junk", "12abc"):
			with self.subTest(value=value):
				code, output, encode, _ = self.run_main(value, batch=True)
				self.assertEqual(code, 1)
				self.assertEqual(output.lower().count("invalid target duration"), 1)
				self.assertNotIn("Traceback", output)
				encode.assert_not_called()

	def test_colon_duration_reaches_encoding(self):
		code, output, encode, _ = self.run_main("1:02.5")
		self.assertEqual(code, 0)
		self.assertNotIn("error", output.lower())
		encode.assert_called_once()
		self.assertIn("setpts=6.25*PTS", encode.call_args.args[0])

	def test_cancelled_duration_does_not_encode(self):
		code, output, encode, _ = self.run_main(None)
		self.assertEqual(code, 0)
		self.assertNotIn("error", output.lower())
		encode.assert_not_called()

	def test_passthrough_needs_no_duration(self):
		code, _, encode, ask = self.run_main(None, effect=6)
		self.assertEqual(code, 0)
		encode.assert_called_once()
		ask.assert_not_called()
