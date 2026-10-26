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
`tui.editorpaint`, the Save/Load/picker/mouse flows in `tui.editoractions`.
"""

import sys

from . import caps, editoractions, editorpaint, editorviews, keys as keyio
from . import mouse, screen, theme_engine, widgets
from .editorviews import BUTTONS, HELP_LINE, PANELS, PROPERTY_KEYS


class ThemeEditor:
	"""One editing session over a theme document; see the module docstring."""

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
		self.save_field = None
		self.load_box = None
		self.entries = []
		self.buttons = []
		self.rects = {}
		self.focus = 0
		self.property_index = 0
		self.property_offset = 0
		self.colour_index = 0
		self.colour_offset = 0
		self.button_index = 0
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
		if widgets.small_terminal(width, height):
			return
		preview_h = max(6, min(12, height - 12))
		column = max(8, (width - 2) // 3)
		for index in range(3):
			self.rects[index] = (1 + index * column, 2, column, preview_h)
		panel_y = 3 + preview_h
		panel_h = max(3, height - panel_y - 2)
		prop_w = min(40, max(30, width // 2 - 6))
		self.rects[3] = (1, panel_y, prop_w, panel_h)
		colour_w = min(30, max(18, width - prop_w - 4))
		self.rects[4] = (2 + prop_w, panel_y, colour_w, panel_h)
		action_x = 3 + prop_w + colour_w
		self.rects[5] = (action_x, panel_y, max(10, width - action_x - 1),
						 panel_h)
		for index, label in enumerate(BUTTONS):
			self.buttons.append(widgets.Button(
				action_x + 2, panel_y + 2 + 2 * index, label, cap=self.cap))

	def _visible(self, panel):
		rect = self.rects.get(panel)
		return max(1, rect[3] - 2) if rect else 9

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

	# -- key routing -----------------------------------------------------

	def handle(self, token):
		"""Route one key/mouse token; True when the editor consumed it."""
		if token is None or self.closed:
			return False
		if self.picker is not None:
			return editoractions.picker_key(self, token)
		if self.prompt == "save":
			return editoractions.save_key(self, token)
		if self.prompt == "load":
			return editoractions.load_key(self, token)
		if self.prompt in ("quit", "discard-load", "overwrite"):
			return editoractions.confirm_key(self, token)
		if self.help:
			if token in ("f1", "esc", "enter", "q", "Q"):
				self.help = False
			return True
		event = mouse.parse_token(token)
		if event is not None:
			return editoractions.mouse(self, *event)
		if token == "ctrl-s":
			self.save_prompt()
			return True
		if token == "f1":
			self.help = True
			return True
		if token in ("delete", "q", "Q"):
			self.quit()
			return True
		if token in ("tab", "shift-tab", "backtab"):
			self.focus = (self.focus + (1 if token == "tab" else -1)) % 3
			self.message = ("info", "{} panel".format(PANELS[self.focus]))
			return True
		if token in ("left", "right"):
			step = 1 if token == "right" else -1
			self.look_index = (self.look_index + step) % 3
			self.message = ("info", "editing the {} look".format(
				editorviews.look_label(self._current_look())))
			return True
		if token == "esc":
			return self._escape()
		if token in ("up", "down", "pageup", "pagedown", "home", "end"):
			return self._move(token)
		if token == "enter":
			return self._activate()
		return False

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

	def _escape(self):
		"""Esc: ask before dropping edits; otherwise just say nothing is lost."""
		if self.dirty:
			self.prompt = "quit"
			self.message = ("warn", "Discard changes? y/n")
		else:
			self.message = ("info", "no unsaved changes; Q or Delete quits")
		return True

	def _move(self, token):
		if self.focus == 2:
			self.button_index = (self.button_index
								 + (-1 if token in ("up", "home") else 1)) % 3
			return True
		panel = 3 if self.focus == 0 else 4
		keys = PROPERTY_KEYS if panel == 3 else theme_engine.PALETTE_KEYS
		index = self.property_index if panel == 3 else self.colour_index
		offset = self.property_offset if panel == 3 else self.colour_offset
		row = self._visible(panel)
		steps = {"up": -1, "down": 1, "pageup": -row, "pagedown": row,
				 "home": -len(keys), "end": len(keys)}
		index = max(0, min(len(keys) - 1, index + steps[token]))
		offset = self._window(index, offset, len(keys), row)
		if panel == 3:
			self.property_index, self.property_offset = index, offset
		else:
			self.colour_index, self.colour_offset = index, offset
		return True

	def _activate(self):
		"""Enter: edit the focused row, open the picker, or press the button."""
		if self.focus == 0:
			return self._edit_property()
		if self.focus == 1:
			return editoractions.open_picker(self) is not None
		action = BUTTONS[self.button_index]
		if action == "Save":
			self.save_prompt()
		elif action == "Load":
			self.load_popup()
		else:
			self.quit()
		return True

	def _property_field(self, key):
		"""A fresh widget for one property, so one edit cannot leak its state."""
		value = self.document["properties"][key]
		if key == "table_zebra":
			return widgets.CheckField(0, 0, key, bool(value), cap=self.cap)
		options = list(theme_engine.PROPERTY_VALUES[key])
		return widgets.SelectField(
			0, 0, options, index=options.index(value) if value in options
			else 0, cap=self.cap)

	def _edit_property(self):
		key = PROPERTY_KEYS[self.property_index]
		before = self.document["properties"][key]
		field = self._property_field(key)
		field.key("enter")
		value = field.value if hasattr(field, "value") else field.selected()
		if value != before:
			self.document["properties"][key] = value
			self.dirty = True
			self.message = ("ok", "{} = {}".format(key, value))
		else:
			self.message = ("info", "{} = {}".format(key, before))
		return True

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

	def draw(self):
		"""Paint one frame onto the injected canvas; returns `self`."""
		editorpaint.draw(self)
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
			self.screen.enter()
			try:
				self._layout()
				paint = True
				reader.start()
				while not self.closed:
					token = reader.wait(0.1)
					if token is not None:
						self.handle(token)
						paint = True
					if self.screen.poll_resize():
						self.canvas = screen.Canvas(stream=stream)
						self._layout()
						paint = True
					if paint and not self.closed:
						self.draw()
						self.canvas.render(full=True)
						paint = False
			finally:
				reader.stop()
				self.screen.exit()
		return 0
