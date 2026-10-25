# Terminal capability detection
"""
			TERMINAL CAPABILITIES
			======================
One frozen `Capabilities` record per run, resolved by a fixed precedence so every
script agrees on colour level, Unicode safety and pipe mode.

Precedence for `level` (first match wins):
	NO_COLOR > FORCE_COLOR/CLICOLOR_FORCE > CATRO_COLOR > config.ini colour.level
	> autodetect (TERM, legacy Windows console, COLORTERM, SSH, tty).

`plain` is the machine-readable mode, and it means one thing only: stdout is not
a tty. A non-tty gets no ANSI, no box glyphs and no padding from the helpers. A
tty stays a tty even when colour is off - level "none" removes the escape codes
but the table keeps its borders, alignment and truncation.

Test seams: pass `stream`/`environ` explicitly, and patch the module-level
`_IS_WINDOWS` flag to simulate a legacy Windows console on any host. Nothing
here touches a terminal at import time, and platform work happens inside
`init_ansi()` only.
"""

import io
import locale
import os
import sys
from dataclasses import dataclass

from . import config

LEVELS = ("none", "16", "256", "true")

# True on a real Windows host; tests patch it to exercise the console rules.
_IS_WINDOWS = os.name == "nt"

_LEGACY_CONSOLE_MARKERS = ("WT_SESSION", "ANSICON", "ConEmuANSI", "TERM", "TERM_PROGRAM")


@dataclass(frozen=True)
class Capabilities:
	level: str
	unicode: bool
	width: "int | None"
	isatty: bool
	plain: bool
	reason: str


def detect(stream=None, environ=None):
	"""Capabilities for `stream` (default stdout) under `environ` (default os)."""
	stream = sys.stdout if stream is None else stream
	env = os.environ if environ is None else environ
	isatty = _isatty(stream)
	level, reason = _forced(env)
	if level is None:
		level, reason = _autodetect(env, isatty)
	return Capabilities(
		level=level,
		unicode=_supports_unicode(env, stream),
		width=_width(stream),
		isatty=isatty,
		plain=not isatty,
		reason=reason,
	)


def init_ansi():
	"""Enable ANSI escape handling on Windows consoles; no-op elsewhere."""
	if _IS_WINDOWS:
		os.system('')


def require_tty(name):
	"""Refuse to run without a terminal: one stderr line, then exit 2."""
	if _isatty(sys.stdin) and _isatty(sys.stdout):
		return
	sys.stderr.write("[Error] {} needs an interactive terminal "
					 "(stdin/stdout is not a tty).\n".format(name))
	raise SystemExit(2)


def _forced(env):
	"""Explicit overrides and config; (None, "") when autodetect should decide."""
	# no-color.org: NO_COLOR disables colour when present and non-empty,
	# whatever its value - "0" and "false" included.
	if str(env.get("NO_COLOR", "")) != "":
		return "none", "NO_COLOR"
	forced = env.get("FORCE_COLOR") if _truthy(env.get("FORCE_COLOR")) else None
	if forced is None and _truthy(env.get("CLICOLOR_FORCE")):
		forced = env.get("CLICOLOR_FORCE")
	if forced is not None:
		return {"2": "256", "3": "true"}.get(str(forced).strip(), "16"), "FORCE_COLOR"
	requested = str(env.get("CATRO_COLOR", "")).strip().lower()
	if requested in LEVELS:
		return requested, "CATRO_COLOR"
	configured = str(config.get("color", "level", "auto")).strip().lower()
	if configured in LEVELS:
		return configured, "config.ini"
	return None, ""


def _autodetect(env, isatty):
	"""Environment-derived level, most specific rule first.

	A pipe is never a terminal: it short-circuits to "none" unless a colour was
	forced explicitly (which `_forced` handles before this point), so piped output
	can never carry ANSI escapes.
	"""
	term = str(env.get("TERM", "")).lower()
	if term == "dumb":
		return "none", "TERM=dumb"
	if not isatty:
		return "none", "pipe"
	if _IS_WINDOWS and not _modern_console(env):
		return "16", "windows-legacy-console"
	if str(env.get("COLORTERM", "")).lower() in ("truecolor", "24bit"):
		return "true", "COLORTERM"
	if "direct" in term or "truecolor" in term:
		return "true", "TERM"
	if "256color" in term:
		return "256", "TERM"
	if env.get("SSH_TTY") or env.get("SSH_CLIENT"):
		# Colour depth is capped remotely unless COLORTERM/TERM already said more.
		return "256", "ssh"
	return "16", "tty"


def _modern_console(env):
	"""True when the Windows console is known to understand ANSI escapes."""
	return any(str(env.get(marker, "")).strip() for marker in _LEGACY_CONSOLE_MARKERS)


def _supports_unicode(env, stream):
	"""False when box-drawing glyphs would raise or look like mojibake."""
	if _truthy(env.get("CATRO_ASCII")):
		return False
	if str(env.get("TERM", "")).lower() == "dumb":
		return False
	encoding = getattr(stream, "encoding", None) or locale.getpreferredencoding(False)
	try:
		"\u2500\u2502".encode(encoding)
	except (UnicodeEncodeError, LookupError):
		return False
	for name in ("LANG", "LC_ALL"):
		value = str(env.get(name, "")).strip().upper()
		if value in ("C", "POSIX") and not _utf8_hint(env, encoding):
			return False
	return True


def _utf8_hint(env, encoding):
	if _truthy(env.get("PYTHONUTF8")):
		return True
	return "utf" in str(encoding or "").lower()


def _width(stream):
	"""Terminal columns, or None when the stream has no size (pipes, fakes)."""
	try:
		return os.get_terminal_size(stream.fileno()).columns
	except (OSError, ValueError, AttributeError, io.UnsupportedOperation):
		return None


def _isatty(stream):
	try:
		return bool(stream.isatty())
	except (AttributeError, ValueError, OSError):
		return False


def _truthy(value):
	"""Non-empty and not an explicit off switch."""
	if value is None:
		return False
	text = str(value).strip().lower()
	return bool(text) and text not in ("0", "false", "no", "off")
