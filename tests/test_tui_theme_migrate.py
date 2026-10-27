# Schema-2 migration and the frame-corner seam
"""
		SCHEMA-2 MIGRATION AND CORNERS
		==============================
Pins the additive half of the palette restructure: a schema-1 document is
migrated in memory and then validated as schema 2 (nine renames, five
byte-preserving derivations, the retired `selection_style` property and the
default `corner-char`), a save writes schema 2, and a read never rewrites a v1
file. The corner seam is pinned separately: only an explicit character moves a
byte, and the override lands after the console's ASCII degradation.

Every engine test points `THEMES_DIR`/`THEME_FILE` at a temporary folder, so
the checkout never gains a theme or a `theme.ini`.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import (caps, config, frame_corners, palette, table,  # noqa: E402
				 table_glyphs, theme_engine, theme_migrate)

SHIPPED = REPO / "themes" / "cozypurple.json"
V1_SHIPPED = REPO / "tests" / "fixtures" / "themes" / "v1-cozypurple.json"
TRUE = caps.Capabilities(level="true", unicode=True, width=None,
						 isatty=False, plain=False, reason="test")
ASCII = caps.Capabilities(level="true", unicode=False, width=None,
						  isatty=False, plain=False, reason="test")


def v1_document():
	"""A frozen schema-1 copy of the shipped theme, kept after the C3 flip."""
	return json.loads(V1_SHIPPED.read_text(encoding="utf-8"))


def shipped_document():
	"""The shipped file as JSON (schema 2 since the flip)."""
	return json.loads(SHIPPED.read_text(encoding="utf-8"))


def v2_properties(**overrides):
	"""A complete schema-2 property table, with `overrides` applied."""
	values = dict(theme_migrate.migrate_doc(v1_document())["properties"])
	values.update(overrides)
	return values


class Seam(unittest.TestCase):
	"""A temp checkout with the shipped document as its built-in fallback."""

	def setUp(self):
		self._temp = tempfile.TemporaryDirectory()
		self.root = Path(self._temp.name)
		self.themes = self.root / "themes"
		self.themes.mkdir()
		self.shipped = self.themes / "cozypurple.json"
		shutil.copyfile(SHIPPED, self.shipped)
		theme_engine.THEMES_DIR = self.themes
		theme_engine.THEME_FILE = self.root / "theme.ini"
		config.CONFIG_FILE = self.root / "config.ini"
		theme_engine._CACHE.clear()

	def tearDown(self):
		theme_engine.THEMES_DIR = None
		theme_engine.THEME_FILE = None
		config.CONFIG_FILE = None
		theme_engine._CACHE.clear()
		self._temp.cleanup()


class MigrationMapTests(unittest.TestCase):
	def test_the_map_renames_every_non_background_v1_key(self):
		v1 = set(theme_migrate.V1_PALETTE_KEYS)
		self.assertEqual(v1 - {"bg", "fg"}, set(theme_migrate.V1_TO_V2))
		for old, new in theme_migrate.V1_TO_V2.items():
			with self.subTest(alias=old):
				self.assertIn(new, theme_migrate.PALETTE_KEYS)
				self.assertNotIn(old, theme_migrate.PALETTE_KEYS)

	def test_the_new_keys_reproduce_the_sixteen_key_set(self):
		carried = (set(theme_migrate.V1_TO_V2.values()) | {"bg", "fg"}
				   | set(theme_migrate.DERIVED))
		self.assertEqual(carried, set(theme_migrate.PALETTE_KEYS))
		self.assertEqual(len(carried), 16)
		self.assertEqual(theme_migrate.SCHEMA_CURRENT, 2)

	def test_every_derivation_reads_a_real_v1_key(self):
		for key, source in theme_migrate.DERIVED.items():
			with self.subTest(key=key):
				self.assertIn(key, theme_migrate.PALETTE_KEYS)
				self.assertIn(source, theme_migrate.V1_PALETTE_KEYS)

	def test_migration_preserves_every_hex_verbatim(self):
		document = theme_migrate.migrate_doc(v1_document())
		for look in theme_engine.LOOKS:
			v1 = v1_document()["looks"][look]
			v2 = document["looks"][look]
			with self.subTest(look=look):
				for old, new in theme_migrate.V1_TO_V2.items():
					self.assertEqual(v2[new], v1[old], new)
				for new, old in theme_migrate.DERIVED.items():
					self.assertEqual(v2[new], v1[old], new)

	def test_migration_drops_selection_style_and_defaults_the_corner(self):
		document = theme_migrate.migrate_doc(v1_document())
		self.assertEqual(document["schema"], theme_migrate.SCHEMA_CURRENT)
		self.assertIn("selection_style", v1_document()["properties"])
		self.assertNotIn("selection_style", document["properties"])
		self.assertEqual(document["properties"]["corner-char"], "none")

	def test_migration_emits_the_canonical_key_and_property_order(self):
		document = theme_migrate.migrate_doc(v1_document())
		self.assertEqual(list(document["looks"]["default"]),
						 list(theme_migrate.PALETTE_KEYS))
		self.assertEqual(list(document["properties"]),
						 list(theme_engine.PROPERTY_VALUES))
		self.assertEqual(list(document), list(v1_document()))

	def test_a_v2_document_is_returned_unchanged_and_idempotent(self):
		document = theme_migrate.migrate_doc(v1_document())
		self.assertIs(theme_migrate.migrate_doc(document), document)
		self.assertEqual(theme_migrate.migrate_doc(document), document)

	def test_a_broken_v1_look_gains_no_invented_colour(self):
		document = v1_document()
		del document["looks"]["default"]["accent"]
		migrated = theme_migrate.migrate_doc(document)
		self.assertIsNone(migrated["looks"]["default"]["fg-accent"])
		self.assertTrue(theme_engine.validate(migrated))


class EngineMigrationTests(Seam):
	def test_a_v1_file_loads_as_v2_and_is_never_rewritten(self):
		self.shipped.write_bytes(V1_SHIPPED.read_bytes())
		before = self.shipped.read_bytes()
		document = theme_engine.load_theme("cozypurple")
		self.assertEqual(document["schema"], 2)
		self.assertEqual(len(document["looks"]["default"]), 16)
		self.assertEqual(self.shipped.read_bytes(), before,
						 "a read must not rewrite the file")

	def test_a_v1_document_is_read_but_only_v2_validates(self):
		errors = theme_engine.validate(v1_document())
		self.assertIn("schema must be 2", errors)
		self.assertEqual(theme_engine.validate_any(v1_document()), [])
		document = v1_document()
		document["looks"]["default"]["fg-muted"] = "#112233"
		self.assertTrue(any("unknown keys" in error
							for error in theme_engine.validate(document)))

	def test_a_v2_document_rejects_the_retired_properties(self):
		document = theme_engine.builtin_document()
		document["looks"]["default"]["surface"] = "#112233"
		document["properties"]["selection_style"] = "accent"
		errors = theme_engine.validate(document)
		self.assertTrue(any("unknown keys" in error for error in errors))
		self.assertIn("unknown properties: selection_style", errors)

	def test_save_writes_schema_two_and_canonicalises_once(self):
		path = theme_engine.save_theme(
			theme_engine.load_theme("cozypurple"), overwrite=True)
		written = json.loads(Path(path).read_text(encoding="utf-8"))
		self.assertEqual(written["schema"], 2)
		self.assertEqual(list(written["looks"]["default"]),
						 list(theme_engine.PALETTE_KEYS))
		self.assertNotIn("selection_style", written["properties"])
		self.assertEqual(written["properties"]["corner-char"], "none")
		first = Path(path).read_bytes()
		theme_engine.save_theme(theme_engine.load_theme("cozypurple"),
								overwrite=True)
		self.assertEqual(Path(path).read_bytes(), first)

	def test_saving_a_v1_document_writes_the_migrated_schema(self):
		document = v1_document()
		document["name"] = "mymint"
		path = theme_engine.save_theme(document)
		written = json.loads(Path(path).read_text(encoding="utf-8"))
		self.assertEqual(written["schema"], 2)
		self.assertEqual(written["looks"], theme_migrate.migrate_doc(
			v1_document())["looks"])

	def test_an_unknown_schema_is_still_refused(self):
		for schema in (0, 3, "2", True):
			document = shipped_document()
			document["schema"] = schema
			with self.subTest(schema=schema):
				self.assertTrue(theme_engine.validate(document))


class CornerTests(unittest.TestCase):
	def setUp(self):
		self._config_file = config.CONFIG_FILE
		self._temp = tempfile.TemporaryDirectory()
		config.CONFIG_FILE = Path(self._temp.name) / "config.ini"

	def tearDown(self):
		config.CONFIG_FILE = self._config_file
		self._temp.cleanup()

	def test_none_keeps_every_family_byte_identical(self):
		for style, glyphs in table.BORDER_GLYPHS.items():
			with self.subTest(style=style):
				self.assertIs(
					frame_corners.apply_corners(
						glyphs, TRUE, {"corner-char": "none"}), glyphs)

	def test_an_unknown_value_falls_back_to_the_family(self):
		for glyphs in table.BORDER_GLYPHS.values():
			self.assertIs(
				frame_corners.apply_corners(glyphs, TRUE, {"corner-char": "z"}),
				glyphs)
			self.assertIs(frame_corners.apply_corners(glyphs, TRUE, {}), glyphs)

	def test_each_character_replaces_only_the_four_corners(self):
		for char in ("@", "x", "#", "+", "o", "*"):
			for style, glyphs in table.BORDER_GLYPHS.items():
				if style == "none":
					continue
				with self.subTest(char=char, style=style):
					framed = frame_corners.apply_corners(
						glyphs, TRUE, {"corner-char": char})
					for key, value in glyphs.items():
						if key in frame_corners.CORNERS:
							self.assertEqual(framed[key], char)
						else:
							self.assertEqual(framed[key], value)

	def test_the_borderless_family_never_gains_corners(self):
		self.assertIs(
			frame_corners.apply_corners(table.SPACE_GLYPHS, TRUE,
										{"corner-char": "@"}),
			table.SPACE_GLYPHS)

	def test_glyphs_for_applies_the_theme_corner_after_ascii_degradation(self):
		with mock.patch.object(
				palette, "properties",
				return_value=v2_properties(**{"corner-char": "@"})):
			glyphs = table_glyphs.glyphs_for(ASCII)
		for key in frame_corners.CORNERS:
			self.assertEqual(glyphs[key], "@")
		self.assertEqual(glyphs["h"], "-")
		self.assertEqual(glyphs["v"], "|")

	def test_glyphs_for_covers_every_border_style(self):
		for style in theme_engine.PROPERTY_VALUES["border_style"]:
			with self.subTest(style=style):
				with mock.patch.object(
						palette, "properties",
						return_value=v2_properties(
							border_style=style, **{"corner-char": "#"})):
					glyphs = table_glyphs.glyphs_for(TRUE)
				family = table.BORDER_GLYPHS[style]
				for key in frame_corners.CORNERS:
					expected = " " if style == "none" else "#"
					self.assertEqual(glyphs[key], expected)
				self.assertEqual(glyphs["h"], family["h"])
				self.assertEqual(glyphs["v"], family["v"])

	def test_glyphs_for_keeps_the_family_corners_at_none(self):
		with mock.patch.object(
				palette, "properties",
				return_value=v2_properties(
					border_style="heavy", **{"corner-char": "none"})):
			self.assertIs(table_glyphs.glyphs_for(TRUE), table.HEAVY_GLYPHS)


if __name__ == "__main__":
	unittest.main()
