# Input prompts shared by the interactive scripts
"""
			INPUT PROMPTS
			==============
The three input loops the scripts used to duplicate. Callers keep their own
prompt strings; these helpers only own validation, cancellation and the styled
prompt label. Every helper returns the cancelled value instead of raising when
stdin closes (EOF), and none of them touch terminal modes.
"""

from . import caps, palette


def _label(text):
	cap = caps.detect()
	return palette.style(text, fg="header", bold=True, cap=cap)


def ask_text(prompt, default=""):
	"""Free text; empty input yields `default`, EOF yields `default`."""
	try:
		value = input(_label(prompt)).strip()
	except (EOFError, KeyboardInterrupt):
		return default
	return value or default


def ask_int(prompt, minimum, maximum, default=None):
	"""Integer within [minimum, maximum]; blank yields `default`."""
	while True:
		raw = ask_text("{} [{}]: ".format(prompt, default if default is not None else "q to cancel"))
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
	for index, option in enumerate(options, 1):
		print("{} {}. {}".format(palette.style(">", fg="accent", cap=cap), index,
								 palette.style(str(option), fg="fg", cap=cap)))
	raw = ask_text("{} [1-{}, q to cancel]: ".format(prompt, len(options)))
	if raw.lower() in ("q", "quit", "exit"):
		return None
	try:
		value = int(str(raw).strip())
	except (TypeError, ValueError):
		return None
	return value - 1 if 1 <= value <= len(options) else None
