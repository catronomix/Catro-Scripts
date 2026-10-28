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
import os
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
    COLOR_DEFAULT = -1

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
        if fg == self.COLOR_DEFAULT and bg == self.COLOR_DEFAULT:
            self.pairs.append((pair, fg, bg))
            return
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
        self.assertEqual(
            proc.stderr.decode("utf-8", "replace").replace("\r\n", "\n"),
            "[Error] mdreader needs an interactive terminal "
            "(stdin/stdout is not a tty).\n",
        )

    def test_markdown_file_on_a_pipe_is_refused_before_reading(self):
        """Non-tty is one contract line + exit 2, not a plain render."""
        proc = run_script("README.md")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b"")
        self.assertEqual(
            proc.stderr.decode("utf-8", "replace").replace("\r\n", "\n"),
            "[Error] mdreader needs an interactive terminal "
            "(stdin/stdout is not a tty).\n",
        )

    def test_no_color_falls_back_to_terminal_defaults(self):
        """cap.level "none" keeps the layout and drops every colour."""
        fake = _FakeCurses()
        cap = mdreader.tui.caps.Capabilities(
            level="none", unicode=True, width=80, isatty=True,
            plain=False, reason="NO_COLOR",
        )
        with mock.patch.object(mdreader, "curses", fake):
            mdreader.init_theme_colors(0, cap)
        self.assertEqual(
            fake.pairs,
            [(pair, fake.COLOR_DEFAULT, fake.COLOR_DEFAULT)
             for pair, _fg, _bg in mdreader.PAIR_ROLES],
        )

    def test_palette_survives_eight_colours(self):
        fake = _FakeCurses()
        with mock.patch.object(mdreader, "curses", fake):
            for theme_mode in (0, 1, 2):
                fake.pairs = []
                mdreader.init_theme_colors(theme_mode)
                self.assertEqual(
                    [pair for pair, _fg, _bg in fake.pairs],
                    [pair for pair, _fg, _bg in mdreader.PAIR_ROLES],
                )
                for _pair, fg, bg in fake.pairs:
                    self.assertLessEqual(fg, fake.COLORS - 1)
                    self.assertLessEqual(bg, fake.COLORS - 1)

    def test_rgb_palette_derived_from_the_house_theme(self):
        """A redefinable terminal gets the mode's palette in exact RGB slots."""
        fake = _FakeCurses()
        fake.COLORS = 256
        fake.can_change_color = lambda: True
        calls = []

        def init_color(slot, red, green, blue):
            calls.append((slot, red, green, blue))

        fake.init_color = init_color
        with mock.patch.object(mdreader, "curses", fake):
            mdreader.init_theme_colors(0)
        soft = mdreader.tui.palette.SOFT
        # Pair 1 is fg on bg, in the first two RGB slots above the base 16.
        self.assertEqual(fake.pairs[0], (1, 16, 17))
        self.assertEqual(
            calls[0],
            (16,) + tuple(round(c * 1000 / 255)
                          for c in mdreader.tui.palette.rgb(soft["fg"])),
        )
        self.assertEqual(
            calls[1],
            (17,) + tuple(round(c * 1000 / 255)
                          for c in mdreader.tui.palette.rgb(soft["bg"])),
        )

    def test_init_color_refusal_falls_back_to_nearest_indices(self):
        """A terminal that claims RGB support and then refuses still gets pairs."""
        fake = _FakeCurses()
        fake.COLORS = 256
        fake.can_change_color = lambda: True
        with mock.patch.object(mdreader, "curses", fake):
            mdreader.init_theme_colors(0)
        self.assertEqual(
            [pair for pair, _fg, _bg in fake.pairs],
            [pair for pair, _fg, _bg in mdreader.PAIR_ROLES],
        )
        for _pair, fg, bg in fake.pairs:
            self.assertTrue(0 <= fg <= 255)
            self.assertTrue(0 <= bg <= 255)

    def test_chrome_pairs_are_palette_roles(self):
        """Background, frame and both bars come from the shared palette keys.

        The reader keeps its own curses renderer, so the gate is the pair map:
        the window fill is `bg`, the frame `border-fg` on the `border-bg` band,
        the status line/thumb a `border-bg` chip on `border-fg`, and the
        shortcut bar `fg`-on-`bg-stripe`, which is the vocabulary `tui.chrome`
        uses for a page.
        """
        expected = {
            "window": ("fg", "bg"),
            "frame": ("border-fg", "border-bg"),
            "thumb": ("border-bg", "border-fg"),
            "status": ("border-bg", "border-fg"),
            "shortcuts": ("fg", "bg-stripe"),
        }
        roles = {pair: (fg, bg) for pair, fg, bg in mdreader.PAIR_ROLES}
        self.assertEqual(
            {name: roles[pair] for name, pair in mdreader.CHROME_PAIRS.items()},
            expected,
        )
        for theme in mdreader.THEME_MODES:
            colours = mdreader.tui.palette.palette(theme)
            for fg, bg in expected.values():
                with self.subTest(theme=theme, fg=fg, bg=bg):
                    self.assertIn(fg, colours)
                    self.assertIn(bg, colours)
            for _pair, fg, bg in mdreader.PAIR_ROLES:
                with self.subTest(theme=theme, pair=(fg, bg)):
                    self.assertIn(fg, colours, "every pair is a palette role")
                    self.assertIn(bg, colours, "every pair is a palette role")

    def test_each_mode_paints_its_own_palette(self):
        fake = _FakeCurses()
        fake.COLORS = 256
        painted = []
        with mock.patch.object(mdreader, "curses", fake):
            for theme_mode in range(len(mdreader.THEME_MODES)):
                fake.pairs = []
                mdreader.init_theme_colors(theme_mode)
                painted.append(tuple(fake.pairs))
        self.assertEqual(len(set(painted)), 3)

    def test_segment_pairs_follow_palette_roles(self):
        """Every mode classifies the same Rich styles to the same pair roles."""
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        from rich.style import Style

        for mode, theme in enumerate(mdreader.THEME_MODES):
            colours = mdreader.tui.palette.palette(theme)
            cases = (
                ("heading", Style(color=colours["button-bg-active"], bold=True),
                 2),
                ("link", Style(color=colours["fg-warn"], underline=True), 3),
                ("table cell", Style(color=colours["fg"],
                                     bgcolor=colours["bg-inside"]), 4),
                ("quote", Style(color=colours["fg-muted"], italic=True), 5),
                # contrast-light uses the same fill for surface and zebra, so a
                # zebra row is indistinguishable from a normal cell there.
                ("zebra", Style(color=colours["fg"],
                                bgcolor=colours["bg-stripe"]),
                 7 if colours["bg-stripe"].lower() != colours["bg-inside"].lower()
                 else 4),
                ("table header", Style(color=colours["button-bg-active"],
                                       bgcolor=colours["bg-inside"]),
                 # contrast-dark's border-fg is its button-bg-active, and both
                 # grounds are the same hex there, so the border rule claims the
                 # header cells too; the pixels are identical.
                 10 if colours["border-fg"].lower()
                 == colours["button-bg-active"].lower() else 9),
                # Inline code: the accent ink on the surface fill. Shipped looks
                # repeat `fg-accent` in `button-bg-active`, so it lands on the
                # heading/header pair (identical pixels) instead of pair 11.
                ("inline code", Style(color=colours["fg-accent"],
                                      bgcolor=colours["bg-inside"]),
                 10 if colours["border-fg"].lower()
                 == colours["fg-accent"].lower() != colours["fg"].lower()
                 else 9 if colours["fg-accent"].lower()
                 == colours["button-bg-active"].lower() else 11),
                # Fenced code carries Rich's own syntax theme (monokai's fixed
                # greens on their own ground); it must take the code pair, not
                # leak the syntax palette.
                ("fenced code", Style(color="#a6e22e", bgcolor="#272822"), 11),
            )
            for role, style, expected in cases:
                with self.subTest(mode=mode, role=role):
                    self.assertEqual(
                        mdreader.segment_pair(style, colours), expected)
            with self.subTest(mode=mode, role="body"):
                self.assertEqual(mdreader.segment_pair(None, colours), 1)

    def test_rendered_document_carries_mode_pairs(self):
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        for mode in range(len(mdreader.THEME_MODES)):
            with self.subTest(mode=mode):
                doc = mdreader.process_markdown_rich(
                    "# Title\n\n> quote\n\n| a |\n|---|\n| b |\n", 40, mode
                )
                pairs = {seg.color for line in doc for seg in line.segments}
                self.assertIn(2, pairs, "the heading keeps the accent pair")

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
            for spec, key in (("markdown.h1", "button-bg-active"),
                              ("markdown.h2", "button-bg-active"),
                              ("markdown.h3", "button-bg-active"),
                              ("markdown.h4", "fg-muted"),
                              ("markdown.item.bullet", "button-bg-active"),
                              ("markdown.item.number", "button-bg-active"),
                              ("markdown.table.header", "button-bg-active"),
                              ("markdown.block_quote", "fg-muted"),
                              ("markdown.link", "fg-warn"),
                              ("markdown.link_url", "fg-warn")):
                with self.subTest(mode=mode, style=spec):
                    self.assertIn(colours[key].lower(), str(styles[spec].color))
            for spec in ("markdown.code", "markdown.code_block"):
                with self.subTest(mode=mode, style=spec):
                    # Inline and fenced code: the accent ink on the surface
                    # fill, never the fixed green of Rich's syntax theme.
                    self.assertIn(colours["fg-accent"].lower(),
                                  str(styles[spec].color))
                    self.assertIn(colours["bg-inside"].lower(),
                                  str(styles[spec].bgcolor))
            with self.subTest(mode=mode, style="markdown.table.border"):
                border = styles["markdown.table.border"]
                self.assertIn(colours["border-fg"].lower(), str(border.color))
                self.assertIn(colours["border-bg"].lower(), str(border.bgcolor))
            headers.append(str(styles["markdown.h1"].color))
        self.assertEqual(len(set(headers)), 3, "the three modes must differ")

    def test_initial_mode_follows_the_configured_theme(self):
        """The reader opens in the theme `theme`/CATRO_THEME selects."""
        with mock.patch.dict(os.environ, {"CATRO_THEME": "contrast-dark"}):
            self.assertEqual(mdreader.initial_theme_mode(), 2)
        with mock.patch.dict(os.environ, {"CATRO_THEME": "light"}):
            self.assertEqual(mdreader.initial_theme_mode(), 1)
        with mock.patch.dict(os.environ, {"CATRO_THEME": "soft"}):
            self.assertEqual(mdreader.initial_theme_mode(), 0)

    def test_missing_dependency_reports_hint(self):
        with mock.patch.object(mdreader, "curses", None), mock.patch.object(
            mdreader, "Theme", None
        ), mock.patch.object(mdreader.tui, "require_tty"), mock.patch.object(
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
            with mock.patch.object(mdreader.tui, "require_tty"), mock.patch.object(
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
            with mock.patch.object(mdreader.tui, "require_tty"), mock.patch.object(
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


class MdreaderColourMappingTests(unittest.TestCase):
    """Task 0041 batch C: what the reader paints, pinned against the palette.

    Each case mirrors a mismatch the 100x30 pty capture proved and fixed: the
    reader must enter colour mode before asking for default colours, links must
    carry the warn pair (Rich styles the visible url through `link_url`, not
    `link`) and table borders must carry the frame colour on the `border-bg`
    band.
    """

    def test_start_color_precedes_use_default_colors(self):
        """Curses refuses use_default_colors() until start_color() ran."""
        order = []

        class _OrderCurses:
            error = _FakeCursesError

            def start_color(self):
                order.append("start_color")

            def use_default_colors(self):
                if "start_color" not in order:
                    raise _FakeCursesError("must call start_color() first")
                order.append("use_default_colors")

            def curs_set(self, _visibility):
                order.append("curs_set")

        stdscr = mock.Mock()
        stdscr.keypad.side_effect = KeyboardInterrupt
        with mock.patch.object(mdreader, "curses", _OrderCurses()), \
                mock.patch.object(mdreader, "init_theme_colors"), \
                mock.patch.object(mdreader, "get_directory_md_files",
                                  return_value=(os.getcwd(), [])):
            with self.assertRaises(KeyboardInterrupt):
                mdreader.render_reader(stdscr, "doc.md", "# hi\n")
        self.assertEqual(order[:2], ["start_color", "use_default_colors"])

    def test_links_carry_the_warn_pair_and_underline(self):
        """The rewritten visible url still gets the link pair in every mode."""
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        for mode in range(len(mdreader.THEME_MODES)):
            with self.subTest(mode=mode):
                doc = mdreader.process_markdown_rich(
                    "[site](https://example.com)", 60, mode)
                links = [seg for line in doc for seg in line.segments
                         if "example.com" in seg.text]
                self.assertTrue(links, "the visible url must stay in the text")
                for seg in links:
                    self.assertEqual(seg.color, 3)
                    self.assertTrue(seg.attr & mdreader.curses.A_UNDERLINE)

    def test_rich_theme_styles_the_hyperlinked_url(self):
        """Rich paints the url itself with `markdown.link_url`."""
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        for mode, theme_id in enumerate(mdreader.THEME_MODES):
            colours = mdreader.tui.palette.palette(theme_id)
            style = mdreader.get_rich_theme(mode).styles["markdown.link_url"]
            with self.subTest(mode=mode):
                self.assertIn(colours["fg-warn"].lower(), str(style.color))

    def test_table_borders_take_the_border_pair(self):
        """Borders sit on the `border-bg` band with the frame colour.

        contrast-light's border-fg *is* its fg (and its border-bg is its
        bg-inside), so there the border is pair 4 like any surface text (same
        colours, hence visually identical).
        """
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        for mode, theme_id in enumerate(mdreader.THEME_MODES):
            colours = mdreader.tui.palette.palette(theme_id)
            expected = (
                4 if colours["border-fg"].lower() == colours["fg"].lower()
                else 10
            )
            with self.subTest(mode=mode):
                doc = mdreader.process_markdown_rich(
                    "| aa | bb |\n|----|----|\n| 11 | 22 |\n", 40, mode)
                # Rich picks ASCII or box-drawing glyphs by terminal, so match
                # any segment made only of border characters.
                glyphs = set("|+-│┌┐└┘├┤┬┴┼─")
                borders = {
                    seg.color for line in doc for seg in line.segments
                    if seg.text and set(seg.text) <= glyphs
                }
                self.assertEqual(borders, {expected})

    def test_border_role_is_its_own_pair(self):
        """Pair 10 is border-fg on border-bg, so the pair table explains it."""
        roles = {pair: (fg, bg) for pair, fg, bg in mdreader.PAIR_ROLES}
        self.assertEqual(roles[10], ("border-fg", "border-bg"))
        self.assertEqual(roles[8], ("border-fg", "border-bg"))
        self.assertEqual(roles[6], ("border-bg", "border-fg"))
        self.assertEqual(roles[2], ("button-bg-active", "bg"))
        self.assertEqual(roles[3], ("fg-warn", "bg"))
        self.assertEqual(roles[9], ("button-bg-active", "bg-inside"))
        self.assertEqual(roles[11], ("fg-accent", "bg-inside"))
        self.assertEqual(len(roles), len(mdreader.PAIR_ROLES),
                         "pair numbers must stay unique")

    def test_link_rewrite_leaves_fences_and_code_spans_alone(self):
        """A document that shows link syntax must render it as written."""
        source = (
            "```\n[x](https://example.com/a)\n```\n\n"
            "~~~\n[y](https://example.com/b)\n~~~\n\n"
            "Use `[z](https://example.com/c)` here, or [site](https://example.com/d).\n"
        )
        rewritten = mdreader.linkify(source)
        for literal in ("[x](https://example.com/a)",
                        "[y](https://example.com/b)",
                        "`[z](https://example.com/c)`"):
            with self.subTest(literal=literal):
                self.assertIn(literal, rewritten)
        self.assertIn("[https://example.com/d](https://example.com/d)",
                      rewritten)

    def test_rendered_code_keeps_its_link_syntax(self):
        """End to end: the fence and the span survive the Rich pass verbatim."""
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        source = ("```\n[x](https://example.com/a)\n```\n\n"
                  "Use `[z](https://example.com/c)` here.\n")
        doc = mdreader.process_markdown_rich(source, 80, 0)
        text = "\n".join(seg.text for line in doc for seg in line.segments)
        self.assertIn("[x](https://example.com/a)", text)
        self.assertIn("[z](https://example.com/c)", text)
        self.assertNotIn("[https://example.com/a]", text)
        self.assertNotIn("[https://example.com/c]", text)

    def test_link_rewrite_skips_indented_code_blocks(self):
        """Four spaces or a tab start a code block: the sample stays literal."""
        source = ("    [a](https://example.com/a)\n\n"
                  "\t[b](https://example.com/b)\n\n"
                  "[c](https://example.com/c)\n")
        rewritten = mdreader.linkify(source)
        self.assertIn("    [a](https://example.com/a)", rewritten)
        self.assertIn("\t[b](https://example.com/b)", rewritten)
        self.assertIn("[https://example.com/c](https://example.com/c)",
                      rewritten)

    def test_link_rewrite_skips_a_fence_inside_a_blockquote(self):
        """A quoted ``` still opens a code block, so its sample is literal."""
        source = ("> ```md\n"
                  "> [a](https://example.com/a)\n"
                  "> ```\n\n"
                  "[b](https://example.com/b)\n")
        rewritten = mdreader.linkify(source)
        self.assertIn("> [a](https://example.com/a)", rewritten)
        self.assertNotIn("[https://example.com/a]", rewritten)
        self.assertIn("[https://example.com/b](https://example.com/b)",
                      rewritten)

    def test_link_rewrite_keeps_multi_backtick_spans(self):
        """A span closes on a run of equal length, ticks inside and all."""
        source = ("Use ``code with ` tick [a](https://example.com/a)`` here, "
                  "then [b](https://example.com/b).\n")
        rewritten = mdreader.linkify(source)
        self.assertIn("``code with ` tick [a](https://example.com/a)``",
                      rewritten)
        self.assertNotIn("[https://example.com/a]", rewritten)
        self.assertIn("[https://example.com/b](https://example.com/b)",
                      rewritten)

    def test_link_rewrite_leaves_an_escaped_bracket_alone(self):
        """`\\[x](url)` shows link syntax, so it is not a link."""
        source = "\\[a](https://example.com/a) then [b](https://example.com/b)\n"
        rewritten = mdreader.linkify(source)
        self.assertIn("\\[a](https://example.com/a)", rewritten)
        self.assertNotIn("[https://example.com/a]", rewritten)
        self.assertIn("[https://example.com/b](https://example.com/b)",
                      rewritten)

    def test_rendered_code_samples_stay_verbatim(self):
        """End to end: every skipped shape reaches the screen as written."""
        if mdreader.Theme is None:
            self.skipTest("rich is not installed")
        source = ("    [a](https://example.com/a)\n\n"
                  "> ```md\n"
                  "> [b](https://example.com/b)\n"
                  "> ```\n\n"
                  "\t[c](https://example.com/c)\n\n"
                  "``tick ` [d](https://example.com/d)``\n\n"
                  "\\[e](https://example.com/e)\n\n"
                  "[f](https://example.com/f)\n")
        doc = mdreader.process_markdown_rich(source, 80, 0)
        text = "".join(seg.text for line in doc for seg in line.segments)
        text = "".join(text.split())
        # Rich drops the delimiters themselves; the sample text stays as written.
        for literal in ("[a](https://example.com/a)",
                        "[b](https://example.com/b)",
                        "[c](https://example.com/c)",
                        "tick`[d](https://example.com/d)",
                        "[e](https://example.com/e)"):
            with self.subTest(literal=literal):
                self.assertIn(literal, text)
        self.assertIn("https://example.com/f", text)
        self.assertNotIn("[f]", text)


if __name__ == "__main__":
    unittest.main()
