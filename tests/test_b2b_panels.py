# Tests for the installer/tooling group's non-rendering behaviour
"""
			INSTALLER AND TOOLING BEHAVIOUR
			===============================

These tests cover what the scripts do, not how their pages look: `oc` runs the
right subcommand, saves a default model only when asked, and asks through the
shared prompt helpers (never bare `input()`).

Output copy and panel geometry are deliberately not asserted: the code is the
reference for what it prints, and snapshot tests only restate it.
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import tui  # noqa: E402  (import after sys.path setup)
from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=78, isatty=True,
							plain=False, reason="test")


class OpencodeSubcommandTest(unittest.TestCase):
	"""Bare run shows usage only; `models` is the one path that dumps models."""

	def main(self, argv, cap=TTY_TRUE):
		"""Run oc.main with argv, a fake binary and a recording runner."""
		import oc

		calls = []

		def fake_run(binary, args):
			calls.append(args)
			return mock.Mock(returncode=0)

		buffer = io.StringIO()
		self.written = mock.Mock()
		with mock.patch.object(tui, "detect", lambda: cap), \
				mock.patch.object(tui, "init_ansi"), \
				mock.patch.object(oc, "find_opencode",
								  lambda: "opencode"), \
				mock.patch.object(oc, "run_opencode", fake_run), \
				mock.patch.object(oc, "read_default_model", lambda: None), \
				mock.patch.object(oc, "write_default_model", self.written), \
				mock.patch.object(sys, "argv", ["oc.py"] + argv), \
				contextlib.redirect_stdout(buffer):
			try:
				oc.main()
			except SystemExit as exc:
				self._exit = exc.code
			else:
				self._exit = None
		return calls, buffer.getvalue()

	def test_bare_run_never_lists_models(self):
		calls, out = self.main([])
		self.assertEqual([], calls, out)
		self.assertIsNone(self._exit)

	def test_models_subcommand_delegates_and_keeps_usage(self):
		calls, out = self.main(["models"])
		self.assertEqual([["models"]], calls, out)
		self.assertEqual(0, self._exit)

	def test_instruction_still_runs_with_model(self):
		calls, out = self.main(["-m", "openai/gpt-5.2", "fix", "the", "tests"])
		self.assertEqual([["run", "-m", "openai/gpt-5.2", "fix the tests"]],
						 calls, out)
		self.written.assert_not_called()

	def test_model_alone_still_saves_the_default(self):
		calls, out = self.main(["-m", "openai/gpt-5.2"])
		self.assertEqual([], calls, out)
		self.written.assert_called_once_with("openai/gpt-5.2")


class NoBareInputTest(unittest.TestCase):
	"""Batch B2b scripts ask through `tui.prompts`, never `input()` directly."""

	def test_no_bare_input_in_the_seven_scripts(self):
		import ast

		for name in ("oc.py", "image_generator.py", "image_resizer.py",
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
