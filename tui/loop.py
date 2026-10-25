# Frame loop and screensaver host
"""
			FRAME LOOP AND SCREENSAVER HOST
			================================
`FrameLoop` is the fixed-FPS loop with a guaranteed screen restore, used by the
screensaver and by any script that redraws a full screen.

`ScreensaverHost` keeps the pre-extraction plugin contract: a `.screensaver` file
is a module exposing `ScreensaverPlugin` with `init(renderer)`,
`update(dt, renderer)` and `draw(renderer)`. The loader semantics (module name
from the file stem, `SourceFileLoader`) and the any-key stop are unchanged.

`poll=` is the test seam: it returns a truthy value to stop, so the loop can be
driven without a keyboard or a terminal.
"""

import importlib.machinery
import importlib.util
import os
import sys
import time

from . import keys
from .screen import Screen, TerminalRenderer


class FrameLoop:
	"""Fixed-FPS redraw loop; KeyboardInterrupt and `stop()` both exit."""

	def __init__(self, fps=60, screen=None):
		self.fps = max(1, int(fps))
		self.screen = screen
		self.frames = 0
		self._stop = False

	def stop(self):
		self._stop = True

	def run(self, draw, poll=None):
		"""Call draw(self) each frame; poll(self) truthy stops the loop."""
		self._stop = False
		self.frames = 0
		interval = 1.0 / self.fps
		if self.screen is not None:
			self.screen.enter()
		next_frame = time.monotonic()
		try:
			while not self._stop:
				draw(self)
				self.frames += 1
				if poll is not None and poll(self):
					break
				next_frame += interval
				delay = next_frame - time.monotonic()
				if delay > 0:
					time.sleep(delay)
				else:
					next_frame = time.monotonic()
		except KeyboardInterrupt:
			self._stop = True
		finally:
			if self.screen is not None:
				self.screen.exit()


class ScreensaverHost:
	"""Loads a `.screensaver` plugin and hosts it in a FrameLoop."""

	def __init__(self, stream=None, fps=60, poll=None):
		self.stream = sys.stdout if stream is None else stream
		self.fps = fps
		self._poll = poll

	def load(self, path):
		"""Load `path` and return its ScreensaverPlugin instance."""
		module_name = os.path.splitext(os.path.basename(str(path)))[0]
		loader = importlib.machinery.SourceFileLoader(module_name, str(path))
		spec = importlib.util.spec_from_loader(loader.name, loader)
		module = importlib.util.module_from_spec(spec)
		loader.exec_module(module)
		return module.ScreensaverPlugin()

	def run(self, path):
		"""init(renderer), then update/draw/render each frame until a key."""
		plugin = self.load(path)
		screen = Screen(self.stream)
		renderer = TerminalRenderer(stream=self.stream)
		reader = keys.KeyReader() if self._poll is None else None
		last = time.monotonic()

		def draw(loop):
			nonlocal last
			now = time.monotonic()
			delta = now - last
			last = now
			renderer.clear()
			plugin.update(delta, renderer)
			plugin.draw(renderer)
			renderer.render()

		def poll(loop):
			if self._poll is not None:
				return bool(self._poll(loop))
			return reader.poll() is not None

		try:
			if reader is not None:
				reader.start()
			plugin.init(renderer)
			FrameLoop(fps=self.fps, screen=screen).run(draw, poll)
		finally:
			if reader is not None:
				reader.stop()
