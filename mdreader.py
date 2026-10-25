# Terminal Markdown Reader
"""
            FULL TERMINAL MARKDOWN READER
            =============================
A full-screen interactive command-line utility for rendering and reading
Markdown (.md) files directly in your terminal with dynamic line wrapping,
Rich-powered custom themes & table boxes, smooth scrolling, and keyboard navigation.

Usage:
    catro-scripts mdreader [filename.md]

Features:
    - Markdown rendering powered by 'rich' with custom palettes & table boxes.
    - Pinned 2-line bottom menu and status bar with page percentage.
    - Full scrolling support (Up/Down, PgUp/PgDn, Home/End, Left/Right file navigation).
    - Viewport border toggle [H] and Contrast theme modes [C].
    - Displays raw URLs for links.
    - Aligned table rendering.

Requirements:
    - python libraries rich, curses
    - On Windows: 'windows-curses'.
    - Nothing is installed automatically: a missing library is reported on
      stderr with the 'catro-scripts installdeps' / 'pip install' hint.

Disclaimer: This script was generated with Gemini 3
"""

import os
import sys
import platform
import argparse
import re

import tui

# Enable ANSI escape sequences on Windows
if platform.system().lower() == "windows":
    os.system("color")

# Dependencies are resolved exactly once here, without side effects: a missing
# module only sets its name to None. Importing mdreader must never install
# anything or touch the network (issue #11); main() reports missing packages.
try:
    import curses
except ImportError:
    curses = None

try:
    from rich.console import Console
    from rich.markdown import Markdown, TableElement, Link
    from rich.segment import Segment as RichSegment
    from rich.theme import Theme
    from rich import box
    from rich.text import Text
except ImportError:
    Console = Markdown = TableElement = Link = None
    RichSegment = Theme = box = Text = None

try:
    _orig_table_console = TableElement.__rich_console__
except AttributeError:
    # rich is not installed; nothing to patch until it is.
    _orig_table_console = None

if _orig_table_console is not None:

    def _custom_table_console(self, console, options):
        from rich.table import Table

        _orig_init = Table.__init__

        def _table_init(table_self, *args, **kwargs):
            # Use HEAVY_EDGE or SQUARE to keep borders rigid.
            # We must set collapse_padding=True and pad_edge=False to help prevent
            # content from pushing the borders out of alignment when rendered to segments.
            kwargs["box"] = box.SQUARE
            kwargs["row_styles"] = ["on #292238", "on #352b49"]
            kwargs["border_style"] = "#9381B0 on #292238"
            kwargs["header_style"] = "bold #F5CD68 on #292238"
            kwargs["style"] = "on #292238"
            kwargs["collapse_padding"] = True
            kwargs["pad_edge"] = False
            kwargs["show_edge"] = True
            _orig_init(table_self, *args, **kwargs)

        Table.__init__ = _table_init
        try:
            yield from _orig_table_console(self, console, options)
        finally:
            Table.__init__ = _orig_init

    TableElement.__rich_console__ = _custom_table_console


class Segment:
    """Represents a formatted piece of text within a line."""

    def __init__(self, text, attr=0, color=1):
        self.text = text
        self.attr = attr
        self.color = color


class FormattedLine:
    """Represents a single visual line made of formatted segments."""

    def __init__(self, segments=None):
        self.segments = segments if segments is not None else []


def slice_line_segments(segments, start_col, max_cols):
    """Slices segment text for horizontal scrolling."""
    if start_col <= 0:
        return segments

    sliced = []
    current_col = 0
    end_col = start_col + max_cols

    for seg in segments:
        seg_len = len(seg.text)
        seg_start = current_col
        seg_end = current_col + seg_len

        if seg_end > start_col and seg_start < end_col:
            sub_start = max(0, start_col - seg_start)
            sub_end = min(seg_len, end_col - seg_start)
            sliced_text = seg.text[sub_start:sub_end]
            if sliced_text:
                sliced.append(Segment(sliced_text, seg.attr, seg.color))

        current_col += seg_len
        if current_col >= end_col:
            break

    return sliced


def terminal_color_count():
    """Number of colour pairs the terminal offers (0 when unknown)."""
    try:
        return int(getattr(curses, "COLORS", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _init_pairs(pairs):
    """Applies (pair, fg, bg) tuples, ignoring colours the terminal rejects."""
    for pair, fg, bg in pairs:
        try:
            curses.init_pair(pair, fg, bg)
        except curses.error:
            pass


def _init_high_contrast_dark():
    """Base-colour palette: Contrast Dark, and the fallback for limited terminals."""
    _init_pairs(
        (
            (1, curses.COLOR_WHITE, curses.COLOR_BLACK),
            (2, curses.COLOR_YELLOW, curses.COLOR_BLACK),
            (3, curses.COLOR_CYAN, curses.COLOR_BLACK),
            (4, curses.COLOR_GREEN, curses.COLOR_BLACK),
            (5, curses.COLOR_CYAN, curses.COLOR_BLACK),
            (6, curses.COLOR_BLACK, curses.COLOR_WHITE),
            (7, curses.COLOR_YELLOW, curses.COLOR_BLACK),
            (8, curses.COLOR_YELLOW, curses.COLOR_BLACK),
            (9, curses.COLOR_YELLOW, curses.COLOR_BLACK),
        )
    )


def init_cozy_colors(theme_mode=0):
    """Initializes curses theme colors, degrading gracefully on limited terminals."""
    try:
        curses.start_color()
    except curses.error:
        return

    if theme_mode == 1:
        # High Contrast Light Mode
        _init_pairs(
            (
                (1, curses.COLOR_BLACK, curses.COLOR_WHITE),
                (2, curses.COLOR_BLUE, curses.COLOR_WHITE),
                (3, curses.COLOR_MAGENTA, curses.COLOR_WHITE),
                (4, curses.COLOR_CYAN, curses.COLOR_WHITE),
                (5, curses.COLOR_BLUE, curses.COLOR_WHITE),
                (6, curses.COLOR_WHITE, curses.COLOR_BLACK),
                (7, curses.COLOR_BLACK, curses.COLOR_WHITE),
                (8, curses.COLOR_WHITE, curses.COLOR_BLACK),
                (9, curses.COLOR_BLACK, curses.COLOR_CYAN),
            )
        )
        return

    if theme_mode == 2:
        # High Contrast Dark Mode
        _init_high_contrast_dark()
        return

    # Mode 0: Cozy Purple
    colors = terminal_color_count()
    if colors < 256:
        # An 8/16-colour terminal rejects the 256-colour indices below with
        # curses.error, so fall back to the base-colour palette instead of
        # aborting the whole reader.
        _init_high_contrast_dark()
        return

    can_rgb = False
    try:
        if curses.can_change_color():
            can_rgb = True
    except Exception:
        can_rgb = False

    if can_rgb:
        curses.init_color(16, 106, 90, 149)  # Dark Velvet Purple BG (#1B1726)
        curses.init_color(17, 160, 133, 220)  # Slate Purple Container BG (#292238)
        curses.init_color(18, 100, 75, 60)  # Amethyst Status BG (#34254F)
        curses.init_color(19, 831, 784, 921)  # Soft Lavender Text (#D4C8EB)
        curses.init_color(20, 250, 250, 300)  # Muted Purple Secondary (#9381B0)
        curses.init_color(21, 960, 803, 407)  # Glowing Gold Accent (#F5CD68)
        curses.init_color(22, 878, 623, 300)  # Warm Amber / Rose Gold (#E09F67)
        curses.init_color(23, 988, 933, 796)  # Pale Golden Cream (#FCEECB)
        curses.init_color(24, 208, 168, 286)  # Alt Slate Purple Row BG (#352B49)
        c_bg, c_slate, c_status = 16, 17, 18
        c_text, c_muted, c_gold, c_amber, c_cream, c_slate_alt = 19, 20, 21, 22, 23, 24
    else:
        c_bg, c_slate, c_status = 235, 236, 237
        c_text, c_muted, c_gold, c_amber, c_cream, c_slate_alt = (
            252,
            140,
            220,
            208,
            230,
            238,
        )

    _init_pairs(
        (
            (1, c_text, c_bg),
            (2, c_gold, c_bg),
            (3, c_amber, c_bg),
            (4, c_cream, c_slate),
            (5, c_muted, c_bg),
            (6, c_gold, c_status),
            (7, c_cream, c_slate_alt),
            (8, c_gold, c_slate),
            (9, c_gold, c_slate),
        )
    )
    return


# mdreader's three display modes map one-to-one onto the shared theme ids, so
# the Rich rendering uses the same hexes as every migrated script. The curses
# colour pairs below stay separate for now (they cannot take hex; group B3 of
# Phase B rewrites that path).
THEME_MODES = ("soft", "contrast-light", "contrast-dark")


def get_rich_theme(theme_mode=0):
    """Generates a custom Rich Theme from the shared palette of the active mode."""
    if 0 <= theme_mode < len(THEME_MODES):
        theme_id = THEME_MODES[theme_mode]
    else:
        theme_id = THEME_MODES[0]
    colours = tui.palette.palette(theme_id)
    return Theme(
        {
            "markdown.h1": "bold " + colours["header"],
            "markdown.h2": "bold " + colours["warn"],
            "markdown.h3": "bold " + colours["header"],
            "markdown.h4": "bold " + colours["muted"],
            "markdown.code": colours["fg"] + " on " + colours["surface"],
            "markdown.code_block": colours["fg"] + " on " + colours["surface"],
            "markdown.block_quote": colours["muted"] + " italic",
            "markdown.item.bullet": "bold " + colours["header"],
            "markdown.item.number": "bold " + colours["header"],
            "markdown.hr": colours["muted"],
            "markdown.table.header": ("bold " + colours["header"] + " on "
                                      + colours["surface"]),
            "markdown.table.cell": colours["fg"] + " on " + colours["surface"],
            "markdown.table.border": colours["border"],
            "markdown.link": "underline " + colours["warn"],
        }
    )


def draw_window_border(stdscr, height, width, scroll_top=0, max_scroll=0):
    """Draws a 2-character wide decorated border with a scroll indicator."""
    if height < 6 or width < 10:
        return

    top_outer = "╔═╤" + "═" * (width - 6) + "╤═╗"
    top_inner = "║ ├" + "─" * (width - 6) + "┤ ║"
    bot_inner = "║ ├" + "─" * (width - 6) + "┤ ║"
    bot_outer = "╚═╧" + "═" * (width - 6) + "╧═╝"

    border_attr = curses.color_pair(8) | curses.A_BOLD
    thumb_attr = curses.color_pair(6) | curses.A_BOLD

    track_top = 2
    track_bottom = height - 3
    track_len = track_bottom - track_top + 1

    if max_scroll > 0 and track_len > 0:
        thumb_offset = int(round((scroll_top / max_scroll) * (track_len - 1)))
        thumb_y = track_top + max(0, min(thumb_offset, track_len - 1))
    else:
        thumb_y = track_top

    try:
        stdscr.addstr(0, 0, top_outer, border_attr)
        stdscr.addstr(1, 0, top_inner, border_attr)
        for y in range(2, height - 2):
            stdscr.addstr(y, 0, "║ │", border_attr)
            stdscr.addstr(y, width - 3, "│", border_attr)
            if y == thumb_y:
                stdscr.addstr(y, width - 2, "#", thumb_attr)
            else:
                stdscr.addstr(y, width - 2, " ", border_attr)
            stdscr.addstr(y, width - 1, "║", border_attr)
        stdscr.addstr(height - 2, 0, bot_inner, border_attr)
        stdscr.addstr(height - 1, 0, bot_outer, border_attr)
    except curses.error:
        pass


def process_markdown_rich(raw_content, width, theme_mode=0):
    """Parses and renders Markdown text into formatted lines using Rich."""
    rich_theme = get_rich_theme(theme_mode)
    console = Console(
        width=max(10, width), force_terminal=True, color_system="256", theme=rich_theme
    )

    # Pre-process links: Convert [name](url) to just the raw url
    # We use regex to find standard markdown links and replace them with the raw URL.
    # This ensures that Rich doesn't try to hide the URL behind an obscure hyperlink protocol,
    # making it directly clickable in most modern terminals, and also solves table alignment
    # since the text length directly matches the visible URL.
    processed_content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\2", raw_content)

    # Disable justify to prevent table columns from drifting
    md = Markdown(processed_content, justify="left")
    options = console.options.update_dimensions(
        width=max(10, width), height=100000
    ).update(justify="left")

    rendered_lines = list(RichSegment.split_lines(console.render(md, options)))
    formatted_doc = []

    for line in rendered_lines:
        line_segments = []
        for seg in line:
            if not seg.text:
                continue

            attr = 0
            color = 1

            if seg.style:
                if seg.style.bold:
                    attr |= curses.A_BOLD
                if seg.style.italic:
                    attr |= curses.A_ITALIC
                if seg.style.underline:
                    attr |= curses.A_UNDERLINE
                if seg.style.dim:
                    attr |= curses.A_DIM

                bg_name = (
                    str(seg.style.bgcolor.name).lower() if seg.style.bgcolor else ""
                )
                cname = str(seg.style.color.name).lower() if seg.style.color else ""
                has_bg = bool(seg.style.bgcolor) or any(
                    k in cname for k in ["#292238", "#352b49", "#fceecb"]
                )
                is_dim = seg.style.dim or any(
                    k in cname for k in ["dim", "gray", "grey", "#9381b0"]
                )

                if has_bg:
                    if "#352b49" in bg_name:
                        color = 7  # Alternate Table Row: Same text color on #352B49 BG
                    elif any(k in cname for k in ["#f5cd68", "gold", "yellow"]):
                        color = 9  # Table Header Gold on Slate BG
                    else:
                        color = 4  # Standard Table Row / Code on Slate BG
                elif seg.style.color:
                    if any(k in cname for k in ["#f5cd68", "gold", "yellow"]):
                        color = 2  # Gold on Main BG
                    elif any(
                        k in cname
                        for k in ["#e09f67", "amber", "cyan", "blue", "magenta"]
                    ):
                        color = 3  # Amber on Main BG
                    elif is_dim:
                        color = 5  # Muted on Main BG
                    else:
                        color = 1  # Standard Body Text on Main BG
                elif is_dim:
                    color = 5

            line_segments.append(Segment(seg.text, attr, color))
        formatted_doc.append(FormattedLine(line_segments))

    # Append blank lines + centered golden end-of-file marker
    formatted_doc.append(FormattedLine())
    formatted_doc.append(FormattedLine())
    eof_str = "~ ~ ~   end of file   ~ ~ ~"
    formatted_doc.append(
        FormattedLine([Segment(eof_str.center(max(1, width)), curses.A_BOLD, 2)])
    )

    return formatted_doc


def get_directory_md_files(current_filepath):
    """Scans the directory of current file (or CWD) for alphanumerically sorted .md files."""
    if os.path.isdir(current_filepath):
        folder = os.path.abspath(current_filepath)
    else:
        folder = os.path.dirname(os.path.abspath(current_filepath)) or os.getcwd()
    try:
        files = [
            f
            for f in os.listdir(folder)
            if f.lower().endswith(".md") and os.path.isfile(os.path.join(folder, f))
        ]
        files.sort(key=lambda x: x.lower())
        return folder, files
    except Exception:
        return folder, [os.path.basename(current_filepath)]


def render_reader(stdscr, filepath, raw_content):
    """Main TUI loop handling viewport rendering, input events, file switching, and status bar."""
    curses.use_default_colors()
    curses.curs_set(0)
    stdscr.keypad(True)

    show_border = True
    theme_mode = 0  # 0: Cozy Purple, 1: High Contrast Light, 2: High Contrast Dark
    theme_names = ["Cozy Purple", "Contrast Light", "Contrast Dark"]

    init_cozy_colors(theme_mode)
    stdscr.bkgd(" ", curses.color_pair(1))

    scroll_top = 0
    scroll_left = 0
    zoom_level = 95
    scroll_positions = {}

    folder, md_files = get_directory_md_files(filepath)
    filename = os.path.basename(filepath)

    current_file_idx = 0
    for idx, fname in enumerate(md_files):
        if fname.lower() == filename.lower():
            current_file_idx = idx
            break

    last_width = -1
    last_zoom = -1
    last_theme = -1
    last_raw_content = None
    doc_lines = []

    while True:
        height, width = stdscr.getmaxyx()

        if show_border and height >= 8 and width >= 12:
            y_offset = 2
            x_offset = 3
            usable_width = max(10, width - 5)
            usable_height = max(1, height - 6)
            status_y1 = height - 4
            status_y2 = height - 3
        else:
            y_offset = 0
            x_offset = 0
            usable_width = max(10, width)
            usable_height = max(1, height - 2)
            status_y1 = height - 2
            status_y2 = height - 1

        content_width = max(
            10, min(usable_width, int(usable_width * (zoom_level / 100.0)))
        )
        margin_left = x_offset + max(0, (usable_width - content_width) // 2)

        # Re-render if layout or content changes
        if (
            usable_width != last_width
            or zoom_level != last_zoom
            or theme_mode != last_theme
            or raw_content != last_raw_content
        ):
            doc_lines = process_markdown_rich(raw_content, content_width, theme_mode)
            last_width = usable_width
            last_zoom = zoom_level
            last_theme = theme_mode
            last_raw_content = raw_content

        total_lines = len(doc_lines)
        half_page = usable_height // 2
        max_scroll = max(0, total_lines - usable_height + half_page)
        scroll_top = max(0, min(scroll_top, max_scroll))

        max_line_len = max(
            [sum(len(s.text) for s in line.segments) for line in doc_lines], default=0
        )
        max_h_scroll = max(0, max_line_len - content_width)
        scroll_left = max(0, min(scroll_left, max_h_scroll))

        stdscr.clear()

        # Render border
        if show_border and height >= 8 and width >= 12:
            draw_window_border(stdscr, height, width, scroll_top, max_scroll)

        # Render content
        for y in range(usable_height):
            line_idx = scroll_top + y
            if line_idx >= total_lines:
                break

            line = doc_lines[line_idx]
            x_pos = margin_left
            max_x = x_offset + usable_width - 1
            rendered_segments = slice_line_segments(
                line.segments, scroll_left, usable_width
            )

            for seg in rendered_segments:
                if x_pos >= max_x:
                    break
                available_space = max_x - x_pos
                printable_text = seg.text[:available_space]
                try:
                    stdscr.addstr(
                        y_offset + y,
                        x_pos,
                        printable_text,
                        seg.attr | curses.color_pair(seg.color),
                    )
                except curses.error:
                    pass
                x_pos += len(printable_text)

        # Render status bars
        pct = (
            100
            if total_lines <= usable_height
            else int((scroll_top / max_scroll) * 100)
        )
        file_count_str = f"({current_file_idx + 1}/{len(md_files)})" if md_files else ""
        theme_str = theme_names[theme_mode]
        h_scroll_str = (
            f" | H-Scroll: {scroll_left}/{max_h_scroll}" if max_h_scroll > 0 else ""
        )
        status_info = f" * File: {filename} {file_count_str} | Theme: {theme_str} | Width: {zoom_level}%{h_scroll_str} | Lines: {scroll_top + 1}-{min(scroll_top + usable_height, total_lines)}/{total_lines} ({pct}%)"
        status_bar = f"{status_info:<{usable_width - 1}}"[: usable_width - 1]

        try:
            stdscr.addstr(
                status_y1, x_offset, status_bar, curses.color_pair(6) | curses.A_BOLD
            )
        except curses.error:
            pass

        shortcuts = " [< / >] Prev/Next | [[ / ]] Horiz Scroll | [+ / -] Width | [H] Border | [C] Contrast | [UP/DN] Scroll | [Q] Quit"
        shortcuts_bar = f"{shortcuts:<{usable_width - 1}}"[: usable_width - 1]

        try:
            stdscr.addstr(
                status_y2, x_offset, shortcuts_bar, curses.color_pair(7) | curses.A_BOLD
            )
        except curses.error:
            pass

        stdscr.refresh()

        # Handle input
        key = stdscr.getch()

        if key in (27, ord("q"), ord("Q")):
            break
        elif key in (ord("h"), ord("H")):
            show_border = not show_border
            stdscr.clear()
        elif key in (ord("c"), ord("C")):
            theme_mode = (theme_mode + 1) % 3
            init_cozy_colors(theme_mode)
            stdscr.bkgd(" ", curses.color_pair(1))
            stdscr.clear()
        elif key in (ord("["), ord("a"), ord("A"), curses.KEY_SLEFT):
            scroll_left = max(0, scroll_left - 4)
        elif key in (ord("]"), ord("d"), ord("D"), curses.KEY_SRIGHT):
            scroll_left = min(max_h_scroll, scroll_left + 4)
        elif key in (curses.KEY_UP, ord("k")):
            scroll_top = max(0, scroll_top - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            scroll_top = min(max_scroll, scroll_top + 1)
        elif key in (curses.KEY_PPAGE, ord("b")):
            page_step = max(1, usable_height - 2)
            scroll_top = max(0, scroll_top - page_step)
        elif key in (curses.KEY_NPAGE, ord("f"), 32):
            page_step = max(1, usable_height - 2)
            scroll_top = min(max_scroll, scroll_top + page_step)
        elif key in (curses.KEY_LEFT, ord(",")):
            if md_files and current_file_idx > 0:
                scroll_positions[filename] = scroll_top
                current_file_idx -= 1
                filename = md_files[current_file_idx]
                filepath = os.path.join(folder, filename)
                scroll_left = 0
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    scroll_top = scroll_positions.get(filename, 0)
                except Exception as e:
                    raw_content = f"# Error\nCould not load file: {e}"
        elif key in (curses.KEY_RIGHT, ord(".")):
            if md_files and current_file_idx < len(md_files) - 1:
                scroll_positions[filename] = scroll_top
                current_file_idx += 1
                filename = md_files[current_file_idx]
                filepath = os.path.join(folder, filename)
                scroll_left = 0
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    scroll_top = scroll_positions.get(filename, 0)
                except Exception as e:
                    raw_content = f"# Error\nCould not load file: {e}"
        elif key in (ord("+"), ord("=")):
            zoom_level = min(100, zoom_level + 5)
        elif key in (ord("-"), ord("_")):
            zoom_level = max(50, zoom_level - 5)
        elif key in (curses.KEY_HOME, ord("g")):
            scroll_top = 0
        elif key in (curses.KEY_END, ord("G")):
            scroll_top = max_scroll
        elif key == curses.KEY_RESIZE:
            stdscr.clear()


def require_tty():
    """Refuse to run when stdin/stdout is redirected: curses needs a terminal."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        return
    sys.stderr.write("[Error] mdreader needs an interactive terminal "
                     "(stdin/stdout is not a tty).\n")
    raise SystemExit(2)


def missing_dependencies():
    """Returns one install hint per unavailable library (empty when ready)."""
    hints = []
    if curses is None:
        package = "windows-curses" if os.name == "nt" else "curses"
        hints.append(
            "curses: catro-scripts installdeps curses"
            f"  (or: python -m pip install {package})"
        )
    if Theme is None:
        hints.append(
            "rich: catro-scripts installdeps rich"
            "  (or: python -m pip install rich)"
        )
    return hints


def main():
    parser = argparse.ArgumentParser(
        prog="mdreader.py",
        description="Read Markdown files in a scrollable terminal (curses) UI.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Markdown file to open (default: first .md file in the current directory)",
    )
    args = parser.parse_args()

    require_tty()

    # mdreader never installs anything itself; it only reports what is missing.
    hints = missing_dependencies()
    if hints:
        sys.stderr.write("[Error] mdreader cannot start: missing libraries.\n")
        for hint in hints:
            sys.stderr.write(f"  {hint}\n")
        raise SystemExit(2)

    filepath = args.file
    if filepath is None:
        folder, md_files = get_directory_md_files(os.getcwd())
        if not md_files:
            sys.stderr.write("[Error] No .md files found in current working directory.\n")
            raise SystemExit(1)
        filepath = os.path.join(folder, md_files[0])

    if not os.path.exists(filepath):
        sys.stderr.write(f"[Error] File not found: '{filepath}'\n")
        raise SystemExit(1)

    if not os.path.isfile(filepath):
        sys.stderr.write(f"[Error] '{filepath}' is not a valid file.\n")
        raise SystemExit(1)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as e:
        sys.stderr.write(f"[Error] Could not read file '{filepath}': {e}\n")
        raise SystemExit(1)

    try:
        curses.wrapper(render_reader, filepath, raw_content)
    except KeyboardInterrupt:
        pass  # Ctrl-C quits cleanly with status 0, like 'q'.
    except Exception as e:
        sys.stderr.write(
            f"\n[Error] An unexpected error occurred while running mdreader: {e}\n"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
