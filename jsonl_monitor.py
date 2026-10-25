# (Nanobot) JSONL reader
"""
                                                Live JSONL Monitor
                                                =============================
A full-screen, passive live monitor for .jsonl files in a directory.

Usage:
                catro-scripts nanobot_monitor [--parser nanobot-chat]

Features:
                - Live passive monitoring of all .jsonl files in the current directory.
                - Files sorted dynamically by most recent modification time.
                - Fading recency indicator (palette success -> background over 5s..2m).
                - Scrollable output history per file without blocking file polling.
                - Full-screen view mode (Enter key) to read multi-line formatted history per event.
                - Event jumping (Left/Right keys) and page scrolling (PgUp/PgDn keys) in full view.
                - Modular parser system for different JSONL formats (default: nanobot-chat).
                - Alternating row backgrounds and rich per-span RGB color-coding.

This script keeps its own span/diff rendering engine (contract non-goal): the
tail/diff/span maths, the line accounting, the filtering and the file-following
loop are unchanged. Everything terminal-facing - capability detection, colour
codes, box glyphs, the page background, the legend/footer chrome, the alternate
screen, cursor moves and key input - now comes from the shared `tui` package, so
no escape code and no private palette lives here.

Disclaimer: This script was generated with Gemini 3.1 Pro.
"""

import os
import sys
import time
import json
import re
import glob
import argparse
import dataclasses
import traceback

import tui

# ---------------------------------------------------------------------------
# Debugging Setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_LOG_PATH = os.path.join(SCRIPT_DIR, "jsonl_debug.log")
DEBUGLEVEL = 0

# Row-luminance offsets for the striped backgrounds. The base colours come from
# the active palette; these only lift a span's own background so a phase block
# stays visible on both zebra rows.
ZEBRA_SHADE = 26
FULLSCREEN_SHADE = 18


def debug_log(msg):
    """Writes a timestamped debug message to jsonl_debug.log in the script's directory."""
    if DEBUGLEVEL > 0:
        try:
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Styling and Data Structures
# ---------------------------------------------------------------------------
# Phase/role identity colours are the monitor's own data, not escape codes: they
# are handed to `tui.prefix()` as (r, g, b) tuples, so every code is emitted by
# the shared library and the monitor keeps its colour vocabulary.
PHASE_COLOURS = {
    "user": (100, 50, 0),
    "activity": (0, 50, 100),
    "reasoning": (50, 0, 50),
    "answer": (0, 50, 0),
    "assistant": (0, 50, 0),
    "complete": (50, 50, 50),
    "tool": (0, 50, 100),
    "meta": (50, 50, 50),
}

EVENT_COLOURS = {
    "message": (255, 255, 0),
    "reasoning_delta": (170, 170, 170),
    "stream_end": (0, 255, 0),
    "turn_end": (255, 0, 0),
    "reasoning_end": (255, 0, 255),
}


def _reset(cap):
    """The SGR reset, or "" when the run emits no codes at all."""
    return "" if cap.level == "none" else tui.RESET


def _hex(value):
    """(r, g, b) for a "#rrggbb" palette entry."""
    text = str(value).strip().lstrip("#")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def _shade(colour, amount):
    """Lift an RGB tuple by `amount` per channel, clamped to 255."""
    return tuple(min(255, channel + amount) for channel in colour)


def _marker(cap):
    """Recency glyph: solid block where Unicode is safe, ASCII elsewhere."""
    return "\u2588" if cap.unicode else "#"


def _layout_cap(cap):
    """`cap` with pipe mode off, for the shared chrome helpers.

    The monitor never writes to a pipe (`require_tty` refuses first), so a
    "plain" capability set here only ever means "the colour-off tests use a
    non-tty stream". Chrome's plain mode would drop the footer frame and its
    padding with it; the full-screen view must keep its layout and only lose
    the escapes, which is exactly what level "none" on a tty does.
    """
    return dataclasses.replace(cap, plain=False)


def _repaint(screen, cap):
    """Clear and paint the theme background between two full-screen views.

    `Screen.fill()` is a no-op at colour level "none", so a monochrome run keeps
    the plain clear that stops the previous view from bleeding through.
    """
    if cap.level == "none":
        screen.clear()
    else:
        screen.fill()


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

    # Phase background colors (RGB tuples, resolved by tui.prefix at paint time)
    bg = PHASE_COLOURS.get(phase)

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
        fg = EVENT_COLOURS["message"]
        tools = json_data.get("tool_events", [])
        for tool in tools:
            name = tool.get("name", "unknown")
            args = json.dumps(tool.get("arguments", {}))
            text += f"[Tool: {name} {args}] "
    elif event == "reasoning_delta":
        fg = EVENT_COLOURS["reasoning_delta"]
    elif event == "stream_end":
        fg = EVENT_COLOURS["stream_end"]
        text += "\u2020"
    elif event == "turn_end":
        fg = EVENT_COLOURS["turn_end"]
        text += "\u2022"
    elif event == "reasoning_end":
        fg = EVENT_COLOURS["reasoning_end"]
        text += "\u00ae"

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
    bg = PHASE_COLOURS.get(phase)

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
            process_text("\u25a0 ", False, (255, 0, 0), bg, "assistant")


PARSERS = {"nanobot-chat": parse_nanobot_chat, "nanobot-session": parse_nanobot_session}


# ---------------------------------------------------------------------------
# File Monitoring Logic
# ---------------------------------------------------------------------------
def get_recency_color(delta_s, colours):
    """Interpolates the palette's success colour towards its background.

    Under 5s is full success, over 120s is the background colour (i.e. cold), and
    the gap between them fades linearly. The endpoints come from the active
    palette so every theme keeps its own green-to-cold ramp.
    """
    fresh = _hex(colours["success"])
    cold = _hex(colours["bg"])
    if delta_s < 5:
        return fresh
    if delta_s > 120:
        return cold

    ratio = (delta_s - 5) / 115.0
    return tuple(
        int(round(start + (end - start) * ratio))
        for start, end in zip(fresh, cold)
    )


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
# Legend (one framed block: rules/glyphs from tui.table, samples from tui.prefix)
# ---------------------------------------------------------------------------
# Total visible cells of the legend, side borders included. The popup is centred
# on this same number, so the frame and its placement cannot drift apart.
LEGEND_WIDTH = 46
LEGEND_INNER = LEGEND_WIDTH - 2


def legend_fits(cols):
    """True when the legend frame fits the terminal width.

    The legend is an optional help overlay, so a terminal narrower than the
    frame simply does not get one. Clipping an already-styled line here would
    be wrong: `tui.truncate()` measures characters, so escape bytes would count
    as cells and a sequence could be cut mid-form with no closing reset.

    One spare cell is required: the popup is inset by at least one column, so
    a 46-column terminal cannot hold a 46-cell frame starting at column 1.
    """
    return cols >= LEGEND_WIDTH + 1


def _legend_rule(glyphs, left, right, cap):
    """A horizontal legend rule, exactly LEGEND_WIDTH cells wide."""
    border = tui.prefix(fg="border", cap=cap)
    return (border + glyphs[left] + glyphs["h"] * LEGEND_INNER
            + glyphs[right] + _reset(cap))


def _legend_row(content, glyphs, cap):
    """One framed row: side borders around exactly LEGEND_INNER cells."""
    border = tui.prefix(fg="border", cap=cap)
    return (border + glyphs["v"] + content + border + glyphs["v"]
            + _reset(cap))


def _legend_body(segments, cap):
    """LEGEND_INNER cells of samples on the palette surface.

    Every sample re-asserts the base style after its own reset, so the padding
    after a coloured sample stays on the surface colour and the row keeps its
    width whatever the sample lengths are.
    """
    base = tui.prefix(fg="fg", bg="surface", cap=cap)
    body = " "  # one cell of gutter, as the old box had
    used = 1
    for label, fg, bg in segments:
        room = LEGEND_INNER - used
        if room <= 0:
            break
        label = tui.truncate(label, room)
        span_bg = "surface" if bg is None else bg
        body += (tui.prefix(fg=fg, bg=span_bg, cap=cap) + label
                 + _reset(cap) + base)
        used += tui.display_width(label)
    return base + body + " " * max(0, LEGEND_INNER - used)


def _legend_title(title, cap):
    """The centred, bold title row content."""
    base = tui.prefix(fg="fg", bg="surface", cap=cap)
    lead = tui.prefix(fg="header", bg="surface", bold=True, cap=cap)
    title = tui.truncate(title, LEGEND_INNER)
    used = tui.display_width(title)
    left = max(0, (LEGEND_INNER - used) // 2)
    right = max(0, LEGEND_INNER - used - left)
    return (base + " " * left + lead + title + _reset(cap) + base
            + " " * right)


def _legend_heading(text, cap):
    """A section heading row content."""
    base = tui.prefix(fg="fg", bg="surface", cap=cap)
    lead = tui.prefix(fg="header", bg="surface", bold=True, cap=cap)
    text = tui.truncate(text, LEGEND_INNER)
    used = tui.display_width(text)
    return (base + lead + text + _reset(cap) + base
            + " " * max(0, LEGEND_INNER - used))


def _legend_frame(title, sections, cap):
    """One closed box: top rule, title, separators, samples, bottom rule.

    The old legend was a single `┌ ├ └` frame; the shared banner helper returns
    a three-line block of its own, so stacking it produced a box that closed
    under the title. Compose the frame here instead, from the capability's own
    glyph set, so it stays one box at every level and in ASCII mode.
    """
    glyphs = tui.table.glyphs_for(cap)
    lines = [
        _legend_rule(glyphs, "tl", "tr", cap),
        _legend_row(_legend_title(title, cap), glyphs, cap),
        _legend_rule(glyphs, "ml", "mr", cap),
    ]
    for index, (heading, strips) in enumerate(sections):
        if index:
            lines.append(_legend_rule(glyphs, "ml", "mr", cap))
        lines.append(_legend_row(_legend_heading(heading, cap), glyphs, cap))
        lines.extend(_legend_row(_legend_body(strip, cap), glyphs, cap)
                     for strip in strips)
    lines.append(_legend_rule(glyphs, "bl", "br", cap))
    return lines


def get_legend_nanobot_chat(cap):
    fg = "fg"
    phase = [
        [("[user]", fg, PHASE_COLOURS["user"]),
         ("[activity]", fg, PHASE_COLOURS["activity"])],
        [("[reasoning]", fg, PHASE_COLOURS["reasoning"]),
         ("[answer]", fg, PHASE_COLOURS["answer"])],
        [("[complete]", fg, PHASE_COLOURS["complete"])],
    ]
    events = [
        [("Message / Tool", EVENT_COLOURS["message"], None)],
        [("Reasoning Delta", EVENT_COLOURS["reasoning_delta"], None)],
        [("\u25cf Stream End", EVENT_COLOURS["stream_end"], None),
         ("  \u25a0 Turn End", EVENT_COLOURS["turn_end"], None)],
        [("\u2666 Reasoning End", EVENT_COLOURS["reasoning_end"], None)],
    ]
    return _legend_frame("CHAT COLOR LEGEND",
                         [(" Phases (Backgrounds):", phase),
                          (" Events (Foregrounds):", events)], cap)


def get_legend_nanobot_session(cap):
    fg = "fg"
    roles = [
        [("[user]", fg, PHASE_COLOURS["user"]),
         ("[tool]", fg, PHASE_COLOURS["tool"])],
        [("[assistant]", fg, PHASE_COLOURS["assistant"]),
         ("[meta]", fg, PHASE_COLOURS["meta"])],
        [("[reasoning]", fg, PHASE_COLOURS["reasoning"])],
    ]
    data = [
        [("Tool Call", (255, 255, 0), None)],
        [("Tool Output", (170, 200, 255), None)],
        [("Reasoning Content", (170, 170, 170), None)],
        [("\u25a0 Turn End (latency)", (255, 0, 0), None)],
    ]
    return _legend_frame("SESSION COLOR LEGEND",
                         [(" Roles (Backgrounds):", roles),
                          (" Data (Foregrounds):", data)], cap)


LEGENDS = {
    "nanobot-chat": get_legend_nanobot_chat,
    "nanobot-session": get_legend_nanobot_session,
}


def legend_lines(parser_name, cap):
    """Legend popup lines for `parser_name`: no escapes when colour is off."""
    legend_func = LEGENDS.get(parser_name, get_legend_nanobot_chat)
    return legend_func(cap)


# ---------------------------------------------------------------------------
# UI Rendering
# ---------------------------------------------------------------------------
def _centre(text, width):
    """Centre `text` in exactly `width` cells, truncating instead of spilling.

    `.center()` measures code points, not cells, and leaves an over-long string
    untouched; both would let a long status line push the enclosing box past the
    terminal edge. Truncate first, then pad by display width.
    """
    text = tui.truncate(text, width)
    space = max(0, width - tui.display_width(text))
    left = space // 2
    return " " * left + text + " " * (space - left)


def _bar(text, cols, cap, fg="fg", bg="surface", bold=False, align="center"):
    """One full-width chrome bar, fitted to `cols` cells and aligned inside it.

    The plain case is `chrome.fill()` (same truncate/pad/background rules). The
    bold case - the full-view header - cannot go through `fill()`, which has no
    bold attribute, so it composes the same band from `palette.prefix()`.
    """
    if align == "center":
        body = _centre(text, cols)
    else:
        body = tui.pad(tui.truncate(text, cols), cols)
    if bold:
        return (tui.prefix(fg=fg, bg=bg, bold=True, cap=cap)
                + body + _reset(cap))
    return tui.chrome.fill(body, cols, bg=bg, fg=fg, cap=_layout_cap(cap))


def render_ui(monitor, last_rendered_rows, screen, cap):
    cols, rows = screen.size()
    max_visible_lines = max(1, rows - 4)  # leave 4 lines for bottom 2-row menu
    glyphs = tui.table.glyphs_for(cap)
    reset = _reset(cap)
    colours = tui.palette.palette(cap=cap)

    show_popup = monitor.show_legend and legend_fits(cols)
    popup_lines = legend_lines(monitor.parser_name, cap) if show_popup else []
    popup_width = LEGEND_WIDTH
    popup_height = len(popup_lines)
    popup_start_x = max(1, (cols - popup_width) // 2)
    popup_start_y = max(1, (max_visible_lines - popup_height) // 2)

    # Adjust scroll_top_index to keep selected_index in view
    if monitor.selected_index < monitor.scroll_top_index:
        monitor.scroll_top_index = monitor.selected_index
    elif monitor.selected_index >= monitor.scroll_top_index + max_visible_lines:
        monitor.scroll_top_index = monitor.selected_index - max_visible_lines + 1

    left_col_width = 18
    content_width = max(1, cols - left_col_width - 4)

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

            base_bg = tui.prefix(bg="surface" if ui_row % 2 == 1 else "bg", cap=cap)
            shade = ZEBRA_SHADE if ui_row % 2 == 1 else 0

            fname_disp = tui.truncate(state.filename, left_col_width - 1)
            if state.scroll_offset > 0:
                prefix_char = ">"
                prefix_color = tui.prefix(fg="error", cap=cap)
            elif is_selected:
                prefix_char = ">"
                prefix_color = tui.prefix(fg="fg", bold=True, cap=cap)
            else:
                prefix_char = " "
                prefix_color = tui.prefix(fg="muted", cap=cap)

            if is_selected:
                fname_color = tui.prefix(fg="fg", bold=True, cap=cap)
                fname_bg = tui.prefix(bg="accent", cap=cap)
            else:
                fname_color = tui.prefix(fg="muted", cap=cap)
                fname_bg = base_bg

            left_col_str = (
                fname_bg
                + prefix_color
                + prefix_char
                + fname_color
                + tui.pad(fname_disp, left_col_width - 1)
                + reset
                + base_bg
            )

            delta_s = now - state.mtime
            rec_color = tui.prefix(fg=get_recency_color(delta_s, colours), cap=cap)

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
                cfg = tui.prefix(fg=sp.fg, cap=cap) if sp.fg else ""
                if sp.bg:
                    cbg = tui.prefix(bg=_shade(sp.bg, shade), cap=cap) or base_bg
                else:
                    cbg = base_bg

                disp_text = sp.text.replace("\n", " ")
                room = content_width - chars_rendered
                if room <= 0:
                    break
                if tui.display_width(disp_text) > room:
                    # A wide/combining glyph would otherwise push the row past
                    # the terminal edge (line wrap is not disabled).
                    disp_text = tui.truncate(disp_text, room)
                content_str += f"{cfg}{cbg}{disp_text}{reset}{base_bg}"
                chars_rendered += tui.display_width(disp_text)

            padding = " " * max(0, content_width - chars_rendered)
            content_str += padding

            spacer = tui.prefix(fg="muted", cap=cap) + glyphs["v"] + reset + base_bg
            recency_block = rec_color + _marker(cap) + reset
            row_str = (
                f"{left_col_str}{spacer}{content_str}{spacer}{recency_block}{reset}"
            )

        else:
            row_str = (
                tui.prefix(bg="surface" if ui_row % 2 == 1 else "bg", cap=cap)
                + (" " * cols) + reset
            )

        if (
            show_popup
            and popup_start_y <= ui_row + 1 < popup_start_y + popup_height
        ):
            last_rendered_rows[ui_row] = None
        else:
            if last_rendered_rows.get(ui_row) != row_str:
                screen.move(0, ui_row)
                screen.write(row_str)
                last_rendered_rows[ui_row] = row_str

    if show_popup:
        for i, line_str in enumerate(popup_lines):
            popup_y = popup_start_y + i
            cache_key = f"popup_{popup_y}"
            if last_rendered_rows.get(cache_key) != line_str:
                screen.move(popup_start_x, popup_y)
                screen.write(line_str)
                last_rendered_rows[cache_key] = line_str
    else:
        keys_to_remove = [
            k
            for k in last_rendered_rows
            if isinstance(k, str) and k.startswith("popup_")
        ]
        for k in keys_to_remove:
            del last_rendered_rows[k]

    raw_status_line_1 = (
        f" Parser: {monitor.parser_name} | Files: {len(monitor.sorted_files)}"
        " | [Enter] Full View | [\u2191/\u2193] Sel | [\u2190/\u2192] Scroll"
        " | [h] Col | [l] Legend | [Esc/q] Quit "
    )
    marker = _marker(cap)
    raw_status_line_2 = f" Freshness: {marker} <5s ... {marker} >2m "

    inner = max(1, cols - 2)
    # Truncate before centring: at 80 columns the full hint line is ~120 cells
    # and .center() would return it unchanged, spilling onto the footer row.
    padded_line_1 = _centre(raw_status_line_1, inner)
    padded_line_2 = _centre(raw_status_line_2, inner)

    fresh_block = tui.prefix(fg=get_recency_color(0, colours), cap=cap) + marker + reset
    cold_block = (tui.prefix(fg=get_recency_color(200, colours), cap=cap)
                  + marker + reset)
    colored_line_2 = padded_line_2.replace(
        f"{marker} <5s", f"{fresh_block} <5s"
    ).replace(f"{marker} >2m", f"{cold_block} >2m")

    # The footer is one shared panel: themed frame, `surface` interior, the two
    # status lines as its body. `padding=0` keeps the rows exactly `cols` wide,
    # so the panel cannot spill past the terminal edge.
    footer_rows = tui.chrome.panel(
        "", [padded_line_1, colored_line_2], width=cols, padding=0,
        cap=_layout_cap(cap)
    ).split("\n")
    for index, row_text in enumerate(footer_rows):
        row_number = rows - 3 + index
        cache_key = f"bottom_{row_number}"
        if last_rendered_rows.get(cache_key) != row_text:
            screen.move(0, row_number - 1)
            screen.write(row_text)
            last_rendered_rows[cache_key] = row_text

    screen.flush()


def render_fullscreen_ui(monitor, last_rendered_rows, screen, cap):
    cols, rows = screen.size()
    viewport_height = max(1, rows - 2)  # Row 1 is header, last row is footer
    glyphs = tui.table.glyphs_for(cap)
    reset = _reset(cap)
    colours = tui.palette.palette(cap=cap)

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
    header_text = (
        f" FULL VIEW: {state.filename} | Entry {curr_event_idx + 1}/{total_events}"
        f" | Line {scroll_y + 1}/{total_lines} "
    )
    header_str = _bar(header_text, cols, cap, fg="bg", bg="accent", bold=True,
                      align="left")

    if last_rendered_rows.get("fs_header") != header_str:
        screen.move(0, 0)
        screen.write(header_str)
        last_rendered_rows["fs_header"] = header_str

    # 2. Viewport Lines
    for ui_row in range(viewport_height):
        line_idx = scroll_y + ui_row
        row_num = ui_row + 2

        if line_idx < total_lines:
            ev_idx, line_spans = rendered_lines[line_idx]

            shade = FULLSCREEN_SHADE if (line_idx % 2 == 1) else 0
            base_bg = tui.prefix(
                bg="surface" if (line_idx % 2 == 1) else "bg", cap=cap)

            line_str = ""
            chars_rendered = 0
            for sp in line_spans:
                cfg = tui.prefix(fg=sp.fg, cap=cap) if sp.fg else ""
                if sp.bg:
                    cbg = tui.prefix(bg=_shade(sp.bg, shade), cap=cap) or base_bg
                else:
                    cbg = base_bg

                text = sp.text
                room = cols - chars_rendered
                if room <= 0:
                    break
                if tui.display_width(text) > room:
                    text = tui.truncate(text, room)
                line_str += f"{cfg}{cbg}{text}{reset}{base_bg}"
                chars_rendered += tui.display_width(text)

            padding = " " * max(0, cols - chars_rendered)
            full_row_str = f"{base_bg}{line_str}{padding}{reset}"
        else:
            full_row_str = tui.prefix(bg="bg", cap=cap) + (" " * cols) + reset

        cache_key = f"fs_row_{ui_row}"
        if last_rendered_rows.get(cache_key) != full_row_str:
            screen.move(0, row_num - 1)
            screen.write(full_row_str)
            last_rendered_rows[cache_key] = full_row_str

    # 3. Popup Legend Overlay (skipped when the frame does not fit)
    if monitor.show_legend and legend_fits(cols):
        popup_width = LEGEND_WIDTH
        popup_lines = legend_lines(monitor.parser_name, cap)
        popup_height = len(popup_lines)
        popup_start_x = max(1, (cols - popup_width) // 2)
        popup_start_y = max(1, (viewport_height - popup_height) // 2 + 1)

        for i, line_str in enumerate(popup_lines):
            popup_y = popup_start_y + i
            cache_key = f"popup_{popup_y}"
            if last_rendered_rows.get(cache_key) != line_str:
                screen.move(popup_start_x, popup_y)
                screen.write(line_str)
                last_rendered_rows[cache_key] = line_str

    # 4. Bottom Footer Bar
    footer_text = (
        " [\u2190/\u2192] Prev/Next Entry | [\u2191/\u2193/PgUp/PgDn] Scroll"
        " | [h] Col | [l] Legend | [Esc/Enter/q] Back "
    )
    footer_str = _bar(footer_text, cols, cap, fg="fg", bg="surface")

    if last_rendered_rows.get("fs_footer") != footer_str:
        screen.move(0, rows - 1)
        screen.write(footer_str)
        last_rendered_rows["fs_footer"] = footer_str

    screen.flush()


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------
def toggle_collapse(monitor):
    """Flip the message-collapse mode and force every file to re-parse."""
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


def run_loop(screen, cap, args):
    """The event loop: keyboard, file polling, resize handling, one render."""
    monitor = Monitor(args.parser, args.dir)
    last_rendered_rows = {}

    while True:
        key = tui.keys.read_key(timeout=0)
        if key == "ctrl-c":
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
                        # Repaint: the theme background replaces the old view,
                        # so the transition does not leave stale rows on the
                        # terminal's own background colour.
                        _repaint(screen, cap)
                        last_rendered_rows.clear()
                    elif key == "h":
                        toggle_collapse(monitor)

        # Mode 2: Full Screen File Reading Mode
        elif monitor.mode == "fullscreen":
            active_file = monitor.fullscreen_file
            state = monitor.files_state.get(active_file)

            if state:
                cols, rows = screen.size()
                viewport_height = rows - 2
                rendered_lines, event_line_map = build_fullscreen_rendered_lines(
                    state.events, cols
                )
                total_lines = len(rendered_lines)
                max_scroll = max(0, total_lines - viewport_height)

                if key in ("esc", "q", "enter", "b"):
                    monitor.mode = "main"
                    _repaint(screen, cap)
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
                    toggle_collapse(monitor)

        # 2. Poll Files
        monitor.poll_files()

        # Check terminal resize
        if screen.poll_resize():
            _repaint(screen, cap)
            last_rendered_rows.clear()

        # 3. Render Active Mode View
        if monitor.mode == "fullscreen":
            render_fullscreen_ui(monitor, last_rendered_rows, screen, cap)
        else:
            render_ui(monitor, last_rendered_rows, screen, cap)

        # 4. Sleep to maintain ~10Hz max update rate
        time.sleep(0.1)


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

    # One capability record for the whole run. argparse has already handled
    # --help; from here on the monitor is a full-screen, keyboard-driven view.
    tui.init_ansi()
    cap = tui.detect()
    tui.require_tty("jsonl_monitor")

    debug_log("\n=== Application Started ===")
    debug_log(f"Arguments: {args}")

    screen = tui.Screen(sys.stdout)
    screen.enter()
    # Paint the whole page with the theme background before the first frame:
    # every later diff assumes that backdrop (it is only re-painted on a mode
    # change or a resize).
    screen.fill()
    try:
        with tui.keys.raw_mode(sys.stdin):
            run_loop(screen, cap, args)
    except KeyboardInterrupt:
        pass
    except Exception:
        screen.exit()
        print("An error occurred:")
        traceback.print_exc()
        return 1
    finally:
        screen.exit()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Downstream reader closed the pipe; exit quietly and point stdout at
        # devnull so the interpreter's shutdown flush cannot raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
