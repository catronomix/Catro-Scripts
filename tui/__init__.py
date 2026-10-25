# Shared terminal library for catro-scripts
"""
			CATRO-SCRIPTS TUI LIBRARY
			=========================
One stdlib-only source of truth for terminal interaction: capability detection,
the house palette, styled text, tables, prompts, full-screen primitives and the
frame loop that hosts `.screensaver` plugins.

Layout:
	config    project config.ini read/optional-write
	caps      Capabilities and detection precedence
	text      display width, truncate, pad, wrap, strip ANSI
	palette   dark/light palettes, style() and level downgrade
	table     box/plain tables, banner, section, key-value blocks
	prompts   ask_text, ask_int, ask_choice
	screen    Screen, Canvas, TerminalRenderer
	keys      raw mode, key decoding, background KeyReader
	progress  Spinner, ProgressBar, LiveRegion
	pager     paged output
	loop      FrameLoop, ScreensaverHost

Importing this package is inert: no printing, no config write, no terminal mode
change, no third-party import. Submodules keep their module names as attributes
(`tui.palette` is the module; use `tui.palette.palette()` for the palette dict),
and the common helpers are re-exported at the top level.

Usage:
	from tui import caps, palette, table
"""

from . import caps, config, keys, loop, palette, pager, progress, prompts, screen, table, text
from .caps import Capabilities, detect, init_ansi, require_tty
from .loop import FrameLoop, ScreensaverHost
from .pager import page
from .palette import DARK, LIGHT, THEMES, style, theme
from .progress import LiveRegion, ProgressBar, Spinner
from .prompts import ask_choice, ask_int, ask_text
from .screen import Canvas, Screen, TerminalRenderer
from .table import banner, key_values, print_table, render_table, section
from .text import display_width, pad, strip_ansi, truncate, wrap

__all__ = [
	"caps", "config", "keys", "loop", "palette", "pager", "progress",
	"prompts", "screen", "table", "text",
	"Capabilities", "detect", "init_ansi", "require_tty",
	"DARK", "LIGHT", "THEMES", "style", "theme",
	"display_width", "pad", "strip_ansi", "truncate", "wrap",
	"banner", "key_values", "print_table", "render_table", "section",
	"Canvas", "Screen", "TerminalRenderer",
	"ask_choice", "ask_int", "ask_text",
	"LiveRegion", "ProgressBar", "Spinner",
	"page", "FrameLoop", "ScreensaverHost",
]
