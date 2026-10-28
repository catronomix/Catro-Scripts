# Virtual-terminal capability probe for Windows consoles
"""
			CONSOLE VT PROBE
			================
Windows consoles do not advertise colour support: conhost exports no marker
variable, yet modern builds accept ANSI escapes once
`ENABLE_VIRTUAL_TERMINAL_PROCESSING` is set. `can_vt()` asks the console itself
by toggling that flag on the output handle and restoring the previous mode
immediately, so the probe leaves no trace behind.

Stdlib only, and `ctypes`/`msvcrt` stay inside the call so `import tui` never
touches a terminal. Every failure (no console, redirected handle, odd host)
degrades to False, leaving the caller its conservative 16-colour answer.
"""

import os

# True on a real Windows host; tests patch it to exercise the probe branch.
_IS_WINDOWS = os.name == "nt"

_STD_OUTPUT_HANDLE = -11
_ENABLE_VT = 0x0004


def can_vt(stream=None):
	"""True when `stream`'s console accepts ANSI escapes; never raises."""
	if not _IS_WINDOWS:
		return False
	try:
		import ctypes
		kernel32 = ctypes.windll.kernel32
		handle = _handle(stream)
		mode = ctypes.c_uint32()
		if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
			return False
		if not kernel32.SetConsoleMode(handle, mode.value | _ENABLE_VT):
			return False
		kernel32.SetConsoleMode(handle, mode.value)  # restore, no side effect
		return True
	except Exception:
		return False


def _handle(stream=None):
	"""The console handle behind `stream`, else the process stdout handle."""
	try:
		import msvcrt
		return msvcrt.get_osfhandle(stream.fileno())
	except Exception:
		pass
	import ctypes
	return ctypes.windll.kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
