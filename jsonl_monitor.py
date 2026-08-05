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

def debug_log(msg):
	"""Writes a timestamped debug message to jsonl_debug.log in the script's directory."""
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
			try:
				return c.decode("utf-8", "ignore").lower()
			except:
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
			if b == "\x1b":
				# Wait briefly to see if it's an escape sequence or a raw ESC key
				if select.select([sys.stdin], [], [], 0.05)[0]:
					b2 = sys.stdin.read(1)
					if b2 == "[":
						b3 = sys.stdin.read(1)
						if b3 == "A":
							return "up"
						if b3 == "B":
							return "down"
						if b3 == "C":
							return "right"
						if b3 == "D":
							return "left"
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
		self.total_chars = 0
		self.last_phase = None
		self.scroll_offset = 0  # 0 means auto-scroll (right-aligned)
		self.collapse_messages = collapse_messages
		self.current_block_char_count = 0

	def append_span(self, span):
		self.spans.append(span)
		self.total_chars += len(span.text)


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
	text = text.replace("\n", " ").replace("\t", " ")
	return re.sub(r"[^\x20-\x7E]", "", text)


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
        line_state.append_span(Span(f"[{phase}] ", fg=(200, 200, 200), bg=bg))
        line_state.last_phase = phase
        line_state.current_block_char_count = 0

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
        line_state.append_span(Span(text, fg=fg, bg=bg))


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

	# Prepend phase indicator if it changed
	if phase and phase != line_state.last_phase:
		line_state.append_span(Span(f"[{phase}] ", fg=(200, 200, 200), bg=bg))
		line_state.last_phase = phase
		line_state.current_block_char_count = 0

	# Helper to process text limits when collapsing is enabled [H]
	def process_text(text, is_collapsible, fg_color, bg_color):
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
			line_state.append_span(Span(text, fg=fg_color, bg=bg_color))

	# Parse based on phase type
	if phase == "meta":
		key = json_data.get("key", "")
		process_text(f"Key: {key} ", False, (255, 255, 255), bg)

	elif phase == "user":
		process_text(json_data.get("content", ""), True, (255, 255, 255), bg)

	elif phase == "tool":
		name = json_data.get("name", "unknown")
		content = json_data.get("content", "")
		process_text(f"[{name}] {content} ", False, (170, 200, 255), bg)

	elif phase == "assistant":
		reasoning = json_data.get("reasoning_content")
		if reasoning:
			line_state.append_span(
				Span("[reasoning] ", fg=(200, 200, 200), bg=(50, 0, 50))
			)
			process_text(reasoning + " ", False, (170, 170, 170), (50, 0, 50))

		content = json_data.get("content")
		if content:
			process_text(content + " ", True, (255, 255, 255), bg)

		tools = json_data.get("tool_calls", [])
		for tool in tools:
			func = tool.get("function", {})
			name = func.get("name", "unknown")
			args = func.get("arguments", "{}")
			process_text(f"[Call: {name} {args}] ", False, (255, 255, 0), bg)

		# Append red block if the response finished (measured via latency presence)
		lat = json_data.get("latency_ms")
		if lat:
			line_state.append_span(Span("■ ", fg=(255, 0, 0), bg=bg))


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

	def poll_files(self):
		"""Checks for file modifications, additions, and deletions."""
		pattern = os.path.join(self.target_dir, "*.jsonl")
		current_files = glob.glob(pattern)

		debug_log(f"poll_files: Target dir='{self.target_dir}', Pattern='{pattern}', Found {len(current_files)} files")

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
					state.total_chars = 0
					state.last_phase = None
					state.current_block_char_count = 0

				if mtime > state.mtime or size > state.cursor_pos:
					debug_log(f"poll_files: Reading new lines for '{f}' (mtime={mtime}, size={size}, cursor={state.cursor_pos})")
					self._read_new_lines(f, state)
					state.mtime = mtime
					needs_reorder = True

			except Exception as e:
				debug_log(f"poll_files: Error processing file '{f}': {e}")
				# file might have been deleted mid-poll between glob and stat
				if f in self.files_state:
					del self.files_state[f]
				needs_reorder = True

		if needs_reorder:
			debug_log("poll_files: Reordering display list")
			# Sort descending by mtime derived directly from our definitive state dictionary
			file_stats = [(f, s.mtime) for f, s in self.files_state.items()]
			file_stats.sort(key=lambda x: x[1], reverse=True)
			new_sorted = [x[0] for x in file_stats]

			if new_sorted != self.sorted_files:
				# Maintain selection on the same file if possible
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
			return True  # indicates full redraw needed due to reorder
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
	# layout: [left_col] │ [content] │ █
	# spaces: 18 + 1 + 1 + content + 1 + 1 + 1 = cols
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

			# Row Background
			row_bg_val = 26 if ui_row % 2 == 1 else 0
			base_bg = rgb(row_bg_val, row_bg_val, row_bg_val, bg=True)

			# Left Column (Filename)
			fname_disp = state.filename[: left_col_width - 1]
			if state.scroll_offset > 0:
				prefix_char = ">"
				prefix_color = rgb(255, 0, 0)  # Red indicates scrolled/paused
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

			# Recency Indicator
			delta_s = now - state.mtime
			rec_color = get_recency_color(delta_s)

			# Main Content
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
					# Alter background slightly per row
					adjusted_bg = (
						min(255, sp.bg[0] + row_bg_val),
						min(255, sp.bg[1] + row_bg_val),
						min(255, sp.bg[2] + row_bg_val),
					)
					cbg = rgb(*adjusted_bg, bg=True)
				else:
					cbg = base_bg

				content_str += f"{cfg}{cbg}{sp.text}{RESET}{base_bg}"
				chars_rendered += len(sp.text)

			# Pad content to full width
			padding = " " * max(0, content_width - chars_rendered)
			content_str += padding

			# Build full line
			spacer = rgb(100, 100, 100) + "│" + RESET + base_bg
			recency_block = rec_color + "█" + RESET
			row_str = (
				f"{left_col_str}{spacer}{content_str}{spacer}{recency_block}{RESET}"
			)

		else:
			# Empty row
			row_bg_val = 26 if ui_row % 2 == 1 else 0
			row_str = (
				rgb(row_bg_val, row_bg_val, row_bg_val, bg=True) + (" " * cols) + RESET
			)

		if (
			monitor.show_legend
			and popup_start_y <= ui_row + 1 < popup_start_y + popup_height
		):
			# Avoid rendering the background text over where the popup will be drawn
			# We invalidate the cache to ensure it fully redraws when the popup closes
			last_rendered_rows[ui_row] = None
		else:
			# Only draw if changed to prevent flicker
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
		# Clean up popup cache to ensure proper redraw if opened again later
		keys_to_remove = [
			k
			for k in last_rendered_rows
			if isinstance(k, str) and k.startswith("popup_")
		]
		for k in keys_to_remove:
			del last_rendered_rows[k]

	# Draw Bottom Status Box (2 lines)
	raw_status_line_1 = f" Parser: {monitor.parser_name} | Files: {len(monitor.sorted_files)} | [↑/↓] Sel | [←/→] Scroll | [a] Auto | [h] Col | [l] Legend | [Esc/q] Quit "
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

	# Use exact positioning instead of \n to prevent terminal scrolling
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
			# 1. Handle Input
			key = get_key()
			if key in ("q", "esc", "\x03"):  # q, Esc, or Ctrl+C
				break

			if key == "l":
				monitor.show_legend = not monitor.show_legend

			if len(monitor.sorted_files) > 0:
				# Clamp index just in case list shrank dynamically
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
							len(monitor.sorted_files) - 1, monitor.selected_index + 1
						)
					elif key == "left":
						state.scroll_offset += 10  # Scroll left (view older history)
					elif key == "right":
						state.scroll_offset = max(0, state.scroll_offset - 10)
					elif key == "a":
						state.scroll_offset = 0  # Jump to end / enable auto-scroll
					elif key == "h":
						monitor.collapse_messages = not monitor.collapse_messages
						# Trigger complete re-parse of all files to apply new formatting
						for s in monitor.files_state.values():
							s.collapse_messages = monitor.collapse_messages
							s.cursor_pos = 0
							s.spans = []
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

			# 3. Render
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