# Generate random cryptographic keys interactively
"""
			CATRO-SCRIPTS KEY GENERATOR
			===========================
Interactive random-key generator. It opens straight onto a freshly generated
ALPHANUMERIC key (32 chars); the hotkeys below then let you change the
algorithm or the key length and roll new keys as often as you like.

Rendering and input come from the shared `tui` library: the palette decides the
colours for the active theme and colour level, `tui.keys` decodes the
keystrokes (EOF reads as cancel), and `tui.Screen` owns the alternate screen
and the cursor. No escape sequence is hardcoded here.

Features:
	- Starts immediately with a default ALPHANUMERIC 32-character key.
	- Multiple-choice algorithm picker (arrow keys + ENTER).
	- Configurable key length (digits + BACKSPACE, ENTER to confirm).
	- Cryptographically secure randomness via the `secrets` module.
	- [ENTER] generates a new key, [ESC] or [Q] exits.
	- [A] returns to the algorithm picker, [L] re-prompts for the length.
	- Live entropy readout (bits) for the generated key.

Usage:
	catro-scripts keygen
"""

import argparse
import math
import uuid
import string
import secrets

import tui

# Algorithm catalogue: (name, human description, character alphabet)
# A None alphabet means the algorithm builds its own output (e.g. UUID).
ALGORITHMS = [
	("ALPHANUMERIC", "A-Z a-z 0-9", string.ascii_letters + string.digits),
	("UPPERCASE", "A-Z 0-9", string.ascii_uppercase + string.digits),
	("LOWERCASE", "a-z 0-9", string.ascii_lowercase + string.digits),
	("HEX", "0-9 a-f", "0123456789abcdef"),
	("BASE64", "A-Z a-z 0-9 + /", string.ascii_letters + string.digits + "+/"),
	("PRINTABLE", "all printable ASCII", "".join(chr(c) for c in range(33, 127))),
	("UUID", "RFC 4122 v4 (fixed 36)", None),
]

DEFAULT_LENGTH = 32
MAX_LENGTH = 4096

CANCEL_KEYS = ("esc", "q", "ctrl-c", None)


# ---------------------------------------------------------------------------
# Input and rendering helpers (all through tui)
# ---------------------------------------------------------------------------
def read_key():
	"""One normalized key token, lowercased for letters.

	`tui.keys.read_key` reports the character as typed and `None` when stdin
	closes; every hotkey in this UI is case-insensitive, and EOF is treated as
	cancel by the callers.
	"""
	key = tui.keys.read_key()
	if key and len(key) == 1 and key.isalpha():
		return key.lower()
	return key


def glyphs(cap):
	"""Box glyphs this stream can encode (ASCII fallback included)."""
	return tui.table.glyphs_for(cap)


def marker_for(stream, cap):
	"""Picker pointer, but only when the target stream can encode it.

	`cap.unicode` only proves the *box* glyphs encode; a legacy codepage
	(cp437, cp850) draws boxes and still cannot take U+25B6, so writing it
	unconditionally would raise `UnicodeEncodeError` mid-picker.
	"""
	if not cap.unicode:
		return ">"
	encoding = getattr(stream, "encoding", None) or "ascii"
	try:
		"\u25b6".encode(encoding)
	except (LookupError, UnicodeEncodeError):
		return ">"
	return "\u25b6"


def border(text, cap):
	"""Border-coloured span; the palette owns the colour, not this module."""
	return tui.style(text, fg="border", cap=cap)


def draw_banner(stream, cap):
	"""House banner: tui owns the box, the glyphs and the title style."""
	stream.write(tui.banner("KEYGEN", width=60, cap=cap) + "\n")


def choose_algorithm(stream, cap, selected_idx):
	"""Render the algorithm picker and return the chosen index, or None if cancelled."""
	box = glyphs(cap)
	marker = marker_for(stream, cap)
	while True:
		stream.write(tui.screen.CLEAR_HOME)
		draw_banner(stream, cap)
		stream.write("\n{} {}\n\n".format(
			tui.style("Select an algorithm", fg="header", bold=True, cap=cap),
			tui.style("(UP/DOWN to move, ENTER to confirm, ESC/Q to quit)",
					  fg="muted", cap=cap)))

		width = 46
		stream.write(border(box["tl"] + box["h"] * width + box["tr"], cap) + "\n")
		for i, (name, desc, _) in enumerate(ALGORITHMS):
			text = " {} {:<16} {}".format(marker if i == selected_idx else " ",
										  name, desc)
			text += " " * (width - len(text))
			# The selected row is reversed rather than recoloured, so it stays
			# readable under every theme and colour level.
			row = tui.style(text, reverse=True, cap=cap) if i == selected_idx else text
			stream.write(border(box["v"], cap) + row + border(box["v"], cap) + "\n")
		stream.write(border(box["bl"] + box["h"] * width + box["br"], cap) + "\n")
		stream.flush()

		key = read_key()
		if key == "up":
			selected_idx = (selected_idx - 1) % len(ALGORITHMS)
		elif key == "down":
			selected_idx = (selected_idx + 1) % len(ALGORITHMS)
		elif key == "enter":
			return selected_idx
		elif key in CANCEL_KEYS:
			return None


def prompt_length(stream, cap, default=DEFAULT_LENGTH):
	"""Read a numeric key length. Returns an int, or None if cancelled.

	This is a single-keystroke editor (digits append, BACKSPACE deletes, no
	line buffering), so the frame is repainted through `tui.Screen` instead of
	using `tui.prompts`, whose helpers read a whole line in cooked mode.
	"""
	buffer = ""
	while True:
		stream.write(tui.screen.CLEAR_HOME)
		draw_banner(stream, cap)
		stream.write("\n{} {} [{}]: {}".format(
			tui.style("Key length", fg="header", bold=True, cap=cap),
			tui.style("(digits, ENTER to confirm, ESC/Q to cancel)",
					  fg="muted", cap=cap),
			default, buffer))
		stream.flush()

		key = read_key()
		if key == "enter":
			value = buffer or str(default)
			if value.isdigit() and 1 <= int(value) <= MAX_LENGTH:
				return int(value)
			buffer = ""  # Reject and start over
		elif key in CANCEL_KEYS:
			return None
		elif key == "backspace":
			buffer = buffer[:-1]
		elif key and key.isdigit() and len(buffer) < 4:
			buffer += key


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------
def generate_key(alphabet, length):
	"""Return a uniformly random string of exactly `length` chars."""
	return "".join(secrets.choice(alphabet) for _ in range(length))


def entropy_bits(alphabet_size, length):
	"""Approximate Shannon entropy of the generated key."""
	return length * math.log2(alphabet_size) if alphabet_size > 1 else 0.0


def show_key(stream, cap, algo_idx, length):
	"""Generate and display one key, then wait for the next action.

	Returns "regenerate", "algorithm", "length", or "quit".
	"""
	name, _, alphabet = ALGORITHMS[algo_idx]
	if alphabet is None:  # UUID ignores the requested length
		key = str(uuid.uuid4())
		bits = 122.0
		shown_len = len(key)
	else:
		key = generate_key(alphabet, length)
		bits = entropy_bits(len(alphabet), length)
		shown_len = length

	box = glyphs(cap)
	stream.write(tui.screen.CLEAR_HOME)
	draw_banner(stream, cap)
	stream.write("\n")
	length_text = "{} chars{}".format(shown_len,
									  " (fixed)" if alphabet is None else "")
	for label, value in (
			("Algorithm:", name),
			("Length:   ", length_text),
			("Entropy:  ", "~{} bits".format(int(round(bits))))):
		stream.write("  {} {}\n".format(
			tui.style(label, fg="muted", cap=cap),
			tui.style(value, fg="fg", bold=True, cap=cap)))
	stream.write("\n")

	# Wrap the key across a few lines so long keys stay readable
	wrap = 64
	lines = [key[i:i + wrap] for i in range(0, len(key), wrap)] or [""]
	inner = max(len(line) for line in lines) + 4
	stream.write(border(box["tl"] + box["h"] * inner + box["tr"], cap) + "\n")
	for line in lines:
		stream.write(border(box["v"], cap) + "  "
					 + tui.style("{:<{}}".format(line, inner - 4), fg="accent",
								 bold=True, cap=cap)
					 + "  " + border(box["v"], cap) + "\n")
	stream.write(border(box["bl"] + box["h"] * inner + box["br"], cap) + "\n")
	stream.write("\n")
	hint = (tui.style("[ENTER]", bold=True, cap=cap) + " new key   "
			+ tui.style("[A]", bold=True, cap=cap) + " algorithm   ")
	if alphabet is not None:
		hint += tui.style("[L]", bold=True, cap=cap) + " length   "
	hint += tui.style("[ESC/Q]", bold=True, cap=cap) + " quit"
	stream.write(hint + "\n")
	stream.flush()

	while True:
		key_press = read_key()
		if key_press == "enter":
			return "regenerate"
		if key_press == "a":
			return "algorithm"
		if key_press == "l":
			return "length"
		if key_press in CANCEL_KEYS:
			return "quit"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
def run_ui(stream, cap):
	"""Main loop: draw a key, then act on the next hotkey."""
	# Start immediately with a default key so there is no setup friction.
	algo_idx = 0          # ALPHANUMERIC
	length = DEFAULT_LENGTH

	while True:
		action = show_key(stream, cap, algo_idx, length)

		if action == "quit":
			return
		elif action == "algorithm":
			# Cancel from the picker keeps the current algorithm
			picked = choose_algorithm(stream, cap, algo_idx)
			if picked is not None:
				algo_idx = picked
		elif action == "length":
			chosen = prompt_length(stream, cap, length)
			if chosen is not None:
				length = chosen
		# "regenerate" simply loops and draws a fresh key


def main():
	# argparse first so `--help` answers with a usage line on any stream, then
	# the terminal preflight (contract: preflight after argparse).
	argparse.ArgumentParser(
		description="Interactive random-key generator: ENTER rolls a new key, "
					"A picks the algorithm, L sets the length, ESC/Q quits."
	).parse_args()
	tui.init_ansi()
	tui.require_tty("keygen")
	cap = tui.detect()

	# Screen owns the alternate screen, the hidden cursor and the restore on
	# the way out; raw_mode owns cbreak and its restore. Both unwind on an
	# exception or Ctrl+C, so there is no separate cleanup path.
	try:
		with tui.Screen() as screen, tui.keys.raw_mode():
			run_ui(screen, cap)
	except KeyboardInterrupt:
		pass


if __name__ == "__main__":
	main()
