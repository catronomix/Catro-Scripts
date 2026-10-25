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
    - Markdown rendering powered by 'rich' with the shared tui palettes and
      table boxes: soft (mode 0), contrast light (mode 1), contrast dark (2).
    - Pinned 2-line bottom menu and status bar with page percentage.
    - Full scrolling support (Up/Down, PgUp/PgDn, Home/End, Left/Right file navigation).
    - Viewport border toggle [H] and theme cycling [C].
    - Displays raw URLs for links.
    - Aligned table rendering.
    - Needs an interactive terminal: a pipe is refused with the tui contract's
      one-line message and exit 2, before curses starts.

Requirements:
    - python libraries rich, curses
    - On Windows: 'windows-curses'.
    - Nothing is installed automatically: a missing library is reported on
      stderr with the 'catro-scripts installdeps' / 'pip install' hint.

Disclaimer: This script was generated with Gemini 3
"""

import os
import sys
import argparse
import re

import tui

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
            # Keep borders rigid: collapse_padding/pad_edge/show_edge stop the
            # content from pushing them out of alignment when rendered to
            # segments. Every colour comes from this console's theme, so the
            # table follows the active mode instead of a baked-in palette.
            cell = console.get_style("markdown.table.cell")
            border = console.get_style("markdown.table.border")
            header = console.get_style("markdown.table.header")
            zebra = console.get_style("mdreader.table.zebra")
            kwargs["box"] = box.SQUARE
            kwargs["row_styles"] = [
                "on {}".format(_colour_name(cell.bgcolor)),
                "on {}".format(_colour_name(zebra.bgcolor)),
            ]
            kwargs["border_style"] = "{} on {}".format(
                _colour_name(border.color), _colour_name(cell.bgcolor)
            )
            kwargs["header_style"] = "bold {} on {}".format(
                _colour_name(header.color), _colour_name(cell.bgcolor)
            )
            kwargs["style"] = "on {}".format(_colour_name(cell.bgcolor))
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


# mdreader's three display modes map one-to-one onto the shared theme ids, so
# every colour the reader draws - curses pairs and Rich alike - comes from the
# same house palette, and the reader matches the other scripts.
THEME_MODES = ("soft", "contrast-light", "contrast-dark")

# Pair number -> (foreground role, background role), using palette keys. The
# numbers are the ones process_markdown_rich and the chrome hand to
# color_pair(); because the roles are semantic, switching mode recolours the
# content and the frame together.
PAIR_ROLES = (
    (1, "fg", "bg"),          # body text
    (2, "header", "bg"),      # headings, bullets, numbers
    (3, "warn", "bg"),        # links and secondary emphasis
    (4, "fg", "surface"),     # code spans, table cells
    (5, "muted", "bg"),       # dimmed text
    (6, "header", "surface"),  # status bar
    (7, "fg", "zebra_bg"),    # shortcut bar, alternate table row
    (8, "border", "bg"),      # window frame
    (9, "header", "surface"),  # table header row
)

# The full-screen furniture of the reader, named instead of numbered so the
# frame and the bars cannot drift away from the palette roles: the window is
# painted `bg`, the frame `border`, and the header/footer bars sit on `surface`
# and `zebra_bg` exactly like a chrome.header/field page in the other scripts.
CHROME_PAIRS = {
    "window": 1,     # fg on bg: the whole-screen background fill
    "frame": 8,      # border on bg: viewport frame and scroll track
    "thumb": 6,      # header on surface: scroll thumb, same band as the status
    "status": 6,     # header on surface: status bar
    "shortcuts": 7,  # fg on zebra_bg: shortcut bar
}


def theme_id(theme_mode=0):
    """Shared theme id for a display mode (mode 0 is soft)."""
    if 0 <= theme_mode < len(THEME_MODES):
        return THEME_MODES[theme_mode]
    return THEME_MODES[0]


def terminal_color_count():
    """Number of colours the terminal offers (0 when unknown)."""
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


def _can_redefine_colors():
    """True when the terminal lets curses replace palette entries with RGB."""
    try:
        return bool(curses.can_change_color())
    except Exception:
        return False


def _fold_index(index, limit):
    """Fold an xterm index into the terminal's real range (bright -> normal)."""
    if limit <= 0:
        return 0
    while index >= limit:
        index -= 8 if limit >= 8 else limit
    return max(0, index)


def _colour_slots(colours):
    """Map each palette role used by PAIR_ROLES to a curses colour number.

    A terminal that can redefine colours gets exact RGB in spare slots above
    the basic sixteen; otherwise the nearest xterm index (256, or the basic 16)
    is used. Allocation order is fixed, so a theme always yields the same
    slots.
    """
    limit = terminal_color_count() or 8
    level = "256" if limit >= 256 else "16"

    slots = {}
    next_slot = 16
    redefinable = level == "256" and _can_redefine_colors()
    for _pair, fg_role, bg_role in PAIR_ROLES:
        for role in (fg_role, bg_role):
            if role in slots:
                continue
            if redefinable and next_slot < limit:
                rgb = tui.palette.rgb(colours[role])
                try:
                    # curses spells RGB in 0..1000.
                    curses.init_color(next_slot, *(
                        int(round(channel * 1000 / 255)) for channel in rgb
                    ))
                except curses.error:
                    # Some terminals claim they can redefine colours and then
                    # refuse; stop trying and use the nearest index instead.
                    redefinable = False
                else:
                    slots[role] = next_slot
                    next_slot += 1
                    continue
            slots[role] = _fold_index(
                tui.palette.index(colours[role], level=level), limit
            )
    return slots


def init_theme_colors(theme_mode=0, cap=None):
    """Initializes the curses colour pairs from the house palette of `theme_mode`.

    Degrades safely: terminals that cannot redefine colours get the nearest
    xterm index, 16/8-colour terminals get the nearest basic colour, and a pair
    the terminal rejects is swallowed (curses then uses its default). With
    `cap.level == "none"` (NO_COLOR, TERM=dumb) the layout is kept and only the
    colour is dropped, as the tui contract requires.
    """
    try:
        curses.start_color()
    except curses.error:
        return

    if cap is not None and getattr(cap, "level", "") == "none":
        default = getattr(curses, "COLOR_DEFAULT", -1)
        _init_pairs(
            tuple((pair, default, default) for pair, _fg, _bg in PAIR_ROLES)
        )
        return

    slots = _colour_slots(tui.palette.palette(theme_id(theme_mode)))
    _init_pairs(
        tuple(
            (pair, slots[fg_role], slots[bg_role])
            for pair, fg_role, bg_role in PAIR_ROLES
        )
    )


def get_rich_theme(theme_mode=0):
    """Generates a custom Rich Theme from the shared palette of the active mode."""
    colours = tui.palette.palette(theme_id(theme_mode))
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
            # The table patch below reads this for the alternate row fill.
            "mdreader.table.zebra": "on " + colours["zebra_bg"],
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

    border_attr = curses.color_pair(CHROME_PAIRS["frame"]) | curses.A_BOLD
    thumb_attr = curses.color_pair(CHROME_PAIRS["thumb"]) | curses.A_BOLD

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


def _colour_name(colour):
    """Lowercase "#rrggbb" (or colour name) for a Rich colour; "" when unset."""
    if colour is None:
        return ""
    return str(getattr(colour, "name", None) or colour).lower()


def segment_pair(style, colours):
    """Curses pair number for a Rich segment style, chosen by palette role.

    Roles come from `colours`, so the same classification works in all three
    modes: body text, heading/accent, warn, code/table cell, muted and the
    zebra row.
    """
    if style is None:
        return 1

    fg = _colour_name(style.color)
    bg = _colour_name(style.bgcolor)
    surface = colours["surface"].lower()
    zebra = colours["zebra_bg"].lower()
    header = {colours["header"].lower(), colours["accent"].lower()}
    warn = colours["warn"].lower()
    is_dim = (bool(style.dim) or "gray" in fg or "grey" in fg
              or fg == colours["muted"].lower())

    if bg or fg in (surface, zebra):
        if fg in header:
            return 9   # table header: accent on the surface fill
        if bg == zebra and zebra != surface:
            return 7   # alternate table row: body text on the zebra fill
        return 4       # code spans and themed table chrome on the surface fill
    if fg:
        # In contrast-dark `header` and `warn` are the same yellow; links are
        # the underlined ones, so they keep their own pair.
        if fg in header and not (style.underline and fg == warn):
            return 2
        if fg == warn:
            return 3
        if is_dim:
            return 5
        return 1
    return 5 if is_dim else 1


def process_markdown_rich(raw_content, width, theme_mode=0):
    """Parses and renders Markdown text into formatted lines using Rich."""
    rich_theme = get_rich_theme(theme_mode)
    colours = tui.palette.palette(theme_id(theme_mode))
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

            if seg.style:
                if seg.style.bold:
                    attr |= curses.A_BOLD
                if seg.style.italic:
                    attr |= curses.A_ITALIC
                if seg.style.underline:
                    attr |= curses.A_UNDERLINE
                if seg.style.dim:
                    attr |= curses.A_DIM

            line_segments.append(
                Segment(seg.text, attr, segment_pair(seg.style, colours))
            )
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


def initial_theme_mode():
    """Display mode for the configured theme (CATRO_THEME > config.ini > soft)."""
    try:
        return THEME_MODES.index(tui.theme())
    except ValueError:
        return 0


def render_reader(stdscr, filepath, raw_content, cap=None):
    """Main TUI loop handling viewport rendering, input events, file switching, and status bar."""
    curses.use_default_colors()
    curses.curs_set(0)
    stdscr.keypad(True)

    show_border = True
    theme_mode = initial_theme_mode()
    theme_names = [name.replace("-", " ") for name in THEME_MODES]

    init_theme_colors(theme_mode, cap)
    stdscr.bkgd(" ", curses.color_pair(CHROME_PAIRS["window"]))

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
                status_y1, x_offset, status_bar,
                curses.color_pair(CHROME_PAIRS["status"]) | curses.A_BOLD
            )
        except curses.error:
            pass

        shortcuts = " [< / >] Prev/Next | [[ / ]] Horiz Scroll | [+ / -] Width | [H] Border | [C] Contrast | [UP/DN] Scroll | [Q] Quit"
        shortcuts_bar = f"{shortcuts:<{usable_width - 1}}"[: usable_width - 1]

        try:
            stdscr.addstr(
                status_y2, x_offset, shortcuts_bar,
                curses.color_pair(CHROME_PAIRS["shortcuts"]) | curses.A_BOLD
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
            theme_mode = (theme_mode + 1) % len(THEME_MODES)
            init_theme_colors(theme_mode, cap)
            stdscr.bkgd(" ", curses.color_pair(CHROME_PAIRS["window"]))
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

    # tui owns the refusal: one stderr line with the contract's wording, exit 2,
    # and it runs before curses (or a file is even opened). The capability
    # snapshot is taken once per run and carried into the renderer.
    tui.require_tty("mdreader")
    cap = tui.detect()

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
        tui.init_ansi()
        curses.wrapper(render_reader, filepath, raw_content, cap)
    except KeyboardInterrupt:
        pass  # Ctrl-C quits cleanly with status 0, like 'q'.
    except Exception as e:
        sys.stderr.write(
            f"\n[Error] An unexpected error occurred while running mdreader: {e}\n"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
