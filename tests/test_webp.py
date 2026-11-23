# Regression tests for webp's ffmpeg-built animated output
"""
			WEBP TESTS
			==========
Pins the behaviour the script promises:

	- the input list is filtered by extension/wildcard and ordered by the
	  renamer's own sort_files() helper, so `-s` means the same thing in both
	  scripts and the list order is the frame order;
	- the output is one animated WebP written one level up, beside the input
	  folder and named after it, never in the caller's cwd;
	- every image is a frame, `--duration` round-trips exactly and `--loop`
	  reaches the file;
	- `--fps` turns into the matching frame duration (1000/F ms);
	- differently-sized frames are padded onto a common canvas instead of
	  being cropped;
	- `-o` flattens onto the given colour, `-m` knocks that colour out and
	  keeps the source alpha everywhere else;
	- with alpha every frame is isolated: ffmpeg's blend=over is patched to
	  "do not blend", so a transparent frame never shows earlier frames;
	- no `.part.webp` survives a run, successful or not;
	- `-v`/`--video` converts a named video, or every matching video in a
	  folder as a batch, to `<video>.webp` beside its source;
	- `-q` and `--lossless`, `--fps` and `--duration`, and video mode and the
	  image-only options cannot be combined.

Pillow is used here only to write fixtures and read results back; the script
itself shells out to ffmpeg. Tests skip when ffmpeg or Pillow is missing.

Run from the repo root:
	python -m unittest tests.test_webp -v
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import webp  # noqa: E402
import tui  # noqa: E402

try:
	from PIL import Image, ImageDraw
except ImportError:  # pillow is optional for the suite
	Image = None
	ImageDraw = None


def have_ffmpeg():
	"""True when the repo ffmpeg or a PATH ffmpeg can run."""
	if shutil.which("ffmpeg") is None and not os.path.isfile(webp.FFMPEG_BIN):
		return False
	return webp.check_ffmpeg()


FFMPEG = have_ffmpeg()
SKIP = (Image is None or not FFMPEG)


def cap16():
	return tui.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")


def options(**overrides):
	values = {"dir": ".", "ext": None, "wildcard": None, "sort": "name_asc",
			  "opaque": None, "matte": None, "quality": 90, "lossless": False,
			  "duration": 100, "fps": None, "loop": 0, "video": None}
	values.update(overrides)
	return argparse.Namespace(**values)


def save_image(path, size, colour):
	with Image.new("RGBA", size, colour) as img:
		img.save(path)


def chunks(data):
	"""Yield (fourcc, payload) for the top-level WebP chunks."""
	position = 12
	while position + 8 <= len(data):
		fourcc = data[position:position + 4]
		size = int.from_bytes(data[position + 4:position + 8], "little")
		yield fourcc, data[position + 8:position + 8 + size]
		position += 8 + size + (size & 1)


def anmf_flags(data):
	"""The flags byte of every top-level ANMF frame, in order."""
	return [payload[15] for fourcc, payload in chunks(data)
			if fourcc == b"ANMF"]


def synthetic_webp(flags=0x00):
	"""A minimal RIFF/WEBP blob: one VP8X, one ANMF with `flags`, one odd chunk.

	The odd-sized trailing chunk exercises the pad-byte stepping that the real
	files rely on.
	"""
	body = b""
	for fourcc, payload in ((b"VP8X", b"\x00" * 10),
							(b"ANMF", b"\x00" * 15 + bytes([flags])),
							(b"ANNO", b"odd")):
		body += fourcc + len(payload).to_bytes(4, "little") + payload
		if len(payload) & 1:
			body += b"\x00"
	return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + body


def save_video(path, rate=10, seconds=1):
	"""Write a tiny synthetic video with ffmpeg (no encoder beyond mpeg4)."""
	done = subprocess.run(
		[webp.FFMPEG_BIN, "-y", "-loglevel", "error",
		 "-f", "lavfi", "-i",
		 "testsrc2=size=32x24:rate={}:duration={}".format(rate, seconds),
		 "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(path)],
		stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
		stderr=subprocess.PIPE)
	if done.returncode != 0:
		raise RuntimeError(done.stderr.decode("utf-8", "replace"))


class TempCase(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.root = Path(self.tmp.name)

	def render(self, folder, quiet=True, **overrides):
		"""Run make_animation for `folder`; return (code, output path)."""
		values = dict(dir=str(folder))
		values.update(overrides)
		# cwd deliberately points somewhere else: the output must not land
		# there, it belongs beside the input folder.
		elsewhere = self.root / "elsewhere"
		elsewhere.mkdir(exist_ok=True)
		with mock.patch.object(os, "getcwd", return_value=str(elsewhere)), \
				mock.patch("sys.stdout"):
			code = webp.make_animation(options(**values), cap16())
		return code, Path(str(folder).rstrip("\\/") + ".webp")


@unittest.skipIf(SKIP, "ffmpeg or pillow is not available")
class AnimationFileTest(TempCase):
	"""End to end: the file really is an animation with the promised shape."""

	def setUp(self):
		super().setUp()
		self.frames = self.root / "frames"
		self.frames.mkdir()
		for name, size, colour in (
				("b.png", (40, 10), (255, 0, 0, 255)),
				("a.png", (20, 20), (0, 255, 0, 255)),
				("c.png", (30, 30), (0, 0, 255, 255))):
			save_image(self.frames / name, size, colour)

	def test_output_is_beside_the_input_folder_not_in_the_cwd(self):
		code, output = self.render(self.frames)
		self.assertEqual(code, 0)
		self.assertEqual(output, self.root / "frames.webp")
		self.assertTrue(output.is_file())
		self.assertFalse((self.root / "elsewhere" / "frames.webp").exists())

	def test_output_follows_the_folder_even_when_nested(self):
		nested = self.root / "deep" / "shots"
		nested.mkdir(parents=True)
		save_image(nested / "a.png", (10, 10), (0, 255, 0, 255))
		code, output = self.render(nested)
		self.assertEqual(code, 0)
		self.assertEqual(output, self.root / "deep" / "shots.webp")

	def test_every_image_is_a_frame_on_the_common_canvas(self):
		code, output = self.render(self.frames, lossless=True)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			self.assertTrue(img.is_animated)
			self.assertEqual(img.n_frames, 3)
			# The canvas is the largest width by the largest height; frames are
			# padded, never cropped.
			self.assertEqual(img.size, (40, 30))
			for index, expected in enumerate([(0, 255, 0), (255, 0, 0),
											  (0, 0, 255)]):
				img.seek(index)
				pixel = img.convert("RGBA").getpixel((20, 15))
				self.assertEqual(pixel[:3], expected)
			# Transparent padding on the first frame's left edge.
			self.assertEqual(img.convert("RGBA").getpixel((0, 0))[3], 0)

	def test_sort_method_decides_the_frame_order(self):
		code, output = self.render(self.frames, sort="name_desc", lossless=True)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			img.seek(0)
			self.assertEqual(img.convert("RGBA").getpixel((20, 15))[:3],
							 (0, 0, 255))
			img.seek(1)
			self.assertEqual(img.convert("RGBA").getpixel((20, 15))[:3],
							 (255, 0, 0))

	def test_duration_round_trips_exactly(self):
		for duration in (120, 83, 80):
			with self.subTest(duration=duration):
				code, output = self.render(self.frames, duration=duration)
				self.assertEqual(code, 0)
				with Image.open(output) as img:
					self.assertEqual(img.n_frames, 3)
					for index in range(img.n_frames):
						img.seek(index)
						img.load()
						self.assertEqual(img.info.get("duration"), duration)

	def test_fps_becomes_the_frame_duration(self):
		code, output = self.render(self.frames, duration=None, fps=25)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			for index in range(img.n_frames):
				img.seek(index)
				img.load()
				self.assertEqual(img.info.get("duration"), 40)

	def test_loop_reaches_the_file(self):
		code, output = self.render(self.frames, loop=3)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			self.assertEqual(img.info.get("loop"), 3)

	def test_filters_decide_the_frame_count(self):
		code, output = self.render(self.frames, wildcard="[ab].png")
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			self.assertEqual(img.n_frames, 2)

	def test_opaque_flattens_onto_the_colour(self):
		code, output = self.render(self.frames, opaque=(16, 16, 16),
								   lossless=True)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			self.assertEqual(img.n_frames, 3)
			for index in range(img.n_frames):
				img.seek(index)
				# Padded corner: the flat background colour, fully opaque.
				self.assertEqual(img.convert("RGBA").getpixel((0, 0)),
								 (16, 16, 16, 255))

	def test_opaque_blends_partial_alpha(self):
		half = self.root / "half"
		half.mkdir()
		save_image(half / "half.png", (10, 10), (255, 0, 0, 128))
		code, output = self.render(half, opaque=(16, 16, 16), lossless=True)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			img.load()
			pixel = img.convert("RGBA").getpixel((5, 5))
		self.assertEqual(pixel[3], 255)
		# 50% red over #101010, so each channel is the mix of the two.
		self.assertAlmostEqual(pixel[0], 136, delta=6)
		self.assertAlmostEqual(pixel[1], 8, delta=6)
		self.assertAlmostEqual(pixel[2], 8, delta=6)

	def test_matte_keys_only_the_exact_colour_and_keeps_alpha(self):
		mixed = self.root / "mixed"
		mixed.mkdir()
		with Image.new("RGBA", (20, 20), (255, 0, 0, 255)) as img:
			draw = ImageDraw.Draw(img)
			draw.rectangle([10, 0, 19, 19], fill=(0, 0, 255, 255))
			img.putpixel((15, 5), (0, 0, 255, 128))
			img.save(mixed / "mix.png")
		code, output = self.render(mixed, matte=(255, 0, 0), lossless=True)
		self.assertEqual(code, 0)
		with Image.open(output) as img:
			img.load()
			image = img.convert("RGBA")
			self.assertEqual(image.getpixel((5, 5))[3], 0)
			self.assertEqual(image.getpixel((15, 15)), (0, 0, 255, 255))
			# Pre-existing alpha is untouched by the key.
			self.assertEqual(image.getpixel((15, 5)), (0, 0, 255, 128))

	def test_no_part_file_after_success(self):
		code, output = self.render(self.frames)
		self.assertEqual(code, 0)
		self.assertFalse(Path(str(output) + ".part.webp").exists())

	def test_no_part_file_after_failure(self):
		broken = self.root / "broken"
		broken.mkdir()
		save_image(broken / "a.png", (10, 10), (0, 255, 0, 255))
		(broken / "b.png").write_bytes(b"this is not a png")
		code, output = self.render(broken)
		self.assertEqual(code, 1)
		self.assertFalse(output.exists())
		self.assertFalse(Path(str(output) + ".part.webp").exists())

	def test_missing_folder_exits_nonzero(self):
		code, _ = self.render(self.root / "no-such-folder")
		self.assertEqual(code, 1)

	def test_quality_and_lossless_are_mutually_exclusive(self):
		done = subprocess.run(
			[sys.executable, str(REPO / "webp.py"),
			 "-q", "80", "--lossless"],
			cwd=str(self.root), stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		self.assertEqual(done.returncode, 2)
		self.assertIn(b"not allowed with argument", done.stderr)


class ForceNoBlendTest(unittest.TestCase):
	"""The patch that stops ffmpeg's frames from compositing onto each other."""

	def test_anmf_flags_get_the_no_blend_bit(self):
		blob = synthetic_webp(flags=0x00)
		patched = webp.force_no_blend(blob)
		self.assertEqual(anmf_flags(patched), [0x02])
		self.assertEqual(len(patched), len(blob))
		# Exactly one byte moved: the ANMF flags byte.
		differing = [index for index, (old, new) in enumerate(zip(blob, patched))
					 if old != new]
		flags_at = blob.index(b"ANMF") + 8 + 15
		self.assertEqual(differing, [flags_at])
		self.assertEqual(patched[flags_at], blob[flags_at] | 0x02)

	def test_dispose_and_other_flags_are_left_alone(self):
		blob = synthetic_webp(flags=0x01)  # dispose = background
		self.assertEqual(anmf_flags(webp.force_no_blend(blob)), [0x03])

	def test_non_riff_blob_is_untouched(self):
		blob = b"this is not a webp file at all"
		self.assertEqual(webp.force_no_blend(blob), blob)


@unittest.skipIf(SKIP, "ffmpeg or pillow is not available")
class FrameIsolationTest(TempCase):
	"""Regression: transparent frames must replace the canvas, not stack on it.

	ffmpeg writes every ANMF frame with blend=over, so a full-canvas frame that
	is mostly transparent let the earlier frames show through and the animation
	accumulated. Each frame now carries the "do not blend" bit.
	"""

	def setUp(self):
		super().setUp()
		self.frames = self.root / "sprite"
		self.frames.mkdir()
		for index, left in enumerate((0, 20, 40)):
			with Image.new("RGBA", (60, 20), (0, 0, 0, 0)) as img:
				ImageDraw.Draw(img).rectangle(
					[left, 0, left + 19, 19], fill=(0, 255, 0, 255))
				img.save(self.frames / "f{}.png".format(index))

	def test_each_frame_shows_only_its_own_sprite(self):
		code, output = self.render(self.frames, lossless=True)
		self.assertEqual(code, 0)
		columns = [(10, 10), (30, 10), (50, 10)]
		with Image.open(output) as img:
			self.assertEqual(img.n_frames, 3)
			for index in range(img.n_frames):
				img.seek(index)
				frame = img.convert("RGBA")
				for column, point in enumerate(columns):
					expected = 255 if column == index else 0
					self.assertEqual(frame.getpixel(point)[3], expected,
									 "frame {} at {}".format(index, point))
				self.assertEqual(frame.getpixel(columns[index])[:3],
								 (0, 255, 0))

	def test_produced_frames_all_carry_the_no_blend_bit(self):
		code, output = self.render(self.frames, lossless=True)
		self.assertEqual(code, 0)
		flags = anmf_flags(output.read_bytes())
		self.assertEqual(len(flags), 3)
		for value in flags:
			self.assertTrue(value & 0x02, hex(value))


@unittest.skipIf(SKIP, "ffmpeg or pillow is not available")
class VideoModeTest(TempCase):
	"""`-v` converts the named video, or every matching video in the folder."""

	def setUp(self):
		super().setUp()
		self.clips = self.root / "clips"
		self.clips.mkdir()
		self.clip = self.clips / "clip.avi"
		save_video(self.clip, rate=10, seconds=1)

	def run_video(self, **overrides):
		values = {"dir": None, "video": str(self.clip)}
		values.update(overrides)
		with mock.patch("sys.stdout"):
			return webp.make_animation(options(**values), cap16())

	def test_named_video_writes_webp_beside_it(self):
		self.assertEqual(self.run_video(), 0)
		output = self.clips / "clip.webp"
		self.assertTrue(output.is_file())
		self.assertFalse(Path(str(output) + ".part.webp").exists())
		with Image.open(output) as img:
			self.assertTrue(img.is_animated)
			self.assertEqual(img.size, (32, 24))

	def test_source_frame_rate_is_kept_by_default(self):
		self.assertEqual(self.run_video(), 0)
		with Image.open(self.clips / "clip.webp") as img:
			self.assertGreaterEqual(img.n_frames, 8)
			for index in range(img.n_frames):
				img.seek(index)
				img.load()
				self.assertAlmostEqual(img.info.get("duration"), 100, delta=15)

	def test_fps_resamples_a_video(self):
		self.assertEqual(self.run_video(fps=5), 0)
		with Image.open(self.clips / "clip.webp") as img:
			self.assertAlmostEqual(img.n_frames, 5, delta=1)
			img.seek(0)
			img.load()
			self.assertAlmostEqual(img.info.get("duration"), 200, delta=15)

	def test_batch_converts_every_video_in_the_folder(self):
		second = self.clips / "second.avi"
		second.write_bytes(self.clip.read_bytes())
		(self.clips / "note.txt").write_bytes(b"not a video")
		self.assertEqual(self.run_video(video="", dir=str(self.clips)), 0)
		self.assertTrue((self.clips / "clip.webp").is_file())
		self.assertTrue((self.clips / "second.webp").is_file())
		self.assertFalse((self.clips / "note.webp").exists())

	def test_batch_filters_with_ext_and_wildcard(self):
		second = self.clips / "second.avi"
		second.write_bytes(self.clip.read_bytes())
		self.assertEqual(self.run_video(video="", dir=str(self.clips),
										ext="avi", wildcard="clip*"), 0)
		self.assertTrue((self.clips / "clip.webp").is_file())
		self.assertFalse((self.clips / "second.webp").exists())

	def test_no_matching_videos_writes_nothing(self):
		self.assertEqual(self.run_video(video="", dir=str(self.clips),
										wildcard="nope*"), 1)
		self.assertFalse((self.clips / "clip.webp").exists())

	def test_failed_video_leaves_no_part_file(self):
		broken = self.clips / "broken.avi"
		broken.write_bytes(b"this is not a video")
		self.assertEqual(self.run_video(video=str(broken)), 1)
		self.assertFalse((self.clips / "broken.webp").exists())
		self.assertFalse((self.clips / "broken.webp.part.webp").exists())


class ArgumentRulesTest(unittest.TestCase):
	"""Option combinations argparse and validate() must refuse."""

	def run_script(self, *arguments):
		return subprocess.run(
			[sys.executable, str(REPO / "webp.py")] + list(arguments),
			stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
			stderr=subprocess.PIPE)

	def test_fps_and_duration_are_mutually_exclusive(self):
		done = self.run_script("--fps", "25", "--duration", "40")
		self.assertEqual(done.returncode, 2)
		self.assertIn(b"not allowed with argument", done.stderr)

	def test_video_rejects_duration(self):
		done = self.run_script("-v", "clip.avi", "--duration", "40")
		self.assertEqual(done.returncode, 2)
		self.assertIn(b"--duration", done.stderr)

	def test_video_rejects_sort(self):
		done = self.run_script("-v", "clip.avi", "-s", "name_asc")
		self.assertEqual(done.returncode, 2)
		self.assertIn(b"--sort", done.stderr)

	def test_named_video_rejects_a_folder(self):
		done = self.run_script("-v", "clip.avi", "-d", ".")
		self.assertEqual(done.returncode, 2)
		self.assertIn(b"--dir", done.stderr)

	def test_named_video_rejects_batch_filters(self):
		done = self.run_script("-v", "clip.avi", "-e", "mp4")
		self.assertEqual(done.returncode, 2)
		self.assertIn(b"batch filters", done.stderr)

	def test_resolve_duration_prefers_fps_then_explicit(self):
		namespace = argparse.Namespace(fps=None, duration=None)
		self.assertEqual(webp.resolve_duration(namespace),
						 webp.DEFAULT_DURATION)
		namespace.duration = 83
		self.assertEqual(webp.resolve_duration(namespace), 83)
		namespace.fps = 25
		self.assertEqual(webp.resolve_duration(namespace), 40)


class CollectImagesTest(TempCase):
	def setUp(self):
		super().setUp()
		for name in ("image10.png", "image2.png", "note.txt", "myimage1.png"):
			(self.root / name).write_bytes(b"x")

	def test_wildcard_and_natural_sort_match_the_renamer(self):
		names = webp.collect_images(str(self.root), wildcard="image*",
										method="alphanum_asc")
		self.assertEqual(names, ["image2.png", "image10.png"])

	def test_extension_filter_accepts_both_spellings(self):
		self.assertEqual(webp.normalise_ext("png"), ".png")
		self.assertEqual(webp.normalise_ext(".PNG"), ".png")
		self.assertEqual(
			webp.collect_images(str(self.root), ext=".png", method="name_asc"),
			["image10.png", "image2.png", "myimage1.png"])


if __name__ == "__main__":
	unittest.main()
