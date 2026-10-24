# Generate random cryptographic keys interactively
"""
			CATRO-SCRIPTS KEY GENERATOR
			===========================
Interactive random-key generator. It opens straight onto a freshly generated
ALPHANUMERIC key (32 chars); the hotkeys below then let you change the
algorithm or the key length and roll new keys as often as you like.

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

import os
import sys
import math
import uuid
import string
import secrets
import platform

IS_WINDOWS = platform.system().lower().startswith("win")

if IS_WINDOWS:
	import msvcrt
else:
	import tty
	import termios
	import select

# ANSI Color Codes (TrueColor support) - mirrors list.py visual identity
class Colors:
	PURPLE = '\033[38;2;170;0;255m'
	LIGHT_BLUE = '\033[38;2;173;216;230m'
	BG_BLACK = '\033[48;2;0;0;0m'
	BG_GREY = '\033[48;2;45;45;45m'
	BOLD = '\033[1m'
	END = '\033[0m'

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


# ---------------------------------------------------------------------------
# Raw terminal input (blocking, cross-platform)
# ---------------------------------------------------------------------------
INIT_SETTINGS = None


def init_terminal():
	"""Prepare the console for raw single-key input."""
	global INIT_SETTINGS
	# Ensure box-drawing glyphs survive consoles using a legacy codepage
	try:
		sys.stdout.reconfigure(encoding="utf-8")
	except Exception:
		pass
	if IS_WINDOWS:
		os.system('')  # Enable ANSI escape sequences on Windows
	else:
		fd = sys.stdin.fileno()
		INIT_SETTINGS = termios.tcgetattr(fd)  # Snapshot before cbreak
		tty.setcbreak(fd)
	# Switch to the alternate screen buffer so every redraw stays off the
	# scrollback: on exit the terminal snaps back to the previous prompt.
	sys.stdout.write("\033[?1049h\033[2J\033[H")
	# Hide the cursor while the UI redraws itself
	sys.stdout.write("\033[?25l")
	sys.stdout.flush()


def restore_terminal():
	"""Undo init_terminal() changes and make the cursor visible again."""
	if not IS_WINDOWS and INIT_SETTINGS is not None:
		try:
			termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, INIT_SETTINGS)
		except Exception:
			pass
	sys.stdout.write("\033[?25h\033[0m")  # Show cursor, reset colors
	sys.stdout.write("\033[?1049l")       # Leave the alternate screen buffer
	sys.stdout.flush()


def read_key():
	"""Block until a key is pressed, returning a normalized token string.

	Tokens: up, down, left, right, enter, esc, backspace, ctrl-c, or the
	lowercased pressed character.
	"""
	if IS_WINDOWS:
		c = msvcrt.getch()
		if c in (b'\x00', b'\xe0'):  # Extended key prefix (arrows etc.)
			c2 = msvcrt.getch()
			return {b'H': 'up', b'P': 'down', b'M': 'right', b'K': 'left'}.get(c2)
		if c == b'\x1b':
			return 'esc'
		if c in (b'\r', b'\n'):
			return 'enter'
		if c == b'\x08':
			return 'backspace'
		if c == b'\x03':
			return 'ctrl-c'
		return c.decode('utf-8', 'ignore').lower()
	else:
		ch = sys.stdin.read(1)
		if ch in ('\r', '\n'):
			return 'enter'
		if ch == '\x03':
			return 'ctrl-c'
		if ch in ('\x7f', '\x08'):
			return 'backspace'
		if ch == '\x1b':
			# A bare ESC arrives alone; an arrow key sends ESC [ A-D.
			if select.select([sys.stdin], [], [], 0.05)[0]:
				if sys.stdin.read(1) == '[':
					third = sys.stdin.read(1)
					return {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left'}.get(third)
				return None
			return 'esc'
		return ch.lower()


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
def clear_screen():
	sys.stdout.write("\033[2J\033[H")
	sys.stdout.flush()


def draw_banner():
	title = " KEYGEN "
	inner = 60
	top = f"{Colors.PURPLE}┌{'─' * inner}┐{Colors.END}"
	bottom = f"{Colors.PURPLE}└{'─' * inner}┘{Colors.END}"
	mid = f"{Colors.PURPLE}│{Colors.END}{Colors.LIGHT_BLUE}{title:^{inner}}{Colors.END}{Colors.PURPLE}│{Colors.END}"
	print(top)
	print(mid)
	print(bottom)


def choose_algorithm(selected_idx):
	"""Render the algorithm picker and return the chosen index, or None if cancelled."""
	while True:
		clear_screen()
		draw_banner()
		print(f"\n{Colors.PURPLE}{Colors.BOLD}Select an algorithm{Colors.END} "
			  f"{Colors.LIGHT_BLUE}(UP/DOWN to move, ENTER to confirm, ESC/Q to quit){Colors.END}\n")

		width = 46
		print(f"{Colors.PURPLE}┌{'─' * width}┐{Colors.END}")
		for i, (name, desc, _) in enumerate(ALGORITHMS):
			marker = "▶" if i == selected_idx else " "
			text = f" {marker} {name:<16} {desc}"
			pad = width - len(text)
			if i == selected_idx:
				print(f"{Colors.PURPLE}│{Colors.END}{Colors.LIGHT_BLUE}{Colors.BG_GREY}"
					  f"{text}{' ' * pad}{Colors.END}{Colors.PURPLE}│{Colors.END}")
			else:
				print(f"{Colors.PURPLE}│{Colors.END}{Colors.LIGHT_BLUE}{text}{' ' * pad}"
					  f"{Colors.END}{Colors.PURPLE}│{Colors.END}")
		print(f"{Colors.PURPLE}└{'─' * width}┘{Colors.END}")
		sys.stdout.flush()

		key = read_key()
		if key == 'up':
			selected_idx = (selected_idx - 1) % len(ALGORITHMS)
		elif key == 'down':
			selected_idx = (selected_idx + 1) % len(ALGORITHMS)
		elif key == 'enter':
			return selected_idx
		elif key in ('esc', 'q', 'ctrl-c'):
			return None


def prompt_length(default=DEFAULT_LENGTH):
	"""Read a numeric key length. Returns an int, or None if cancelled."""
	buffer = ""
	label = (f"{Colors.PURPLE}{Colors.BOLD}Key length{Colors.END} "
			 f"{Colors.LIGHT_BLUE}(digits, ENTER to confirm, ESC/Q to cancel)"
			 f"{Colors.END} [{default}]: ")
	sys.stdout.write("\n" + label)
	sys.stdout.flush()
	while True:
		key = read_key()
		if key == 'enter':
			value = buffer or str(default)
			if value.isdigit() and 1 <= int(value) <= MAX_LENGTH:
				sys.stdout.write("\n")
				sys.stdout.flush()
				return int(value)
			buffer = ""  # Reject and start over
		elif key in ('esc', 'q', 'ctrl-c'):
			sys.stdout.write("\n")
			sys.stdout.flush()
			return None
		elif key == 'backspace':
			buffer = buffer[:-1]
		elif key and key.isdigit() and len(buffer) < 4:
			buffer += key
		# Redraw just the typed portion of the line
		sys.stdout.write("\r" + label + buffer + "\033[K")
		sys.stdout.flush()


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------
def generate_key(alphabet, length):
	"""Return a uniformly random string of exactly `length` chars."""
	return "".join(secrets.choice(alphabet) for _ in range(length))


def entropy_bits(alphabet_size, length):
	"""Approximate Shannon entropy of the generated key."""
	return length * math.log2(alphabet_size) if alphabet_size > 1 else 0.0


def show_key(algo_idx, length):
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

	clear_screen()
	draw_banner()
	print()
	print(f"  {Colors.PURPLE}Algorithm:{Colors.END} {Colors.LIGHT_BLUE}{Colors.BOLD}{name}{Colors.END}")
	print(f"  {Colors.PURPLE}Length:   {Colors.END} {Colors.LIGHT_BLUE}{shown_len} chars"
		  f"{' (fixed)' if alphabet is None else ''}{Colors.END}")
	print(f"  {Colors.PURPLE}Entropy:  {Colors.END} {Colors.LIGHT_BLUE}~{bits:.0f} bits{Colors.END}")
	print()

	# Wrap the key across a few lines so long keys stay readable
	wrap = 64
	lines = [key[i:i + wrap] for i in range(0, len(key), wrap)] or [""]
	inner = max(len(line) for line in lines) + 4
	print(f"{Colors.PURPLE}┌{'─' * inner}┐{Colors.END}")
	for line in lines:
		print(f"{Colors.PURPLE}│{Colors.END}  {Colors.LIGHT_BLUE}{Colors.BOLD}{line:<{inner - 4}}"
			  f"{Colors.END}  {Colors.PURPLE}│{Colors.END}")
	print(f"{Colors.PURPLE}└{'─' * inner}┘{Colors.END}")
	print()
	hint = (f"{Colors.BOLD}[ENTER]{Colors.END} new key   "
			f"{Colors.BOLD}[A]{Colors.END} algorithm   ")
	if alphabet is not None:
		hint += f"{Colors.BOLD}[L]{Colors.END} length   "
	hint += f"{Colors.BOLD}[ESC/Q]{Colors.END} quit"
	print(hint)
	sys.stdout.flush()

	while True:
		key_press = read_key()
		if key_press == 'enter':
			return "regenerate"
		if key_press == 'a':
			return "algorithm"
		if key_press == 'l':
			return "length"
		if key_press in ('esc', 'q', 'ctrl-c'):
			return "quit"


def main():
	init_terminal()

	try:
		# Start immediately with a default key so there is no setup friction.
		algo_idx = 0          # ALPHANUMERIC
		length = DEFAULT_LENGTH

		while True:
			action = show_key(algo_idx, length)

			if action == "quit":
				return
			elif action == "algorithm":
				# Cancel from the picker keeps the current algorithm
				picked = choose_algorithm(algo_idx)
				if picked is not None:
					algo_idx = picked
			elif action == "length":
				clear_screen()
				draw_banner()
				chosen = prompt_length(length)
				if chosen is not None:
					length = chosen
			# "regenerate" simply loops and draws a fresh key
	finally:
		restore_terminal()


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		restore_terminal()
	except Exception:
		restore_terminal()
		raise
