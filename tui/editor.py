# Full-screen theme editor: previews, Properties/Colours panels, Save/Load
"""
			THEME EDITOR
			=============
The full-screen theme editor behind `theme edit [name]`: three live
kitchen-sink previews (one per look), a Properties panel for every rendering
property, a Colours panel that edits one palette key at a time through
`tui.colorpicker`, and Save/Load popups. Save writes through
`theme_engine.save_theme` (atomic, `.json` implied, overwrite confirmed) and
updates `theme.ini`; Load lists `themes/*.json` with the active theme marked
`*`, keeps an invalid file as an `!` row and never breaks the list.

Construction is inert and terminal-free: pass a `Canvas` and a key source and
`open()`, `handle()`, `preview_titles()`, `save_prompt()`, `load_popup()` and
`quit()` all run headless. The real `Screen`, `KeyReader` and mouse reporting
are created by `run()` only, inside `try/finally`, so the alternate screen is
restored on every exit path including an exception. Painting lives in
`tui.editorpaint`, the Save/Load/picker/mouse flows in `tui.editoractions` and
the token router in `tui.editor_keys`.
"""

import sys

from . import caps, editoractions, editorpaint, editorviews, keys as keyio
from . import mouse, mouse_clicks, screen, theme_engine, widgets
from .editor_keys import EditorKeys
from .editorviews import BUTTONS, HELP_LINE


class ThemeEditor(EditorKeys):
	"""One editing session over a theme document; keys come from `EditorKeys`."""

	def __init__(self, name=None, *, canvas=None, keys=None, cap=None,
				 document=None):
		self.name = name
		self.canvas = canvas
		self.key_queue = keys
		self.cap = cap
		self.screen = None
		self.stream = None
		self.closed = False
		self.help = False
		self.prompt = None
		self.pending = None
		self.dirty = False
		self.picker = None
		self.edit = None
		self.save_field = None
		self.load_box = None
		self.entries = []
		self.buttons = []
		self.rects = {}
		self._layout_size = None
		self._overlay_rect = None
		self.focus = 0
		self.property_index = 0
		self.property_offset = 0
		self.colour_index = 0
		self.colour_offset = 0
		self.button_index = 0
		self.clicks = mouse_clicks.ClickTracker()
		self.message = ("info", HELP_LINE)
		self.document = document if document is not None else self._initial(name)
		self.look_index = self._initial_look()
		self._layout()

	# -- construction ----------------------------------------------------

	@staticmethod
	def _initial(name):
		"""The named document, else the active one; never raises."""
		if name:
			try:
				return theme_engine.load_theme(name)
			except (theme_engine.ThemeError, OSError):
				pass
		return theme_engine.document()

	def _initial_look(self):
		"""The selected look when editing the selected theme, else the first."""
		selected, selector = theme_engine.selection()
		look_id = theme_engine.SELECTORS.get(selector, "default")
		if (self.document.get("name") == selected
				and look_id in editorviews.LOOK_ORDER):
			return editorviews.LOOK_ORDER.index(look_id)
		return 0

	def preview_titles(self):
		"""`<display> - <selector>` for each of the three previews."""
		return editorviews.preview_titles(self.document)

	def open(self):
		"""Lay out and paint the first frame; no terminal I/O."""
		self.message = ("info", HELP_LINE)
		self._layout()
		self.draw()
		return self

	# -- geometry --------------------------------------------------------

	def _layout(self):
		"""Recompute every rectangle for the current canvas size."""
		self.rects, self.buttons = {}, []
		if self.canvas is None:
			return
		width, height = self.canvas.width, self.canvas.height
		self._layout_size = (width, height)
		if widgets.small_terminal(width, height):
			return
		preview_h = max(6, min(12, height - 12))
		# One blank column between (and around) the three live previews.
		column = max(8, (width - 4) // 3)
		for index in range(3):
			self.rects[index] = (1 + index * (column + 1), 2, column, preview_h)
		panel_y = 3 + preview_h
		panel_h = max(3, height - panel_y - 2)
		prop_w = min(40, max(30, width // 2 - 6))
		self.rects[3] = (1, panel_y, prop_w, panel_h)
		colour_w = min(30, max(18, width - prop_w - 4))
		self.rects[4] = (2 + prop_w, panel_y, colour_w, panel_h)
		action_x = 3 + prop_w + colour_w
		self.rects[5] = (action_x, panel_y, max(10, width - action_x - 1),
						 panel_h)
		# One blank row under the title, two between buttons: the top and bottom
		# rules stay visible even in the smallest supported terminal (90x24).
		for index, label in enumerate(BUTTONS):
			self.buttons.append(widgets.Button(
				action_x + 2, panel_y + 1 + 2 * index, label, cap=self.cap))

	def _visible(self, panel):
		rect = self.rects.get(panel)
		return max(1, rect[3] - 2) if rect else 9

	def _rows(self, panel):
		"""The display-order key names of the Properties or Colours pane."""
		return (editorviews.PROPERTY_KEYS, theme_engine.PALETTE_KEYS)[panel - 3]

	@staticmethod
	def _window(selected, offset, count, visible):
		"""Scroll `offset` so `selected` is inside a `visible`-row window."""
		if count <= visible:
			return 0
		if selected < offset:
			offset = selected
		elif selected >= offset + visible:
			offset = selected - visible + 1
		return max(0, min(offset, count - visible))

	def _panel_at(self, x, y):
		"""Panel index (3 Properties, 4 Colours, 5 Actions) under a point."""
		for index in (3, 4, 5):
			rect = self.rects.get(index)
			if rect and rect[0] <= x < rect[0] + rect[2] \
					and rect[1] <= y < rect[1] + rect[3]:
				return index
		return None

	# -- key routing (implemented in `tui.editor_keys`) -------------------

	def pump(self, tokens=None):
		"""Feed an injected token sequence, stopping when the editor closes."""
		for token in (self.key_queue if tokens is None else tokens) or ():
			if self.closed:
				break
			self.handle(token)
		return self

	def _current_look(self):
		return editorviews.LOOK_ORDER[self.look_index % 3]

	def _look_colours(self):
		return self.document["looks"][self._current_look()]

	# -- popups (implemented in `tui.editoractions`) ----------------------

	def quit(self):
		"""Quit, or ask first when there are unsaved changes."""
		if self.dirty:
			self.prompt = "quit"
			self.message = ("warn", "Discard changes? y/n")
			return False
		self.closed = True
		return True

	def save_prompt(self):
		"""Open the Save popup; returns the preseeded, editable filename."""
		return editoractions.save_prompt(self)

	def load_popup(self):
		"""Open the Load popup; returns the rows it lists (invalid ones marked)."""
		return editoractions.load_popup(self)

	# -- drawing ---------------------------------------------------------

	def draw(self, full=True):
		"""Paint one frame onto the injected canvas; returns `self`.

		`full` asks for a full-screen repaint (first frame, resize, anything
		that cleared the terminal); otherwise the painter erases only the
		overlay a previous frame left and redraws its bands, so the caller can
		render a changed-cell diff.
		"""
		editorpaint.draw(self, full=full)
		return self

	# -- real terminal wiring --------------------------------------------

	def run(self, stream=None):
		"""Own the terminal for one session; alt-screen restored in `finally`."""
		stream = sys.stdout if stream is None else stream
		self.stream = stream
		self.cap = self.cap or caps.detect(stream)
		self.screen = screen.Screen(stream)
		self.canvas = screen.Canvas(stream=stream)
		reader = keyio.KeyReader()
		with mouse.reporting(stream):
			# cbreak mode so Tab/Esc/arrows arrive one key at a time on POSIX;
			# restored after the screen leaves even when the loop raises.
			with keyio.raw_mode():
				self.screen.enter()
				try:
					self._layout()
					paint = True
					# A full frame is only needed when the terminal has no
					# previous image: the first paint, a resize, or a clear.
					# Every later keystroke goes out as a batched diff.
					full = True
					reader.start()
					while not self.closed:
						token = reader.wait(0.1)
						if token is not None:
							self.handle(token)
							paint = True
						if self.screen.poll_resize():
							self.canvas = screen.Canvas(stream=stream)
							self._layout()
							paint = full = True
						if paint and not self.closed:
							self.draw(full=full)
							self.canvas.render(full=full)
							paint = full = False
				finally:
					reader.stop()
					self.screen.exit()
		return 0
