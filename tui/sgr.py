# SGR state: what a colour string leaves active on the terminal
"""
			SGR STATE
			=========
The emitters' state machine, split out of `tui.canvas` so the canvas keeps its
line budget and this one rule has a leaf home. `_sgr_state()` parses a colour
prefix into the `(fg, bg, attrs)` triple the terminal really holds;
`_emit_sgr()` appends a run's codes and inserts a reset only when the run would
otherwise inherit a sticky attribute (reverse/bold/dim/bg) or a colour slot it
does not set - never before every run, so pure-fg runs stay byte-identical.

No `tui` imports: this is a leaf. `tui.canvas` re-exports everything here, so
`canvas._sgr_state`, `canvas._emit_sgr` and `canvas.SGR_RESET` keep resolving.
"""

SGR_RESET = "\033[0m"

# No cell colour ever equals this: the first changed cell always emits.
_SGR_UNKNOWN = object()


def _sgr_state(color):
	"""(fg, bg, attrs) the SGR state `color` leaves active on the terminal."""
	fg = bg = None
	attrs = set()
	for chunk in str(color or "").split("\033[")[1:]:
		params = chunk.split("m")[0].split(";")
		code = int(params[0] or 0)
		if code in (38, 48):
			fg, bg = ((";".join(params), bg) if code == 38
					  else (fg, ";".join(params)))
		elif 30 <= code <= 37 or 90 <= code <= 97:
			fg = code
		elif 40 <= code <= 47 or 100 <= code <= 107:
			bg = code
		else:
			attrs.add(code)
	return fg, bg, frozenset(attrs)


def _emit_sgr(out, active, color):
	"""Append `color`'s codes; reset first when a run would inherit state."""
	state = _sgr_state(color)
	if state != active:
		if active is not _SGR_UNKNOWN and color and not (
				active[2] <= state[2]
				and (state[0] is not None or active[0] is None)
				and (state[1] is not None or active[1] is None)):
			out.append(SGR_RESET)
		out.append(color if color else SGR_RESET)
	return state
