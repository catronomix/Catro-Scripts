# Regression tests for mdreader.py
"""
    Preflight / dependency behaviour of the terminal Markdown reader.

    Cover issue #11: importing mdreader must never install anything or touch the
    network, --help must work without a tty, the 8-colour palette must not
    abort, and an unexpected render failure must exit 1 with the message on
    stderr.
"""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "mdreader.py"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import mdreader  # noqa: E402  (import after sys.path setup)


def run_script(*args):
    """Runs mdreader.py with stdin from DEVNULL, exactly like a CI caller."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )


class _FakeCursesError(Exception):
    """Stand-in for curses.error."""


class _FakeCurses:
    """Minimal 8-colour curses module: rejects any index above COLORS-1."""

    COLORS = 8
    error = _FakeCursesError

    COLOR_BLACK = 0
    COLOR_RED = 1
    COLOR_GREEN = 2
    COLOR_YELLOW = 3
    COLOR_BLUE = 4
    COLOR_MAGENTA = 5
    COLOR_CYAN = 6
    COLOR_WHITE = 7

    def __init__(self):
        self.pairs = []

    def start_color(self):
        pass

    def can_change_color(self):
        return False

    def init_color(self, _number, _r, _g, _b):
        raise _FakeCursesError("terminal cannot change colours")

    def init_pair(self, pair, fg, bg):
        if not 0 <= fg <= self.COLORS - 1 or not 0 <= bg <= self.COLORS - 1:
            raise _FakeCursesError(
                f"Color number is greater than COLORS-1 ({self.COLORS - 1})"
            )
        self.pairs.append((pair, fg, bg))


class MdreaderPreflightTests(unittest.TestCase):
    def test_import_is_side_effect_free(self):
        """`python -S -c "import mdreader"`: no output, no install, exit 0."""
        proc = subprocess.run(
            [sys.executable, "-S", "-c", "import mdreader"],
            cwd=str(REPO),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        self.assertEqual(
            proc.returncode, 0, proc.stderr.decode("utf-8", "replace")
        )
        self.assertEqual(proc.stdout, b"")
        self.assertEqual(proc.stderr, b"")

    def test_help_without_a_tty(self):
        proc = run_script("--help")
        stdout = proc.stdout.decode("utf-8", "replace")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn("usage:", stdout)
        self.assertIn("file", stdout)
        self.assertNotIn("Traceback", stdout)

    def test_tty_still_refused(self):
        proc = run_script()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b"")
        self.assertIn(b"interactive terminal", proc.stderr)

    def test_palette_survives_eight_colours(self):
        fake = _FakeCurses()
        with mock.patch.object(mdreader, "curses", fake):
            for theme_mode in (0, 1, 2):
                mdreader.init_cozy_colors(theme_mode)
        self.assertTrue(fake.pairs)
        for _pair, fg, bg in fake.pairs:
            self.assertLessEqual(fg, fake.COLORS - 1)
            self.assertLessEqual(bg, fake.COLORS - 1)

    def test_cozy_palette_kept_on_256_colours(self):
        """A full-colour terminal still gets the original cozy-purple pairs."""
        fake = _FakeCurses()
        fake.COLORS = 256
        fake.can_change_color = lambda: True
        fake.init_color = lambda *_args: None
        with mock.patch.object(mdreader, "curses", fake):
            mdreader.init_cozy_colors(0)
        # Pair 1 is text-on-background using the RGB palette (16..24).
        pair_numbers = [pair for pair, _fg, _bg in fake.pairs]
        self.assertEqual(pair_numbers, [1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(fake.pairs[0], (1, 19, 16))

    def test_rich_themes_follow_the_shared_palette(self):
        """Modes 0/1/2 draw their Rich colours from soft/contrast-* hexes."""
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        self.assertEqual(mdreader.THEME_MODES,
                         ("soft", "contrast-light", "contrast-dark"))
        headers = []
        for mode, theme_id in enumerate(mdreader.THEME_MODES):
            colours = mdreader.tui.palette.palette(theme_id)
            styles = mdreader.get_rich_theme(mode).styles
            for spec, key in (("markdown.h1", "header"),
                              ("markdown.table.border", "border"),
                              ("markdown.block_quote", "muted")):
                with self.subTest(mode=mode, style=spec):
                    self.assertIn(colours[key].lower(), str(styles[spec].color))
            with self.subTest(mode=mode, style="markdown.code"):
                self.assertIn(colours["fg"].lower(), str(styles["markdown.code"].color))
                self.assertIn(colours["surface"].lower(),
                              str(styles["markdown.code"].bgcolor))
            headers.append(str(styles["markdown.h1"].color))
        self.assertEqual(len(set(headers)), 3, "the three modes must differ")

    def test_missing_dependency_reports_hint(self):
        with mock.patch.object(mdreader, "curses", None), mock.patch.object(
            mdreader, "Theme", None
        ), mock.patch.object(mdreader, "require_tty"), mock.patch.object(
            sys, "argv", ["mdreader.py"]
        ), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr, contextlib.redirect_stdout(
            io.StringIO()
        ) as stdout:
            with self.assertRaises(SystemExit) as caught:
                mdreader.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("pip install rich", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_unexpected_error_exits_one_with_stderr_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "doc.md"
            doc.write_text("# hello\n", encoding="utf-8")
            with mock.patch.object(mdreader, "require_tty"), mock.patch.object(
                mdreader, "missing_dependencies", return_value=[]
            ), mock.patch.object(
                mdreader.curses, "wrapper", side_effect=RuntimeError("boom")
            ), mock.patch.object(
                sys, "argv", ["mdreader.py", str(doc)]
            ), mock.patch(
                "sys.stderr", new_callable=io.StringIO
            ) as stderr, contextlib.redirect_stdout(
                io.StringIO()
            ) as stdout:
                with self.assertRaises(SystemExit) as caught:
                    mdreader.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("boom", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_keyboard_interrupt_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "doc.md"
            doc.write_text("# hello\n", encoding="utf-8")
            with mock.patch.object(mdreader, "require_tty"), mock.patch.object(
                mdreader, "missing_dependencies", return_value=[]
            ), mock.patch.object(
                mdreader.curses, "wrapper", side_effect=KeyboardInterrupt
            ), mock.patch.object(
                sys, "argv", ["mdreader.py", str(doc)]
            ):
                self.assertIsNone(mdreader.main())

    def test_no_shell_true(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main()
