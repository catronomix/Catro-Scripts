# Tests for the sysadmin/confirm group's non-rendering behaviour
"""
			SYSADMIN BEHAVIOUR
			==================

These tests cover things a rendering change must not break: prompts route
through the shared prompt helpers, a closed stdin ends the shutdown flow, and
the privileged tools never run their mutating paths here.

Output copy and panel geometry are deliberately not asserted: the code is the
reference for what it prints, and snapshot tests only restate it.
"""
import contextlib
import io
import os
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

TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=70, isatty=True,
							plain=False, reason="test")


class NoBareInputTest(unittest.TestCase):
	"""Batch B2a scripts ask through `tui.prompts`, never `input()` directly."""

	def test_no_bare_input_in_the_five_scripts(self):
		import ast

		for name in ("netconfig.py", "renamer.py", "randomsorter.py",
					 "shutdown.py", "keygen.py"):
			with self.subTest(script=name):
				tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
				calls = [node for node in ast.walk(tree)
						 if isinstance(node, ast.Call)
						 and isinstance(node.func, ast.Name)
						 and node.func.id == "input"]
				self.assertEqual([], calls,
								 "{} still calls input() directly".format(name))


class ShutdownPromptTest(unittest.TestCase):
	"""EOF is a quit: the delay prompt must not loop on a closed stdin."""

	def test_closed_stdin_quits_instead_of_reprompting(self):
		import shutdown

		with mock.patch.object(tui, "detect", lambda: TTY_TRUE), \
				mock.patch.object(tui, "init_ansi"), \
				mock.patch.object(tui, "ask_text", return_value=shutdown._EOF), \
				mock.patch.object(tui, "header", lambda *a, **k: "header"), \
				contextlib.redirect_stdout(io.StringIO()):
			shutdown.main()  # returns, never schedules, never spins


if __name__ == "__main__":
	unittest.main()
