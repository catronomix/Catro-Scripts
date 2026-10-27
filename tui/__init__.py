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
	palette   soft and contrast palettes, style() and level downgrade
	table     box/plain tables, banner, section, key-value blocks
	chrome    masthead, panel, rule, field, status, fill, menu, button, scrollbar
	colorpicker  hex/RGB/HSV conversions and the colour picker popup
	prompts   ask_text, ask_int, ask_choice
	screen    Screen, Canvas, TerminalRenderer
	keys      raw mode, key decoding, background KeyReader
	mouse     SGR mouse reporting, decoding and restore
	widgetkit widget base, clipping panel, focus styling, small-terminal fallback
	widgets   buttons, fields, list, scrollbar (re-exports widgetkit)
	progress  Spinner, ProgressBar, LiveRegion
	pager     paged output
	loop      FrameLoop, ScreensaverHost

Importing this package is inert: no printing, no config write, no terminal mode
change, no third-party import. Submodules keep their module names as attributes
(`tui.palette` is the module; use `tui.palette.palette()` for the palette dict),
and the common helpers are re-exported at the top level. `tui.chrome` is the
page-chrome module and its helpers are re-exported by name; `tui.page` is still
the pager helper, not a module.

Usage:
	from tui import caps, palette, table
"""

from . import caps, chrome, colorpicker, config, keys, loop, mouse, palette, pager, progress, prompts, screen, table, text, widgetkit, widgets
from .caps import Capabilities, detect, init_ansi, require_tty
from .chrome import button, field, fill, header, menu, panel, rule, scrollbar, status
from .colorpicker import (WCAG_AA, ColorPicker, contrast_ratio, hex_to_rgb, hsv_to_rgb,
						  luminance, rgb_to_hex, rgb_to_hsv)
from .loop import FrameLoop, ScreensaverHost
from .mouse import decode, disable, enable, parse_token, reporting, token
from .palette import CONTRAST_DARK, CONTRAST_LIGHT, RESET, SOFT, THEMES, prefix, style, theme
from .pager import page
from .progress import LiveRegion, ProgressBar, Spinner
from .prompts import ask_choice, ask_int, ask_text
from .screen import Canvas, Screen, TerminalRenderer
from .table import banner, key_values, print_table, render_table, section
from .text import display_width, pad, strip_ansi, truncate, wrap
from .widgets import (Button, CheckField, Clip, ListBox, Panel,
					  ScrollBar, SelectField, TextField, Widget, cells,
					  focus_prefix, resize_notice, small_terminal)

__all__ = [
	"caps", "chrome", "colorpicker", "config", "keys", "loop", "mouse", "palette",
	"pager", "progress", "prompts", "screen", "table", "text", "widgetkit",
	"widgets",
	"Capabilities", "detect", "init_ansi", "require_tty",
	"WCAG_AA", "ColorPicker", "contrast_ratio", "hex_to_rgb", "hsv_to_rgb",
	"luminance", "rgb_to_hex", "rgb_to_hsv",
	"CONTRAST_DARK", "CONTRAST_LIGHT", "RESET", "SOFT", "THEMES", "prefix",
	"style", "theme",
	"display_width", "pad", "strip_ansi", "truncate", "wrap",
	"banner", "key_values", "print_table", "render_table", "section",
	"header", "panel", "rule", "field", "status", "fill", "menu", "button",
	"scrollbar",
	"Canvas", "Screen", "TerminalRenderer",
	"decode", "disable", "enable", "parse_token", "reporting", "token",
	"Button", "CheckField", "Clip", "ListBox", "Panel",
	"ScrollBar", "SelectField", "TextField", "Widget", "cells", "focus_prefix",
	"resize_notice", "small_terminal",
	"ask_choice", "ask_int", "ask_text",
	"LiveRegion", "ProgressBar", "Spinner",
	"page", "FrameLoop", "ScreensaverHost",
]
