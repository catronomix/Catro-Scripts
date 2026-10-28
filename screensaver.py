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
import importlib.util
import importlib.machinery
import threading

import tui


def get_screensavers():
	"""Scans the program directory for .screensaver files."""
	program_dir = os.path.dirname(os.path.abspath(__file__))
	files = [os.path.join(program_dir, f) for f in os.listdir(program_dir) if f.endswith('.screensaver')]
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

def menu_step(count, index, key):
	"""Apply one key token to the menu; returns (action, index).

	Actions: "move" (redraw at the returned index), "select" (take the index)
	or "exit" (leave with status 0). Unknown keys redraw in place, so every
	press gives feedback.
	"""
	if key == "up":
		return "move", (index - 1) % count
	if key == "down":
		return "move", (index + 1) % count
	if key == "enter":
		return "select", index
	if key in ("esc", "ctrl-c"):
		return "exit", index
	return "move", index


def draw_menu(stream, names, selected_idx, cap):
	"""Paint one menu frame; every write goes to `stream` (test seam).

	The picker is the shared `tui.menu` inside a `tui.panel`, so its frame,
	selection bar and glyph fallback are the same ones every other page uses.
	The plugin API is untouched: only this host-side frame changed.
	"""
	stream.write(tui.screen.CLEAR_HOME)

	# The menu rows carry their own styling and close with a reset; re-open the
	# panel's interior ground so its right gutter is not left unpainted.
	ground = tui.prefix(fg="fg", bg="bg-inside", cap=cap)
	body = [line + ground
			for line in tui.menu(names, selected_idx, cap=cap).splitlines()]
	stream.write(tui.panel("SCREENSAVERS", body, cap=cap) + "\n")
	stream.write("Use UP/DOWN arrows to select, ENTER to run.\n")
	stream.flush()


def get_menu_selection(screensavers):
	"""Displays an interactive styled menu to select a screensaver.

	Key input goes through `tui.keys.read_key` and the screen lifecycle through
	`tui.Screen`, so both platforms share the decoder that Phase A extracted
	instead of a private msvcrt/termios loop. A real POSIX terminal smoke test
	is still owed; the unit tests drive the decode path with fakes.
	"""
	names = [os.path.splitext(os.path.basename(f))[0] for f in screensavers]
	selected_idx = 0
	cap = tui.detect()

	# Screen owns the alternate screen, cursor hide/show and the reset on the
	# way out; raw_mode owns cbreak and its restore. sys.exit(0) inside the
	# blocks still unwinds both context managers, so the cursor comes back.
	with tui.Screen() as screen, tui.keys.raw_mode():
		while True:
			draw_menu(screen, names, selected_idx, cap)
			action, selected_idx = menu_step(len(names), selected_idx,
											 tui.keys.read_key())
			if action == "select":
				return screensavers[selected_idx]
			if action == "exit":
				sys.exit(0)

def main():
	tui.init_ansi()

	# No tty (piped stdin, cron, IDE output pane): the menu cannot work.
	tui.require_tty("screensaver")

	# Clear screen initially
	sys.stdout.write(tui.screen.CLEAR_HOME)
	sys.stdout.flush()

	screensavers = get_screensavers()

	if not screensavers:
		print("No .screensaver files found in the current directory.")
		sys.exit(1)

	try:
		chosen_file = get_menu_selection(screensavers)
	except KeyboardInterrupt:
		sys.stdout.write(tui.screen.CURSOR_SHOW + tui.screen.SGR_RESET
						 + tui.screen.CLEAR_HOME)
		sys.exit(0)

	plugin = load_screensaver(chosen_file)
	renderer = tui.TerminalRenderer()

	# Hide cursor, clear screen for screensaver
	sys.stdout.write(tui.screen.CURSOR_HIDE + tui.screen.CLEAR_HOME)
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
		sys.stdout.write(tui.screen.CURSOR_SHOW + tui.screen.SGR_RESET
						 + tui.screen.CLEAR_HOME)
		sys.stdout.flush()

if __name__ == "__main__":
	main()