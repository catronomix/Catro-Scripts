# Click counting: consecutive presses become one `double` event
"""
			CLICK COUNTING
			==============
The click-count model the widgets share: `ClickTracker.push()` returns the kind
to dispatch, so a host feeds every decoded mouse event through it and passes on
whatever comes back. Nothing here reads a terminal, a clock of its own or a
canvas.

	| input                                      | returns   | state    |
	|--------------------------------------------|-----------|----------|
	| first `press`                              | `press`   | armed    |
	| second `press` inside the window/radius    | `double`  | disarmed |
	| `press` outside the window or the radius   | `press`   | re-armed |
	| `press` with other button/modifiers        | `press`   | re-armed |
	| `release`, `drag`, `move`                  | unchanged | disarmed |
	| `wheel-*`                                  | unchanged | unchanged|

The window (0.4 s) and radius (one cell) are the tolerance of a human double
click, not a preference: a longer window turns two deliberate clicks into one
edit, a shorter one never fires on a real mouse. `now` is injected - it
defaults to `time.monotonic` - so tests advance a mutable cell instead of
sleeping, and `reset()` lets a host forget an armed press between unrelated
gestures (test setup, a mode change, a resize).
"""

import time

from . import mouse

CLICK_WINDOW = 0.4
CLICK_RADIUS = 1


class ClickTracker:
	"""Click-count state for one host; the module docstring has the rules."""
	def __init__(self, window=CLICK_WINDOW, radius=CLICK_RADIUS, now=None):
		self.window, self.radius = float(window), int(radius)
		self._now = now or time.monotonic
		self._armed = None

	def push(self, kind, x, y, modifiers=(), *, button=0):
		"""The kind to dispatch for one event; paired presses become `double`."""
		if kind == mouse.PRESS:
			return self._press(int(x), int(y), tuple(modifiers), int(button))
		# A wheel notch can land between the two halves of a double click, so
		# it passes through without breaking the count; everything else moves
		# the pointer or ends the gesture and disarms.
		if not str(kind).startswith("wheel-"):
			self._armed = None
		return kind

	def reset(self):
		"""Forget an armed press; the next press is a first press again."""
		self._armed = None
		return self

	def _press(self, x, y, modifiers, button):
		"""Emit `press`, or `double` when this press closes the previous one."""
		armed, when = self._armed, self._now()
		self._armed = None
		if (armed is not None and when - armed[4] <= self.window
				and abs(x - armed[0]) <= self.radius
				and abs(y - armed[1]) <= self.radius
				and modifiers == armed[2] and button == armed[3]):
			return mouse.DOUBLE
		self._armed = (x, y, modifiers, button, when)
		return mouse.PRESS
