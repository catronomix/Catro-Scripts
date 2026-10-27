# Theme CLI split tests
"""
		THEME CLI SPLIT
		===============
`tui.__main__` is now only the `python -m tui` entrypoint; the command surface
(dispatch, pages, selectors, writers, the `edit` launcher) lives in
`tui.theme_cli` and is re-exported, so the old path keeps resolving.

Three structural pins: every moved name is the same object through both modules,
the entrypoint defines no command of its own, and importing the CLI module stays
inert - no capability probe, print or file access before `main()` runs.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))


class CliSplitShimTests(unittest.TestCase):
	"""The dispatch moved to `tui.theme_cli`; `tui.__main__` is the entrypoint."""

	MOVED = ("USAGE", "main", "summary", "theme_rows", "palette_rows",
			 "_look_selector", "_error_line", "_dispatch", "_set", "_page",
			 "_write", "_write_look", "_select_theme", "_edit")

	def test_every_command_name_resolves_through_both_modules(self):
		import tui.__main__ as entry
		import tui.theme_cli as cli
		for name in self.MOVED:
			with self.subTest(name=name):
				self.assertIs(getattr(cli, name), getattr(entry, name))

	def test_the_entrypoint_defines_no_commands_of_its_own(self):
		import ast
		source = (REPO / "tui" / "__main__.py").read_text(encoding="utf-8")
		tree = ast.parse(source)
		defs = [node.name for node in tree.body
				if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
		self.assertEqual(defs, [])
		self.assertIn("if __name__ == \"__main__\":", source)

	def test_the_cli_module_loads_without_touching_the_terminal(self):
		# Import stays inert: module level holds only the docstring, imports,
		# constants and `def`s - `main()` is where `caps.detect()` happens.
		import ast
		source = (REPO / "tui" / "theme_cli.py").read_text(encoding="utf-8")
		tree = ast.parse(source)
		for node in tree.body:
			with self.subTest(node=type(node).__name__):
				self.assertIsInstance(
					node, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign,
						   ast.FunctionDef))
		self.assertIn("def main(", source)


if __name__ == "__main__":
	unittest.main()
