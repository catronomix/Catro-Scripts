# Terminal Markdown Reader
"""
                                                FULL TERMINAL MARKDOWN READER
                                                =============================
A full-screen interactive command-line utility for rendering and reading
Markdown (.md) files directly in your terminal with dynamic line wrapping,
color formatting, smooth scrolling, and keyboard navigation.

Usage:
                python mdreader.py <filename.md>
                Or, if using the catro-scripts wrapper:
                catro-scripts mdreader <filename.md>

Features:
                - Full-screen TUI rendering using standard Python 'curses'.
                - Rich Markdown formatting (Headers, Lists, Code blocks, Blockquotes, Rules).
                - Pinned 2-line bottom menu and status bar with page percentage.
                - Full scrolling support (Up/Down, Page Up/Page Down, Home/End).
                - Automatic line wrapping and dynamic terminal window resizing.

Requirements:
                - Standard Python modules (curses, os, sys, re, textwrap).
                - On Windows: Run 'pip install windows-curses' if standard curses is absent.

Disclaimer: This script was generated with Gemini 3
"""

import os
import sys
import re
import textwrap
import platform

# Enable ANSI escape sequences on Windows
if platform.system().lower() == "windows":
    os.system("color")

try:
    import curses
except ImportError:
    if os.name == "nt":
        print(
            "[Error] 'curses' module is missing on Windows. Trying to install it automatically."
        )
        import subprocess

        script_dir = os.path.dirname(os.path.abspath(__file__))
        installdeps_path = os.path.join(script_dir, "installdeps.py")
        if os.path.exists(installdeps_path):
            subprocess.run([sys.executable, installdeps_path, "curses"], check=False)
        else:
            subprocess.run(
                ["catro-scripts", "installdeps", "curses"], shell=True, check=False
            )
        print(
            "If this failed, Please install it by running: pip install windows-curses"
        )
    else:
        print("[Error] 'curses' library is missing from Python environment.")
    sys.exit(1)


class Segment:
    """Represents a formatted piece of text within a line."""

    def __init__(self, text, attr=0, color=0):
        self.text = text
        self.attr = attr
        self.color = color


class FormattedLine:
    """Represents a single visual line made of formatted segments."""

    def __init__(self, segments=None, bg_color=0):
        self.segments = segments if segments is not None else []
        self.bg_color = bg_color


def init_cozy_colors(theme_mode=0):
    """
    Initializes theme colors.
    theme_mode:
        0 = Default Cozy Purple RGB/256 palette
        1 = High Contrast Light (Black on White)
        2 = High Contrast Dark (White on Black)
    """
    curses.start_color()

    if theme_mode == 1:
        # High Contrast Light Mode
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Default text
        curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_WHITE)  # Headers / Accent
        curses.init_pair(
            3, curses.COLOR_MAGENTA, curses.COLOR_WHITE
        )  # Links / Secondary
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Code block
        curses.init_pair(
            5, curses.COLOR_BLUE, curses.COLOR_WHITE
        )  # Muted / Blockquotes
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Status Bar
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Shortcuts Bar
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Frame Border
        return

    if theme_mode == 2:
        # High Contrast Dark Mode
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Default text
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Headers / Accent
        curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Links / Secondary
        curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Code block
        curses.init_pair(
            5, curses.COLOR_CYAN, curses.COLOR_BLACK
        )  # Muted / Blockquotes
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Status Bar
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Shortcuts Bar
        curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Frame Border
        return

    # Mode 0: Default Cozy Purple
    can_rgb = False
    try:
        if curses.can_change_color():
            can_rgb = True
    except Exception:
        can_rgb = False

    if can_rgb:
        # Redefine color slots (16-23) with custom 0-1000 RGB scale
        curses.init_color(16, 106, 90, 149)  # Dark Velvet Purple BG (#1B1726)
        curses.init_color(17, 160, 133, 220)  # Slate Purple Container BG (#292238)
        curses.init_color(18, 204, 145, 310)  # Amethyst Status BG (#34254F)
        curses.init_color(19, 831, 784, 921)  # Soft Lavender Text (#D4C8EB)
        curses.init_color(20, 576, 505, 690)  # Muted Purple Secondary (#9381B0)
        curses.init_color(21, 960, 803, 407)  # Glowing Gold Accent (#F5CD68)
        curses.init_color(22, 878, 623, 403)  # Warm Amber / Rose Gold (#E09F67)
        curses.init_color(23, 988, 933, 796)  # Pale Golden Cream (#FCEECB)

        c_bg, c_slate, c_status = 16, 17, 18
        c_text, c_muted, c_gold, c_amber, c_cream = 19, 20, 21, 22, 23
    else:
        # Fallback to standard 256-color palette index mapping
        c_bg, c_slate, c_status = 235, 236, 237
        c_text, c_muted, c_gold, c_amber, c_cream = 252, 140, 220, 208, 230

    # Initialize Cozy Purple Color Pairs (1-8)
    curses.init_pair(1, c_text, c_bg)  # Default text & background
    curses.init_pair(2, c_gold, c_bg)  # Headers / Glowing Gold
    curses.init_pair(3, c_amber, c_bg)  # Links / Warm Amber
    curses.init_pair(4, c_cream, c_slate)  # Inline & Code blocks
    curses.init_pair(5, c_muted, c_bg)  # Blockquotes / Muted Purple
    curses.init_pair(6, c_gold, c_status)  # Top Status Bar
    curses.init_pair(7, c_cream, c_slate)  # Bottom Shortcuts Bar
    curses.init_pair(8, c_gold, c_bg)  # Frame Border


def draw_window_border(stdscr, height, width, scroll_top=0, max_scroll=0):
    """Draws a 2-character wide decorated border around the terminal screen frame with a scroll progress indicator on the right edge."""
    if height < 6 or width < 10:
        return

    top_outer = "╔═╤" + "═" * (width - 6) + "╤═╗"
    top_inner = "║ ├" + "─" * (width - 6) + "┤ ║"
    bot_inner = "║ ├" + "─" * (width - 6) + "┤ ║"
    bot_outer = "╙o└" + "─" * (width - 6) + "┘o╜"

    border_attr = curses.color_pair(8) | curses.A_BOLD
    thumb_attr = curses.color_pair(6) | curses.A_BOLD

    track_top = 2
    track_bottom = height - 3
    track_len = track_bottom - track_top + 1

    # Calculate scroll indicator thumb position on the right border
    if max_scroll > 0 and track_len > 0:
        thumb_offset = int(round((scroll_top / max_scroll) * (track_len - 1)))
        thumb_y = track_top + max(0, min(thumb_offset, track_len - 1))
    else:
        thumb_y = track_top

    try:
        # Top 2-line border
        stdscr.addstr(0, 0, top_outer, border_attr)
        stdscr.addstr(1, 0, top_inner, border_attr)

        # Side 2-character borders with scroll indicator inside the right border line
        for y in range(2, height - 2):
            stdscr.addstr(y, 0, "║ │", border_attr)
            stdscr.addstr(y, width - 3, "│", border_attr)

            if y == thumb_y:
                stdscr.addstr(y, width - 2, "#", thumb_attr)
            else:
                stdscr.addstr(y, width - 2, " ", border_attr)

            stdscr.addstr(y, width - 1, "║", border_attr)

        # Bottom 2-line border
        stdscr.addstr(height - 2, 0, bot_inner, border_attr)
        stdscr.addstr(height - 1, 0, bot_outer, border_attr)
    except curses.error:
        pass


def parse_inline_formatting(text, default_attr=curses.A_NORMAL, default_color=1):
    """
    Parses inline elements like **bold**, *italic*, `code`, and [links](url).
    Returns a list of Segment objects with cozy gold & purple color pairings.
    """
    segments = []
    # Pattern matches **bold**, *italic*, `code`, or [link](url)
    pattern = re.compile(r"(\*\*.*?\*\*|\*.*?\*|`.*?`|\[.*?\]\(.*?\))")
    parts = pattern.split(text)

    for part in parts:
        if not part:
            continue

        # Bold: **text** -> Glowing Cream/Gold
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            segments.append(Segment(part[2:-2], default_attr | curses.A_BOLD, 2))
        # Italic: *text* -> Soft Muted Purple
        elif part.startswith("*") and part.endswith("*") and len(part) >= 2:
            segments.append(Segment(part[1:-1], default_attr | curses.A_ITALIC, 5))
        # Inline Code: `text` -> Cream text on Slate Purple BG
        elif part.startswith("`") and part.endswith("`") and len(part) >= 2:
            segments.append(Segment(f" {part[1:-1]} ", curses.A_BOLD, 4))
        # Link: [text](url) -> Warm Amber text
        elif (
            part.startswith("[") and "]" in part and "(" in part and part.endswith(")")
        ):
            link_match = re.match(r"\[(.*?)\]\((.*?)\)", part)
            if link_match:
                link_text, link_url = link_match.groups()
                segments.append(
                    Segment(link_text, default_attr | curses.A_UNDERLINE, 3)
                )
                segments.append(Segment(f" ({link_url})", curses.A_DIM, 5))
            else:
                segments.append(Segment(part, default_attr, default_color))
        else:
            segments.append(Segment(part, default_attr, default_color))

    return segments


def process_markdown(raw_content, width):
    """
    Parses raw Markdown string into structured lines wrapped to display width,
    applying cozy ASCII art borders, golden headers, and muted purple formatting.
    """
    lines = raw_content.splitlines()
    formatted_doc = []
    in_code_block = False

    wrapper = textwrap.TextWrapper(
        width=max(10, width - 2),
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
        expand_tabs=True,
        tabsize=4,
    )

    code_wrapper = textwrap.TextWrapper(
        width=max(10, width - 6),
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
        expand_tabs=True,
        tabsize=4,
    )

    for line in lines:
        # Horizontal Rules
        if re.match(r"^[*\-_]{3,}\s*$", line.strip()):
            rule_len = max(1, width - 6)
            rule_str = f"* {'=' * rule_len} *"
            formatted_doc.append(
                FormattedLine(
                    [Segment(rule_str.center(max(1, width)), curses.A_BOLD, 2)]
                )
            )
            continue

        # Code Blocks with ASCII Art Box Borders
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            border_len = max(1, width - 10)
            if in_code_block:
                top_border = f"+--[ code ]{'-' * border_len}+"
                formatted_doc.append(
                    FormattedLine([Segment(top_border, curses.A_BOLD, 2)])
                )
            else:
                bot_border = f"+{'-' * (border_len + 11)}+"
                formatted_doc.append(
                    FormattedLine([Segment(bot_border, curses.A_BOLD, 2)])
                )
            continue

        if in_code_block:
            code_w = max(10, width - 6)
            wrapped_code = code_wrapper.wrap(line) or [""]
            for cl in wrapped_code:
                formatted_doc.append(
                    FormattedLine(
                        [
                            Segment("| ", curses.A_BOLD, 2),
                            Segment(f"{cl:<{code_w}}", curses.A_NORMAL, 4),
                            Segment(" |", curses.A_BOLD, 2),
                        ]
                    )
                )
            continue

        # Headers with Golden Details (# Header)
        header_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2)

            if level == 1:
                title_len = min(width - 6, len(title) + 4)
                rule = "+ " + "=" * title_len + " +"
                formatted_doc.append(FormattedLine())
                formatted_doc.append(FormattedLine([Segment(rule, curses.A_BOLD, 2)]))
                formatted_doc.append(
                    FormattedLine([Segment(f"   {title.upper()}   ", curses.A_BOLD, 2)])
                )
                formatted_doc.append(FormattedLine([Segment(rule, curses.A_BOLD, 2)]))
            elif level == 2:
                formatted_doc.append(FormattedLine())
                formatted_doc.append(
                    FormattedLine([Segment(f"=== {title} ===", curses.A_BOLD, 3)])
                )
            else:
                formatted_doc.append(
                    FormattedLine([Segment(f"> {title}", curses.A_BOLD, 2)])
                )
            continue

        # Blockquotes (| Quote)
        if line.strip().startswith(">"):
            quote_text = line.strip().lstrip(">").strip()
            wrapped_quote = code_wrapper.wrap(quote_text) or [""]
            for ql in wrapped_quote:
                segments = [Segment("| ", curses.A_BOLD, 2)] + parse_inline_formatting(
                    ql, curses.A_ITALIC, 5
                )
                formatted_doc.append(FormattedLine(segments))
            continue

        # Bullet / Numbered Lists
        list_match = re.match(r"^\s*([*\-+]|\d+\.)\s+(.*)", line)
        if list_match:
            bullet = (
                "*" if list_match.group(1) in ["*", "-", "+"] else list_match.group(1)
            )
            item_text = list_match.group(2)
            indent = "  "
            wrapped_item = code_wrapper.wrap(item_text) or [""]

            for idx, il in enumerate(wrapped_item):
                if idx == 0:
                    segments = [
                        Segment(f"{indent}{bullet} ", curses.A_BOLD, 2)
                    ] + parse_inline_formatting(il)
                else:
                    segments = [
                        Segment(f"{indent}   ", 0, 1)
                    ] + parse_inline_formatting(il)
                formatted_doc.append(FormattedLine(segments))
            continue

        # Standard Paragraph / Empty Line
        if not line.strip():
            formatted_doc.append(FormattedLine())
        else:
            wrapped_lines = wrapper.wrap(line) or [""]
            for wl in wrapped_lines:
                formatted_doc.append(FormattedLine(parse_inline_formatting(wl)))

    # Append blank lines + cozy centered golden end-of-file marker
    formatted_doc.append(FormattedLine())
    formatted_doc.append(FormattedLine())
    eof_str = "~ ~ ~   end of file   ~ ~ ~"
    formatted_doc.append(
        FormattedLine([Segment(eof_str.center(max(1, width)), curses.A_BOLD, 2)])
    )

    return formatted_doc


def get_directory_md_files(current_filepath):
    """
    Scans the directory of current file (or CWD) for alphanumerically sorted .md files.
    """
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
    """
    Main TUI loop handling viewport rendering, input events, file switching, and bottom bar.
    """
    curses.use_default_colors()
    curses.curs_set(0)  # Hide blinking cursor
    stdscr.keypad(True)

    show_border = True
    theme_mode = 0  # 0: Cozy Purple, 1: High Contrast Light, 2: High Contrast Dark
    theme_names = ["Cozy Purple", "Contrast Light", "Contrast Dark"]

    # Enable palette
    init_cozy_colors(theme_mode)
    stdscr.bkgd(" ", curses.color_pair(1))

    scroll_top = 0
    zoom_level = 95  # Reader width percentage (50% - 100%)
    scroll_positions = {}  # Store per-file scroll history

    # Load folder file list
    folder, md_files = get_directory_md_files(filepath)
    filename = os.path.basename(filepath)

    current_file_idx = 0
    for idx, fname in enumerate(md_files):
        if fname.lower() == filename.lower():
            current_file_idx = idx
            break

    last_width = -1
    last_zoom = -1
    last_raw_content = None
    doc_lines = []

    while True:
        height, width = stdscr.getmaxyx()

        # Viewport margins depending on border visibility
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

        if (
            usable_width != last_width
            or zoom_level != last_zoom
            or raw_content != last_raw_content
        ):
            doc_lines = process_markdown(raw_content, content_width)
            last_width = usable_width
            last_zoom = zoom_level
            last_raw_content = raw_content

        total_lines = len(doc_lines)
        half_page = usable_height // 2
        max_scroll = max(0, total_lines - usable_height + half_page)
        scroll_top = max(0, min(scroll_top, max_scroll))

        stdscr.clear()

        # Render 2-char decorated border if enabled with scrollbar indicator
        if show_border and height >= 8 and width >= 12:
            draw_window_border(stdscr, height, width, scroll_top, max_scroll)

        # Render Document Lines
        for y in range(usable_height):
            line_idx = scroll_top + y
            if line_idx >= total_lines:
                break

            line = doc_lines[line_idx]
            x_pos = margin_left
            max_x = x_offset + usable_width - 1

            for seg in line.segments:
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

        # Line 1: Information Bar (Gold on Amethyst)
        pct = (
            100
            if total_lines <= usable_height
            else int((scroll_top / max_scroll) * 100)
        )
        file_count_str = f"({current_file_idx + 1}/{len(md_files)})" if md_files else ""
        theme_str = theme_names[theme_mode]
        status_info = f" * File: {filename} {file_count_str} | Theme: {theme_str} | Width: {zoom_level}% | Lines: {scroll_top + 1}-{min(scroll_top + usable_height, total_lines)}/{total_lines} ({pct}%)"
        status_bar = f"{status_info:<{usable_width - 1}}"[: usable_width - 1]

        try:
            stdscr.addstr(
                status_y1, x_offset, status_bar, curses.color_pair(6) | curses.A_BOLD
            )
        except curses.error:
            pass

        # Line 2: Shortcuts Bar (Cream on Slate)
        shortcuts = " [< / >] Prev/Next | [+ / -] Width | [H] Border | [C] Contrast | [UP/DN] Scroll | [Q] Quit"
        shortcuts_bar = f"{shortcuts:<{usable_width - 1}}"[: usable_width - 1]

        try:
            stdscr.addstr(
                status_y2, x_offset, shortcuts_bar, curses.color_pair(7) | curses.A_BOLD
            )
        except curses.error:
            pass

        stdscr.refresh()

        key = stdscr.getch()

        if key in (27, ord("q"), ord("Q")):  # ESC or Q to quit
            break

        # Border visibility toggle
        elif key in (ord("h"), ord("H")):
            show_border = not show_border
            stdscr.clear()

        # Contrast mode switcher
        elif key in (ord("c"), ord("C")):
            theme_mode = (theme_mode + 1) % 3
            init_cozy_colors(theme_mode)
            stdscr.bkgd(" ", curses.color_pair(1))
            stdscr.clear()

        # Up / Down: scroll line by line
        elif key in (curses.KEY_UP, ord("k")):
            scroll_top = max(0, scroll_top - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            scroll_top = min(max_scroll, scroll_top + 1)

        # Page Up / Page Down: scroll one page with 2 lines of overlap
        elif key in (curses.KEY_PPAGE, ord("b")):  # Page Up
            page_step = max(1, usable_height - 2)
            scroll_top = max(0, scroll_top - page_step)
        elif key in (curses.KEY_NPAGE, ord("f"), 32):  # Page Down or Space
            page_step = max(1, usable_height - 2)
            scroll_top = min(max_scroll, scroll_top + page_step)

        # Left / Right: instantly load previous/next .md file in working directory
        elif key in (curses.KEY_LEFT, ord("h"), ord(",")):
            if md_files and current_file_idx > 0:
                scroll_positions[filename] = scroll_top  # Save current position
                current_file_idx -= 1
                filename = md_files[current_file_idx]
                filepath = os.path.join(folder, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    scroll_top = scroll_positions.get(filename, 0)  # Restore position
                except Exception as e:
                    raw_content = f"# Error\nCould not load file: {e}"
        elif key in (curses.KEY_RIGHT, ord("l"), ord(".")):
            if md_files and current_file_idx < len(md_files) - 1:
                scroll_positions[filename] = scroll_top  # Save current position
                current_file_idx += 1
                filename = md_files[current_file_idx]
                filepath = os.path.join(folder, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    scroll_top = scroll_positions.get(filename, 0)  # Restore position
                except Exception as e:
                    raw_content = f"# Error\nCould not load file: {e}"

        # Plus / Minus: Increase / decrease font zoom / reading width
        elif key in (ord("+"), ord("=")):
            zoom_level = min(100, zoom_level + 5)
        elif key in (ord("-"), ord("_")):
            zoom_level = max(50, zoom_level - 5)

        # Top / Bottom
        elif key in (curses.KEY_HOME, ord("g")):  # Home / Top
            scroll_top = 0
        elif key in (curses.KEY_END, ord("G")):  # End / Bottom
            scroll_top = max_scroll
        elif key == curses.KEY_RESIZE:
            stdscr.clear()


def main():
    filepath = None

    if len(sys.argv) == 1:
        # Default behavior with no arguments: open first .md file in working directory
        folder, md_files = get_directory_md_files(os.getcwd())
        if not md_files:
            print("[Error] No .md files found in current working directory.")
            sys.exit(1)
        filepath = os.path.join(folder, md_files[0])
    elif len(sys.argv) == 2:
        filepath = sys.argv[1]
    else:
        print("Usage: python mdreader.py [filename.md]")
        print("Or:    catro-scripts mdreader [filename.md]")
        sys.exit(1)

    if not os.path.exists(filepath):
        print(f"[Error] File not found: '{filepath}'")
        sys.exit(1)

    if not os.path.isfile(filepath):
        print(f"[Error] '{filepath}' is not a valid file.")
        sys.exit(1)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as e:
        print(f"[Error] Could not read file '{filepath}': {e}")
        sys.exit(1)

    # Start curses full-screen interface
    try:
        curses.wrapper(render_reader, filepath, raw_content)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[Error] An unexpected error occurred while running mdreader: {e}")


if __name__ == "__main__":
    main()
