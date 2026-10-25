# Input prompts shared by the interactive scripts
"""
			INPUT PROMPTS
			==============
The three input loops the scripts used to duplicate. Callers keep their own
prompt strings; these helpers only own validation, cancellation and the styled
prompt label. Every helper returns the cancelled value instead of raising when
stdin closes (EOF), and none of them touch terminal modes.
"""

from . import caps, chrome, palette


def _label(text):
	"""Accent pointer plus a `header`-on-`surface` label, resolved once."""
	cap = caps.detect()
	return "{} {}".format(
		palette.style(">", fg="accent", cap=cap),
		palette.style(text, fg="header", bg="surface", bold=True, cap=cap))


_EOF = object()  # sentinel: a caller wants EOF told apart from a blank answer


def _read(prompt, default="", eof=None):
	"""One stripped line; closed/aborted stdin yields `eof` or `default`."""
	try:
		value = input(_label(prompt)).strip()
	except (EOFError, KeyboardInterrupt):
		return default if eof is None else eof
	return value or default


def ask_text(prompt, default="", eof=None):
	"""Free text; empty input yields `default`, EOF yields `default` (or `eof`)."""
	return _read(prompt, default, eof)


def ask_int(prompt, minimum, maximum, default=None):
	"""Integer within [minimum, maximum]; blank yields `default`, EOF cancels.

	EOF has to cancel rather than re-prompt: `ask_text` cannot tell a closed
	stdin from an empty line, so the blank branch below used to `continue`
	straight into another `input()` that raised `EOFError` again - a prompt
	loop that never ended (and swallowed Ctrl-C with it).
	"""
	while True:
		raw = ask_text("{} [{}]: ".format(prompt, default if default is not None else "q to cancel"),
					   eof=_EOF)
		if raw is _EOF:
			return None
		if raw.lower() in ("q", "quit", "exit"):
			return None
		if not str(raw).strip():
			if default is not None:
				return int(default)
			continue
		try:
			value = int(str(raw).strip())
		except (TypeError, ValueError):
			continue
		if minimum <= value <= maximum:
			return value


def ask_choice(prompt, options):
	"""Numbered choice; returns the 0-based index, or None on cancel/EOF."""
	options = list(options)
	if not options:
		return None
	cap = caps.detect()
	print(chrome.menu(options, selected=None, cap=cap))
	raw = ask_text("{} [1-{}, q to cancel]: ".format(prompt, len(options)))
	if raw.lower() in ("q", "quit", "exit"):
		return None
	try:
		value = int(str(raw).strip())
	except (TypeError, ValueError):
		return None
	return value - 1 if 1 <= value <= len(options) else None
