# SGR mouse reporting: enable, decode, restore
"""
			MOUSE INPUT
			============
SGR mouse reporting (`\\x1b[?1006h`) plus its decoder. `enable()` writes the mode
sequences only to an injected stream and only when that stream is a tty; a write
that fails returns False and leaves reporting disarmed, so `disable()` cannot
claim to have restored a mode that never went on. `disable()` undoes them, is
safe twice and never raises. Import is inert.

`decode()` is pure and total: one SGR sequence in, one
`(kind, x, y, modifiers)` out, or `None` for anything else. Kinds are `press`,
`release`, `drag`, `move` and the four `wheel-*` names; `x`/`y` are 0-based
cells and `modifiers` names the held `shift`/`alt`/`ctrl`. `token()` /
`parse_token()` carry that event in the `mouse:...` form `tui.keys` emits, and
both are total: a malformed value yields the empty string / `None`, never an
exception.

Windows: `enable()` tries to turn on VT input through `ctypes` (imported inside
the function, so no platform module at import time); a console that refuses it
stays keyboard-only instead of failing.
"""

import os
import sys
from contextlib import contextmanager

DISABLE = "\033[?1006l\033[?1002l\033[?1000l"

PRESS = "press"
RELEASE = "release"
DRAG = "drag"
MOVE = "move"

# SGR button code bits: motion (32), wheel (64), and the modifier bits.
_MOTION = 32
_WHEEL = 64
_MODIFIERS = ((4, "shift"), (8, "alt"), (16, "ctrl"))
_WHEELS = ("wheel-up", "wheel-down", "wheel-left", "wheel-right")

# The stream currently holding the mouse modes; `disable()` only talks about it.
_active = None

def enable(stream=None, *, drag=True):
	"""Turn on button, wheel and (optionally) drag reporting; True when written."""
	global _active
	stream = sys.stdout if stream is None else stream
	if not _isatty(stream):
		return False
	_enable_windows_vt()
	if _active is stream:
		return True
	codes = "\033[?1000h" + ("\033[?1002h" if drag else "") + "\033[?1006h"
	if not _write(stream, codes):
		return False
	_active = stream
	return True

def disable(stream=None):
	"""Undo `enable()`; writes once and never raises when it was never on."""
	global _active
	stream = sys.stdout if stream is None else stream
	if _active is not stream:
		return False
	_write(stream, DISABLE)
	_active = None
	return True

@contextmanager
def reporting(stream=None, *, drag=True):
	"""`enable()` for the block, with `disable()` guaranteed on the way out."""
	enable(stream, drag=drag)
	try:
		yield stream
	finally:
		disable(stream)

def decode(sequence):
	"""`(kind, x, y, modifiers)` for one SGR mouse sequence, else `None`."""
	text = str(sequence or "")
	if not text.startswith("\x1b[<") or text[-1:] not in ("M", "m"):
		return None
	fields = text[3:-1].split(";")
	if len(fields) != 3:
		return None
	try:
		code, x, y = (int(field) for field in fields)
	except ValueError:
		return None
	return (kind(code, text[-1]), max(0, x - 1), max(0, y - 1),
			tuple(name for bit, name in _MODIFIERS if code & bit))

def kind(code, final="M"):
	"""Event name for an SGR button code and final byte."""
	if code & _WHEEL:
		return _WHEELS[code & 3]
	if code & _MOTION:
		return MOVE if code & 3 == 3 else DRAG
	return PRESS if final == "M" else RELEASE

def token(event):
	"""`mouse:<kind>:<x>:<y>[:<mod>,...]` for a decoded event, else `""`.

	Total by design: a malformed shape is not an error, it is just not a mouse
	event, so the key stream can pass anything through without a traceback.
	"""
	if not event:
		return ""
	try:
		name, x, y, modifiers = event
		suffix = (":" + ",".join(str(mod) for mod in modifiers)
				  if modifiers else "")
		return "mouse:{}:{}:{}{}".format(name, int(x), int(y), suffix)
	except (TypeError, ValueError):
		return ""

def parse_token(value):
	"""The event `token()` produced, or `None` for any other key token."""
	text = str(value or "")
	if not text.startswith("mouse:"):
		return None
	parts = text[6:].split(":")
	if len(parts) not in (3, 4):
		return None
	try:
		x, y = int(parts[1]), int(parts[2])
	except ValueError:
		return None
	modifiers = tuple(filter(None, parts[3].split(","))) if len(parts) == 4 else ()
	if (parts[0] not in (PRESS, RELEASE, DRAG, MOVE) + _WHEELS
			or not set(modifiers) <= {"shift", "alt", "ctrl"}):
		return None
	return (parts[0], x, y, modifiers)

def _enable_windows_vt():
	"""Best-effort VT input on a Windows console; silent when unavailable."""
	if os.name != "nt":
		return False
	try:
		import ctypes

		kernel32 = ctypes.windll.kernel32
		handle = kernel32.GetStdHandle(-10)
		mode = ctypes.c_uint()
		if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
			return False
		return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0200))
	except Exception:
		return False

def _write(stream, text):
	try:
		stream.write(text)
		stream.flush()
	except (AttributeError, OSError, ValueError):
		return False
	return True

def _isatty(stream):
	try:
		return bool(stream.isatty())
	except (AttributeError, OSError, ValueError):
		return False
