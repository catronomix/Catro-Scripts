# Regression tests for the sysadmin/confirm group's boxed blocks
"""
			SYSADMIN BLOCK PANELS
			=====================
Issue 0041 batch B2a moved the plan/confirm/result blocks of `netconfig`,
`renamer`, `randomsorter`, `shutdown` and `keygen` onto `tui.panel`; their
single-line status lines stay inline `tui.status` text and the machine-readable
(piped) output keeps its exact pre-sweep bytes.

`netconfig` and `shutdown` are privileged/system tools: their mutating paths are
never executed here. The block is captured with the platform calls, the
subprocess runner and the prompts stubbed, so nothing elevates, schedules or
touches an adapter.

Run with:
	python -m unittest tests.test_b2a_panels -v
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

FRAME = "\u250c"
BOX_GLYPHS = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"

TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=70, isatty=True,
							plain=False, reason="test")
TTY_16 = tui.Capabilities(level="16", unicode=True, width=70, isatty=True,
						  plain=False, reason="test")
TTY_NONE = tui.Capabilities(level="none", unicode=True, width=70, isatty=True,
							plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


def capture(render, cap, theme="soft"):
	"""Run one block-producing call with `cap` and return its stdout."""
	buffer = io.StringIO()
	with mock.patch.dict(os.environ, {"CATRO_THEME": theme}), \
			mock.patch.object(tui, "detect", lambda: cap), \
			contextlib.redirect_stdout(buffer):
		render(cap)
	return buffer.getvalue()


class NetconfigPlanPanelTest(unittest.TestCase):
	"""The static-IP plan heading is one page-width panel."""

	def render(self, cap):
		import netconfig

		with mock.patch.object(netconfig.tui, "ask_text",
							   side_effect=["10.0.0.5", "24", "10.0.0.1"]):
			netconfig.get_manual_input(
				"eth0",
				{"eth0": {"ip": "10.0.0.2", "mask": "255.255.255.0",
						  "gw": "10.0.0.1"}},
				cap)

	def test_true_colour_frames_the_plan(self):
		out = capture(self.render, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("Setting up static IP for:", tui.strip_ansi(out), out)
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
		self.assertEqual("\nSetting up static IP for: eth0\n", out)
		for glyph in BOX_GLYPHS:
			self.assertNotIn(glyph, out)


if __name__ == "__main__":
	unittest.main()
