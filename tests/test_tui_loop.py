# Frame loop and screensaver host tests
"""
		LOOP AND PLUGIN HOST
		=====================
The frame loop must stop on poll/KeyboardInterrupt/stop() and always restore the
screen. The screensaver host must keep the plugin order init -> update -> draw ->
render and the old loader semantics. A fake plugin writes its call order to a
temp file, so no real screensaver and no keyboard are involved.
"""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import canvas as canvas_module  # noqa: E402
from tui import screen as screen_module  # noqa: E402
from tui.loop import FrameLoop, ScreensaverHost  # noqa: E402

PLUGIN_SOURCE = '''
import os

def record(name):
	with open(os.environ["CATRO_FAKE_LOG"], "a", encoding="utf-8") as handle:
		handle.write(name + "\\n")

class ScreensaverPlugin:
	def init(self, renderer):
		record("init {}x{}".format(renderer.width, renderer.height))

	def update(self, dt, renderer):
		record("update")

	def draw(self, renderer):
		record("draw")
'''


class FakeStream:
	def __init__(self, tty=True):
		self._buffer = io.StringIO()
		self.encoding = "utf-8"
		self._tty = tty

	def write(self, text):
		return self._buffer.write(text)

	def getvalue(self):
		return self._buffer.getvalue()

	def flush(self):
		pass

	def isatty(self):
		return self._tty

	def fileno(self):
		raise io.UnsupportedOperation("fake stream has no file descriptor")


class FakeScreen:
	def __init__(self, stream=None):
		self.stream = stream
		self.entered = 0
		self.exited = 0
		self.entered_flag = False

	def enter(self):
		self.entered += 1
		self.entered_flag = True

	def exit(self):
		self.exited += 1
		self.entered_flag = False


class FrameLoopTests(unittest.TestCase):
	def test_poll_stops_the_loop_and_restores_the_screen(self):
		lifecycle = FakeScreen()
		frames = []
		calls = {"count": 0}

		def draw(loop):
			frames.append(loop.frames)

		def poll(loop):
			calls["count"] += 1
			return calls["count"] > 2

		FrameLoop(fps=240, screen=lifecycle).run(draw, poll)
		self.assertEqual(len(frames), 3)
		self.assertEqual((lifecycle.entered, lifecycle.exited), (1, 1))
		self.assertFalse(lifecycle.entered_flag)

	def test_stop_from_draw_ends_the_loop(self):
		lifecycle = FakeScreen()
		frames = []

		def draw(loop):
			frames.append(1)
			loop.stop()

		FrameLoop(fps=240, screen=lifecycle).run(draw)
		self.assertEqual(len(frames), 1)
		self.assertEqual(lifecycle.exited, 1)

	def test_keyboard_interrupt_still_restores_the_screen(self):
		lifecycle = FakeScreen()

		def draw(loop):
			raise KeyboardInterrupt()

		FrameLoop(fps=240, screen=lifecycle).run(draw)
		self.assertEqual(lifecycle.exited, 1)

	def test_loop_without_a_screen_just_runs(self):
		calls = []

		def draw(loop):
			calls.append(1)
			loop.stop()

		FrameLoop(fps=240).run(draw)
		self.assertEqual(len(calls), 1)


class ScreensaverHostTests(unittest.TestCase):
	def setUp(self):
		self._td = tempfile.TemporaryDirectory()
		self.dir = Path(self._td.name)
		self.log = self.dir / "calls.log"
		self.plugin = self.dir / "fake.screensaver"
		self.plugin.write_text(PLUGIN_SOURCE, encoding="utf-8")
		self.env = mock.patch.dict(os.environ, {"CATRO_FAKE_LOG": str(self.log)})
		self.env.start()
		self.size = mock.patch.object(screen_module, "terminal_size",
									  lambda stream=None: (8, 3))
		self.size.start()
		self.canvas_size = mock.patch.object(canvas_module, "terminal_size",
											 lambda stream=None: (8, 3))
		self.canvas_size.start()

	def tearDown(self):
		self.canvas_size.stop()
		self.size.stop()
		self.env.stop()
		self._td.cleanup()

	def calls(self):
		return self.log.read_text(encoding="utf-8").split()

	def test_load_returns_the_plugin_instance(self):
		host = ScreensaverHost(stream=FakeStream())
		plugin = host.load(self.plugin)
		self.assertEqual(type(plugin).__name__, "ScreensaverPlugin")

	def test_run_calls_init_update_draw_in_order(self):
		stream = FakeStream()
		polls = {"count": 0}

		def poll(loop):
			polls["count"] += 1
			return polls["count"] > 2

		host = ScreensaverHost(stream=stream, fps=240, poll=poll)
		host.run(self.plugin)
		calls = self.calls()
		self.assertEqual(calls[:3], ["init", "8x3", "update"])
		self.assertEqual(calls[3], "draw")
		self.assertEqual(calls.count("update"), calls.count("draw"))
		self.assertEqual(calls.count("update"), 3)
		# One home from Screen.enter() plus one per rendered frame.
		self.assertEqual(stream.getvalue().count("\033[H"), 4)
		self.assertIn(screen_module.ALT_SCREEN_ON, stream.getvalue())
		self.assertIn(screen_module.ALT_SCREEN_OFF, stream.getvalue())


if __name__ == "__main__":
	unittest.main()
