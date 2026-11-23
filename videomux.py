# Combine a video with an audio file using FFmpeg (video stream copied as-is)
"""
			VIDEO MUX (AUDIO SWAP)
			======================
Combines a video file with an audio file into one new clip. The video stream is
stream-copied (the picture is never re-encoded) and any audio already inside the
video is discarded, so the result carries exactly one video track and exactly
one stereo audio track.

Audio rules:
	- One stereo track is always produced: the first two channels of the source
	  are kept, a mono source is doubled to both sides, and any surround layout is
	  reduced to its front pair.
	- The video decides the length: a longer audio is cut off at the last frame,
	  a shorter one is padded with silence at the end.
	- The audio is re-encoded, because trimming, channel mapping, looping and
	  padding all happen in one filter graph; the video is not.

Usage:
	catro-scripts videomux <inputvideopath> <inputaudiopath> [options]

Options:
	-s, --cutstart <sec>  Cut off the start of the audio (seconds).
	-e, --cutend <sec>    Cut off the end of the audio (seconds, from the end).
	-l, --loop            Loop the audio when it is shorter than the video.
	-o, --output <path>   Output filename; no directory means the CWD.
	-x, --suffix <text>   Custom suffix instead of "_<audiocodec>".

Output name:
	<input video name>_<audiocodec>.<video ext>, for example clip_aac.mp4. The
	audio codec is the one the target container gets: aac for mp4/mov/mkv/m4v,
	opus for webm, mp3 for avi.

Notes:
	- --suffix and --output are mutually exclusive: both would name the same file.
	- A cut window that removes the whole audio is refused before FFmpeg runs.

Requirements:
	- ffmpeg and ffprobe must be available: in the system PATH, or placed next
	  to this script (videomux.py).

Exit status:
	0 = the combined clip was written (or the run was skipped on request).
	1 = bad input, a missing binary, or FFmpeg failed.
"""

import os
import sys
import json
import math
import argparse
import subprocess

import tui

# Container that the audio encoder and the extension are picked from.
CONTAINER_AUDIO = {
	".webm": ("libopus", "opus", ["-b:a", "160k"]),
	".avi": ("libmp3lame", "mp3", ["-b:a", "192k"]),
}
DEFAULT_AUDIO = ("aac", "aac", ["-b:a", "192k"])
# Containers whose muxer accepts (and likes) a faststart index.
FASTSTART_EXTS = (".mp4", ".mov", ".m4v")

def get_bin_path(name):
	"""Returns the path to a binary, prioritizing the script's directory."""
	script_dir = os.path.dirname(os.path.abspath(__file__))
	local_path = os.path.join(script_dir, name)
	if os.name == "nt" and not local_path.lower().endswith(".exe"):
		local_path += ".exe"
	if os.path.exists(local_path) and os.access(local_path, os.X_OK):
		return local_path
	return name

FFMPEG_BIN = get_bin_path("ffmpeg")
FFPROBE_BIN = get_bin_path("ffprobe")

def check_bin(binary):
	"""True when the binary answers --version, False when it cannot be run."""
	try:
		subprocess.run([binary, "-version"], stdout=subprocess.DEVNULL,
					   stderr=subprocess.DEVNULL)
		return True
	except OSError:
		return False

def _error_tail(stderr, fallback):
	"""Last non-empty stderr line, so a failure reads as one short sentence."""
	if isinstance(stderr, bytes):
		stderr = stderr.decode("utf-8", "replace")
	lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
	return lines[-1] if lines else fallback

def _seconds(value):
	"""ffprobe duration strings to float; None when absent or unparseable."""
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if number > 0 else None

def probe(path):
	"""ffprobe the file as JSON; None when it cannot be read."""
	cmd = [FFPROBE_BIN, "-v", "error", "-print_format", "json",
		   "-show_streams", "-show_format", path]
	try:
		result = subprocess.run(cmd, capture_output=True, text=True)
	except OSError:
		return None
	if result.returncode != 0:
		return None
	try:
		return json.loads(result.stdout)
	except ValueError:
		return None

def first_stream(data, kind):
	"""The first stream of `kind` ("video"/"audio"), or None."""
	for stream in (data or {}).get("streams", []):
		if stream.get("codec_type") == kind:
			return stream
	return None

def stream_duration(data, kind):
	"""Duration of the first `kind` stream, falling back to the container."""
	stream = first_stream(data, kind)
	value = _seconds((stream or {}).get("duration"))
	if value is None:
		value = _seconds((data or {}).get("format", {}).get("duration"))
	return value

def audio_encoder(ext):
	"""(encoder, label, extra args) for the target container extension."""
	return CONTAINER_AUDIO.get((ext or "").lower(), DEFAULT_AUDIO)

def default_output(video_path, suffix=None):
	"""`<stem>_<audiocodec><ext>`, or `<stem><suffix><ext>` when given."""
	stem, ext = os.path.splitext(video_path)
	if not ext:
		stem, ext = video_path, ".mp4"
	label = audio_encoder(ext)[1]
	tag = "_{}".format(label) if suffix is None else suffix
	return stem + tag + ext

def resolve_output(raw, video_path):
	"""`-o` path as given, or in the CWD when it carries no directory."""
	ext = os.path.splitext(video_path)[1] or ".mp4"
	output = os.path.expanduser(raw)
	if not os.path.splitext(output)[1]:
		output += ext
	if not os.path.dirname(output):
		output = os.path.join(os.getcwd(), output)
	return os.path.normpath(output)

def same_file(a, b):
	"""Case-insensitive path identity; Windows also folds the separators."""
	return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

def build_audio_filter(channels, sample_rate, start, end, video_duration, loop):
	"""The filter graph that produces the single stereo track `[aout]`.

	Three steps, in order: trim the requested window out of the source, fold it
	down to stereo (front pair, mono doubled), then loop it if asked and pad or
	cut it to the video's length. `apad` adds silence only when the audio is
	short, and the closing `atrim` caps a long one, so the video always decides
	the length.
	"""
	# Mono is doubled into both sides; a stereo or surround source keeps its
	# first two channels (the front pair of a 5.1 layout).
	pan = "pan=stereo|c0=c0|c1=c0" if channels <= 1 else "pan=stereo|c0=c0|c1=c1"
	chain = "atrim=start={}:end={},asetpts=PTS-STARTPTS,{}".format(start, end, pan)
	if loop:
		# `aloop` repeats the trimmed window by sample count, so the seam lands
		# on a sample boundary instead of drifting like a repeated packet run.
		samples = max(1, int(round((end - start) * sample_rate)))
		chain += ",aloop=loop=-1:size={},asetpts=N/SR/TB".format(samples)
	chain += ",apad=whole_dur={},atrim=end={}[aout]".format(video_duration,
														   video_duration)
	return chain

def run_mux(video_path, audio_path, output, video, audio_info, options, cap):
	"""Run FFmpeg once; True when the output file was written."""
	video_duration = stream_duration(video, "video")
	channels = int(audio_info.get("channels") or 2)
	sample_rate = int(audio_info.get("sample_rate") or 44100)
	encoder, _label, extra = audio_encoder(os.path.splitext(output)[1])

	filter_graph = "[1:a]" + build_audio_filter(
		channels, sample_rate, options["start"], options["end"],
		video_duration, options["loop"])

	cmd = [FFMPEG_BIN, "-y", "-i", video_path, "-i", audio_path,
		   "-filter_complex", filter_graph,
		   "-map", "0:v:0", "-map", "[aout]",
		   "-c:v", "copy", "-c:a", encoder, *extra,
		   "-map_metadata", "0", "-map_chapters", "0",
		   # The video decides the length: the audio is already trimmed to it,
		   # and `-shortest` keeps a frame-accurate video tail from being padded.
		   "-shortest"]
	ext = os.path.splitext(output)[1].lower()
	if ext in FASTSTART_EXTS:
		cmd += ["-movflags", "+faststart"]
	cmd.append(output)

	print(tui.status("info", "Running FFmpeg for {}...".format(
		os.path.basename(output)), cap=cap))
	result = subprocess.run(cmd, capture_output=True, text=True)
	if result.returncode != 0:
		print(tui.status("error", "{}: {}".format(
			os.path.basename(output),
			_error_tail(result.stderr, "FFmpeg exited with status {}".format(
				result.returncode))), cap=cap))
		return False
	return True

def describe(key, value, cap, width=12):
	"""One `key<TAB>value` row of the settings panel."""
	return tui.field(key, value, width=width, cap=cap)

def collect_options(args, audio_duration, video, cap):
	"""Validate the run and return the filter inputs, or None after an error.

	Everything that can be refused before FFmpeg runs is refused here, so a bad
	flag never reaches a half-written output file.
	"""
	if not all(math.isfinite(value) for value in (args.cutstart, args.cutend)):
		print(tui.status("error", "Cut values must be finite seconds.", cap=cap))
		return None
	if args.cutstart < 0 or args.cutend < 0:
		print(tui.status("error", "Cut values must be zero or positive seconds.",
						 cap=cap))
		return None

	start = args.cutstart
	end = audio_duration - args.cutend
	if start >= audio_duration:
		print(tui.status("error",
						 "Cut start {:.2f}s is past the end of the audio ({:.2f}s)."
						 .format(start, audio_duration), cap=cap))
		return None
	if end - start <= 0.01:
		print(tui.status("error",
						 "The cut leaves no audio: {:.2f}s source minus {:.2f}s "
						 "from the start and {:.2f}s from the end.".format(
							 audio_duration, start, args.cutend), cap=cap))
		return None

	video_duration = stream_duration(video, "video")
	if video_duration is None:
		print(tui.status("error", "Could not read the video duration.",
						 cap=cap))
		return None

	window = end - start
	if window < video_duration and not args.loop:
		print(tui.status("warn",
						 "Audio is {:.2f}s shorter than the video ({:.2f}s): the "
						 "tail is padded with silence.".format(
							 window, video_duration), cap=cap))
	if args.loop and window >= video_duration:
		print(tui.status("info", "Audio is not shorter than the video: "
						 "--loop has nothing to repeat.", cap=cap))

	return {"start": start, "end": end, "loop": bool(args.loop)}

def main(argv=None):
	tui.init_ansi()
	parser = argparse.ArgumentParser(
		prog="videomux",
		description="Combine a video with an audio file, discarding the video's audio.")
	parser.add_argument("video", help="Input video file")
	parser.add_argument("audio", help="Input audio file")
	parser.add_argument("-s", "--cutstart", type=float, default=0.0,
						help="Cut off the start of the audio (seconds)")
	parser.add_argument("-e", "--cutend", type=float, default=0.0,
						help="Cut off the end of the audio (seconds)")
	parser.add_argument("-l", "--loop", action="store_true",
						help="Loop the audio when it is shorter than the video")
	group = parser.add_mutually_exclusive_group()
	group.add_argument("-o", "--output", help="Output filename")
	group.add_argument("-x", "--suffix",
					   help="Custom suffix instead of _<audiocodec>")

	args = parser.parse_args(argv)
	# Capabilities are resolved once: one colour level, unicode decision and
	# plain/tty mode for the whole run.
	cap = tui.detect()

	# Preflight: the binaries first, then the two inputs, so a missing tool is
	# never reported as a missing file.
	missing = [name for name, binary in (("ffmpeg", FFMPEG_BIN),
										 ("ffprobe", FFPROBE_BIN))
			   if not check_bin(binary)]
	if missing:
		print(tui.status("error", "{} not installed or not found. Place the "
						 "binary in the script folder or add it to PATH."
						 .format(" and ".join(missing)), cap=cap))
		return 1

	for label, path in (("Video", args.video), ("Audio", args.audio)):
		if not os.path.exists(path):
			print(tui.status("error", "{} file not found: {}".format(label, path),
							 cap=cap))
			return 1
		if not os.path.isfile(path):
			print(tui.status("error", "{} is not a file: {}".format(label, path),
							 cap=cap))
			return 1

	video = probe(args.video)
	if video is None:
		print(tui.status("error", "Could not read the video file: {}".format(
			args.video), cap=cap))
		return 1
	video_info = first_stream(video, "video")
	if video_info is None:
		print(tui.status("error", "No video stream in {}.".format(args.video),
						 cap=cap))
		return 1

	audio = probe(args.audio)
	if audio is None:
		print(tui.status("error", "Could not read the audio file: {}".format(
			args.audio), cap=cap))
		return 1
	audio_info = first_stream(audio, "audio")
	if audio_info is None:
		print(tui.status("error", "No audio stream in {}.".format(args.audio),
						 cap=cap))
		return 1

	audio_duration = stream_duration(audio, "audio")
	if audio_duration is None:
		print(tui.status("error", "Could not read the audio duration.",
						 cap=cap))
		return 1

	# The output name is fixed before validation so the settings panel can show
	# the real target, and so an input can never be overwritten in place.
	output = (resolve_output(args.output, args.video)
			  if args.output else default_output(args.video, args.suffix))
	if same_file(output, args.video) or same_file(output, args.audio):
		print(tui.status("error",
						 "Output {} would overwrite an input file.".format(output),
						 cap=cap))
		return 1

	options = collect_options(args, audio_duration, video, cap)
	if options is None:
		return 1

	encoder = audio_encoder(os.path.splitext(output)[1])[1]
	video_duration = stream_duration(video, "video")
	print()
	print(tui.header("VIDEO MUX", "video copied, one stereo audio track", cap=cap))
	print()
	print(tui.panel("MUX SETTINGS", [
		describe("Video", os.path.basename(args.video), cap),
		describe("Audio", os.path.basename(args.audio), cap),
		describe("Cut", "start {:.2f}s / end {:.2f}s".format(
			args.cutstart, args.cutend), cap),
		describe("Loop", "yes" if args.loop else "no", cap),
		describe("Audio Track", "{} -> stereo, {}".format(
			audio_info.get("codec_name", "unknown"), encoder), cap),
		describe("Length", "video {:.2f}s".format(video_duration), cap),
		describe("Output", os.path.basename(output), cap),
	], cap=cap))
	print()

	# A single mux is one job, but it still opens the shared box so the run
	# reads exactly like the other video tools.
	box = tui.progress.BatchBox("Muxing 1 output", 1, cap=cap)
	box.update(op="Muxing audio into {}".format(os.path.basename(output)), done=0)
	gate = tui.OverwriteGate(cap=cap, box=box)
	if os.path.exists(output):
		action, effective = gate.decide(output)
		if action == "abort":
			box.add("warn", "Aborted on {}".format(os.path.basename(output)))
			box.update(done=1)
			box.close("Aborted: 0/1 output written")
			return 1
		if action == "skip":
			box.add("warn", "Skipped {}: output exists".format(
				os.path.basename(output)))
			box.update(done=1)
			box.close("Batch finished: 0/1 output written")
			return 0
		if action == "rename":
			output = tui.overwrite.settle(output, effective)
			box.update(op="Muxing audio into {}".format(
				os.path.basename(output)), done=0)

	ok = run_mux(args.video, args.audio, output, video, audio_info, options, cap)
	box.update(done=1)
	if not ok:
		box.add("error", "FFmpeg failed for {}".format(os.path.basename(output)))
		box.close("Failed: 0/1 output written")
		return 1

	box.add("ok", "Combined clip saved as {}".format(output))
	box.close("Batch finished: 1/1 output written")
	return 0

if __name__ == "__main__":
	sys.exit(main())
