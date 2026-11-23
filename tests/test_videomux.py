# Regression tests for videomux: naming, filter graph, guards and the run
"""
			VIDEOMUX BEHAVIOUR
			==================
The muxer's contract is checked without running FFmpeg: the default output name
carries the audio codec of the target container, the filter graph keeps exactly
one stereo track (front pair, mono doubled) and always pads/caps to the video's
length, and every input that cannot be combined is refused before a command is
built. The successful path is asserted on the command FFmpeg would receive: the
video is stream-copied, the video's own audio is never mapped, and the audio is
encoded for the target container.

Run with:
	python -m unittest tests.test_videomux -v
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

import tui  # noqa: E402  (import after sys.path setup)
import videomux  # noqa: E402

PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")

VIDEO_DATA = {
	"streams": [{"codec_type": "video", "codec_name": "h264",
				 "duration": "10.0"}],
	"format": {"duration": "10.0"},
}
AUDIO_DATA = {
	"streams": [{"codec_type": "audio", "codec_name": "aac", "channels": 2,
				 "sample_rate": "48000", "duration": "3.0"}],
	"format": {"duration": "3.0"},
}
SILENT_VIDEO = {
	"streams": [{"codec_type": "audio", "codec_name": "aac", "channels": 1,
				 "sample_rate": "44100", "duration": "10.0"}],
	"format": {"duration": "10.0"},
}


class Done:
	"""Stand-in for a finished FFmpeg/ffprobe process."""

	returncode = 0
	stdout = ""
	stderr = ""


def fake_probe(path):
	"""The video probe for video-looking paths, the audio probe otherwise."""
	return AUDIO_DATA if Path(path).suffix.lower() in (".m4a", ".wav") else VIDEO_DATA


class MuxRun:
	"""Drive `videomux.main` with faked binaries and record the FFmpeg call."""

	def __init__(self, video="clip.mp4", audio="track.m4a", extra=(), exists=(),
				 fail=False, create=("video", "audio")):
		self.argv = ["videomux.py", video, audio] + list(extra)
		self.extra = list(extra)
		self.exists = set(exists)
		self.fail = fail
		self.create = set(create)
		self.commands = []

	def __call__(self, cap=PIPE, probe=fake_probe):
		out = io.StringIO()
		self.commands = []

		class Failed:
			returncode = 1
			stdout = ""
			stderr = "boom\nNo space left on device\n"

		def record(cmd, *args, **kwargs):
			self.commands.append(list(cmd))
			return Failed() if self.fail else Done()

		previous = os.getcwd()
		with tempfile.TemporaryDirectory() as tmp:
			# The run names a bare `-o` relative to the CWD, so the scratch
			# folder is the CWD: existing outputs and inputs line up with it.
			os.chdir(tmp)
			try:
				video = os.path.join(tmp, "clip.mp4")
				audio = os.path.join(tmp, "track.m4a")
				for kind, path in (("video", video), ("audio", audio)):
					if kind in self.create:
						open(path, "w").close()
				for path in self.exists:
					open(os.path.join(tmp, path), "w").close()
				argv = [self.argv[0], video, audio] + self.extra
				with mock.patch.object(sys, "argv", argv), \
						mock.patch.object(videomux.tui, "detect",
										  return_value=cap), \
						mock.patch.object(videomux, "check_bin",
										  return_value=True), \
						mock.patch.object(videomux, "probe", side_effect=probe), \
						mock.patch.object(videomux.subprocess, "run", record), \
						contextlib.redirect_stdout(out):
					try:
						code = videomux.main()
					except SystemExit as exc:
						code = exc.code
			finally:
				os.chdir(previous)
		self.output = out.getvalue()
		return code


class OutputNamingTests(unittest.TestCase):
	"""`_<audiocodec>` follows the container, a suffix replaces it."""

	def test_default_name_carries_the_container_audio_codec(self):
		self.assertEqual(videomux.default_output("clip.mp4"), "clip_aac.mp4")
		self.assertEqual(videomux.default_output("clip.webm"), "clip_opus.webm")
		self.assertEqual(videomux.default_output("clip.avi"), "clip_mp3.avi")
		self.assertEqual(videomux.default_output("clip.mkv"), "clip_aac.mkv")

	def test_extensionless_video_is_named_as_mp4(self):
		self.assertEqual(videomux.default_output("clip"), "clip_aac.mp4")

	def test_custom_suffix_replaces_the_codec_tag(self):
		self.assertEqual(videomux.default_output("clip.mp4", "_muxed"),
						 "clip_muxed.mp4")

	def test_bare_output_name_lands_in_the_working_directory(self):
		output = videomux.resolve_output("muxed", "clip.webm")
		self.assertEqual(output, os.path.join(os.getcwd(), "muxed.webm"))

	def test_output_with_a_directory_is_kept_as_given(self):
		output = videomux.resolve_output("sub/muxed.mp4", "clip.mp4")
		self.assertEqual(output, os.path.join("sub", "muxed.mp4"))

	def test_encoder_follows_the_output_container(self):
		self.assertEqual(videomux.audio_encoder(".mp4")[1], "aac")
		self.assertEqual(videomux.audio_encoder(".WEBM")[1], "opus")
		self.assertEqual(videomux.audio_encoder(".avi")[1], "mp3")


class AudioFilterTests(unittest.TestCase):
	"""One stereo track: front pair for surround, doubled for mono."""

	def test_surround_keeps_its_front_pair(self):
		graph = videomux.build_audio_filter(6, 48000, 0.0, 10.0, 10.0, False)
		self.assertIn("pan=stereo|c0=c0|c1=c1", graph)

	def test_mono_is_doubled_to_both_sides(self):
		graph = videomux.build_audio_filter(1, 44100, 0.0, 10.0, 10.0, False)
		self.assertIn("pan=stereo|c0=c0|c1=c0", graph)

	def test_the_video_length_pads_and_caps_the_audio(self):
		graph = videomux.build_audio_filter(2, 48000, 0.0, 3.0, 10.0, False)
		self.assertIn("apad=whole_dur=10", graph)
		self.assertIn("atrim=end=10", graph)

	def test_trims_become_the_window(self):
		graph = videomux.build_audio_filter(2, 48000, 2.5, 8.0, 10.0, False)
		self.assertIn("atrim=start=2.5:end=8.0", graph)

	def test_loop_repeats_the_trimmed_window_by_samples(self):
		graph = videomux.build_audio_filter(2, 48000, 0.0, 2.0, 10.0, True)
		self.assertIn("aloop=loop=-1:size=96000", graph)

	def test_no_loop_means_no_aloop(self):
		graph = videomux.build_audio_filter(2, 48000, 0.0, 2.0, 10.0, False)
		self.assertNotIn("aloop", graph)


class RunTests(unittest.TestCase):
	"""The refusal paths stop before FFmpeg; the good path copies the video."""

	def test_missing_input_is_refused_without_running_ffmpeg(self):
		run = MuxRun(create=())
		self.assertEqual(run(), 1)
		self.assertEqual(run.commands, [])
		self.assertIn("file not found", run.output)

	def test_video_without_a_video_stream_is_refused(self):
		run = MuxRun()
		self.assertEqual(run(probe=lambda path: SILENT_VIDEO
							 if path.endswith(".mp4") else AUDIO_DATA), 1)
		self.assertEqual(run.commands, [])
		self.assertIn("No video stream", run.output)

	def test_audio_without_an_audio_stream_is_refused(self):
		run = MuxRun()
		self.assertEqual(run(probe=lambda path: VIDEO_DATA), 1)
		self.assertEqual(run.commands, [])
		self.assertIn("No audio stream", run.output)

	def test_cut_start_past_the_audio_end_is_refused(self):
		run = MuxRun(extra=["-s", "9"])
		self.assertEqual(run(), 1)
		self.assertEqual(run.commands, [])
		self.assertIn("past the end of the audio", run.output)

	def test_a_cut_that_removes_everything_is_refused(self):
		run = MuxRun(extra=["-e", "5"])
		self.assertEqual(run(), 1)
		self.assertEqual(run.commands, [])
		self.assertIn("leaves no audio", run.output)

	def test_negative_cuts_are_refused(self):
		run = MuxRun(extra=["-s", "-1"])
		self.assertEqual(run(), 1)
		self.assertIn("zero or positive", run.output)

	def test_output_cannot_be_an_input(self):
		run = MuxRun(extra=["-o", "clip.mp4"])
		self.assertEqual(run(), 1)
		self.assertEqual(run.commands, [])
		self.assertIn("would overwrite an input", run.output)

	def test_output_and_suffix_are_mutually_exclusive(self):
		run = MuxRun(extra=["-o", "x.mp4", "--suffix", "_y"])
		self.assertEqual(run(), 2)

	def test_success_copies_the_video_and_encodes_one_stereo_track(self):
		run = MuxRun()
		self.assertEqual(run(), 0)
		self.assertEqual(len(run.commands), 1)
		cmd = run.commands[0]
		self.assertEqual(cmd[cmd.index("-c:v") + 1], "copy")
		self.assertEqual(cmd[cmd.index("-map") + 1], "0:v:0")
		# The video's own audio is never mapped: exactly one audio map, the
		# filtered track.
		self.assertEqual(cmd.count("-map"), 2)
		self.assertIn("[aout]", cmd)
		self.assertEqual(cmd[cmd.index("-c:a") + 1], "aac")
		self.assertIn("pan=stereo", cmd[cmd.index("-filter_complex") + 1])
		self.assertTrue(cmd[-1].endswith("clip_aac.mp4"))
		self.assertIn("Combined clip saved as", run.output)

	def test_existing_output_is_skipped_on_a_pipe(self):
		run = MuxRun(exists=("out.mp4",), extra=["-o", "out.mp4"])
		self.assertEqual(run(), 0)
		self.assertEqual(run.commands, [])
		self.assertIn("Skipped out.mp4", run.output)

	def test_a_failed_ffmpeg_run_reports_and_returns_one(self):
		run = MuxRun(fail=True)
		self.assertEqual(run(), 1)
		self.assertEqual(len(run.commands), 1)
		self.assertIn("No space left on device", run.output)
		self.assertIn("Failed: 0/1 output written", run.output)


if __name__ == "__main__":
	unittest.main()
