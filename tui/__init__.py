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
change, no third-party import. Submodules are importable as `tui.<name>`.

Usage:
	from tui import caps, palette, table
"""
