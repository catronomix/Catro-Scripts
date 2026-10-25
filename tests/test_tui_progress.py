# Progress indicator tests
"""
		SPINNER, BAR AND LIVE REGION
		=============================
Off a tty every indicator must degrade to one final line of plain text, with no
carriage return and no escape codes. On a tty the same objects animate in place.
Capabilities are injected so the assertions never depend on the real terminal.
"""

import io
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from tui import caps, progress, screen  # noqa: E402  (import after sys.path setup)


class FakeStream:
	def __init__(self, tty=True, encoding="utf-8"):
		self._buffer = io.StringIO()
		self.encoding = encoding
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


def cap(level="true", unicode=True, tty=True):
	return caps.Capabilities(
		level=level,
		unicode=unicode,
		width=80,
		isatty=tty,
		plain=not tty,
		reason="test",
	)


class ProgressBarTests(unittest.TestCase):
	def make(self, tty=True, total=50, value=0, **kwargs):
		stream = FakeStream(tty)
		cap_object = kwargs.pop("cap", None) or cap(tty=tty)
		bar = progress.ProgressBar(total, stream=stream, cap=cap_object, **kwargs)
		bar.update(value)
		return bar, stream

	def test_plain_updates_write_nothing(self):
		bar, stream = self.make(tty=False, value=10)
		bar.update(20)
		self.assertEqual(stream.getvalue(), "")

	def test_plain_finish_prints_one_summary_line(self):
		bar, stream = self.make(tty=False, total=50, label="downloading")
		bar.update(21)
		bar.finish()
		self.assertEqual(stream.getvalue(), "downloading 42% (21/50)\n")
		self.assertNotIn("\r", stream.getvalue())
		self.assertNotIn("\033", stream.getvalue())

	def test_plain_finish_after_several_updates_still_one_line(self):
		bar, stream = self.make(tty=False, total=4, label="copy")
		for value in range(5):
			bar.update(value)
		bar.finish()
		self.assertEqual(stream.getvalue(), "copy 100% (4/4)\n")
		self.assertEqual(stream.getvalue().count("\n"), 1)

	def test_total_and_value_are_clamped(self):
		bar = progress.ProgressBar(0, stream=FakeStream(False), cap=cap(tty=False))
		self.assertEqual(bar.total, 1)
		bar.update(-5)
		self.assertEqual(bar.value, 0)
		bar.update(99)
		self.assertEqual(bar.value, 1)
		self.assertEqual(bar.line(), "100% (1/1)")

	def test_line_format_and_rounding(self):
		bar = progress.ProgressBar(3, stream=FakeStream(False), cap=cap(tty=False),
								   label="sync")
		bar.value = 1
		self.assertEqual(bar.line(), "sync 33% (1/3)")
		bar.value = 2
		self.assertEqual(bar.line(), "sync 67% (2/3)")

	def test_tty_updates_animate_with_carriage_return(self):
		bar, stream = self.make(tty=True, total=4, value=2, width=4, label="go")
		self.assertEqual(stream.getvalue(), "\rgo \u2588\u2588\u2591\u2591\u2591 50% (2/4)")
		bar.update(3)
		self.assertEqual(stream.getvalue().count("\r"), 2)
		self.assertTrue(stream.getvalue().endswith("\rgo \u2588\u2588\u2588\u2588\u2591 75% (3/4)"))

	def test_tty_bar_uses_ascii_glyphs_without_unicode(self):
		stream = FakeStream(True)
		bar = progress.ProgressBar(2, width=4, stream=stream, cap=cap(unicode=False))
		bar.update(1)
		self.assertEqual(bar._bar(), "##---")

	def test_tty_finish_clears_then_prints_the_final_line(self):
		bar, stream = self.make(tty=True, total=2, value=2, label="go")
		bar.finish()
		self.assertEqual(stream.getvalue()[-len("\r\033[Kgo 100% (2/2)\n"):],
						 "\r\033[Kgo 100% (2/2)\n")

	def test_finish_label_overrides_the_previous_one(self):
		bar, stream = self.make(tty=False, total=2, value=2, label="old")
		bar.finish("done")
		self.assertEqual(stream.getvalue(), "done 100% (2/2)\n")

	def test_monochrome_tty_prints_one_line_and_no_escapes(self):
		# Level "none" on a real terminal: no animation, but no pipe either.
		bar, stream = self.make(tty=True, total=4, value=1, label="copy",
								cap=cap(level="none"))
		bar.update(2)
		self.assertEqual(stream.getvalue(), "")
		bar.finish()
		self.assertEqual(stream.getvalue(), "copy 50% (2/4)\n")
		self.assertNotIn("\033", stream.getvalue())
		self.assertNotIn("\r", stream.getvalue())


class SpinnerTests(unittest.TestCase):
	def test_plain_ticks_write_nothing(self):
		stream = FakeStream(False)
		spinner = progress.Spinner(frames=("a", "b"), stream=stream, cap=cap(tty=False))
		spinner.tick("working").tick("working")
		self.assertEqual(stream.getvalue(), "")

	def test_plain_stop_prints_at_most_one_line(self):
		stream = FakeStream(False)
		spinner = progress.Spinner(frames=("a", "b"), stream=stream, cap=cap(tty=False))
		spinner.tick("working")
		spinner.stop()
		self.assertEqual(stream.getvalue(), "")
		spinner.stop("done")
		self.assertEqual(stream.getvalue(), "done\n")

	def test_tty_ticks_cycle_through_the_frames_in_place(self):
		stream = FakeStream(True)
		spinner = progress.Spinner(frames=("a", "b"), stream=stream, cap=cap())
		spinner.tick("sync")
		spinner.tick("sync")
		spinner.tick("sync")
		self.assertEqual(stream.getvalue(), "\ra sync\rb sync\ra sync")

	def test_tty_stop_clears_the_line_and_prints_the_label(self):
		stream = FakeStream(True)
		spinner = progress.Spinner(frames=("a",), stream=stream, cap=cap())
		spinner.tick("sync")
		spinner.stop("finished")
		self.assertEqual(stream.getvalue()[-len("\r\033[Kfinished\n"):],
						 "\r\033[Kfinished\n")

	def test_monochrome_tty_ticks_nothing_and_stops_with_one_clean_line(self):
		stream = FakeStream(True)
		spinner = progress.Spinner(frames=("a", "b"), stream=stream,
								   cap=cap(level="none"))
		spinner.tick("sync").tick("sync")
		self.assertEqual(stream.getvalue(), "")
		spinner.stop("done")
		self.assertEqual(stream.getvalue(), "done\n")
		self.assertNotIn("\033", stream.getvalue())
		self.assertNotIn("\r", stream.getvalue())

	def test_stop_without_a_label_or_history_is_silent_on_a_tty_too(self):
		stream = FakeStream(True)
		spinner = progress.Spinner(frames=("a",), stream=stream, cap=cap())
		spinner.stop()
		self.assertEqual(stream.getvalue(), "\r\033[K")

	def test_empty_frames_fall_back_to_the_default_set(self):
		spinner = progress.Spinner(frames=(), stream=FakeStream(False), cap=cap(tty=False))
		self.assertEqual(spinner.frames, progress.SPINNER_FRAMES)

	def test_context_manager_stops_on_exit(self):
		stream = FakeStream(True)
		with progress.Spinner(frames=("a",), stream=stream, cap=cap()) as spinner:
			spinner.tick("x")
		self.assertTrue(stream.getvalue().endswith("\r\033[Ka x\n"))


class LiveRegionTests(unittest.TestCase):
	def make(self, tty=True, max_lines=2, width=4):
		stream = FakeStream(tty)
		region = progress.LiveRegion(screen.Screen(stream), 1, 2, width, max_lines)
		return region, stream

	def test_plain_output_degrades_to_whole_lines(self):
		region, stream = self.make(tty=False)
		region.update("too long for the region")
		self.assertEqual(stream.getvalue(), "too long for the region\n")
		self.assertNotIn("\033", stream.getvalue())

	def test_plain_output_respects_max_lines(self):
		region, stream = self.make(tty=False, max_lines=1)
		region.update(["one", "two", "three"])
		self.assertEqual(stream.getvalue(), "one\n")

	def test_tty_paints_padded_truncated_rows_at_the_offset(self):
		region, stream = self.make(tty=True, width=4)
		region.update(["abcdef", "xy"])
		written = stream.getvalue()
		self.assertEqual(written, "\033[3;2Hab..\033[4;2Hxy  ")

	def test_tty_blanks_rows_past_the_content(self):
		region, stream = self.make(tty=True, width=3, max_lines=2)
		region.update(["ok"])
		self.assertEqual(stream.getvalue(), "\033[3;2Hok \033[4;2H   ")

	def test_string_input_is_treated_as_one_row(self):
		region, stream = self.make(tty=True, width=2, max_lines=1)
		region.update("hello")
		self.assertEqual(stream.getvalue(), "\033[3;2H..")


if __name__ == "__main__":
	unittest.main()
