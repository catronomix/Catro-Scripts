"""
                                                Live JSONL Monitor
                                                =============================
A full-screen, passive live monitor for .jsonl files in a directory.

Usage:
                catro-scripts nanobot_monitor [--parser nanobot-chat]

Features:
                - Live passive monitoring of all .jsonl files in the current directory.
                - Files sorted dynamically by most recent modification time.
                - Fading recency indicator (Green <5s to Dark Blue >2m).
                - Scrollable output history per file without blocking file polling.
                - Full-screen view mode (Enter key) to read multi-line formatted history per event.
                - Event jumping (Left/Right keys) and page scrolling (PgUp/PgDn keys) in full view.
                - Modular parser system for different JSONL formats (default: nanobot-chat).
                - Alternating background colors and rich RGB ANSI color-coding.

Disclaimer: This script was generated with Gemini 3.1 Pro.
"""

import os
import sys
import time
import json
import re
import glob
import argparse
import traceback
import platform

# ---------------------------------------------------------------------------
# Debugging Setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_LOG_PATH = os.path.join(SCRIPT_DIR, "jsonl_debug.log")
DEBUGLEVEL = 0


def debug_log(msg):
    """Writes a timestamped debug message to jsonl_debug.log in the script's directory."""
    if DEBUGLEVEL > 0:
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cross-Platform Terminal Utilities
# ---------------------------------------------------------------------------
if platform.system().lower() == "windows":
    import msvcrt

    def enable_ansi_windows():
        os.system("color")

    def get_key():
        if msvcrt.kbhit():
            c = msvcrt.getch()
            if c == b"\x1b":
                return "esc"
            if c in (b"\r", b"\n"):
                return "enter"
            if c in (b"\x00", b"\xe0"):
                c2 = msvcrt.getch()
                if c2 == b"H":
                    return "up"
                if c2 == b"P":
                    return "down"
                if c2 == b"M":
                    return "right"
                if c2 == b"K":
                    return "left"
                if c2 == b"I":
                    return "pageup"
                if c2 == b"Q":
                    return "pagedown"
                if c2 == b"G":
                    return "home"
                if c2 == b"O":
                    return "end"
            try:
                decoded = c.decode("utf-8", "ignore").lower()
                if decoded in ("\r", "\n"):
                    return "enter"
                return decoded
            except Exception:
                return None
        return None

    def setup_terminal():
        enable_ansi_windows()
        sys.stdout.write("\x1b[?25l\x1b[?7l")  # hide cursor, disable line wrap
        sys.stdout.flush()

    def restore_terminal(clear=False):
        sys.stdout.write(
            "\x1b[?25h\x1b[?7h\x1b[0m"
        )  # show cursor, enable line wrap, reset
        if clear:
            sys.stdout.write("\x1b[2J\x1b[1;1H")
        else:
            sys.stdout.write("\n")
        sys.stdout.flush()
else:
    import termios
    import tty
    import select

    orig_settings = None

    def get_key():
        if select.select([sys.stdin], [], [], 0)[0]:
            b = sys.stdin.read(1)
            if b in ("\r", "\n"):
                return "enter"
            if b == "\x1b":
                # Wait briefly to see if it's an escape sequence or a raw ESC key
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    b2 = sys.stdin.read(1)
                    if b2 == "[":
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            b3 = sys.stdin.read(1)
                            if b3 == "A":
                                return "up"
                            if b3 == "B":
                                return "down"
                            if b3 == "C":
                                return "right"
                            if b3 == "D":
                                return "left"
                            if b3 == "H":
                                return "home"
                            if b3 == "F":
                                return "end"
                            if b3 in ("5", "6"):
                                if select.select([sys.stdin], [], [], 0.02)[0]:
                                    sys.stdin.read(1)  # Consume trailing ~
                                if b3 == "5":
                                    return "pageup"
                                if b3 == "6":
                                    return "pagedown"
                else:
                    return "esc"
            return b.lower()
        return None

    def setup_terminal():
        global orig_settings
        orig_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write("\x1b[?25l\x1b[?7l")  # hide cursor, disable line wrap
        sys.stdout.flush()

    def restore_terminal(clear=False):
        if orig_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, orig_settings)
        sys.stdout.write("\x1b[?25h\x1b[?7h\x1b[0m")
        if clear:
            sys.stdout.write("\x1b[2J\x1b[1;1H")
        else:
            sys.stdout.write("\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Styling and Data Structures
# ---------------------------------------------------------------------------
def rgb(r, g, b, bg=False):
    code = 48 if bg else 38
    return f"\x1b[{code};2;{r};{g};{b}m"


RESET = "\x1b[0m"


class Span:
    """Represents a piece of text with foreground and background colors (as RGB tuples)."""

    def __init__(self, text, fg=None, bg=None):
        self.text = text
        self.fg = fg
        self.bg = bg


class LineState:
    """Maintains the parsed display state for a single tracked file."""

    def __init__(self, filepath, collapse_messages=False):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.mtime = 0.0
        self.cursor_pos = 0
        self.spans = []
        self.events = []  # List of dicts: {'phase': str, 'spans': [Span, ...]}
        self.total_chars = 0
        self.last_phase = None
        self.scroll_offset = 0  # 0 means auto-scroll (right-aligned)
        self.collapse_messages = collapse_messages
        self.current_block_char_count = 0

    def append_span(self, span, phase=None):
        if not span.text:
            return

        if phase is None:
            phase = self.last_phase

        # 1. Main horizontal overview spans
        if self.spans and self.spans[-1].fg == span.fg and self.spans[-1].bg == span.bg:
            self.spans[-1].text += span.text
        else:
            self.spans.append(Span(span.text, span.fg, span.bg))

        self.total_chars += len(span.text)

        # 2. Block/entry grouping for full screen view and navigation
        if not self.events or self.events[-1].get("phase") != phase:
            self.events.append(
                {"phase": phase, "spans": [Span(span.text, span.fg, span.bg)]}
            )
        else:
            curr_spans = self.events[-1]["spans"]
            if (
                curr_spans
                and curr_spans[-1].fg == span.fg
                and curr_spans[-1].bg == span.bg
            ):
                curr_spans[-1].text += span.text
            else:
                curr_spans.append(Span(span.text, span.fg, span.bg))


def slice_spans(spans, start_idx, length):
    """Slices a list of Spans to a specific character window."""
    result = []
    curr_idx = 0
    for span in spans:
        span_len = len(span.text)
        if curr_idx + span_len <= start_idx:
            curr_idx += span_len
            continue
        if curr_idx >= start_idx + length:
            break

        overlap_start = max(0, start_idx - curr_idx)
        overlap_end = min(span_len, start_idx + length - curr_idx)

        result.append(Span(span.text[overlap_start:overlap_end], span.fg, span.bg))
        curr_idx += span_len
    return result


def strip_special(text):
    text = text.replace("\r", "").replace("\t", " ")
    return re.sub(r"[^\x20-\x7E\n]", "", text)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------
def parse_nanobot_chat(json_data, line_state):
    """
    Parses a 'nanobot-chat' JSON event and updates the line_state spans.
    """
    phase = json_data.get("turn_phase", "")
    if not phase:
        phase = json_data.get("role", "")
    event = json_data.get("event", "")

    # Phase background colors (RGB tuples)
    bg = None
    if phase == "activity":
        bg = (0, 50, 100)
    elif phase == "reasoning":
        bg = (50, 0, 50)
    elif phase in ("answer", "assistant"):
        bg = (0, 50, 0)
    elif phase == "complete":
        bg = (50, 50, 50)
    elif phase == "user":
        bg = (100, 50, 0)

    # Prepend phase indicator if it changed
    if phase and phase != line_state.last_phase:
        line_state.last_phase = phase
        line_state.current_block_char_count = 0
        line_state.append_span(
            Span(f"[{phase}] ", fg=(200, 200, 200), bg=bg), phase=phase
        )

    text = json_data.get("text", json_data.get("content", ""))
    text = strip_special(text)

    # Collapse user/answer messages if toggled
    is_collapsible = line_state.collapse_messages and phase in (
        "user",
        "answer",
        "assistant",
    )
    if is_collapsible:
        allowed = 12 - line_state.current_block_char_count
        if allowed > 0:
            text = text[:allowed]
            line_state.current_block_char_count += len(text)
        else:
            text = ""
    else:
        line_state.current_block_char_count += len(text)

    # Event foreground colors & special markers
    fg = (255, 255, 255)  # default white
    if event == "message":
        fg = (255, 255, 0)  # yellow
        tools = json_data.get("tool_events", [])
        for tool in tools:
            name = tool.get("name", "unknown")
            args = json.dumps(tool.get("arguments", {}))
            text += f"[Tool: {name} {args}] "
    elif event == "reasoning_delta":
        fg = (170, 170, 170)
    elif event == "stream_end":
        fg = (0, 255, 0)
        text += "†"
    elif event == "turn_end":
        fg = (255, 0, 0)
        text += "•"
    elif event == "reasoning_end":
        fg = (255, 0, 255)
        text += "®"

    if text:
        line_state.append_span(Span(text, fg=fg, bg=bg), phase=phase)


def parse_nanobot_session(json_data, line_state):
    """
    Parses a 'nanobot-session' JSON event and updates the line_state spans.
    """
    role = json_data.get("role")
    _type = json_data.get("_type")

    phase = role
    if _type == "metadata":
        phase = "meta"

    if not phase:
        return

    # Role/Phase background colors
    bg = None
    if phase == "user":
        bg = (100, 50, 0)
    elif phase == "assistant":
        bg = (0, 50, 0)
    elif phase == "tool":
        bg = (0, 50, 100)
    elif phase == "meta":
        bg = (50, 50, 50)

    # Helper to process text limits when collapsing is enabled [H]
    def process_text(text, is_collapsible, fg_color, bg_color, current_phase):
        if not text:
            return
        text = strip_special(text)
        if is_collapsible and line_state.collapse_messages:
            allowed = 12 - line_state.current_block_char_count
            if allowed > 0:
                text = text[:allowed]
                line_state.current_block_char_count += len(text)
            else:
                text = ""

        if text:
            if current_phase != line_state.last_phase:
                line_state.last_phase = current_phase
                line_state.current_block_char_count = 0
                line_state.append_span(
                    Span(f"[{current_phase}] ", fg=(200, 200, 200), bg=bg_color),
                    phase=current_phase,
                )
            line_state.append_span(
                Span(text, fg=fg_color, bg=bg_color), phase=current_phase
            )

    # Parse based on phase type
    if phase == "meta":
        key = json_data.get("key", "")
        process_text(f"Key: {key} ", False, (255, 255, 255), bg, "meta")

    elif phase == "user":
        process_text(json_data.get("content", ""), True, (255, 255, 255), bg, "user")

    elif phase == "tool":
        name = json_data.get("name", "unknown")
        content = json_data.get("content", "")
        process_text(f"[{name}] {content} ", False, (170, 200, 255), bg, "tool")

    elif phase == "assistant":
        reasoning = json_data.get("reasoning_content")
        if reasoning:
            process_text(
                reasoning + " ", False, (170, 170, 170), (50, 0, 50), "reasoning"
            )

        content = json_data.get("content")
        if content:
            process_text(content + " ", True, (255, 255, 255), bg, "assistant")

        tools = json_data.get("tool_calls", [])
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            args = func.get("arguments", "{}")
            process_text(
                f"[Call: {name} {args}] ", False, (255, 255, 0), bg, "assistant"
            )

        # Append red block if the response finished (measured via latency presence)
        lat = json_data.get("latency_ms")
        if lat:
            process_text("■ ", False, (255, 0, 0), bg, "assistant")


PARSERS = {"nanobot-chat": parse_nanobot_chat, "nanobot-session": parse_nanobot_session}


# ---------------------------------------------------------------------------
# File Monitoring Logic
# ---------------------------------------------------------------------------
def get_recency_color(delta_s):
    """Interpolates from Green (<5s) to Dark Blue (>120s)"""
    if delta_s < 5:
        return rgb(0, 255, 0)
    if delta_s > 120:
        return rgb(0, 0, 50)

    ratio = (delta_s - 5) / 115.0
    r = 0
    g = int(255 * (1 - ratio))
    b = int(50 * ratio)
    return rgb(r, g, b)


class Monitor:
    def __init__(self, parser_name, target_dir="."):
        self.parser_name = parser_name
        self.parser = PARSERS.get(parser_name, PARSERS["nanobot-chat"])
        self.target_dir = target_dir
        self.files_state = {}  # filepath -> LineState
        self.sorted_files = []  # list of filepaths sorted by mtime
        self.selected_index = 0
        self.scroll_top_index = 0
        self.collapse_messages = False
        self.show_legend = False
        self.mode = "main"  # "main" or "fullscreen"
        self.fullscreen_file = None
        self.fullscreen_scroll_y = 0

    def poll_files(self):
        """Checks for file modifications, additions, and deletions."""
        pattern = os.path.join(self.target_dir, "*.jsonl")
        current_files = glob.glob(pattern)

        debug_log(
            f"poll_files: Target dir='{self.target_dir}', Pattern='{pattern}', Found {len(current_files)} files"
        )

        needs_reorder = False

        current_files_set = set(current_files)
        tracked_files = list(self.files_state.keys())
        for f in tracked_files:
            if f not in current_files_set:
                debug_log(f"poll_files: Untracking deleted file '{f}'")
                del self.files_state[f]
                needs_reorder = True

        for f in current_files:
            try:
                mtime = os.stat(f).st_mtime

                if f not in self.files_state:
                    debug_log(f"poll_files: Tracking new file '{f}'")
                    self.files_state[f] = LineState(f, self.collapse_messages)
                    needs_reorder = True

                state = self.files_state[f]

                # Check for updates or truncations
                size = os.path.getsize(f)
                if size < state.cursor_pos:
                    debug_log(f"poll_files: File truncated '{f}'. Resetting cursor.")
                    # File was truncated, reset
                    state.cursor_pos = 0
                    state.spans = []
                    state.events = []
                    state.total_chars = 0
                    state.last_phase = None
                    state.current_block_char_count = 0

                if mtime > state.mtime or size > state.cursor_pos:
                    debug_log(
                        f"poll_files: Reading new lines for '{f}' (mtime={mtime}, size={size}, cursor={state.cursor_pos})"
                    )
                    self._read_new_lines(f, state)
                    state.mtime = mtime
                    needs_reorder = True

            except Exception as e:
                debug_log(f"poll_files: Error processing file '{f}': {e}")
                if f in self.files_state:
                    del self.files_state[f]
                needs_reorder = True

        if needs_reorder:
            debug_log("poll_files: Reordering display list")
            file_stats = [(f, s.mtime) for f, s in self.files_state.items()]
            file_stats.sort(key=lambda x: x[1], reverse=True)
            new_sorted = [x[0] for x in file_stats]

            if new_sorted != self.sorted_files:
                selected_file = (
                    self.sorted_files[self.selected_index]
                    if self.sorted_files
                    and self.selected_index < len(self.sorted_files)
                    else None
                )
                self.sorted_files = new_sorted
                if selected_file in self.sorted_files:
                    self.selected_index = self.sorted_files.index(selected_file)
                else:
                    self.selected_index = min(
                        self.selected_index, max(0, len(self.sorted_files) - 1)
                    )
            return True
        return False

    def _read_new_lines(self, filepath, state):
        with open(filepath, "r", encoding="utf-8") as f:
            f.seek(state.cursor_pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    self.parser(data, state)
                except json.JSONDecodeError:
                    pass
            state.cursor_pos = f.tell()


# ---------------------------------------------------------------------------
# Text Wrapping and Full-Screen View Helpers
# ---------------------------------------------------------------------------
def wrap_spans_to_lines(spans, max_width):
    """
    Wraps a list of Span objects into lines where each line length <= max_width.
    Preserves exact RGB foreground and background styling per character.
    """
    if not spans:
        return [[]]

    lines = []
    current_line = []
    current_len = 0

    for span in spans:
        text = span.text
        if not text:
            continue
        fg = span.fg
        bg = span.bg

        sub_lines = text.split("\n")
        for s_idx, sub_text in enumerate(sub_lines):
            if s_idx > 0:
                lines.append(current_line)
                current_line = []
                current_len = 0

            parts = re.split(r"(\s+)", sub_text)
            for part in parts:
                if not part:
                    continue
                part_len = len(part)

                if current_len + part_len <= max_width:
                    current_line.append(Span(part, fg, bg))
                    current_len += part_len
                else:
                    if part.isspace():
                        if current_line:
                            lines.append(current_line)
                            current_line = []
                            current_len = 0
                        continue

                    if part_len > max_width:
                        rem = part
                        while len(rem) > max_width - current_len:
                            take = max_width - current_len
                            if take > 0:
                                current_line.append(Span(rem[:take], fg, bg))
                                rem = rem[take:]
                            lines.append(current_line)
                            current_line = []
                            current_len = 0
                        if rem:
                            current_line.append(Span(rem, fg, bg))
                            current_len += len(rem)
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = [Span(part, fg, bg)]
                        current_len = part_len

    if current_line or not lines:
        lines.append(current_line)

    return lines


def build_fullscreen_rendered_lines(events, cols):
    """
    Formats all events for a file into terminal lines of width `cols`.
    Returns:
            rendered_lines: list of tuples `(event_index, line_spans)`
            event_line_map: dict mapping `event_index -> start_line_index`
    """
    rendered_lines = []
    event_line_map = {}

    if not events:
        rendered_lines.append(
            (-1, [Span(" (No events logged in file) ", fg=(150, 150, 150))])
        )
        return rendered_lines, event_line_map

    for idx, event in enumerate(events):
        event_line_map[idx] = len(rendered_lines)
        spans = event.get("spans", [])

        wrapped = wrap_spans_to_lines(spans, max_width=cols)
        for w_line in wrapped:
            rendered_lines.append((idx, w_line))

    return rendered_lines, event_line_map


# ---------------------------------------------------------------------------
# UI Rendering
# ---------------------------------------------------------------------------
def get_legend_nanobot_chat():
    bg = rgb(40, 40, 40, bg=True)
    fg = rgb(255, 255, 255)
    bg_user = rgb(100, 50, 0, bg=True)
    bg_act = rgb(0, 50, 100, bg=True)
    bg_reason = rgb(50, 0, 50, bg=True)
    bg_ans = rgb(0, 50, 0, bg=True)
    bg_comp = rgb(50, 50, 50, bg=True)
    fg_msg = rgb(255, 255, 0)
    fg_reason = rgb(170, 170, 170)
    fg_stream = rgb(0, 255, 0)
    fg_turn = rgb(255, 0, 0)
    fg_reason_end = rgb(255, 0, 255)

    return [
        f"{bg}{fg}┌{'─' * 44}┐{RESET}",
        f"{bg}{fg}│{'CHAT COLOR LEGEND'.center(44)}│{RESET}",
        f"{bg}{fg}├{'─' * 44}┤{RESET}",
        f"{bg}{fg}│{' Phases (Backgrounds):'.ljust(44)}│{RESET}",
        f"{bg}{fg}│ {bg_user}[user]{bg} {bg_act}[activity]{bg}{' ' * 24}│{RESET}",
        f"{bg}{fg}│ {bg_reason}[reasoning]{bg} {bg_ans}[answer]{bg}{' ' * 23}│{RESET}",
        f"{bg}{fg}│ {bg_comp}[complete]{bg}{' ' * 33}│{RESET}",
        f"{bg}{fg}│{' ' * 44}│{RESET}",
        f"{bg}{fg}│{' Events (Foregrounds / Markers):'.ljust(44)}│{RESET}",
        f"{bg}{fg}│ {fg_msg}Message / Tool{fg}{' ' * 29}│{RESET}",
        f"{bg}{fg}│ {fg_reason}Reasoning Delta{fg}{' ' * 28}│{RESET}",
        f"{bg}{fg}│ {fg_stream}● Stream End{fg}    {fg_turn}■ Turn End{fg}{' ' * 17}│{RESET}",
        f"{bg}{fg}│ {fg_reason_end}♦ Reasoning End{fg}{' ' * 28}│{RESET}",
        f"{bg}{fg}└{'─' * 44}┘{RESET}",
    ]


def get_legend_nanobot_session():
    bg = rgb(40, 40, 40, bg=True)
    fg = rgb(255, 255, 255)
    bg_user = rgb(100, 50, 0, bg=True)
    bg_tool = rgb(0, 50, 100, bg=True)
    bg_reason = rgb(50, 0, 50, bg=True)
    bg_ast = rgb(0, 50, 0, bg=True)
    bg_meta = rgb(50, 50, 50, bg=True)
    fg_call = rgb(255, 255, 0)
    fg_reason = rgb(170, 170, 170)
    fg_tool_out = rgb(170, 200, 255)
    fg_turn = rgb(255, 0, 0)

    return [
        f"{bg}{fg}┌{'─' * 44}┐{RESET}",
        f"{bg}{fg}│{'SESSION COLOR LEGEND'.center(44)}│{RESET}",
        f"{bg}{fg}├{'─' * 44}┤{RESET}",
        f"{bg}{fg}│{' Roles (Backgrounds):'.ljust(44)}│{RESET}",
        f"{bg}{fg}│ {bg_user}[user]{bg} {bg_tool}[tool]{bg}{' ' * 28}│{RESET}",
        f"{bg}{fg}│ {bg_ast}[assistant]{bg} {bg_meta}[meta]{bg}{' ' * 23}│{RESET}",
        f"{bg}{fg}│ {bg_reason}[reasoning]{bg}{' ' * 33}│{RESET}",
        f"{bg}{fg}│{' ' * 44}│{RESET}",
        f"{bg}{fg}│{' Data (Foregrounds / Markers):'.ljust(44)}│{RESET}",
        f"{bg}{fg}│ {fg_call}Tool Call{fg}{' ' * 34}│{RESET}",
        f"{bg}{fg}│ {fg_tool_out}Tool Output{fg}{' ' * 32}│{RESET}",
        f"{bg}{fg}│ {fg_reason}Reasoning Content{fg}{' ' * 26}│{RESET}",
        f"{bg}{fg}│ {fg_turn}■ Turn End (latency){fg}{' ' * 23}│{RESET}",
        f"{bg}{fg}└{'─' * 44}┘{RESET}",
    ]


LEGENDS = {
    "nanobot-chat": get_legend_nanobot_chat,
    "nanobot-session": get_legend_nanobot_session,
}


def render_ui(monitor, last_rendered_rows):
    cols, rows = os.get_terminal_size()
    max_visible_lines = rows - 4  # leave 4 lines for bottom 2-row menu

    popup_width = 46
    popup_lines = []
    if monitor.show_legend:
        legend_func = LEGENDS.get(monitor.parser_name, get_legend_nanobot_chat)
        popup_lines = legend_func()

    popup_height = len(popup_lines) if monitor.show_legend else 0
    popup_start_x = max(1, (cols - popup_width) // 2)
    popup_start_y = max(1, (max_visible_lines - popup_height) // 2)

    # Adjust scroll_top_index to keep selected_index in view
    if monitor.selected_index < monitor.scroll_top_index:
        monitor.scroll_top_index = monitor.selected_index
    elif monitor.selected_index >= monitor.scroll_top_index + max_visible_lines:
        monitor.scroll_top_index = monitor.selected_index - max_visible_lines + 1

    left_col_width = 18
    content_width = cols - left_col_width - 4

    now = time.time()

    for ui_row in range(max_visible_lines):
        data_index = monitor.scroll_top_index + ui_row
        row_str = ""

        if data_index < len(monitor.sorted_files):
            filepath = monitor.sorted_files[data_index]
            state = monitor.files_state.get(filepath)

            if not state:
                continue

            is_selected = data_index == monitor.selected_index

            row_bg_val = 26 if ui_row % 2 == 1 else 0
            base_bg = rgb(row_bg_val, row_bg_val, row_bg_val, bg=True)

            fname_disp = state.filename[: left_col_width - 1]
            if state.scroll_offset > 0:
                prefix_char = ">"
                prefix_color = rgb(255, 0, 0)
            elif is_selected:
                prefix_char = ">"
                prefix_color = rgb(255, 255, 255)
            else:
                prefix_char = " "
                prefix_color = rgb(150, 150, 150)

            fname_color = rgb(255, 255, 255) if is_selected else rgb(150, 150, 150)
            fname_bg = rgb(0, 0, 150 + row_bg_val, bg=True) if is_selected else base_bg

            left_col_str = (
                fname_bg
                + prefix_color
                + prefix_char
                + fname_color
                + fname_disp.ljust(left_col_width - 1)
                + RESET
                + base_bg
            )

            delta_s = now - state.mtime
            rec_color = get_recency_color(delta_s)

            if state.scroll_offset > 0:
                start_idx = max(
                    0, state.total_chars - content_width - state.scroll_offset
                )
            else:
                start_idx = max(0, state.total_chars - content_width)

            visible_spans = slice_spans(state.spans, start_idx, content_width)

            content_str = ""
            chars_rendered = 0
            for sp in visible_spans:
                if sp.fg:
                    cfg = rgb(*sp.fg)
                else:
                    cfg = ""

                if sp.bg:
                    adjusted_bg = (
                        min(255, sp.bg[0] + row_bg_val),
                        min(255, sp.bg[1] + row_bg_val),
                        min(255, sp.bg[2] + row_bg_val),
                    )
                    cbg = rgb(*adjusted_bg, bg=True)
                else:
                    cbg = base_bg

                disp_text = sp.text.replace("\n", " ")
                content_str += f"{cfg}{cbg}{disp_text}{RESET}{base_bg}"
                chars_rendered += len(disp_text)

            padding = " " * max(0, content_width - chars_rendered)
            content_str += padding

            spacer = rgb(100, 100, 100) + "│" + RESET + base_bg
            recency_block = rec_color + "█" + RESET
            row_str = (
                f"{left_col_str}{spacer}{content_str}{spacer}{recency_block}{RESET}"
            )

        else:
            row_bg_val = 26 if ui_row % 2 == 1 else 0
            row_str = (
                rgb(row_bg_val, row_bg_val, row_bg_val, bg=True) + (" " * cols) + RESET
            )

        if (
            monitor.show_legend
            and popup_start_y <= ui_row + 1 < popup_start_y + popup_height
        ):
            last_rendered_rows[ui_row] = None
        else:
            if last_rendered_rows.get(ui_row) != row_str:
                sys.stdout.write(f"\x1b[{ui_row + 1};1H{row_str}")
                last_rendered_rows[ui_row] = row_str

    if monitor.show_legend:
        for i, line_str in enumerate(popup_lines):
            popup_y = popup_start_y + i
            cache_key = f"popup_{popup_y}"
            if last_rendered_rows.get(cache_key) != line_str:
                sys.stdout.write(f"\x1b[{popup_y};{popup_start_x}H{line_str}")
                last_rendered_rows[cache_key] = line_str
    else:
        keys_to_remove = [
            k
            for k in last_rendered_rows
            if isinstance(k, str) and k.startswith("popup_")
        ]
        for k in keys_to_remove:
            del last_rendered_rows[k]

    raw_status_line_1 = f" Parser: {monitor.parser_name} | Files: {len(monitor.sorted_files)} | [Enter] Full View | [↑/↓] Sel | [←/→] Scroll | [h] Col | [l] Legend | [Esc/q] Quit "
    raw_status_line_2 = f" Freshness: █ <5s ... █ >2m "

    padded_line_1 = raw_status_line_1.center(cols - 2)
    padded_line_2 = raw_status_line_2.center(cols - 2)

    colored_line_2 = padded_line_2.replace(
        "█ <5s", f"{rgb(0, 255, 0)}█{RESET} <5s"
    ).replace("█ >2m", f"{rgb(0, 0, 50)}█{RESET} >2m")

    box_top = "┌" + "─" * (cols - 2) + "┐"
    box_mid_1 = "│" + padded_line_1 + "│"
    box_mid_2 = "│" + colored_line_2 + "│"
    box_bot = "└" + "─" * (cols - 2) + "┘"

    bottom_ui = (
        f"\x1b[{rows - 3};1H{box_top}"
        f"\x1b[{rows - 2};1H{box_mid_1}"
        f"\x1b[{rows - 1};1H{box_mid_2}"
        f"\x1b[{rows};1H{box_bot}"
    )
    if last_rendered_rows.get("bottom") != bottom_ui:
        sys.stdout.write(bottom_ui)
        last_rendered_rows["bottom"] = bottom_ui

    sys.stdout.flush()


def render_fullscreen_ui(monitor, last_rendered_rows):
    cols, rows = os.get_terminal_size()
    viewport_height = rows - 2  # Row 1 is header, Row rows is footer

    active_file = monitor.fullscreen_file
    state = monitor.files_state.get(active_file)

    if not state:
        monitor.mode = "main"
        return

    rendered_lines, event_line_map = build_fullscreen_rendered_lines(state.events, cols)
    total_lines = len(rendered_lines)
    max_scroll = max(0, total_lines - viewport_height)

    # Clamp scroll offset
    monitor.fullscreen_scroll_y = max(0, min(monitor.fullscreen_scroll_y, max_scroll))
    scroll_y = monitor.fullscreen_scroll_y

    curr_event_idx = 0
    if rendered_lines and scroll_y < total_lines:
        curr_event_idx = rendered_lines[scroll_y][0]
        if curr_event_idx < 0:
            curr_event_idx = 0

    total_events = len(state.events)

    # 1. Top Header Bar
    header_text = f" FULL VIEW: {state.filename} | Entry {curr_event_idx + 1}/{total_events} | Line {scroll_y + 1}/{total_lines} "
    header_bg = rgb(0, 60, 120, bg=True)
    header_fg = rgb(255, 255, 255)
    header_str = f"\x1b[1m{header_bg}{header_fg}{header_text.ljust(cols)}{RESET}"

    if last_rendered_rows.get("fs_header") != header_str:
        sys.stdout.write(f"\x1b[1;1H{header_str}")
        last_rendered_rows["fs_header"] = header_str

    # 2. Viewport Lines
    for ui_row in range(viewport_height):
        line_idx = scroll_y + ui_row
        row_num = ui_row + 2

        if line_idx < total_lines:
            ev_idx, line_spans = rendered_lines[line_idx]

            row_bg_val = 18 if (line_idx % 2 == 1) else 0
            base_bg = rgb(row_bg_val, row_bg_val, row_bg_val, bg=True)

            line_str = ""
            chars_rendered = 0
            for sp in line_spans:
                cfg = rgb(*sp.fg) if sp.fg else ""
                if sp.bg:
                    cbg = rgb(
                        min(255, sp.bg[0] + row_bg_val),
                        min(255, sp.bg[1] + row_bg_val),
                        min(255, sp.bg[2] + row_bg_val),
                        bg=True,
                    )
                else:
                    cbg = base_bg

                line_str += f"{cfg}{cbg}{sp.text}{RESET}{base_bg}"
                chars_rendered += len(sp.text)

            padding = " " * max(0, cols - chars_rendered)
            full_row_str = f"{base_bg}{line_str}{padding}{RESET}"
        else:
            full_row_str = rgb(10, 10, 10, bg=True) + (" " * cols) + RESET

        cache_key = f"fs_row_{ui_row}"
        if last_rendered_rows.get(cache_key) != full_row_str:
            sys.stdout.write(f"\x1b[{row_num};1H{full_row_str}")
            last_rendered_rows[cache_key] = full_row_str

    # 3. Popup Legend Overlay
    if monitor.show_legend:
        popup_width = 46
        legend_func = LEGENDS.get(monitor.parser_name, get_legend_nanobot_chat)
        popup_lines = legend_func()
        popup_height = len(popup_lines)
        popup_start_x = max(1, (cols - popup_width) // 2)
        popup_start_y = max(1, (viewport_height - popup_height) // 2 + 1)

        for i, line_str in enumerate(popup_lines):
            popup_y = popup_start_y + i
            cache_key = f"popup_{popup_y}"
            if last_rendered_rows.get(cache_key) != line_str:
                sys.stdout.write(f"\x1b[{popup_y};{popup_start_x}H{line_str}")
                last_rendered_rows[cache_key] = line_str

    # 4. Bottom Footer Bar
    footer_text = " [←/→] Prev/Next Entry | [↑/↓/PgUp/PgDn] Scroll | [h] Col | [l] Legend | [Esc/Enter/q] Back "
    footer_bg = rgb(40, 40, 40, bg=True)
    footer_fg = rgb(220, 220, 220)
    footer_str = f"{footer_bg}{footer_fg}{footer_text.center(cols)}{RESET}"

    if last_rendered_rows.get("fs_footer") != footer_str:
        sys.stdout.write(f"\x1b[{rows};1H{footer_str}")
        last_rendered_rows["fs_footer"] = footer_str

    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Live monitor for JSONL logs.")
    parser.add_argument(
        "--parser",
        default="nanobot-chat",
        choices=PARSERS.keys(),
        help="Content type parser to use.",
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Directory to monitor for .jsonl files.",
    )
    args = parser.parse_args()

    debug_log("\n=== Application Started ===")
    debug_log(f"Arguments: {args}")

    setup_terminal()
    monitor = Monitor(args.parser, args.dir)
    last_rendered_rows = {}

    try:
        while True:
            key = get_key()
            if key in ("\x03",):  # Ctrl+C
                break

            if key == "l":
                monitor.show_legend = not monitor.show_legend

            # Mode 1: Main Overview Mode
            if monitor.mode == "main":
                if key in ("q", "esc"):
                    break

                if len(monitor.sorted_files) > 0:
                    monitor.selected_index = min(
                        monitor.selected_index, max(0, len(monitor.sorted_files) - 1)
                    )
                    active_file = monitor.sorted_files[monitor.selected_index]
                    state = monitor.files_state.get(active_file)

                    if state:
                        if key == "up":
                            monitor.selected_index = max(0, monitor.selected_index - 1)
                        elif key == "down":
                            monitor.selected_index = min(
                                len(monitor.sorted_files) - 1,
                                monitor.selected_index + 1,
                            )
                        elif key == "left":
                            state.scroll_offset += 10
                        elif key == "right":
                            state.scroll_offset = max(0, state.scroll_offset - 10)
                        elif key == "a":
                            state.scroll_offset = 0
                        elif key == "enter":
                            monitor.mode = "fullscreen"
                            monitor.fullscreen_file = active_file
                            monitor.fullscreen_scroll_y = 0
                            sys.stdout.write(
                                "\x1b[2J"
                            )  # Clear screen for view transition
                            last_rendered_rows.clear()
                        elif key == "h":
                            monitor.collapse_messages = not monitor.collapse_messages
                            for s in monitor.files_state.values():
                                s.collapse_messages = monitor.collapse_messages
                                s.cursor_pos = 0
                                s.spans = []
                                s.events = []
                                s.total_chars = 0
                                s.last_phase = None
                                s.current_block_char_count = 0
                                s.mtime = 0

            # Mode 2: Full Screen File Reading Mode
            elif monitor.mode == "fullscreen":
                active_file = monitor.fullscreen_file
                state = monitor.files_state.get(active_file)

                if state:
                    cols, rows = os.get_terminal_size()
                    viewport_height = rows - 2
                    rendered_lines, event_line_map = build_fullscreen_rendered_lines(
                        state.events, cols
                    )
                    total_lines = len(rendered_lines)
                    max_scroll = max(0, total_lines - viewport_height)

                    if key in ("esc", "q", "enter", "b"):
                        monitor.mode = "main"
                        sys.stdout.write("\x1b[2J")
                        last_rendered_rows.clear()
                    elif key == "up":
                        monitor.fullscreen_scroll_y = max(
                            0, monitor.fullscreen_scroll_y - 1
                        )
                    elif key == "down":
                        monitor.fullscreen_scroll_y = min(
                            max_scroll, monitor.fullscreen_scroll_y + 1
                        )
                    elif key == "pageup":
                        monitor.fullscreen_scroll_y = max(
                            0, monitor.fullscreen_scroll_y - viewport_height
                        )
                    elif key == "pagedown":
                        monitor.fullscreen_scroll_y = min(
                            max_scroll, monitor.fullscreen_scroll_y + viewport_height
                        )
                    elif key in ("home", "g"):
                        monitor.fullscreen_scroll_y = 0
                    elif key in ("end", "G"):
                        monitor.fullscreen_scroll_y = max_scroll
                    elif key == "right":
                        if rendered_lines:
                            curr_line = min(
                                monitor.fullscreen_scroll_y, total_lines - 1
                            )
                            curr_ev = rendered_lines[curr_line][0]
                            next_ev = curr_ev + 1
                            if next_ev in event_line_map:
                                monitor.fullscreen_scroll_y = min(
                                    max_scroll, event_line_map[next_ev]
                                )
                    elif key == "left":
                        if rendered_lines:
                            curr_line = min(
                                monitor.fullscreen_scroll_y, total_lines - 1
                            )
                            curr_ev = rendered_lines[curr_line][0]
                            start_of_curr = event_line_map.get(curr_ev, 0)
                            if monitor.fullscreen_scroll_y > start_of_curr:
                                monitor.fullscreen_scroll_y = start_of_curr
                            else:
                                prev_ev = curr_ev - 1
                                if prev_ev in event_line_map:
                                    monitor.fullscreen_scroll_y = event_line_map[
                                        prev_ev
                                    ]
                    elif key == "h":
                        monitor.collapse_messages = not monitor.collapse_messages
                        for s in monitor.files_state.values():
                            s.collapse_messages = monitor.collapse_messages
                            s.cursor_pos = 0
                            s.spans = []
                            s.events = []
                            s.total_chars = 0
                            s.last_phase = None
                            s.current_block_char_count = 0
                            s.mtime = 0

            # 2. Poll Files
            monitor.poll_files()

            # Check terminal resize
            cols, rows = os.get_terminal_size()
            if (
                last_rendered_rows.get("cols") != cols
                or last_rendered_rows.get("rows") != rows
            ):
                sys.stdout.write("\x1b[2J")  # Clear screen
                last_rendered_rows.clear()
                last_rendered_rows["cols"] = cols
                last_rendered_rows["rows"] = rows

            # 3. Render Active Mode View
            if monitor.mode == "fullscreen":
                render_fullscreen_ui(monitor, last_rendered_rows)
            else:
                render_ui(monitor, last_rendered_rows)

            # 4. Sleep to maintain ~10Hz max update rate
            time.sleep(0.1)

    except KeyboardInterrupt:
        restore_terminal(clear=True)
    except Exception as e:
        restore_terminal(clear=False)
        print("An error occurred:")
        traceback.print_exc()
        sys.exit(1)
    else:
        restore_terminal(clear=True)


if __name__ == "__main__":
    main()
