# Prompt-loop tests: blank, cancellation and closed stdin
"""
			INPUT PROMPTS
			==============
`tui.prompts` owns the three input loops every interactive script used to
duplicate. The helpers are driven here with `builtins.input` patched, so no
terminal is needed:

	- blank takes the default (free text) or re-prompts (integer, no default)
	- q/quit/exit and a closed stdin cancel instead of looping
	- the EOF case is the regression: `ask_int` used to treat a closed stdin as
		a blank answer and re-enter `input()` for ever, so a Ctrl-D at the
		prompt hung the script (and swallowed Ctrl-C with it)

Run with:
	python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import prompts  # noqa: E402  (import after sys.path setup)


class Scripted:
	"""Stand-in for `input`: replays answers, then raises EOFError."""

	def __init__(self, answers):
		self.answers = list(answers)
		self.prompts = []

	def __call__(self, label=""):
		self.prompts.append(label)
		if not self.answers:
			raise EOFError
		answer = self.answers.pop(0)
		if answer is EOFError:
			raise EOFError
		return answer


class AskTextTests(unittest.TestCase):
	def ask(self, answers, **kwargs):
		script = Scripted(answers)
		with mock.patch("builtins.input", script):
			return prompts.ask_text("Name", **kwargs)

	def test_blank_takes_the_default(self):
		self.assertEqual(self.ask([""], default="image"), "image")

	def test_answer_is_stripped(self):
		self.assertEqual(self.ask(["  bob  "]), "bob")

	def test_eof_returns_the_default(self):
		self.assertEqual(self.ask([], default="image"), "image")

	def test_eof_can_be_told_apart_when_asked_for(self):
		sentinel = object()
		self.assertIs(self.ask([], default="x", eof=sentinel), sentinel)


class AskIntTests(unittest.TestCase):
	def ask(self, answers, **kwargs):
		script = Scripted(answers)
		with mock.patch("builtins.input", script):
			return prompts.ask_int("Count", 1, 10, **kwargs), script

	def test_value_in_range(self):
		value, _ = self.ask(["7"])
		self.assertEqual(value, 7)

	def test_out_of_range_re_prompts(self):
		value, script = self.ask(["0", "99", "4"])
		self.assertEqual(value, 4)
		self.assertEqual(len(script.prompts), 3)

	def test_non_number_re_prompts(self):
		value, script = self.ask(["x", "3"])
		self.assertEqual(value, 3)
		self.assertEqual(len(script.prompts), 2)

	def test_blank_with_default_returns_it(self):
		value, _ = self.ask([""], default=5)
		self.assertEqual(value, 5)

	def test_quit_words_cancel(self):
		for word in ("q", "Q", "quit", "exit"):
			value, _ = self.ask([word])
			self.assertIsNone(value)

	def test_eof_cancels_instead_of_looping(self):
		# The regression: no answers means `input` raises EOFError on the very
		# first read. Before the fix this returned immediately without
		# cancelling and called `input` again, without bound.
		value, script = self.ask([])
		self.assertIsNone(value)
		self.assertEqual(len(script.prompts), 1)

	def test_ctrl_c_cancels_instead_of_looping(self):
		script = Scripted([])
		calls = []

		def interrupt(label=""):
			calls.append(label)
			raise KeyboardInterrupt

		with mock.patch("builtins.input", interrupt):
			self.assertIsNone(prompts.ask_int("Count", 1, 10))
		self.assertEqual(len(calls), 1)

	def test_blank_without_default_still_re_prompts(self):
		value, script = self.ask(["", "", "2"])
		self.assertEqual(value, 2)
		self.assertEqual(len(script.prompts), 3)


class AskChoiceTests(unittest.TestCase):
	def ask(self, answers):
		with mock.patch("builtins.input", Scripted(answers)), \
				mock.patch("builtins.print"):
			return prompts.ask_choice("Pick", ["a", "b", "c"])

	def test_choice_is_zero_based(self):
		self.assertEqual(self.ask(["2"]), 1)

	def test_out_of_range_is_cancel(self):
		self.assertIsNone(self.ask(["9"]))

	def test_eof_is_cancel(self):
		self.assertIsNone(self.ask([]))

	def test_empty_option_list_is_cancel(self):
		self.assertIsNone(prompts.ask_choice("Pick", []))


if __name__ == "__main__":
	unittest.main()
