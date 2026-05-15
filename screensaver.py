#terminal screensaver system
"""
			TERMINAL SCREENSAVER SYSTEM
			===========================
A general terminal renderer and screensaver host.
It loads external screensaver modules (.screensaver files)
and provides them with a high-performance double-buffered
terminal drawing API.

Usage:
	python screensaver.py
"""

import os
import sys
import time
import shutil
import importlib.util
import importlib.machinery
import platform
import threading

# Enable ANSI escape sequences on Windows
if platform.system().lower() == "windows":
	os.system('color')

class TerminalRenderer:
	"""A double-buffered terminal renderer using character grids."""
	def __init__(self):
		self.width, self.height = shutil.get_terminal_size()
		self.buffer = []
		self.colors = []
		self._init_buffers()

	def _init_buffers(self):
		self.buffer = [[' ' for _ in range(self.width)] for _ in range(self.height)]
		self.colors = [[None for _ in range(self.width)] for _ in range(self.height)]

	def clear(self):
		"""Clears the buffer and updates dimensions if the terminal resized."""
		new_w, new_h = shutil.get_terminal_size()
		if new_w != self.width or new_h != self.height:
			self.width, self.height = new_w, new_h
		self._init_buffers()

	def draw_char(self, x, y, char, color=None):
		"""Draws a single character to the buffer at (x,y) with optional ANSI color."""
		x, y = int(x), int(y)
		if 0 <= x < self.width and 0 <= y < self.height:
			self.buffer[y][x] = str(char)[0]
			self.colors[y][x] = color

	def draw_text(self, x, y, text, color=None):
		"""Draws a string of text starting at (x,y)."""
		for i, char in enumerate(text):
			self.draw_char(x + i, y, char, color)

	def render(self):
		"""Flushes the buffer to the terminal using a single print to prevent flicker."""
		# \033[H moves cursor to top-left (home)
		out = ["\033[H"]
		current_color = None

		for y in range(self.height):
			for x in range(self.width):
				color = self.colors[y][x]
				if color != current_color:
					out.append(color if color else "\033[0m")
					current_color = color
				out.append(self.buffer[y][x])
			
			if y < self.height - 1:
				out.append("\n")

		if current_color is not None:
			out.append("\033[0m")

		sys.stdout.write("".join(out))
		sys.stdout.flush()

def get_screensavers():
	"""Scans the directory for .screensaver files."""
	files = [f for f in os.listdir('.') if f.endswith('.screensaver')]
	return sorted(files)

def load_screensaver(filepath):
	"""Dynamically loads a .screensaver file as a Python module."""
	module_name = os.path.splitext(os.path.basename(filepath))[0]
	loader = importlib.machinery.SourceFileLoader(module_name, filepath)
	spec = importlib.util.spec_from_loader(loader.name, loader)
	module = importlib.util.module_from_spec(spec)
	loader.exec_module(module)
	return module.ScreensaverPlugin()

def listen_for_any_key(stop_event):
	"""Background thread to listen for any key press cross-platform."""
	if os.name == 'nt':
		import msvcrt
		while not stop_event.is_set():
			if msvcrt.kbhit():
				msvcrt.getch()
				stop_event.set()
				break
			stop_event.wait(0.1)
	else:
		try:
			import tty
			import termios
			import select
			fd = sys.stdin.fileno()
			old_settings = termios.tcgetattr(fd)
			try:
				tty.setcbreak(fd)
				while not stop_event.is_set():
					dr, dw, de = select.select([sys.stdin], [], [], 0.1)
					if dr:
						sys.stdin.read(1)
						stop_event.set()
						break
			finally:
				termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
		except Exception:
			# Failsafe if not running in a standard TTY
			pass

def get_menu_selection(screensavers):
	"""Displays an interactive styled menu to select a screensaver."""
	names = [os.path.splitext(f)[0] for f in screensavers]
	selected_idx = 0
	
	sys.stdout.write("\033[?25l") # Hide cursor
	sys.stdout.flush()

	def draw_menu():
		sys.stdout.write("\033[2J\033[H")
		purple = "\033[35m"
		reset = "\033[0m"
		highlight = "\033[7m"
		
		title = " SCREENSAVERS "
		width = max(len(title), max(len(n) for n in names) + 8)
		
		# Draw Top Border
		sys.stdout.write(f"{purple}┌{'─' * width}┐{reset}\n")
		
		# Draw Title
		pad_left = (width - len(title)) // 2
		pad_right = width - len(title) - pad_left
		sys.stdout.write(f"{purple}│{reset}{' ' * pad_left}{title}{' ' * pad_right}{purple}│{reset}\n")
		
		# Draw Divider
		sys.stdout.write(f"{purple}├{'─' * width}┤{reset}\n")
		
		# Draw Rows
		for i, name in enumerate(names):
			prefix = "  > " if i == selected_idx else "    "
			text = f"{prefix}{name}"
			pad = width - len(text)
			
			if i == selected_idx:
				sys.stdout.write(f"{purple}│{reset}{highlight}{text}{' ' * pad}{reset}{purple}│{reset}\n")
			else:
				sys.stdout.write(f"{purple}│{reset}{text}{' ' * pad}{purple}│{reset}\n")
				
		# Draw Bottom Border
		sys.stdout.write(f"{purple}└{'─' * width}┘{reset}\n")
		sys.stdout.write("Use UP/DOWN arrows to select, ENTER to run.\n")
		sys.stdout.flush()

	def exit_menu():
		sys.stdout.write("\033[?25h\033[0m") # Show cursor, reset colors
		sys.stdout.flush()
		sys.exit(0)

	if os.name == 'nt':
		import msvcrt
		while True:
			draw_menu()
			key = msvcrt.getch()
			if key in (b'\x00', b'\xe0'):
				arrow = msvcrt.getch()
				if arrow == b'H': # Up
					selected_idx = (selected_idx - 1) % len(names)
				elif arrow == b'P': # Down
					selected_idx = (selected_idx + 1) % len(names)
			elif key == b'\r':
				return screensavers[selected_idx]
			elif key in (b'\x03', b'\x1b'): # Ctrl+C or ESC
				exit_menu()
	else:
		import tty
		import termios
		import select
		fd = sys.stdin.fileno()
		old_settings = termios.tcgetattr(fd)
		try:
			tty.setcbreak(fd)
			while True:
				draw_menu()
				key = sys.stdin.read(1)
				if key == '\x1b': # Escape seq start
					dr, _, _ = select.select([sys.stdin], [], [], 0.1)
					if dr:
						seq = sys.stdin.read(2)
						if seq == '[A': # Up
							selected_idx = (selected_idx - 1) % len(names)
						elif seq == '[B': # Down
							selected_idx = (selected_idx + 1) % len(names)
					else:
						exit_menu()
				elif key in ('\n', '\r'):
					return screensavers[selected_idx]
				elif key == '\x03': # Ctrl+C
					exit_menu()
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def main():
	# Clear screen initially
	sys.stdout.write("\033[2J\033[H")
	sys.stdout.flush()

	screensavers = get_screensavers()

	if not screensavers:
		print("No .screensaver files found in the current directory.")
		sys.exit(1)

	try:
		chosen_file = get_menu_selection(screensavers)
	except KeyboardInterrupt:
		sys.stdout.write("\033[?25h\033[0m\033[2J\033[H")
		sys.exit(0)

	plugin = load_screensaver(chosen_file)
	renderer = TerminalRenderer()

	# Hide cursor, clear screen for screensaver
	sys.stdout.write("\033[?25l\033[2J")
	sys.stdout.flush()

	plugin.init(renderer)

	stop_event = threading.Event()
	listener = threading.Thread(target=listen_for_any_key, args=(stop_event,), daemon=True)
	listener.start()

	last_time = time.time()
	try:
		while not stop_event.is_set():
			current_time = time.time()
			dt = current_time - last_time
			last_time = current_time

			renderer.clear()
			plugin.update(dt, renderer)
			plugin.draw(renderer)
			renderer.render()

			# Cap framerate to ~60 FPS
			elapsed = time.time() - current_time
			sleep_time = max(0.016 - elapsed, 0)
			stop_event.wait(sleep_time)

	except KeyboardInterrupt:
		pass
	finally:
		# Show cursor, reset colors, clear screen
		sys.stdout.write("\033[?25h\033[0m\033[2J\033[H")
		sys.stdout.flush()

if __name__ == "__main__":
	main()