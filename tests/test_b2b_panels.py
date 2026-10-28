# Regression tests for the installer/tooling summary panels
"""
			INSTALLER AND TOOLING SUMMARY PANELS
			====================================
Issue 0041 batch B2b boxes the summary/result blocks of `opencode`,
`image_generator`, `image_resizer`, `installdeps`, `ts_export`, `ts_setup` and
`venvreplicator` in a `tui.panel`. Their streaming/inline rows (the per-file
log, `tui.status` progress lines, the venv package table) keep their existing
chrome, and the machine-readable (piped) output keeps its exact pre-sweep
bytes - `tui.panel` in plain mode is just the title plus the body lines.

Every probe below stubs the network, pip, npm, PIL and filesystem work, so
nothing installs, scaffolds, generates images or reads a real venv. All writes
land in a temporary directory.

Run with:
	python -m unittest tests.test_b2b_panels -v
"""
import contextlib
import io
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)

FRAME = "\u250c"
BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"

TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=78, isatty=True,
							plain=False, reason="test")
TTY_16 = tui.Capabilities(level="16", unicode=True, width=78, isatty=True,
						  plain=False, reason="test")
TTY_NONE = tui.Capabilities(level="none", unicode=True, width=78, isatty=True,
							plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


def capture(render, cap):
	"""Run one block-producing call with `cap` and return its stdout."""
	buffer = io.StringIO()
	with mock.patch.dict(os.environ, {"CATRO_THEME": "soft"}), \
			mock.patch.object(tui, "detect", lambda: cap), \
			mock.patch.object(tui, "init_ansi"), \
			contextlib.redirect_stdout(buffer):
		try:
			render(cap)
		except SystemExit:
			pass
	return buffer.getvalue()


def no_frame(test, out):
	"""A pipe carries no escapes and no box glyphs."""
	test.assertNotIn("\x1b", out, out)
	for glyph in BOX_GLYPHS:
		test.assertNotIn(glyph, out, out)


class _TemporaryCwd:
	"""Run a page inside a throwaway directory, restoring the cwd after."""

	def __init__(self, test):
		self._test = test
		self._temp = tempfile.TemporaryDirectory(prefix="catro-b2b-")
		test.addCleanup(self._temp.cleanup)
		self.path = Path(self._temp.name)

	def __enter__(self):
		self._previous = os.getcwd()
		os.chdir(self.path)
		return self

	def __exit__(self, *exc):
		os.chdir(self._previous)
		return False


# --- opencode ----------------------------------------------------------------

class OpencodeGuidancePanelTest(unittest.TestCase):
	"""The not-installed guidance and the usage summary are page panels."""

	def render(self, cap):
		import opencode

		opencode.print_not_installed(cap)
		opencode.print_usage("anthropic/claude", cap)

	def test_true_colour_frames_both_blocks(self):
		out = capture(self.render, TTY_TRUE)
		self.assertEqual(2, out.count(FRAME), out)
		plain = tui.strip_ansi(out)
		self.assertIn("--- OPENCODE NOT FOUND ---", plain, out)
		self.assertIn("--- USAGE ---", plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertEqual(2, out16.count(FRAME), out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertEqual(2, out.count(FRAME), out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		self.assertTrue(out.startswith(
			"\n--- OPENCODE NOT FOUND ---\n"
			"[error] The `opencode` CLI is not installed or not on your PATH.\n"
			"\nGet it here:\thttps://opencode.ai\n"), out)
		self.assertIn("\n--- USAGE ---\n"
					  '  catro-scripts opencode "<instruction>"\n', out)
		self.assertTrue(out.endswith(
			"\nDefault model:\tanthropic/claude (from opencode.default)\n"), out)
		no_frame(self, out)


# --- image_generator ---------------------------------------------------------

class _FakePixels:
	def __setitem__(self, key, value):
		pass


class _FakeImage:
	"""Just enough of PIL to run the generator without pillow."""

	NEAREST = 0

	@staticmethod
	def new(mode, size, color=None):
		return _FakeImage()

	def putdata(self, data):
		pass

	def resize(self, size, resample=None):
		return _FakeImage()

	def paste(self, other, box):
		pass

	def load(self):
		return _FakePixels()

	def save(self, path):
		with open(path, "w", encoding="utf-8") as handle:
			handle.write("x")


class ImageGeneratorSummaryPanelTest(unittest.TestCase):
	"""The completion line is a panel; the per-file log stays colour-only."""

	def render(self, cap):
		import image_generator

		answers = iter(["3498db", 2, "shot", "2026-10-28"])
		with _TemporaryCwd(self) as folder, \
				mock.patch.object(image_generator, "Image", _FakeImage), \
				mock.patch.object(tui, "ask_text", lambda *a, **k: next(answers)), \
				mock.patch.object(tui, "ask_int", lambda *a, **k: next(answers)), \
				mock.patch.object(random, "randint", return_value=1):
			image_generator.generate_colored_images(cap)
			return folder.path / "202610280101"

	def test_true_colour_frames_the_completion(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("[ok] Process complete.",
					  tui.strip_ansi(out), out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_keeps_the_log_and_the_completion_line(self):
		out = capture(self.render, PIPE)
		self.assertIn("Created {} | Timestamp: 10:00:00".format(
			os.path.join("202610280101", "shot_001.png")), out)
		self.assertIn("[ok] Process complete. Files are in: ", out)
		no_frame(self, out)


# --- image_resizer -----------------------------------------------------------

class ImageResizerResultPanelTest(unittest.TestCase):
	"""The 'Resizing complete' result is a panel."""

	def render(self, cap):
		import image_resizer

		with _TemporaryCwd(self) as folder:
			(folder.path / "a.png").write_text("x", encoding="utf-8")
			with mock.patch.object(tui, "ask_int", return_value=64), \
					mock.patch.object(tui, "ask_choice", return_value=0), \
					mock.patch.object(image_resizer, "Image",
									  mock.Mock(NEAREST=0, BILINEAR=1,
												BICUBIC=2, LANCZOS=3)), \
					mock.patch.object(image_resizer, "resize_and_fit_image",
									  return_value=True):
				image_resizer.resize_images_in_folder(cap)

	def test_true_colour_frames_the_result(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("[ok] Resizing complete.",
					  tui.strip_ansi(out), out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_keeps_the_progress_and_result_lines(self):
		out = capture(self.render, PIPE)
		self.assertIn("Found\t1 images to process\n", out)
		self.assertIn("Processing: a.png 100% (1/1)\n", out)
		self.assertIn("\n[ok] Resizing complete. Resized images are in: ", out)
		no_frame(self, out)

	def test_a_long_output_path_wraps_instead_of_truncating(self):
		"""The result path is the payload: it must not become `C:/Users/..`."""
		import image_resizer

		with _TemporaryCwd(self) as folder:
			deep = (folder.path / "first-very-long-directory-name"
					/ "second-very-long-directory-name" / "resized")
			deep.mkdir(parents=True)
			os.chdir(deep)
			(deep / "a.png").write_text("x", encoding="utf-8")
			with mock.patch.object(tui, "ask_int", return_value=64), \
					mock.patch.object(tui, "ask_choice", return_value=0), \
					mock.patch.object(image_resizer, "Image",
									  mock.Mock(NEAREST=0, BILINEAR=1,
												BICUBIC=2, LANCZOS=3)), \
					mock.patch.object(image_resizer, "resize_and_fit_image",
									  return_value=True):
				out = capture(
					lambda cap: image_resizer.resize_images_in_folder(cap),
					TTY_TRUE)
		plain = tui.strip_ansi(out)
		for glyph in BOX_GLYPHS:
			plain = plain.replace(glyph, "")
		self.assertIn(str(deep.resolve()).replace(os.sep, "/"),
					  "".join(plain.split()).replace("\\", "/"))
		self.assertNotIn("..", plain)


# --- installdeps -------------------------------------------------------------

class InstalldepsSummaryPanelTest(unittest.TestCase):
	"""The final summary is one panel; the install log stays inline."""

	def render(self, cap, failures=("beta",)):
		import installdeps

		targets = ["alpha", "beta"]
		args = mock.Mock(positional_packages=targets, flag_packages=None,
						 workdir=None, skip_scan=True)

		def fake_run(cmd, **kwargs):
			if cmd[-1] in failures:
				raise installdeps.subprocess.CalledProcessError(1, cmd)
			return mock.Mock(returncode=0)

		with mock.patch.object(installdeps, "parse_arguments",
							   return_value=args), \
				mock.patch.object(installdeps, "ensure_pip"), \
				mock.patch.object(installdeps, "fetch_package_mapping",
								  return_value={}), \
				mock.patch.object(installdeps.subprocess, "run",
								  side_effect=fake_run):
			installdeps.main()

	def test_true_colour_frames_the_summary(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		plain = tui.strip_ansi(out)
		self.assertIn("INSTALLATION SUMMARY", plain, out)
		self.assertIn("Successfully processed (1)", plain, out)
		self.assertIn("Failed to install (1)", plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		self.assertEqual(
			"[info] Installing 'alpha'...\n"
			"[info] Installing 'beta'...\n"
			"[warn] Failed to install 'beta' (exit code 1). Moving to next "
			"dependency...\n"
			"\nINSTALLATION SUMMARY\n"
			"Successfully processed (1)\talpha\n"
			"Failed to install (1)\tbeta\n"
			"[warn] Continuing execution despite missing packages...\n",
			out)
		no_frame(self, out)

	def test_all_success_summary_is_the_same_panel(self):
		out = capture(lambda cap: self.render(cap, failures=()), TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("[ok] All dependencies were processed successfully.",
					  tui.strip_ansi(out), out)


# --- ts_export ---------------------------------------------------------------

class TsExportResultPanelTest(unittest.TestCase):
	"""The 'Export Complete' result pair is one panel."""

	def render(self, cap):
		import ts_export

		with _TemporaryCwd(self) as folder:
			bin_dir = folder.path / "node_modules" / ".bin"
			bin_dir.mkdir(parents=True)
			# The compiler probe looks for `tsc.cmd` on Windows and a bare
			# `tsc` elsewhere, so place both: the clean-compile branch must be
			# the one under test on every platform (the container images have
			# neither npm installed nor the Windows shim).
			(bin_dir / "tsc.cmd").write_text("", encoding="utf-8")
			(bin_dir / "tsc").write_text("", encoding="utf-8")
			(folder.path / "tsconfig.json").write_text("{}", encoding="utf-8")
			(folder.path / "index.html").write_text(
				'<script type="module" src="./main.ts"></script>',
				encoding="utf-8")
			with mock.patch.object(ts_export.subprocess, "check_call",
								   return_value=0):
				ts_export.main()

	def test_true_colour_frames_the_result(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		plain = tui.strip_ansi(out)
		self.assertIn("[ok] \u2728 Export Complete!", plain, out)
		self.assertIn("You can now open 'export/index.html'", plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		# Pin the clean-compile path itself: the panel is only drawn after the
		# local compiler is found, so a missing-binary run must not satisfy the
		# byte pin instead of the panel under test.
		self.assertIn("esbuild not found, falling back to standard tsc...\n"
					  "[ok] Compiled JavaScript successfully.\n", out)
		self.assertTrue(out.endswith(
			"Copying styles and assets...\n"
			"[ok] Processed index.html for local loading.\n"
			"\n[ok] \u2728 Export Complete!\n"
			"[info] You can now open 'export/index.html' directly in your "
			"browser.\n"), out)
		no_frame(self, out)


# --- ts_setup ----------------------------------------------------------------

class TsSetupResultPanelTest(unittest.TestCase):
	"""The scaffold's success/next-steps block is one panel."""

	def render(self, cap):
		import ts_setup

		argv = sys.argv
		sys.argv = ["ts_setup.py"]
		try:
			with _TemporaryCwd(self), \
					mock.patch.object(tui, "require_tty", lambda name: None), \
					mock.patch.object(ts_setup, "check_env",
									  return_value=("v20.0.0", "10.0.0")), \
					mock.patch.object(ts_setup.subprocess, "check_call",
									  return_value=0), \
					mock.patch.object(tui, "ask_text", return_value="demo"):
				ts_setup.main()
		finally:
			sys.argv = argv

	def test_true_colour_frames_the_result(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		plain = tui.strip_ansi(out)
		self.assertIn("[ok] Success! Project 'demo' is ready.", plain, out)
		self.assertIn("To start the development server:", plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		self.assertTrue(out.endswith(
			"[ok] Dependencies installed successfully.\n"
			"\n[ok] Success! Project 'demo' is ready.\n"
			"To start the development server:\n"
			"  cd demo\n"
			"  npm run dev\n"), out)
		no_frame(self, out)


# --- venvreplicator ----------------------------------------------------------

class VenvreplicatorSummaryPanelTest(unittest.TestCase):
	"""The venv facts block and both completion lines are panels."""

	def _source(self, test):
		folder = tempfile.TemporaryDirectory(prefix="catro-venv-")
		test.addCleanup(folder.cleanup)
		root = Path(folder.name)
		bindir = root / ("Scripts" if os.name == "nt" else "bin")
		bindir.mkdir()
		(bindir / ("python.exe" if os.name == "nt" else "python")).write_text(
			"", encoding="utf-8")
		(root / "pyvenv.cfg").write_text(
			"home = /usr/bin\nversion = 3.11.9\n"
			"include-system-site-packages = false\n", encoding="utf-8")
		return root

	def render(self, cap, mode="info"):
		import venvreplicator

		source = self._source(self)
		packages = [
			{"metadata": {"name": "requests", "version": "2.31.0"}},
			{"metadata": {"name": "urllib3", "version": "2.0.0"}},
		]
		with _TemporaryCwd(self), \
				mock.patch.object(venvreplicator.venvreplicator,
								  "get_detailed_packages",
								  return_value=(packages if mode == "info"
												else ["requests==2.31.0"])):
			instance = venvreplicator.venvreplicator(source, cap=cap)
			if mode == "info":
				instance.display_info()
			else:
				instance.generate_restore_script()

	def test_true_colour_frames_the_blocks(self):
		out = capture(self.render, TTY_TRUE)
		self.assertGreaterEqual(out.count(FRAME), 2, out)
		plain = tui.strip_ansi(out)
		self.assertIn("VENV SOURCE INFORMATION", plain, out)
		self.assertIn("[ok] VENV information saved to: venv_info.txt",
					  plain, out)
		self.assertIn("\x1b[38;2;", out)

	def test_level_16_and_none_degrade_cleanly(self):
		out16 = capture(self.render, TTY_16)
		self.assertIn(FRAME, out16)
		self.assertNotIn("38;2;", out16)
		out = capture(self.render, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_restore_script_result_is_a_panel(self):
		out = capture(lambda cap: self.render(cap, mode="script"), TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("[ok] Restoration script generated: recreate_venv.py",
					  tui.strip_ansi(out), out)

	def test_plain_bytes_are_the_pre_sweep_bytes(self):
		out = capture(self.render, PIPE)
		self.assertTrue(out.startswith(
			"VENV SOURCE INFORMATION\n"
			"VENV Path:\t"), out)
		self.assertIn("\nINSTALLED PACKAGES\n"
					  "Package\tVersion\tSource\n"
					  "requests\t2.31.0\tPyPI\n", out)
		self.assertIn("\nTotal Packages: 2\n"
					  "[ok] VENV information saved to: venv_info.txt\n", out)
		self.assertNotIn("recreate_venv.py", out)
		no_frame(self, out)

	def test_plain_restore_script_line_is_unchanged(self):
		out = capture(lambda cap: self.render(cap, mode="script"), PIPE)
		self.assertEqual("[ok] Restoration script generated: recreate_venv.py\n",
						 out)
		no_frame(self, out)


# --- shared ------------------------------------------------------------------

class NoBareInputTest(unittest.TestCase):
	"""Batch B2b scripts ask through `tui.prompts`, never `input()` directly."""

	def test_no_bare_input_in_the_seven_scripts(self):
		import ast

		for name in ("opencode.py", "image_generator.py", "image_resizer.py",
					 "installdeps.py", "ts_export.py", "ts_setup.py",
					 "venvreplicator.py"):
			with self.subTest(script=name):
				tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
				calls = [node for node in ast.walk(tree)
						 if isinstance(node, ast.Call)
						 and isinstance(node.func, ast.Name)
						 and node.func.id == "input"]
				self.assertEqual([], calls,
								 "{} still calls input() directly".format(name))


if __name__ == "__main__":
	unittest.main()
