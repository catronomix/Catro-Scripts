# Regression tests for the migrated help/action rendering
"""
			SCRIPT MIGRATION SEAMS
			======================
Pins the two things the help/action migration deliberately kept as data rather
than as private ANSI strings:

	- help.INDENT_STYLES: the indentation palette must still resolve to the old
		16-colour codes (1;37, 0;36, 0;32, 0;33, 0;31), so a 16-colour terminal
		sees the same colours it always did.
	- action.list_actions(): fixed widths and its own `..` truncation survive,
		while a pipe gets the library's plain TAB-separated records.

Run with:
	python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
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


def cap16():
	return tui.Capabilities(level="16", unicode=True, width=None,
							isatty=True, plain=False, reason="test")


class HelpIndentStylesTest(unittest.TestCase):
	"""help.py's indentation mapping is data passed to tui.style()."""

	def setUp(self):
		import help as help_module
		self.help = help_module

	def test_each_level_keeps_its_16_colour_code(self):
		expected = ["\033[37m", "\033[36m", "\033[32m", "\033[33m", "\033[31m"]
		self.assertEqual(len(self.help.INDENT_STYLES), len(expected))
		for level, code in enumerate(expected):
			styled = tui.style("x", cap=cap16(),
							   **self.help.INDENT_STYLES[level])
			self.assertIn(code, styled,
						  "indentation level {} lost its {} code: {!r}".format(
							  level, code, styled))
			self.assertTrue(styled.endswith("x" + tui.RESET))

	def test_level_zero_is_still_bold(self):
		styled = tui.style("x", cap=cap16(), **self.help.INDENT_STYLES[0])
		self.assertIn("\033[1m", styled)


class ActionPlainTableTest(unittest.TestCase):
	"""action.list_actions() keeps its layout and emits plain records in a pipe."""

	def render(self, actions):
		import action as action_module
		with tempfile.TemporaryDirectory() as td:
			path = os.path.join(td, "actions.json")
			with open(path, "w", encoding="utf-8") as handle:
				json.dump(actions, handle)
			buffer = io.StringIO()
			with mock.patch.object(action_module, "ACTIONS_FILE", path):
				with contextlib.redirect_stdout(buffer):
					action_module.list_actions()
		return buffer.getvalue()

	def records(self, out):
		lines = out.splitlines()
		start = lines.index("ID\tAction Name\tCommand\tDescription") + 1
		body = lines[start:]
		end = next(index for index, line in enumerate(body)
				   if line.startswith("Total macros saved:"))
		return body[:end]

	def test_pipe_is_tab_separated_without_ansi_or_glyphs(self):
		out = self.render({
			"ping": {"command": "ping 127.0.0.1", "description": "Loopback"},
		})
		records = self.records(out)
		self.assertEqual(len(records), 1, out)
		self.assertEqual(records[0].split("\t"),
						 ["1", "ping", "ping 127.0.0.1", "Loopback"])
		self.assertNotIn("\x1b", out)
		for glyph in "\u2500\u2502\u250c\u2510\u2514\u2518\u253c":
			self.assertNotIn(glyph, out)

	def test_long_cells_keep_the_table_truncation_rule(self):
		command = "x" * 40
		description = "y" * 40
		out = self.render({
			"long": {"command": command, "description": description},
		})
		fields = self.records(out)[0].split("\t")
		self.assertEqual(fields[2], "x" * 28 + "..")
		self.assertEqual(fields[3], "y" * 32 + "..")


if __name__ == "__main__":
	unittest.main()
