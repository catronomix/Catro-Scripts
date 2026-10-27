# Theme engine tests: JSON schema, atomic save, selection and migration
"""
		THEME ENGINE: DATA AND SELECTION
		================================
Pins the stage-1 seam: one JSON file per theme drives the palettes, `theme.ini`
holds the selection, and nothing a render touches can raise.

Covered: the shipped document against the built-in table, validation of every
schema rule (all-or-nothing, so a typo cannot ship a half-theme), the atomic
save round-trip (canonical lowercase, stable key order, no temp file left),
look-selector resolution and its fallback to the built-in default, and the
`theme.ini` read/write/migration paths. Every test points `THEME_FILE` and
`THEMES_DIR` at a temporary directory, so the repository never gains either.
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import config, theme_engine  # noqa: E402  (import after sys.path setup)

SHIPPED = REPO / "themes" / "cozypurple.json"


def builtin():
	"""A fresh copy of the built-in document, safe to mutate in a test."""
	return copy.deepcopy(theme_engine.BUILTIN_DOCUMENT)


class SeamCase(unittest.TestCase):
	"""Every test gets its own theme.ini and themes/ directory.

	The temp checkout starts with the shipped document, so a selection there
	resolves like a real one instead of falling back to the built-in table.
	"""

	def setUp(self):
		self._temp = tempfile.TemporaryDirectory()
		self.root = Path(self._temp.name)
		self.themes = self.root / "themes"
		self.themes.mkdir()
		shutil.copyfile(SHIPPED, self.themes / "cozypurple.json")
		self.selection_file = self.root / "theme.ini"
		self.config_file = self.root / "config.ini"
		theme_engine.THEMES_DIR = self.themes
		theme_engine.THEME_FILE = self.selection_file
		config.CONFIG_FILE = self.config_file
		theme_engine._CACHE.clear()

	def tearDown(self):
		theme_engine.THEMES_DIR = None
		theme_engine.THEME_FILE = None
		config.CONFIG_FILE = None
		theme_engine._CACHE.clear()
		self._temp.cleanup()

	def write_theme(self, document=None, name=None):
		"""Write a document into the temp themes/ directory and return its path."""
		document = document or builtin()
		target = self.themes / "{}.json".format(name or document["name"])
		target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
		return target


class ShippedDocumentTests(SeamCase):
	def test_the_shipped_file_is_valid_and_matches_the_builtin_table(self):
		document = json.loads(SHIPPED.read_text(encoding="utf-8"))
		self.assertEqual(theme_engine.validate(document), [])
		self.assertEqual(document, builtin())

	def test_load_preserves_the_file_spelling(self):
		theme_engine.THEMES_DIR = REPO / "themes"
		document = theme_engine.load_theme("cozypurple")
		self.assertEqual(document["looks"]["default"]["bg"], "#1B1726")
		self.assertEqual(document["looks"]["contrast-dark"]["accent"], "#00FFFF")

	def test_document_carries_the_pinned_key_order(self):
		theme_engine.THEMES_DIR = REPO / "themes"
		document = theme_engine.load_theme("cozypurple")
		self.assertEqual(list(document), ["schema", "name", "display",
										  "properties", "looks"])
		self.assertEqual(list(document["looks"]),
						 list(theme_engine.LOOKS))
		self.assertEqual(list(document["looks"]["default"]),
						 list(theme_engine.PALETTE_KEYS))

	def test_list_themes_reads_the_directory(self):
		theme_engine.THEMES_DIR = REPO / "themes"
		self.assertIn("cozypurple", theme_engine.list_themes())

	def test_list_themes_is_empty_without_a_directory(self):
		theme_engine.THEMES_DIR = self.root / "nowhere"
		self.assertEqual(theme_engine.list_themes(), [])


class ValidationTests(SeamCase):
	def check(self, document):
		return theme_engine.validate(document)

	def test_missing_and_unknown_property_values_are_rejected(self):
		document = builtin()
		del document["properties"]["table_zebra"]
		self.assertTrue(self.check(document))
		document = builtin()
		document["properties"]["border_style"] = "wavy"
		self.assertTrue(any("border_style" in error
							for error in self.check(document)))

	def test_table_zebra_must_be_a_real_bool(self):
		document = builtin()
		document["properties"]["table_zebra"] = 1
		self.assertTrue(self.check(document))

	def test_unknown_properties_and_looks_are_rejected(self):
		document = builtin()
		document["properties"]["glow"] = True
		self.assertTrue(self.check(document))
		document = builtin()
		document["looks"]["sepia"] = dict(document["looks"]["default"])
		self.assertTrue(self.check(document))

	def test_every_look_needs_every_palette_key(self):
		document = builtin()
		del document["looks"]["contrast-light"]["warn"]
		self.assertTrue(self.check(document))

	def test_hexes_accept_optional_hash_and_mixed_case(self):
		document = builtin()
		document["looks"]["default"]["accent"] = "f5CD68"
		self.assertEqual(self.check(document), [])
		document["looks"]["default"]["accent"] = "#12345"
		self.assertTrue(self.check(document))
		document["looks"]["default"]["accent"] = "#GGGGGG"
		self.assertTrue(self.check(document))

	def test_schema_and_name_rules(self):
		for schema in (2, "1", True):
			document = builtin()
			document["schema"] = schema
			self.assertTrue(self.check(document), schema)
		for name in ("Cozy Purple", "", "-leading", "UPPER"):
			document = builtin()
			document["name"] = name
			self.assertTrue(self.check(document), name)

	def test_display_is_required_text(self):
		document = builtin()
		document["display"] = "  "
		self.assertTrue(self.check(document))


class LoadTests(SeamCase):
	def test_missing_file_raises_theme_error(self):
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.load_theme("nope")

	def test_corrupt_file_raises_theme_error(self):
		(self.themes / "broken.json").write_text("{oops", encoding="utf-8")
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.load_theme("broken")

	def test_invalid_document_raises_theme_error(self):
		document = builtin()
		document["looks"]["default"]["bg"] = "purple"
		self.write_theme(document)
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.load_theme("cozypurple")

	def test_name_must_match_the_filename(self):
		self.write_theme(builtin(), name="other")
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.load_theme("other")

	def test_invalid_slug_is_rejected(self):
		for name in ("../escape", "", "Cozy"):
			with self.assertRaises(theme_engine.ThemeError):
				theme_engine.load_theme(name)

	def test_render_paths_never_raise(self):
		theme_engine.THEMES_DIR = self.root / "missing"
		self.assertEqual(theme_engine.resolve("ghost")[0], "cozypurple")
		self.assertEqual(theme_engine.look_palette("ghost"),
						 theme_engine.BUILTIN_LOOKS["default"])
		self.assertEqual(theme_engine.document("ghost")["name"], "cozypurple")
		self.assertEqual(set(theme_engine.properties("ghost")),
						 set(theme_engine.PROPERTY_VALUES))


class CacheTests(SeamCase):
	"""Reads are memoized by path+mtime, and a write re-opens exactly that key."""

	def test_a_warm_cache_resolves_without_re_reading_or_re_validating(self):
		self.assertEqual(theme_engine.look_palette("cozypurple")["bg"],
						 theme_engine.BUILTIN_LOOKS["default"]["bg"])
		with mock.patch.object(theme_engine, "_document_for",
							   side_effect=AssertionError("re-read")):
			for _ in range(50):
				self.assertEqual(theme_engine.look_palette("cozypurple")["bg"],
								 theme_engine.BUILTIN_LOOKS["default"]["bg"])
				theme_engine.properties("cozypurple")
				theme_engine.document("cozypurple")

	def test_load_theme_still_hands_out_a_copy(self):
		document = theme_engine.load_theme("cozypurple")
		document["looks"]["default"]["bg"] = "#010203"
		self.assertNotEqual(theme_engine.look_palette("cozypurple")["bg"],
							"#010203")

	def test_a_save_invalidates_the_document_memo(self):
		document = theme_engine.load_theme("cozypurple")
		self.assertEqual(theme_engine.look_palette("cozypurple")["bg"],
						 theme_engine.BUILTIN_LOOKS["default"]["bg"])
		document["looks"]["default"]["bg"] = "#010203"
		theme_engine.save_theme(document, overwrite=True)
		self.assertEqual(theme_engine.look_palette("cozypurple")["bg"],
						 "#010203")

	def test_a_selection_write_is_visible_immediately(self):
		self.assertEqual(theme_engine.selection(), ("cozypurple", "soft"))
		# Same tick or not, the write drops its own memo: no stale selection.
		theme_engine.set_selection("cozypurple", "contrast-dark")
		self.assertEqual(theme_engine.selection(), ("cozypurple", "dark"))
		self.assertEqual(theme_engine.resolve()[1], "contrast-dark")

	def test_redirecting_the_theme_dir_is_a_different_cache_key(self):
		self.assertEqual(theme_engine.look_palette()["bg"],
						 theme_engine.BUILTIN_LOOKS["default"]["bg"])
		other = self.root / "other"
		other.mkdir()
		document = builtin()
		document["looks"]["default"]["bg"] = "#010203"
		document["name"] = "cozypurple"
		(other / "cozypurple.json").write_text(json.dumps(document),
											   encoding="utf-8")
		theme_engine.THEMES_DIR = other
		self.assertEqual(theme_engine.look_palette()["bg"], "#010203")


class SaveTests(SeamCase):
	def test_save_normalises_and_round_trips(self):
		document = builtin()
		document["name"] = "mymint"
		document["display"] = "My Mint"
		for key in document["looks"]["default"]:
			document["looks"]["default"][key] = document["looks"]["default"][key].lower()
		path = theme_engine.save_theme(document)
		self.assertEqual(Path(path), self.themes / "mymint.json")
		self.assertEqual(sorted(entry.name for entry in self.themes.iterdir()),
						 ["cozypurple.json", "mymint.json"],
						 "no temp file may be left behind")
		text = Path(path).read_text(encoding="utf-8")
		self.assertIn('"#1b1726"', text)
		loaded = theme_engine.load_theme("mymint")
		self.assertEqual(theme_engine.validate(loaded), [])
		self.assertEqual(loaded["looks"]["default"]["bg"], "#1b1726")

	def test_saving_a_loaded_document_is_byte_stable(self):
		document = builtin()
		document["name"] = "mymint"
		path = theme_engine.save_theme(document)
		first = Path(path).read_text(encoding="utf-8")
		theme_engine.save_theme(theme_engine.load_theme("mymint"), overwrite=True)
		self.assertEqual(Path(path).read_text(encoding="utf-8"), first)

	def test_existing_file_needs_overwrite(self):
		document = builtin()
		document["name"] = "mymint"
		theme_engine.save_theme(document)
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.save_theme(document)
		path = theme_engine.save_theme(document, overwrite=True)
		self.assertTrue(Path(path).is_file())

	def test_invalid_document_is_never_written(self):
		document = builtin()
		document["schema"] = 3
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.save_theme(document)
		self.assertEqual([entry.name for entry in self.themes.iterdir()],
						 ["cozypurple.json"])

	def test_save_finds_the_new_document_immediately(self):
		document = builtin()
		document["name"] = "fresh"
		theme_engine.save_theme(document)
		self.assertEqual(theme_engine.load_theme("fresh")["name"], "fresh")


class SelectionTests(SeamCase):
	def test_default_selection(self):
		self.assertEqual(theme_engine.selection(), ("cozypurple", "soft"))
		self.assertEqual(theme_engine.resolve(), ("cozypurple", "default"))

	def test_reads_do_not_create_theme_ini(self):
		theme_engine.selection()
		theme_engine.look_palette()
		theme_engine.document()
		self.assertFalse(self.selection_file.exists())

	def test_theme_ini_drives_name_and_look(self):
		self.selection_file.write_text(
			"[theme]\nname = cozypurple\nlook = dark\n", encoding="utf-8")
		self.assertEqual(theme_engine.selection(), ("cozypurple", "dark"))
		self.assertEqual(theme_engine.resolve()[1], "contrast-dark")
		self.assertEqual(theme_engine.look_palette(),
						 theme_engine.BUILTIN_LOOKS["contrast-dark"])

	def test_the_selected_theme_drives_document_and_properties(self):
		document = builtin()
		document["name"] = "mint"
		document["display"] = "Mint"
		document["properties"]["border_style"] = "ascii"
		document["looks"]["contrast-dark"]["accent"] = "#22CC88"
		self.write_theme(document)
		self.selection_file.write_text(
			"[theme]\nname = mint\nlook = dark\n", encoding="utf-8")
		self.assertEqual(theme_engine.resolve(), ("mint", "contrast-dark"))
		self.assertEqual(theme_engine.document()["name"], "mint")
		self.assertEqual(theme_engine.properties()["border_style"], "ascii")
		self.assertEqual(theme_engine.look_palette()["accent"], "#22CC88")

	def test_a_selected_theme_that_breaks_later_falls_back(self):
		document = builtin()
		document["name"] = "mint"
		self.write_theme(document)
		self.selection_file.write_text("[theme]\nname = mint\n", encoding="utf-8")
		self.assertEqual(theme_engine.document()["name"], "mint")
		(self.themes / "mint.json").write_text("{oops", encoding="utf-8")
		self.assertEqual(theme_engine.resolve()[0], "cozypurple")
		self.assertEqual(theme_engine.document()["name"], "cozypurple")
		self.assertEqual(theme_engine.properties()["header_align"], "left")

	def test_set_selection_rejects_a_corrupt_theme_file(self):
		(self.themes / "broken.json").write_text("{oops", encoding="utf-8")
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.set_selection("broken")
		self.assertFalse(self.selection_file.exists(),
						 "a rejected selection must not be written")

	def test_malformed_theme_ini_falls_back_to_the_default(self):
		for text in ("nonsense\n[theme\nlook = dark\n",
					 "[theme]\nlook = ultraviolet\n",
					 "[theme]\nname = Not A Slug\nlook = soft\n"):
			with self.subTest(text=text):
				self.selection_file.write_text(text, encoding="utf-8")
				self.assertEqual(theme_engine.selection(), ("cozypurple", "soft"))

	def test_look_selectors_and_ids_resolve(self):
		cases = {
			"soft": "default", "default": "default",
			"light": "contrast-light", "contrast-light": "contrast-light",
			"contrast light": "contrast-light",
			"dark": "contrast-dark", "contrast-dark": "contrast-dark",
			"unknown": "default",
		}
		for spelling, expected in cases.items():
			with self.subTest(spelling=spelling):
				self.assertEqual(theme_engine.resolve(None, spelling)[1], expected)

	def test_set_selection_writes_canonical_values(self):
		self.assertTrue(theme_engine.set_selection("cozypurple", "Contrast_Light"))
		text = self.selection_file.read_text(encoding="utf-8")
		self.assertIn("name = cozypurple", text)
		self.assertIn("look = light", text)
		self.assertEqual(theme_engine.selection(), ("cozypurple", "light"))

	def test_set_selection_rejects_unknown_values(self):
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.set_selection("ghost")
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.set_selection("cozypurple", "ultraviolet")
		with self.assertRaises(theme_engine.ThemeError):
			theme_engine.set_selection("../escape")

	def test_set_selection_reports_an_unwritable_file(self):
		theme_engine.THEME_FILE = self.root / "missing" / "theme.ini"
		self.assertFalse(theme_engine.set_selection("cozypurple", "light"))
		self.assertFalse((self.root / "missing").exists())

	def test_legacy_config_mode_is_migrated_in_memory(self):
		self.config_file.write_text("[theme]\nmode = light\n", encoding="utf-8")
		with mock.patch.dict(os.environ, {}, clear=True):
			self.assertEqual(theme_engine.selection(), ("cozypurple", "light"))
		self.assertFalse(self.selection_file.exists(),
						 "a read must not migrate on its own")

	def test_legacy_dark_maps_onto_the_default_look(self):
		self.config_file.write_text("[theme]\nmode = dark\n", encoding="utf-8")
		self.assertEqual(theme_engine.selection(), ("cozypurple", "soft"))

	def test_migrate_persists_the_legacy_value_once(self):
		self.config_file.write_text("[theme]\nmode = high-contrast\n",
									encoding="utf-8")
		self.assertTrue(theme_engine.migrate())
		self.assertIn("look = dark",
					  self.selection_file.read_text(encoding="utf-8"))
		# Later config edits no longer matter: theme.ini is the owner now.
		self.config_file.write_text("[theme]\nmode = light\n", encoding="utf-8")
		self.assertEqual(theme_engine.selection(), ("cozypurple", "dark"))

	def test_theme_ini_wins_over_the_legacy_value(self):
		self.selection_file.write_text("[theme]\nlook = light\n", encoding="utf-8")
		self.config_file.write_text("[theme]\nmode = dark\n", encoding="utf-8")
		self.assertEqual(theme_engine.selection(), ("cozypurple", "light"))

	def test_unknown_theme_name_renders_with_the_builtin_default(self):
		self.selection_file.write_text("[theme]\nname = ghost\n", encoding="utf-8")
		self.assertEqual(theme_engine.selection()[0], "ghost")
		self.assertEqual(theme_engine.resolve()[0], "cozypurple")
		self.assertEqual(theme_engine.look_palette(),
						 theme_engine.BUILTIN_LOOKS["default"])


class PropertiesTests(SeamCase):
	def test_properties_returns_a_copy(self):
		values = theme_engine.properties()
		values["header_align"] = "right"
		self.assertEqual(theme_engine.properties()["header_align"], "left")

	def test_properties_come_from_the_active_document(self):
		document = builtin()
		document["properties"]["border_style"] = "ascii"
		self.write_theme(document)
		self.assertEqual(theme_engine.properties()["border_style"], "ascii")


if __name__ == "__main__":
	unittest.main()
