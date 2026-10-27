# Editor key routing: token -> action for one editing session
"""
			EDITOR KEY ROUTING
			==================
The token router of `tui.editor`, mixed into the session class: `handle()` and
the helpers it dispatches to - the panel move (`_move`), Enter (`_activate`),
Esc (`_escape`), the small-terminal guard (`_small`/`_small_key`) and the
property draft fields (`_property_field`/`_field_for`/`_field_value`).

It is purely token -> action: no layout, no drawing, no terminal, no
`themes/` access. The mixin never imports `tui.editor`; it reaches the session
only through `self` and the flows it delegates to live in `tui.editoractions`.
This is where ticket B's arrow-editing and double-click routing lands, so the
key half stays free of session and storage code.
"""

from . import editoractions, editorviews, mouse, theme_engine, widgets
from .editorviews import BUTTONS, PANELS, PROPERTY_KEYS


class EditorKeys:
	"""Token routing mixed into `ThemeEditor`; see the module docstring."""

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
		if self._small():
			return self._small_key(token)
		if self.edit is not None:
			return editoractions.edit_key(self, token)
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

	def _small(self):
		"""True when the terminal is below the editor's minimum size."""
		return (self.canvas is not None
				and widgets.small_terminal(self.canvas.width, self.canvas.height))

	def _small_key(self, token):
		"""Below the minimum only the quit keys act; nothing opens or mutates."""
		if token in ("q", "Q", "delete", "esc"):
			self.quit()
		return True

	def _activate(self):
		"""Enter: edit the focused row, open the picker, or press the button."""
		if self.focus == 0:
			if self.edit is not None:
				return editoractions.commit_property(self)
			return editoractions.begin_property_edit(self)
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

	def _field_for(self, key):
		"""The draft field while that property is being edited, else a fresh one."""
		if self.edit is not None and self.edit["key"] == key:
			return self.edit["field"]
		return self._property_field(key)

	@staticmethod
	def _field_value(field):
		"""The value a SelectField/CheckField currently shows."""
		if hasattr(field, "selected"):
			return field.selected()
		return field.value
