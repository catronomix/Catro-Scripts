# Build an animated WebP from a folder's images or from a video
"""
			WEBP
			----
This script turns the images in a folder into one animated .webp file: every
matching image is a frame, in the chosen sort order, and the result is saved
one level up, next to the folder, carrying the folder's name. It can also
convert a video: either one named file, or every video in a folder as a batch
(one .webp per video, written beside its source).

Encoding is delegated to ffmpeg (libwebp). For images the frames are described
by a concat list - one entry per image, each with the frame duration - and
ffmpeg probes that list for the common canvas (largest width x largest height)
and then encodes the animation in a second pass. Frames keep their exact
pixels: they are never resized or cropped, only centred on the canvas, which
is transparent by default and filled with the -o colour when asked.

A video already has its own frame timing, so it is encoded in one pass and
keeps the source frame rate unless --fps asks for a different one.

USAGE:
	python webp.py                     # current folder -> ../<cwd>.webp
	python webp.py -d ./frames         # ./frames -> ./frames.webp
	python webp.py -d ./frames -e png  # only PNGs in ./frames
	python webp.py -w "shot*" -s alphanum_asc --duration 80
	python webp.py --fps 24            # 24 fps = 42 ms per frame
	python webp.py -q 80               # lossy quality
	python webp.py --lossless          # lossless WebP
	python webp.py -o "#101010"        # flatten transparency onto a colour
	python webp.py -m "#00FF00"        # key that colour out of every frame
	python webp.py -v clip.mp4         # one video -> clip.webp
	python webp.py -v                  # every video in the current folder
	python webp.py -v -d ./clips -e mp4 # every MP4 in ./clips

OPTIONS:
	-d, --dir PATH       Input folder (default: current directory). For images
	                     the output is written one level up, beside the folder;
	                     for a video batch it is the folder that is scanned.
	-e, --ext EXT        Only images/videos with this extension ("png"/".png").
	-w, --wildcard STR   Only names matching this fnmatch pattern ("shot*").
	-s, --sort METHOD    Image frame order, same methods as `renamer` (default:
	                     name_asc): name_asc, name_desc, date_asc, date_desc,
	                     cdate_asc, cdate_desc, alphanum_asc, alphanum_desc,
	                     winname_asc, winname_desc.
	-v, --video [FILE]   Convert a video instead of an image folder. With a
	                     filename only that file is converted; without one,
	                     every video in -d (default: the current folder) is
	                     converted to its own .webp, filtered by -e and -w.
	                     Videos keep their source frame rate by default and
	                     cannot be combined with -s, --duration or (for a
	                     named file) -d.
	-o, --opaque HEX     Composite every frame onto this #RRGGBB colour and
	                     drop alpha.
	-m, --matte HEX      Treat this #RRGGBB colour as transparent per frame.
	-q, --quality NN     Lossy quality 1-100 (default 90).
	--lossless           Lossless WebP; mutually exclusive with -q.
	--duration N         Milliseconds per frame for images (default 100).
	--fps F              Frames per second; the image frame duration becomes
	                     1000/F ms. Mutually exclusive with --duration. For a
	                     video it resamples the output instead of keeping the
	                     source rate.
	--loop N             Animation loops (default 0 = forever).

OUTPUT:
	Images: <parent of the input folder>/<folder name>.webp. So `-d ./frames`
	writes ./frames.webp, and the default (`-d .`) writes
	../<current folder>.webp.
	Videos: <source name>.webp beside the video, so `-v clip.mp4` writes
	./clip.webp and a batch writes one next to every converted video.
	An existing file is overwritten. The encode goes to a temporary
	"<output>.part.webp" that is renamed onto the real name only once ffmpeg
	succeeds, so a failed run never leaves an empty file behind.

REQUIREMENTS:
	- ffmpeg (the repository's ffmpeg.exe, or one on PATH). libwebp is used
	  for the encode; no Python imaging library is needed.
"""

import argparse
import fnmatch
import os
import platform
import re
import subprocess
import sys
import tempfile

import tui
import renamer

DEFAULT_QUALITY = 90
DEFAULT_DURATION = 100
DEFAULT_LOOP = 0

# ffmpeg's WebP encoder: libwebp also writes animations, there is no separate
# libwebp_anim encoder in current builds.
ENCODER = "libwebp"

# One "s:WxH" per frame on showinfo's stderr lines; the set of sizes gives the
# canvas the animation needs.
SHOWINFO_SIZE = re.compile(r"\bs:(\d+)x(\d+)\b")


def get_bin_path(name):
	"""Returns the path to a binary, prioritizing the script's directory."""
	script_dir = os.path.dirname(os.path.abspath(__file__))
	local_path = os.path.join(script_dir, name)
	if platform.system().lower() == "windows" and not local_path.lower().endswith(".exe"):
		local_path += ".exe"
	if os.path.exists(local_path) and os.access(local_path, os.X_OK):
		return local_path
	return name


FFMPEG_BIN = get_bin_path("ffmpeg")


def check_ffmpeg():
	"""Checks if ffmpeg is available in the system path or program dir."""
	try:
		subprocess.run([FFMPEG_BIN, "-version"], stdout=subprocess.DEVNULL,
					   stderr=subprocess.DEVNULL)
		return True
	except FileNotFoundError:
		return False


def get_ffmpeg_instructions(cap):
	return (
		"\n" + tui.status("warn", "FFmpeg is missing or not found.", cap=cap) + "\n"
		"Place ffmpeg (ffmpeg.exe) in the script folder or add it to PATH.\n"
	)


def parse_hex_colour(value):
	"""Parse "#RRGGBB" into an (r, g, b) tuple for argparse."""
	text = value.lstrip("#")
	if len(text) != 6:
		raise argparse.ArgumentTypeError(
			"expected #RRGGBB, got {!r}".format(value))
	try:
		return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
	except ValueError:
		raise argparse.ArgumentTypeError(
			"expected #RRGGBB, got {!r}".format(value))


def hex_colour(colour):
	"""Render an (r, g, b) tuple back as #RRGGBB for the page."""
	return "#{:02X}{:02X}{:02X}".format(*colour)


def normalise_ext(value):
	"""Accept "png" and ".png" as the same filter."""
	if not value:
		return None
	value = value.lower()
	return value if value.startswith(".") else "." + value


def collect_media(folder, extensions, ext=None, wildcard=None,
				  method="name_asc"):
	"""Return the matching file names, in the renamer's sort order.

	The extension filter is the renamer's own IMAGE_EXTENSIONS /
	VIDEO_EXTENSIONS tuple and its sort_files() helper, so `-s` means exactly
	what it means in `renamer` and the two scripts cannot drift apart. The
	list order is the frame order.
	"""
	names = []
	for name in os.listdir(folder):
		path = os.path.join(folder, name)
		if not os.path.isfile(path):
			continue
		if ext and not name.lower().endswith(ext):
			continue
		if wildcard and not fnmatch.fnmatch(name, wildcard):
			continue
		if not name.lower().endswith(extensions):
			continue
		names.append(name)
	return renamer.sort_files(folder, names, method)


def collect_images(folder, ext=None, wildcard=None, method="name_asc"):
	"""The matching image names, in the renamer's sort order."""
	return collect_media(folder, renamer.IMAGE_EXTENSIONS, ext=ext,
						 wildcard=wildcard, method=method)


def collect_videos(folder, ext=None, wildcard=None):
	"""The matching video names; batch order is always plain name order."""
	return collect_media(folder, renamer.VIDEO_EXTENSIONS, ext=ext,
						 wildcard=wildcard, method="name_asc")


def resolve_duration(args):
	"""Frame duration in milliseconds: explicit, from --fps, or the default.

	--fps and --duration are mutually exclusive at the parser, so at most one
	of them is set. Rounding keeps whole milliseconds, and a very high frame
	rate still gets the minimum of 1 ms that WebP can store.
	"""
	if args.fps is not None:
		return max(1, round(1000.0 / args.fps))
	if args.duration is not None:
		return args.duration
	return DEFAULT_DURATION


def concat_quote(path):
	"""Render one absolute path for a concat list's `file '...'` line.

	The demuxer wants forward slashes and a literal ' written as '\\''.
	"""
	return os.path.abspath(path).replace("\\", "/").replace("'", "'\\''")


def write_concat_list(paths, duration_ms):
	"""Write the frames as a concat list and return its temporary path.

	One block per frame: the file line names the image, the duration line is
	the time it stays on screen. ffmpeg reads the list in this order, so the
	list order is the frame order and every frame carries the duration.
	"""
	handle = tempfile.NamedTemporaryFile(
		mode="w", suffix=".txt", prefix="webp-", delete=False,
		encoding="utf-8", newline="\n")
	try:
		for path in paths:
			handle.write("file '{}'\n".format(concat_quote(path)))
			handle.write("duration {}\n".format(duration_ms / 1000))
	finally:
		handle.close()
	return handle.name


def probe_canvas(listing, expected):
	"""Measure the common canvas and count the frames ffmpeg can decode.

	Pass one decodes every frame through `showinfo` into the null muxer. The
	null muxer reports failure even on success, so only the sizes and the
	frame count matter: at least one "s:WxH" line and exactly one line per
	list entry. The canvas is the largest width by the largest height, since
	WebP frames must all share a size.
	"""
	command = [FFMPEG_BIN, "-hide_banner", "-nostdin", "-f", "concat",
			   "-safe", "0", "-i", listing, "-vf", "showinfo",
			   "-f", "null", "-"]
	done = subprocess.run(command, stdin=subprocess.DEVNULL,
						  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
	text = done.stderr.decode("utf-8", "replace")
	sizes = [(int(width), int(height))
			 for width, height in SHOWINFO_SIZE.findall(text)]
	if not sizes or len(sizes) != expected:
		return None, text
	return (max(width for width, _ in sizes),
			max(height for _, height in sizes)), text


def matte_filter(colour):
	"""Zero the alpha of pixels whose RGB is exactly `colour`.

	Each channel contributes an equality test, the three are multiplied into
	one mask, and the mask picks 0 alpha where it matches while leaving the
	source's own alpha untouched elsewhere. A colorkey filter would throw the
	source alpha away, hence geq.
	"""
	red, green, blue = colour
	return (
		"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
		"a='if(eq(r(X,Y),{red})*eq(g(X,Y),{green})*eq(b(X,Y),{blue}),"
		"0,alpha(X,Y))'"
	).format(red=red, green=green, blue=blue)


def video_filter(width, height, matte=None):
	"""The plain -vf chain: optional matte key, then centred padding."""
	pad = "pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=0x00000000".format(width, height)
	if matte is not None:
		return "{},{},format=rgba".format(matte_filter(matte), pad)
	return "{},format=rgba".format(pad)


def opaque_filter(width, height, colour):
	"""The -filter_complex graph that flattens every frame onto a colour.

	Both branches are split from the same input, so they share timestamps and
	frame count; an independent colour source makes framesync emit an extra,
	out-of-order frame. The background branch pads the frame with the colour
	and then paints the whole canvas with it, so it is a plain colour plate
	rather than a copy of the frame; the foreground branch keeps the frame's
	own alpha, and overlay blends the two.
	"""
	red, green, blue = colour
	tint = "{:02X}{:02X}{:02X}".format(red, green, blue)
	return (
		"[0:v]split=2[fg][bg];"
		"[fg]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
		"format=rgba[fgr];"
		"[bg]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x{tint},"
		"drawbox=x=0:y=0:w=iw:h=ih:color=0x{tint}@1:t=fill,format=rgb24[bgr];"
		"[bgr][fgr]overlay=shortest=1,format=rgb24[v]"
	).format(width=width, height=height, tint=tint)


def video_opaque_filter(colour, fps=None):
	"""Flatten a video onto a colour without measuring it first.

	A video's frames already share one size, so no padding is needed: the
	background branch paints a plate at the input's own width/height and the
	foreground branch keeps its alpha, and overlay blends the two. An optional
	fps filter runs before the split so both branches see the same timestamps.
	"""
	red, green, blue = colour
	tint = "{:02X}{:02X}{:02X}".format(red, green, blue)
	resample = "fps={:g},".format(fps) if fps is not None else ""
	return (
		"[0:v]{resample}split=2[fg][bg];"
		"[bg]drawbox=x=0:y=0:w=iw:h=ih:color=0x{tint}@1:t=fill,format=rgb24[bgr];"
		"[bgr][fg]overlay=shortest=1,format=rgb24[v]"
	).format(resample=resample, tint=tint)


def video_chain(args, fps):
	"""The -vf chain for a video: optional resample, then the matte key."""
	chain = []
	if fps is not None:
		chain.append("fps={:g}".format(fps))
	if args.matte is not None:
		chain.append(matte_filter(args.matte))
	return ",".join(chain)


def encoder_options(args):
	"""The codec/muxer options shared by the image and video passes."""
	options = ["-c:v", ENCODER]
	if args.lossless:
		options += ["-lossless", "1"]
	else:
		options += ["-quality", str(args.quality)]
	return options + ["-loop", str(args.loop), "-f", "webp"]


def encode_command(listing, args, duration, width, height, destination):
	"""Build the second pass: encode the concat list as an animated WebP.

	`-r` before the input pins the source frame rate to the requested frame
	duration and `-fps_mode vfr` keeps it, otherwise ffmpeg snaps every frame
	to 25 fps and 100 ms becomes 120 ms. `-loop` and `-f webp` are muxer
	options, so they must sit with the output.
	"""
	command = [FFMPEG_BIN, "-y", "-loglevel", "error", "-nostdin",
			   "-r", "1000/{}".format(duration),
			   "-f", "concat", "-safe", "0", "-i", listing,
			   "-fps_mode", "vfr"]
	if args.opaque is not None:
		command += ["-filter_complex",
					opaque_filter(width, height, args.opaque),
					"-map", "[v]"]
	else:
		command += ["-vf", video_filter(width, height, args.matte)]
	return command + encoder_options(args) + [destination]


def video_encode_command(source, args, fps, destination):
	"""Build the one-pass video encode.

	Without --fps the source timing is passed through unchanged (`-fps_mode
	vfr` keeps the original frame intervals instead of snapping them to a
	guessed constant rate). With --fps the `fps` filter resamples to that rate;
	`-r` is avoided because it duplicates frames at the tail.
	"""
	command = [FFMPEG_BIN, "-y", "-loglevel", "error", "-nostdin",
			   "-i", source]
	if args.opaque is not None:
		command += ["-filter_complex",
					video_opaque_filter(args.opaque, fps), "-map", "[v]"]
	else:
		chain = video_chain(args, fps)
		if chain:
			command += ["-vf", chain]
	if fps is None:
		command += ["-fps_mode", "vfr"]
	return command + encoder_options(args) + [destination]


ERROR_HINTS = ("error", "invalid", "could not", "failed", "cannot",
			   "unable", "no such file")


def force_no_blend(data):
	"""Set the "do not blend" flag on every top-level ANMF frame.

	ffmpeg's WebP muxer writes every frame with flags 0, i.e. dispose=NONE and
	blend=over. Each frame is the full canvas, so with alpha the transparent
	areas let the previous frames show through and the animation accumulates
	instead of replacing. Bit 0x02 is "do not blend": the frame replaces the
	canvas. Dispose (bit 0) is left alone.

	Only the top-level chunk list is walked - ANMF payloads hold nested image
	chunks that must not be touched. A file that is not RIFF/WEBP, or has no
	ANMF frame (a still image), is returned unchanged.
	"""
	if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
		return data
	patched = bytearray(data)
	position = 12
	while position + 8 <= len(patched):
		fourcc = bytes(patched[position:position + 4])
		size = int.from_bytes(patched[position + 4:position + 8], "little")
		payload = position + 8
		end = payload + size
		if end > len(patched):
			break
		# The flags byte is the 16th byte of an ANMF payload, after the
		# three-byte XYWH fields, the frame duration and the reserved byte.
		if fourcc == b"ANMF" and size > 15:
			patched[payload + 15] |= 0x02
		position = end + (size & 1)
	return bytes(patched)


def error_tail(text, limit=3):
	"""The most telling stderr lines, for a failed run's status block.

	ffmpeg buries the reason among filter chatter, so lines that look like
	errors win over the raw tail; if none look like errors the tail is used.
	"""
	lines = [line.strip() for line in text.splitlines() if line.strip()]
	interesting = [line for line in lines
				   if any(hint in line.lower() for hint in ERROR_HINTS)]
	return (interesting or lines)[-limit:]


def format_size(size):
	"""Human-readable byte count for the closing status line."""
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024 or unit == "GB":
			return "{:.2f} {}".format(size, unit) if unit != "B" else "{} B".format(size)
		size /= 1024.0


def finish_animation(part, output):
	"""Patch the frames in the part file, then rename it into place.

	ffmpeg always emits blend=over, which stacks every full-canvas frame onto
	the previous ones wherever it is transparent. Patching the part file
	before the rename means the real output is never half written.
	"""
	with open(part, "rb") as handle:
		frames = force_no_blend(handle.read())
	with open(part, "wb") as handle:
		handle.write(frames)
	os.replace(part, output)


def encode_file(command, part, output):
	"""Run one ffmpeg encode and land it on `output`; return stderr text or None."""
	done = subprocess.run(command, stdin=subprocess.DEVNULL,
						  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
	if done.returncode != 0 or not os.path.isfile(part):
		return done.stderr.decode("utf-8", "replace")
	finish_animation(part, output)
	return None


def filters_text(ext, wildcard):
	"""The filter line shared by both input modes."""
	filters = []
	if ext:
		filters.append("ext {}".format(ext))
	if wildcard:
		filters.append("wildcard {!r}".format(wildcard))
	return ", ".join(filters) or "all files"


def mode_text(args):
	"""Lossy/lossless plus whichever colour filter is active."""
	mode = "lossless" if args.lossless else "lossy q{}".format(args.quality)
	if args.matte is not None:
		mode += ", matte {}".format(hex_colour(args.matte))
	elif args.opaque is not None:
		mode += ", opaque {}".format(hex_colour(args.opaque))
	return mode


def make_frames(args, cap, folder, ext):
	"""Image mode: one animation from the folder's frames."""
	display = folder
	names = collect_images(folder, ext=ext, wildcard=args.wildcard,
						   method=args.sort or "name_asc")
	# One level up from the input folder, named after that folder: the animation
	# sits beside the frames it was built from, not in whatever cwd the shell
	# happened to be in.
	parent = os.path.dirname(folder)
	output_name = os.path.basename(os.path.normpath(folder)) or "animation"
	output = os.path.join(parent, output_name + ".webp")
	duration = resolve_duration(args)

	# One aligned block: what was read, where it goes, and how it was encoded.
	print(tui.field("Input", display, width=8, cap=cap))
	print(tui.field("Filter", filters_text(ext, args.wildcard), width=8,
					cap=cap))
	print(tui.field("Sort", args.sort or "name_asc", width=8, cap=cap))
	print(tui.field("Output", output, width=8, cap=cap))
	print(tui.field("Encoding", mode_text(args), width=8, cap=cap))
	print(tui.field("Timing", "{} ms/frame, loop {}".format(
		duration, args.loop), width=8, cap=cap))
	print()

	if not names:
		print(tui.status("warn", "No matching images found; nothing written.",
						 cap=cap))
		return 1

	paths = [os.path.join(folder, name) for name in names]
	print(tui.status("info", "Building {} frame(s)".format(len(paths)), cap=cap))

	listing = write_concat_list(paths, duration)
	part = output + ".part.webp"
	try:
		canvas, text = probe_canvas(listing, len(paths))
		if canvas is None:
			for line in error_tail(text):
				print(tui.status("error", line, cap=cap))
			print(tui.status("error", "Could not read the frames; nothing "
									 "written.", cap=cap))
			return 1
		width, height = canvas

		failure = encode_file(
			encode_command(listing, args, duration, width, height, part),
			part, output)
		if failure is not None:
			for line in error_tail(failure):
				print(tui.status("error", line, cap=cap))
			print(tui.status("error", "ffmpeg could not encode the animation; "
									 "nothing written.", cap=cap))
			return 1
	finally:
		# The part file never survives: on success it has been renamed away, on
		# any failure it is deleted, so no empty .webp is ever left behind.
		if os.path.exists(listing):
			os.unlink(listing)
		if os.path.exists(part):
			os.unlink(part)

	size = format_size(os.path.getsize(output))
	print(tui.status("ok", "{} x {} px canvas, {} frame(s)".format(
		width, height, len(paths)), cap=cap))
	print(tui.status_panel([("ok", "Saved {} ({})".format(output, size))],
						   cap=cap))
	return 0


def convert_video(path, args, cap, fps):
	"""Image mode's counterpart for one video; returns True on success."""
	stem = os.path.splitext(path)[0]
	output = stem + ".webp"
	part = output + ".part.webp"
	try:
		failure = encode_file(
			video_encode_command(path, args, fps, part), part, output)
		if failure is not None:
			for line in error_tail(failure):
				print(tui.status("error", line, cap=cap))
			print(tui.status("error", "ffmpeg could not encode {}; nothing "
									 "written.".format(path), cap=cap))
			return False
	finally:
		if os.path.exists(part):
			os.unlink(part)
	size = format_size(os.path.getsize(output))
	print(tui.status("ok", "Saved {} ({})".format(output, size), cap=cap))
	return True


def make_videos(args, cap, folder, ext):
	"""Video mode: one named video, or every matching video in the folder."""
	if args.video:
		videos = [os.path.abspath(args.video)]
		if not os.path.isfile(videos[0]):
			print(tui.status("error", "Not a file: {}".format(videos[0]),
							 cap=cap))
			return 1
		input_display = videos[0]
		output_display = os.path.splitext(videos[0])[0] + ".webp"
	else:
		if not os.path.isdir(folder):
			print(tui.status("error", "Not a directory: {}".format(folder),
							 cap=cap))
			return 1
		names = collect_videos(folder, ext=ext, wildcard=args.wildcard)
		videos = [os.path.join(folder, name) for name in names]
		input_display = folder
		output_display = "<video>.webp beside each video"

	fps = args.fps
	timing = "source frame rate" if fps is None else "{:g} fps".format(fps)
	print(tui.field("Input", input_display, width=8, cap=cap))
	print(tui.field("Filter", filters_text(ext, args.wildcard), width=8,
					cap=cap))
	print(tui.field("Output", output_display, width=8, cap=cap))
	print(tui.field("Encoding", mode_text(args), width=8, cap=cap))
	print(tui.field("Timing", "{}, loop {}".format(timing, args.loop),
					width=8, cap=cap))
	print()

	if not videos:
		print(tui.status("warn", "No matching videos found; nothing written.",
						 cap=cap))
		return 1

	failed = 0
	for path in videos:
		print(tui.status("info", "Converting {}".format(os.path.basename(path)),
						 cap=cap))
		if not convert_video(path, args, cap, fps):
			failed += 1
	converted = len(videos) - failed
	if failed:
		print(tui.status("error", "{} of {} video(s) failed.".format(
			failed, len(videos)), cap=cap))
		if not converted:
			return 1
	print(tui.status_panel([("ok", "{} video(s) converted".format(converted))],
						   cap=cap))
	return 0


def make_animation(args, cap):
	"""Run one conversion run and print the page."""
	folder = os.path.abspath(args.dir or ".")
	video_mode = args.video is not None

	print()
	print(tui.header("WebP", "Animate a folder's images or convert a video"
							 " into WebP", cap=cap))
	if video_mode:
		return make_videos(args, cap, folder, normalise_ext(args.ext))
	if not os.path.isdir(folder):
		print(tui.status("error", "Not a directory: {}".format(folder), cap=cap))
		return 1
	return make_frames(args, cap, folder, normalise_ext(args.ext))


def build_parser():
	parser = argparse.ArgumentParser(
		description="Animate a folder's images into one .webp file named after "
					"the folder, saved one level up beside that folder, or "
					"convert a video (or every video in a folder) to .webp.")
	parser.add_argument("-d", "--dir", default=None,
						help="Input folder (default: current directory). Images "
							 "are written one level up as <folder>.webp; a "
							 "video batch is scanned here.")
	parser.add_argument("-e", "--ext",
						help="Only images/videos with this extension")
	parser.add_argument("-w", "--wildcard",
						help="Only names matching this fnmatch pattern")
	parser.add_argument("-s", "--sort", default=None,
						choices=renamer.SORT_METHODS,
						help="Image frame order (default: name_asc)")
	parser.add_argument("-v", "--video", nargs="?", const="", default=None,
						metavar="FILE",
						help="Convert this video, or every video in -d when no "
							 "file is given (default: keep the source frame "
							 "rate)")
	colour_filter = parser.add_mutually_exclusive_group()
	colour_filter.add_argument("-o", "--opaque", type=parse_hex_colour,
							   metavar="#RRGGBB",
							   help="Composite frames onto an opaque background")
	colour_filter.add_argument("-m", "--matte", type=parse_hex_colour,
							   metavar="#RRGGBB",
							   help="Treat this colour as transparent")
	encoding = parser.add_mutually_exclusive_group()
	encoding.add_argument("-q", "--quality", type=int, default=DEFAULT_QUALITY,
						  metavar="NN", help="Lossy quality 1-100 "
											 "(default: {})".format(DEFAULT_QUALITY))
	encoding.add_argument("--lossless", action="store_true",
						  help="Lossless WebP")
	timing = parser.add_mutually_exclusive_group()
	timing.add_argument("--duration", type=int, default=None, metavar="N",
						help="Milliseconds per image frame (default: {})".format(
							DEFAULT_DURATION))
	timing.add_argument("--fps", type=float, default=None, metavar="F",
						help="Frames per second; image duration becomes "
							 "1000/F ms, video output is resampled")
	parser.add_argument("--loop", type=int, default=DEFAULT_LOOP, metavar="N",
						help="Animation loops, 0 = forever (default: {})".format(
							DEFAULT_LOOP))
	return parser


def validate(parser, args):
	"""Cross-option rules argparse cannot express on its own."""
	# A named video is the whole input, so a folder and an image frame order
	# make no sense with it.
	if args.video:
		if args.dir is not None:
			parser.error("-d/--dir cannot be combined with a named -v/--video")
		if args.sort is not None:
			parser.error("-s/--sort cannot be combined with -v/--video")
		if args.ext or args.wildcard:
			parser.error("-e/--ext and -w/--wildcard are batch filters; they "
						 "cannot be combined with a named -v/--video")
	elif args.video is not None and args.sort is not None:
		parser.error("-s/--sort cannot be combined with -v/--video")
	if args.video is not None and args.duration is not None:
		parser.error("--duration cannot be combined with -v/--video; videos "
					 "keep their source frame rate (use --fps to resample)")
	if not args.lossless and not 1 <= args.quality <= 100:
		parser.error("-q/--quality must be between 1 and 100")
	if args.duration is not None and args.duration < 1:
		parser.error("--duration must be at least 1 ms")
	if args.fps is not None and not args.fps > 0:
		parser.error("--fps must be greater than 0")
	if args.loop < 0:
		parser.error("--loop cannot be negative")
	if args.loop > 65535:
		parser.error("--loop cannot exceed 65535")


def main():
	# parse_args() first so --help works without ffmpeg or a terminal.
	parser = build_parser()
	args = parser.parse_args()
	validate(parser, args)

	# Capabilities are resolved once: the whole run uses one colour level,
	# Unicode decision and plain/tty mode.
	tui.init_ansi()
	cap = tui.detect()

	# ffmpeg is only needed for an actual run.
	if not check_ffmpeg():
		print(get_ffmpeg_instructions(cap))
		return 1

	return make_animation(args, cap)


if __name__ == "__main__":
	try:
		sys.exit(main())
	except BrokenPipeError:
		sys.exit(0)
