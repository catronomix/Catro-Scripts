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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import caps, config, palette, theme_engine  # noqa: E402  (import after sys.path setup)
from tui.__main__ import main, summary  # noqa: E402
from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()


def _checkout_state(path):
	"""Fingerprint of a checkout file: (exists, bytes, mtime_ns)."""
	try:
		stat = path.stat()
	except OSError:
		return (False, None, None)
	return (True, path.read_bytes(), stat.st_mtime_ns)


class ResolutionTests(unittest.TestCase):
	def setUp(self):
		self._config_file = config.CONFIG_FILE

	def tearDown(self):
		config.CONFIG_FILE = self._config_file

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
		self._config_file = config.CONFIG_FILE
		self._theme_file = theme_engine.THEME_FILE
		self._themes_dir = theme_engine.THEMES_DIR
		self._td = tempfile.TemporaryDirectory()
		config.CONFIG_FILE = Path(self._td.name) / "config.ini"
		theme_engine.THEME_FILE = Path(self._td.name) / "theme.ini"
		theme_engine.THEMES_DIR = Path(self._td.name) / "themes"
		theme_engine.THEMES_DIR.mkdir()
		theme_engine._CACHE.clear()

	def tearDown(self):
		config.CONFIG_FILE = self._config_file
		theme_engine.THEME_FILE = self._theme_file
		theme_engine.THEMES_DIR = self._themes_dir
		theme_engine._CACHE.clear()
		self._td.cleanup()

	def run_main(self, argv):
		stream = io.StringIO()
		with redirect_stdout(stream):
			code = main(argv)
		return code, stream.getvalue()

	def add_theme(self, slug, display=None):
		"""Write `themes/<slug>.json`; returns its path."""
		document = theme_engine.document()
		document["name"] = slug
		document["display"] = display or slug.title()
		theme_engine.save_theme(document, overwrite=True)
		return theme_engine.themes_dir() / "{}.json".format(slug)

	def test_show_reports_mode_level_style_path_and_writability(self):
		code, out = self.run_main([])
		self.assertEqual(code, 0)
		for marker in ("theme.mode", "color.level", "table.style", "config", "writable"):
			self.assertIn(marker, out)
		self.assertIn(str(config.path()), out)

	def test_show_names_the_selected_theme_and_look(self):
		# Piped rows are TAB records; `theme.mode` stays for back-compat.
		code, out = self.run_main([])
		self.assertEqual(code, 0)
		self.assertIn("theme.name\tcozypurple", out)
		self.assertIn("theme.look\tsoft", out)
		self.assertIn("theme.mode\tsoft", out)

	def test_dark_is_the_contrast_dark_look(self):
		# The CLI spelling `dark` selects contrast-dark; only the legacy
		# config.ini migration still reads it as the old default look.
		for spelling, look, look_id in (("dark", "contrast-dark", "dark"),
										("light", "contrast-light", "light")):
			with self.subTest(spelling=spelling):
				self.assertEqual(self.run_main([spelling])[0], 0)
				self.assertEqual(palette.theme(), look)
				self.assertEqual(theme_engine.selection()[1], look_id)

	def test_a_theme_name_selects_its_file(self):
		self.add_theme("plain", "Plain")
		code, out = self.run_main(["plain"])
		self.assertEqual((code, out), (0, ""))
		self.assertEqual(theme_engine.selection()[0], "plain")

	def test_an_unknown_theme_name_exits_two_and_names_the_expected_file(self):
		code, out = self.run_main(["bogus"])
		self.assertEqual(code, 2)
		self.assertEqual(out.count("\n"), 1)
		self.assertIn("bogus.json", out)
		self.assertNotIn("usage:", out)

	def test_list_names_the_available_themes(self):
		self.add_theme("cozypurple", "Cozy Purple")
		self.add_theme("plain", "Plain")
		code, out = self.run_main(["list"])
		self.assertEqual(code, 0)
		self.assertIn("cozypurple\tCozy Purple (active)", out)
		self.assertIn("plain\tPlain", out)

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
		# `dark` is deliberately absent: the CLI now reads it as the
		# contrast-dark look, not as the legacy alias of `soft`.
		cases = {
			"cozy": "soft", "default": "soft",
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

	def test_set_theme_look_rejects_unknown_values(self):
		code, out = self.run_main(["set", "theme.look", "neon"])
		self.assertEqual(code, 2)
		self.assertEqual(
			out, "invalid theme.look: neon (valid: soft, contrast-light, "
				 "contrast-dark)\n")

	def test_set_theme_name_and_look(self):
		self.add_theme("plain", "Plain")
		self.assertEqual(self.run_main(["set", "theme.name", "plain"])[0], 0)
		self.assertEqual(theme_engine.selection()[0], "plain")
		self.assertEqual(self.run_main(["set", "theme.look", "light"])[0], 0)
		self.assertEqual(theme_engine.selection()[1], "light")

	def test_edit_off_a_tty_exits_two_before_loading_anything(self):
		target = io.StringIO()
		with redirect_stdout(target), redirect_stderr(io.StringIO()) as err:
			with self.assertRaises(SystemExit) as caught:
				main(["edit", "bogus"])
		self.assertEqual(caught.exception.code, 2)
		self.assertIn("needs an interactive terminal", err.getvalue())
		self.assertEqual(target.getvalue(), "")

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
		# The operator's checkout may already own a config.ini/theme.ini; what
		# matters is that the run leaves them exactly as they were.
		before = {name: _checkout_state(REPO / name)
				  for name in ("config.ini", "theme.ini")}
		code, out = self.run_python("theme.py")
		self.assertEqual(code, 0)
		# Piped rows are TAB-joined fields (the `field` plain contract).
		self.assertIn("theme.mode\tsoft", out)
		self.assertIn("config\t{}".format(self.root / "config.ini"), out)
		self.assertFalse((self.root / "config.ini").exists())
		self.assertFalse((self.root / "theme.ini").exists())
		for name, state in before.items():
			self.assertEqual(_checkout_state(REPO / name), state,
							 "the script wrote to the checkout: " + name)

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
