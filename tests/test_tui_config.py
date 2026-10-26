# Configuration and theme-command tests
"""
		CONFIG RESOLUTION AND DEFAULTS
		===============================
`config.ini` belongs to the checkout, not the caller's cwd, and a broken or
missing file must never break a script. Every test points the module at a temp
path through the documented `CONFIG_FILE` seam, so the repository never gains a
config.ini.
"""

import configparser
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import caps, config, palette, theme_engine  # noqa: E402  (import after sys.path setup)
from tui.__main__ import main, summary  # noqa: E402


class ResolutionTests(unittest.TestCase):
	def tearDown(self):
		config.CONFIG_FILE = None

	def test_path_is_the_project_folder_not_the_cwd(self):
		config.CONFIG_FILE = None
		self.assertEqual(config.path(), REPO / "config.ini")
		previous = os.getcwd()
		with tempfile.TemporaryDirectory() as td:
			os.chdir(td)
			try:
				self.assertEqual(config.path(), REPO / "config.ini")
			finally:
				os.chdir(previous)

	def test_defaults_when_the_file_is_missing(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			# Theme selection moved to theme.ini, owned by the engine.
			self.assertIsNone(config.get("theme", "mode"))
			self.assertEqual(config.get("color", "level"), "auto")
			self.assertEqual(config.get("table", "style"), "auto")
			self.assertEqual(config.get("nope", "nope", "fallback"), "fallback")

	def test_defaults_when_the_file_is_malformed(self):
		with tempfile.TemporaryDirectory() as td:
			target = Path(td) / "config.ini"
			target.write_text("this is not ini\n[theme\nmode = light\n", encoding="utf-8")
			config.CONFIG_FILE = target
			self.assertIsNone(config.get("theme", "mode"))
			self.assertEqual(config.get("color", "level"), "auto")

	def test_defaults_when_the_file_is_unreadable(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td)  # a directory: opening it raises OSError
			self.assertEqual(config.get("color", "level"), "auto")
			self.assertFalse(config.writable())

	def test_values_are_read_back(self):
		with tempfile.TemporaryDirectory() as td:
			target = Path(td) / "config.ini"
			target.write_text("[theme]\nmode = contrast-light\n\n[table]\nstyle = ascii\n",
							  encoding="utf-8")
			config.CONFIG_FILE = target
			# The legacy value stays readable so the engine can migrate it.
			self.assertEqual(config.get("theme", "mode"), "contrast-light")
			self.assertEqual(config.get("table", "style"), "ascii")
			self.assertEqual(config.get("color", "level"), "auto")

	def test_writes_land_in_the_config_file_only(self):
		previous = os.getcwd()
		with tempfile.TemporaryDirectory() as td:
			target = Path(td) / "config.ini"
			config.CONFIG_FILE = target
			os.chdir(td)
			try:
				self.assertTrue(config.set("color", "level", "256"))
				self.assertTrue(target.is_file())
				self.assertEqual(config.get("color", "level"), "256")
				self.assertEqual(sorted(p.name for p in Path(td).iterdir()), ["config.ini"])
			finally:
				os.chdir(previous)

	def test_set_reports_failure_and_writable_agrees(self):
		with tempfile.TemporaryDirectory() as td:
			target = Path(td) / "missing" / "config.ini"
			config.CONFIG_FILE = target
			self.assertFalse(config.writable())
			self.assertFalse(config.set("color", "level", "256"))
			self.assertFalse(target.exists())

	def test_writable_accepts_a_normal_temp_path(self):
		with tempfile.TemporaryDirectory() as td:
			config.CONFIG_FILE = Path(td) / "config.ini"
			self.assertTrue(config.writable())

	def test_gitignore_covers_the_local_state_files(self):
		# The container oracle drops .gitignore from the build context
		# (.dockerignore), so there is nothing to read there.
		if not (REPO / ".gitignore").is_file():
			self.skipTest("no .gitignore in this checkout (container image)")
		lines = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
		entries = [line.split("#")[0].strip() for line in lines]
		self.assertIn("config.ini", entries)
		self.assertIn("theme.ini", entries)

	def test_config_example_documents_only_the_remaining_sections(self):
		parser = configparser.ConfigParser()
		with open(REPO / "config.ini.example", encoding="utf-8") as handle:
			parser.read_file(handle)
		self.assertEqual(set(parser.sections()), {"color", "table"})
		self.assertFalse(parser.has_option("color", "level"))

	def test_theme_example_parses_and_points_at_the_selection_file(self):
		parser = configparser.ConfigParser()
		with open(REPO / "theme.ini.example", encoding="utf-8") as handle:
			parser.read_file(handle)
		self.assertEqual(set(parser.sections()), {"theme"})
		self.assertFalse(parser.has_option("theme", "name"))
		self.assertFalse(parser.has_option("theme", "look"))


class ThemeCommandTests(unittest.TestCase):
	def setUp(self):
		self._td = tempfile.TemporaryDirectory()
		config.CONFIG_FILE = Path(self._td.name) / "config.ini"
		theme_engine.THEME_FILE = Path(self._td.name) / "theme.ini"

	def tearDown(self):
		config.CONFIG_FILE = None
		theme_engine.THEME_FILE = None
		self._td.cleanup()

	def run_main(self, argv):
		stream = io.StringIO()
		with redirect_stdout(stream):
			code = main(argv)
		return code, stream.getvalue()

	def test_show_reports_mode_level_style_path_and_writability(self):
		code, out = self.run_main([])
		self.assertEqual(code, 0)
		for marker in ("theme.mode", "color.level", "table.style", "config", "writable"):
			self.assertIn(marker, out)
		self.assertIn(str(config.path()), out)

	def test_every_theme_command_writes_its_look(self):
		for mode, look in (("soft", "soft"), ("contrast-light", "light"),
						   ("contrast-dark", "dark")):
			with self.subTest(mode=mode):
				self.assertEqual(self.run_main([mode])[0], 0)
				self.assertEqual(palette.theme(), mode)
				self.assertEqual(theme_engine.selection()[1], look)
				self.assertIn("look = {}".format(look),
							  theme_engine.theme_file().read_text(encoding="utf-8"))

	def test_aliases_write_the_canonical_look(self):
		cases = {
			"cozy": "soft", "default": "soft", "dark": "soft",
			"contrastlight": "contrast-light", "contrast_light": "contrast-light",
			"CLIGHT": "contrast-light",
			"highcontrast": "contrast-dark", "contrast dark": "contrast-dark",
			"HC": "contrast-dark", "cdark": "contrast-dark",
		}
		for alias, expected in cases.items():
			with self.subTest(alias=alias):
				self.assertEqual(self.run_main([alias])[0], 0)
				self.assertEqual(palette.theme(), expected)

	def test_toggle_cycles_soft_light_dark_soft(self):
		self.run_main(["soft"])
		for expected in ("contrast-light", "contrast-dark", "soft"):
			self.assertEqual(self.run_main(["toggle"])[0], 0)
			self.assertEqual(palette.theme(), expected)

	def test_legacy_config_dark_resolves_to_soft_and_migrates(self):
		config.path().write_text("[theme]\nmode = dark\n", encoding="utf-8")
		with mock.patch.dict(os.environ, {}, clear=True):
			self.assertEqual(palette.theme(), "soft")
		# A read never writes; the first write persists the migrated selection.
		self.assertFalse(theme_engine.theme_file().exists())
		self.assertEqual(self.run_main(["toggle"])[0], 0)
		self.assertEqual(palette.theme(), "contrast-light")
		self.assertIn("look = light",
					  theme_engine.theme_file().read_text(encoding="utf-8"))
		# config.ini is no longer the owner: the legacy value is left alone.
		self.assertEqual(config.get("theme", "mode"), "dark")

	def test_an_unrelated_set_also_persists_a_legacy_mode(self):
		config.path().write_text("[theme]\nmode = dark\n", encoding="utf-8")
		self.assertEqual(self.run_main(["set", "color.level", "256"])[0], 0)
		self.assertEqual(config.get("color", "level"), "256")
		self.assertEqual(theme_engine.selection(), ("cozypurple", "soft"))
		self.assertIn("look = soft",
					  theme_engine.theme_file().read_text(encoding="utf-8"))

	def test_set_theme_mode_names_all_valid_modes_when_it_rejects_one(self):
		code, out = self.run_main(["set", "theme.mode", "neon"])
		self.assertEqual(code, 2)
		self.assertEqual(
			out, "invalid theme.mode: neon (valid: soft, contrast-light, contrast-dark)\n")

	def test_set_accepts_known_keys(self):
		self.assertEqual(self.run_main(["set", "color.level", "256"])[0], 0)
		self.assertEqual(config.get("color", "level"), "256")
		self.assertEqual(self.run_main(["set", "table.style", "ascii"])[0], 0)
		self.assertEqual(config.get("table", "style"), "ascii")

	def test_set_theme_mode_accepts_aliases_and_stores_the_canonical_look(self):
		self.assertEqual(self.run_main(["set", "theme.mode", "Contrast_Light"])[0], 0)
		self.assertEqual(palette.theme(), "contrast-light")
		self.assertEqual(theme_engine.selection()[1], "light")

	def test_set_rejects_unknown_keys_and_values(self):
		self.assertEqual(self.run_main(["set", "color.level", "banana"])[0], 2)
		code, out = self.run_main(["set", "theme.nope", "soft"])
		self.assertEqual(code, 2)
		self.assertIn("invalid setting", out)

	def test_unwritable_theme_ini_prints_one_line_and_exits_one(self):
		theme_engine.THEME_FILE = Path(self._td.name) / "missing" / "theme.ini"
		code, out = self.run_main(["set", "theme.mode", "contrast-light"])
		self.assertEqual(code, 1)
		self.assertEqual(out, "theme.ini is not writable here: {}\n".format(
			theme_engine.theme_file()))

	def test_help_lists_every_theme_selector(self):
		code, out = self.run_main(["--help"])
		self.assertEqual(code, 0)
		self.assertIn("usage: theme", out)
		for mode in ("soft", "contrast-light", "contrast-dark", "toggle"):
			self.assertIn(mode, out)

	def test_help_and_palette(self):
		code, out = self.run_main(["palette"])
		self.assertEqual(code, 0)
		for key in ("bg", "fg", "accent", "zebra_bg"):
			self.assertIn(key, out)

	def test_palette_swatches_carry_each_keys_own_colour(self):
		# A terminal page paints the swatch with the key's own palette role and
		# always prints the hex value, so the row is readable without the swatch.
		cap = caps.Capabilities(level="true", unicode=True, width=None,
								isatty=False, plain=False, reason="test")
		stream = io.StringIO()
		with mock.patch.object(caps, "detect", return_value=cap), \
				redirect_stdout(stream):
			self.assertEqual(main(["palette"]), 0)
		out = stream.getvalue()
		for key, value in palette.palette().items():
			self.assertIn(palette.prefix(fg=key, cap=cap) + "\u25a0", out)
			self.assertIn(value, out)

	def test_unknown_command_prints_usage(self):
		code, out = self.run_main(["bogus"])
		self.assertEqual(code, 2)
		self.assertIn("usage: theme", out)

	def test_summary_is_plain_text(self):
		lines = summary(io.StringIO())
		self.assertTrue(all("\x1b" not in line for line in lines))


class ThemeScriptTests(unittest.TestCase):
	"""Run the script and the module in a throwaway copy of the package."""

	def setUp(self):
		self._td = tempfile.TemporaryDirectory()
		self.root = Path(self._td.name)
		shutil.copytree(REPO / "tui", self.root / "tui",
						ignore=shutil.ignore_patterns("__pycache__"))
		shutil.copy2(REPO / "theme.py", self.root / "theme.py")
		self.env = dict(os.environ)
		for name in ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "CATRO_COLOR",
					 "CATRO_THEME", "CATRO_ASCII"):
			self.env.pop(name, None)
		self.env["PYTHONIOENCODING"] = "utf-8"

	def tearDown(self):
		self._td.cleanup()

	def run_python(self, *args):
		completed = subprocess.run(
			[sys.executable] + list(args), cwd=str(self.root), env=self.env,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
		)
		return (completed.returncode,
				completed.stdout.decode("utf-8").replace("\r\n", "\n"))

	def test_script_shows_the_summary_without_writing_anything(self):
		code, out = self.run_python("theme.py")
		self.assertEqual(code, 0)
		# Piped rows are TAB-joined fields (the `field` plain contract).
		self.assertIn("theme.mode\tsoft", out)
		self.assertIn("config\t{}".format(self.root / "config.ini"), out)
		self.assertFalse((self.root / "config.ini").exists())
		self.assertFalse((self.root / "theme.ini").exists())
		self.assertFalse((REPO / "config.ini").exists())

	def test_script_help_lists_the_commands(self):
		code, out = self.run_python("theme.py", "--help")
		self.assertEqual(code, 0)
		self.assertIn("usage: theme", out)

	def test_script_writes_the_look_next_to_the_package(self):
		code, _ = self.run_python("theme.py", "contrast-light")
		self.assertEqual(code, 0)
		text = (self.root / "theme.ini").read_text(encoding="utf-8")
		self.assertIn("look = light", text)
		self.assertFalse((self.root / "config.ini").exists())

	def test_module_entry_point_matches_the_script(self):
		code, out = self.run_python("-m", "tui", "show")
		self.assertEqual(code, 0)
		self.assertIn("theme.mode", out)
		self.assertFalse((self.root / "config.ini").exists())
		self.assertFalse((self.root / "theme.ini").exists())

	def test_unwritable_theme_ini_exits_one_with_a_single_line(self):
		(self.root / "theme.ini").mkdir()
		code, out = self.run_python("theme.py", "contrast-light")
		self.assertEqual(code, 1)
		self.assertEqual(out, "theme.ini is not writable here: {}\n".format(
			self.root / "theme.ini"))


if __name__ == "__main__":
	unittest.main()
