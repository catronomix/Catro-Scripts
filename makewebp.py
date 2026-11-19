# Build an animated WebP from a folder's images
"""
			MAKEWEBP
			--------
This script turns the images in a folder into one animated .webp file: every
matching image is a frame, in the chosen sort order, and the result is saved
one level up, next to the folder, carrying the folder's name.

Encoding is delegated to ffmpeg (libwebp). The frames are described by a
concat list - one entry per image, each with the frame duration - and ffmpeg
probes that list for the common canvas (largest width x largest height) and
then encodes the animation in a second pass. Frames keep their exact pixels:
they are never resized or cropped, only centred on the canvas, which is
transparent by default and filled with the -o colour when asked.

USAGE:
	python makewebp.py                     # current folder -> ../<cwd>.webp
	python makewebp.py -d ./frames         # ./frames -> ./frames.webp
	python makewebp.py -d ./frames -e png  # only PNGs in ./frames
	python makewebp.py -w "shot*" -s alphanum_asc --duration 80
	python makewebp.py -q 80               # lossy quality
	python makewebp.py --lossless          # lossless WebP
	python makewebp.py -o "#101010"        # flatten transparency onto a colour
	python makewebp.py -m "#00FF00"        # key that colour out of every frame

OPTIONS:
	-d, --dir PATH       Input folder (default: current directory). The
	                     output is written one level up, beside the folder.
	-e, --ext EXT        Only images with this extension ("png" or ".png").
	-w, --wildcard STR   Only names matching this fnmatch pattern ("shot*").
	-s, --sort METHOD    Frame order, same methods as `renamer` (default:
	                     name_asc): name_asc, name_desc, date_asc, date_desc,
	                     cdate_asc, cdate_desc, alphanum_asc, alphanum_desc,
	                     winname_asc, winname_desc.
	-o, --opaque HEX     Composite every frame onto this #RRGGBB colour and
	                     drop alpha.
	-m, --matte HEX      Treat this #RRGGBB colour as transparent per frame.
	-q, --quality NN     Lossy quality 1-100 (default 90).
	--lossless           Lossless WebP; mutually exclusive with -q.
	--duration N         Milliseconds per frame (default 100).
	--loop N             Animation loops (default 0 = forever).

OUTPUT:
	<parent of the input folder>/<folder name>.webp. So `-d ./frames` writes
	./frames.webp, and the default (`-d .`) writes ../<current folder>.webp.
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


def collect_images(folder, ext=None, wildcard=None, method="name_asc"):
	"""Return the matching image names, in the renamer's sort order.

	The filter is the renamer's own IMAGE_EXTENSIONS tuple and its sort_files()
	helper, so `-s` means exactly what it means in `renamer` and the two
	scripts cannot drift apart. The list order is the frame order.
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
		if not name.lower().endswith(renamer.IMAGE_EXTENSIONS):
			continue
		names.append(name)
	return renamer.sort_files(folder, names, method)


def concat_quote(path):
	"""Render one absolute path for a concat list's `file '...'` line.

	The demuxer wants forward slashes and a literal ' written as '\\''.
	"""
	return os.path.abspath(path).replace("\\", "/").replace("'", "'\\''")


def write_concat_list(paths, duration_ms):
	"""Write the frames as a concat list and return its temporary path.

	One block per frame: the file line names the image, the duration line is
	the time it stays on screen. ffmpeg reads the list in this order, so the
	list order is the frame order and every frame carries --duration.
	"""
	handle = tempfile.NamedTemporaryFile(
		mode="w", suffix=".txt", prefix="makewebp-", delete=False,
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


def encode_command(listing, args, width, height, destination):
	"""Build the second pass: encode the concat list as an animated WebP.

	`-r` before the input pins the source frame rate to the requested frame
	duration and `-fps_mode vfr` keeps it, otherwise ffmpeg snaps every frame
	to 25 fps and 100 ms becomes 120 ms. `-loop` and `-f webp` are muxer
	options, so they must sit with the output.
	"""
	command = [FFMPEG_BIN, "-y", "-loglevel", "error", "-nostdin",
			   "-r", "1000/{}".format(args.duration),
			   "-f", "concat", "-safe", "0", "-i", listing,
			   "-fps_mode", "vfr"]
	if args.opaque is not None:
		command += ["-filter_complex",
					opaque_filter(width, height, args.opaque),
					"-map", "[v]"]
	else:
		command += ["-vf", video_filter(width, height, args.matte)]
	command += ["-c:v", ENCODER]
	if args.lossless:
		command += ["-lossless", "1"]
	else:
		command += ["-quality", str(args.quality)]
	command += ["-loop", str(args.loop), "-f", "webp", destination]
	return command


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


def make_animation(args, cap):
	"""Run one makewebp conversion and print the page."""
	folder = os.path.abspath(args.dir)

	print()
	print(tui.header("Make WebP", "Animate a folder's images into one .webp file",
					 cap=cap))
	if not os.path.isdir(folder):
		print(tui.status("error", "Not a directory: {}".format(folder), cap=cap))
		return 1
	display = folder

	ext = normalise_ext(args.ext)
	names = collect_images(folder, ext=ext, wildcard=args.wildcard,
						   method=args.sort)
	# One level up from the input folder, named after that folder: the animation
	# sits beside the frames it was built from, not in whatever cwd the shell
	# happened to be in.
	parent = os.path.dirname(folder)
	output_name = os.path.basename(os.path.normpath(folder)) or "animation"
	output = os.path.join(parent, output_name + ".webp")

	# One aligned block: what was read, where it goes, and how it was encoded.
	background = args.opaque
	matte = args.matte
	mode = "lossless" if args.lossless else "lossy q{}".format(args.quality)
	if matte is not None:
		mode += ", matte {}".format(hex_colour(matte))
	elif background is not None:
		mode += ", opaque {}".format(hex_colour(background))
	filters = []
	if ext:
		filters.append("ext {}".format(ext))
	if args.wildcard:
		filters.append("wildcard {!r}".format(args.wildcard))
	print(tui.field("Input", display, width=8, cap=cap))
	print(tui.field("Filter", ", ".join(filters) or "all images", width=8, cap=cap))
	print(tui.field("Sort", args.sort, width=8, cap=cap))
	print(tui.field("Output", output, width=8, cap=cap))
	print(tui.field("Encoding", mode, width=8, cap=cap))
	print(tui.field("Timing", "{} ms/frame, loop {}".format(
		args.duration, args.loop), width=8, cap=cap))
	print()

	if not names:
		print(tui.status("warn", "No matching images found; nothing written.",
						 cap=cap))
		return 1

	paths = [os.path.join(folder, name) for name in names]
	print(tui.status("info", "Building {} frame(s)".format(len(paths)), cap=cap))

	listing = write_concat_list(paths, args.duration)
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

		done = subprocess.run(
			encode_command(listing, args, width, height, part),
			stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE)
		if done.returncode != 0 or not os.path.isfile(part):
			for line in error_tail(done.stderr.decode("utf-8", "replace")):
				print(tui.status("error", line, cap=cap))
			print(tui.status("error", "ffmpeg could not encode the animation; "
									 "nothing written.", cap=cap))
			return 1
		# ffmpeg always emits blend=over, which stacks every full-canvas frame
		# onto the previous ones wherever it is transparent. Patch the frames
		# in the part file, then rename it, so the output is never half written.
		with open(part, "rb") as handle:
			frames = force_no_blend(handle.read())
		with open(part, "wb") as handle:
			handle.write(frames)
		os.replace(part, output)
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


def main():
	# parse_args() first so --help works without ffmpeg or a terminal.
	parser = argparse.ArgumentParser(
		description="Animate a folder's images into one .webp file named after "
					"the folder, saved one level up beside that folder.")
	parser.add_argument("-d", "--dir", default=".",
						help="Input folder (default: current directory); the "
							 "output is written one level up as <folder>.webp")
	parser.add_argument("-e", "--ext",
						help="Only images with this extension")
	parser.add_argument("-w", "--wildcard",
						help="Only names matching this fnmatch pattern")
	parser.add_argument("-s", "--sort", default="name_asc",
						choices=renamer.SORT_METHODS,
						help="Frame order (default: name_asc)")
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
	parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
						metavar="N",
						help="Milliseconds per frame (default: {})".format(
							DEFAULT_DURATION))
	parser.add_argument("--loop", type=int, default=DEFAULT_LOOP, metavar="N",
						help="Animation loops, 0 = forever (default: {})".format(
							DEFAULT_LOOP))
	args = parser.parse_args()

	if not args.lossless and not 1 <= args.quality <= 100:
		parser.error("-q/--quality must be between 1 and 100")
	if args.duration < 1:
		parser.error("--duration must be at least 1 ms")
	if args.loop < 0:
		parser.error("--loop cannot be negative")
	if args.loop > 65535:
		parser.error("--loop cannot exceed 65535")

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
