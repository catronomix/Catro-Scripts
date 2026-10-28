# Masked secret intake and page blocks for sanitize.py
"""
			SANITIZE INTAKE AND PAGE
			=======================
Pins the secret-intake contract (issue 0041): argv keeps working unchanged, a
terminal may be prompted for a missing secret through `getpass` (no echo), the
prompt row is blanked in a `finally`, the temporary replacement file is always
removed, and an off-tty run with no argv secret refuses with one stderr line and
exit 2 instead of blocking.

Every test drives `sanitize.main()` in-process with git and filter-repo patched,
so no repository is read, rewritten or created.

Run with:
	python -m unittest discover -s tests -v
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))

import tui  # noqa: E402  (import after sys.path setup)
import sanitize  # noqa: E402
from support import clean_env  # noqa: E402  (test helper, not production)

FRAME = "\u250c"
TTY_TRUE = tui.Capabilities(level="true", unicode=True, width=80, isatty=True,
							plain=False, reason="test")
TTY_16 = tui.Capabilities(level="16", unicode=True, width=80, isatty=True,
						  plain=False, reason="test")
TTY_NONE = tui.Capabilities(level="none", unicode=True, width=80, isatty=True,
							plain=False, reason="test")
NARROW = tui.Capabilities(level="true", unicode=True, width=48, isatty=True,
						  plain=False, reason="test")
PIPE = tui.Capabilities(level="none", unicode=False, width=None, isatty=False,
						plain=True, reason="test")


class FakeStream:
	"""A tty-able stream: writes are captured, `isatty` is the argument."""

	def __init__(self, tty):
		self.buffer = io.StringIO()
		self._tty = tty
		self.encoding = "utf-8"

	def write(self, text):
		return self.buffer.write(text)

	def flush(self):
		pass

	def isatty(self):
		return self._tty

	def getvalue(self):
		return self.buffer.getvalue()


def ok_run(stdout="", returncode=0):
	return mock.Mock(returncode=returncode, stdout=stdout, stderr="")


class SanitizeTest(unittest.TestCase):
	"""Shared driver: git, the backend and both streams are patched."""

	def setUp(self):
		self.stdout = FakeStream(tty=False)
		self.stderr = FakeStream(tty=True)
		self.history = mock.Mock(return_value=False)
		self.repo_patch = mock.patch.object(
			sanitize, "find_repo_root", return_value=(Path("/tmp/repo"), ""))
		self.filter_patch = mock.patch.object(
			sanitize, "find_filter_repo", return_value=["git", "filter-repo"])
		self.history_patch = mock.patch.object(
			sanitize, "secret_in_history", self.history)
		self.run_patch = mock.patch.object(sanitize, "run", return_value=ok_run())
		for patcher in (self.repo_patch, self.filter_patch,
						self.history_patch, self.run_patch):
			patcher.start()
			self.addCleanup(patcher.stop)

	def run_main(self, argv, stdin=None):
		with mock.patch.dict(os.environ, clean_env(), clear=True), \
				mock.patch.object(tui, "init_ansi"), \
				mock.patch.object(sys, "argv", ["sanitize.py", *argv]), \
				mock.patch.object(sys, "stdout", self.stdout), \
				mock.patch.object(sys, "stderr", self.stderr):
			if stdin is not None:
				with mock.patch.object(sys, "stdin", stdin):
					return sanitize.main()
			return sanitize.main()

	def test_argv_secret_is_used_unchanged(self):
		rc = self.run_main(["SECRET", "<redacted>", "--yes"])
		self.assertEqual(rc, 0)
		self.history.assert_called_once_with("SECRET")
		out = self.stdout.getvalue()
		self.assertIn("SANITIZE PLAN", out)
		self.assertIn("<redacted>", out)
		self.assertNotIn("SECRET", out, "the argv secret was printed")

	def test_argv_secret_still_wins_over_the_prompt(self):
		getpass_ = mock.patch.object(sanitize.getpass, "getpass").start()
		self.addCleanup(mock.patch.stopall)
		rc = self.run_main(["SECRET", "<redacted>", "--yes"],
						   stdin=FakeStream(tty=True))
		self.assertEqual(rc, 0)
		getpass_.assert_not_called()

	def test_terminal_prompt_reads_a_masked_secret(self):
		with mock.patch.object(sanitize.getpass, "getpass",
							   return_value="PROMPTED") as getpass_:
			rc = self.run_main(["--yes"], stdin=FakeStream(tty=True))
		self.assertEqual(rc, 0)
		getpass_.assert_called_once()
		self.history.assert_called_once_with("PROMPTED")
		page = self.stdout.getvalue() + self.stderr.getvalue()
		self.assertNotIn("PROMPTED", page, "the prompted secret was printed")
		self.assertIn("<redacted>", self.stdout.getvalue())

	def test_prompt_row_is_blanked_in_a_finally(self):
		with mock.patch.object(sanitize.getpass, "getpass",
							   return_value="PROMPTED"):
			self.run_main(["--yes"], stdin=FakeStream(tty=True))
		self.assertIn(tui.screen.ERASE_ROW_UP, self.stderr.getvalue(),
					  "the prompt row was left on screen")

	def test_prompt_row_is_blanked_when_the_prompt_is_aborted(self):
		with mock.patch.object(sanitize.getpass, "getpass",
							   side_effect=EOFError):
			rc = self.run_main(["--yes"], stdin=FakeStream(tty=True))
		self.assertEqual(rc, 1)
		self.assertIn("Aborted.", self.stdout.getvalue())
		self.assertIn(tui.screen.ERASE_ROW_UP, self.stderr.getvalue())

	def test_off_tty_without_a_secret_refuses_with_exit_2(self):
		getpass_ = mock.patch.object(sanitize.getpass, "getpass").start()
		self.addCleanup(mock.patch.stopall)
		rc = self.run_main(["--yes"], stdin=FakeStream(tty=False))
		self.assertEqual(rc, 2)
		getpass_.assert_not_called()
		self.assertIn("interactive terminal", self.stderr.getvalue())
		self.assertEqual(self.stdout.getvalue(), "")

	def test_temp_replace_file_is_removed_when_history_matches(self):
		self.history.return_value = True
		created = []
		real = tempfile.NamedTemporaryFile

		def tracked(*args, **kwargs):
			handle = real(*args, **kwargs)
			created.append(handle.name)
			return handle

		fake_tempfile = mock.Mock(NamedTemporaryFile=tracked)
		with mock.patch.object(sanitize, "tempfile", fake_tempfile), \
				mock.patch.object(sanitize.subprocess, "run",
								  return_value=ok_run()):
			rc = self.run_main(["SECRET", "<redacted>", "--yes"])
		self.assertEqual(rc, 0)
		self.assertEqual(len(created), 1, "no replacement file was written")
		self.assertFalse(os.path.exists(created[0]),
						 "the temp replacement file survived the run")
		self.assertNotIn("SECRET", self.stdout.getvalue())

	def test_the_successful_page_shows_the_whole_force_push(self):
		self.history.return_value = True
		with mock.patch.object(sanitize.subprocess, "run",
							   return_value=ok_run()):
			rc = self.run_main(["SECRET", "<redacted>", "--yes"])
		self.assertEqual(rc, 0)
		out = self.stdout.getvalue()
		self.assertIn("git push --force --all && git push --force --tags", out)
		self.assertIn("Rotate the leaked secret", out)

	def test_one_positional_is_a_usage_error(self):
		"""The prompt form takes no positional: never read it as the secret."""
		getpass_ = mock.patch.object(sanitize.getpass, "getpass").start()
		self.addCleanup(mock.patch.stopall)
		stderr = io.StringIO()
		with mock.patch.object(sys, "stderr", stderr), \
				self.assertRaises(SystemExit) as caught:
			self.run_main(["<redacted>", "--yes"])
		self.assertEqual(caught.exception.code, 2)
		self.assertIn("both the secret and the placeholder",
					  self.stderr.getvalue())
		getpass_.assert_not_called()
		self.history.assert_not_called()


class SanitizePlanPageTest(unittest.TestCase):
	"""The PLAN and NEXT STEPS boxes are a tty frame around complete values."""

	PLAN = [("Repo", "/tmp/repo"), ("Secret", "<redacted>"),
			("Placeholder", "<redacted>"), ("Backend", "git filter-repo")]
	STEPS = [
		("1. Force-push", "git push --force --all && git push --force --tags"),
		("2. Teammates", "Everyone else must re-clone"),
		("3. Rotation", "Rotate the leaked secret"),
	]

	@staticmethod
	def text(out):
		"""The page's words: no frame glyphs, no escapes, single spaces."""
		plain = tui.strip_ansi(out)
		for glyph in "─│┌┐└┘":
			plain = plain.replace(glyph, " ")
		return " ".join(plain.split())

	def test_true_colour_draws_a_centred_frame(self):
		out = sanitize.plan_block("SANITIZE PLAN", self.PLAN, TTY_TRUE)
		self.assertIn(FRAME, out, out)
		self.assertIn("\x1b[38;2;", out)
		self.assertEqual(len(out.splitlines()), len(self.PLAN) + 2)
		self.assertIn("SANITIZE PLAN", tui.strip_ansi(out))

	def test_level_16_keeps_the_frame_and_drops_truecolour(self):
		out = sanitize.plan_block("SANITIZE PLAN", self.PLAN, TTY_16)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("38;2;", out)
		self.assertNotIn("48;2;", out)

	def test_level_none_keeps_the_layout_and_drops_every_escape(self):
		out = sanitize.plan_block("SANITIZE PLAN", self.PLAN, TTY_NONE)
		self.assertIn(FRAME, out, out)
		self.assertNotIn("\x1b", out)

	def test_plain_keeps_the_tab_records(self):
		out = sanitize.plan_block("SANITIZE PLAN", self.PLAN, PIPE)
		self.assertEqual(
			out,
			"SANITIZE PLAN\n"
			"Repo\t/tmp/repo\n"
			"Secret\t<redacted>\n"
			"Placeholder\t<redacted>\n"
			"Backend\tgit filter-repo")

	def test_plain_next_steps_records_are_unchanged(self):
		out = sanitize.plan_block("NEXT STEPS", self.STEPS, PIPE)
		self.assertEqual(
			out,
			"NEXT STEPS\n"
			"1. Force-push\tgit push --force --all && git push --force --tags\n"
			"2. Teammates\tEveryone else must re-clone\n"
			"3. Rotation\tRotate the leaked secret")

	def test_the_force_push_command_survives_every_width(self):
		for label, cap in (("80", TTY_TRUE), ("48", NARROW)):
			with self.subTest(width=label):
				out = sanitize.plan_block("NEXT STEPS", self.STEPS, cap)
				text = self.text(out)
				self.assertIn(
					"git push --force --all && git push --force --tags", text)
				self.assertNotIn("..", text)
				self.assertIn("Rotate the leaked secret", text)

	def test_a_long_repo_path_wraps_instead_of_truncating(self):
		repo = "C:/Users/catronomix/GITHUB/a-really-long-repository-name"
		out = sanitize.plan_block("SANITIZE PLAN",
								  [("Repo", repo), ("Secret", "<redacted>")],
								  NARROW)
		text = self.text(out)
		self.assertIn(repo, text.replace(" ", ""))
		self.assertNotIn("..", text)


class SanitizePromptRowTest(unittest.TestCase):
	"""The prompt-row erase is the shared seam and only on a capable tty."""

	def test_erase_writes_the_shared_seam_on_a_tty(self):
		stream = FakeStream(tty=True)
		sanitize.blank_prompt_row(TTY_16, stream)
		self.assertEqual(stream.getvalue(), tui.screen.ERASE_ROW_UP)

	def test_erase_is_silent_off_a_tty(self):
		stream = FakeStream(tty=False)
		sanitize.blank_prompt_row(TTY_TRUE, stream)
		self.assertEqual(stream.getvalue(), "")

	def test_erase_is_silent_when_the_run_asked_for_no_escapes(self):
		stream = FakeStream(tty=True)
		sanitize.blank_prompt_row(TTY_NONE, stream)
		self.assertEqual(stream.getvalue(), "")

	def test_erase_is_silent_on_a_stream_without_isatty(self):
		class Bare:
			def write(self, text):
				raise AssertionError("wrote to a stream without isatty")

		sanitize.blank_prompt_row(TTY_TRUE, Bare())

	def test_erase_is_silent_when_a_windows_console_rejects_vt(self):
		"""A console without VT support would type the erase bytes out."""
		stream = FakeStream(tty=True)
		stream.fileno = lambda: 1
		with mock.patch.object(sanitize.os, "name", "nt"), \
				mock.patch.object(tui.console_vt, "can_vt",
								  return_value=False) as probe:
			sanitize.blank_prompt_row(TTY_TRUE, stream)
		self.assertEqual(stream.getvalue(), "")
		probe.assert_called_once_with(stream)


if __name__ == "__main__":
	unittest.main()
