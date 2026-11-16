# OSC 8 hyperlink tests for tui.hyperlink and the mdreader wiring
"""
		HYPERLINK SEAM
		==============
Pins the pure layer: the sequence byte shape, the support gate, the URL
allowlist, and that mdreader carries the target on a Segment, keeps it through
slicing, and never hands an escape byte to curses (the escape could be counted
as a cell or clipped before its close). The raw re-emission itself is proved on
a real pty by tests/container/mdreader_capture.py, not here.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

from support import module_isolation  # noqa: E402  (test helper, not production)

setUpModule, tearDownModule = module_isolation()

from tui import caps, hyperlink  # noqa: E402  (import after sys.path setup)


def _cap(level="true", plain=False, reason="WT_SESSION"):
	return caps.Capabilities(level=level, unicode=True, width=80, isatty=True,
							 plain=plain, reason=reason)


class WrapTests(unittest.TestCase):
	def test_wrap_brackets_the_visible_text(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False):
			wrapped = hyperlink.wrap("https://example.com", "example.com", _cap())
		self.assertEqual(
			wrapped,
			"\x1b]8;;https://example.com\x1b\\example.com\x1b]8;;\x1b\\")
		self.assertEqual(wrapped.count("example.com"), 2,
						 "the target is the opener, the text is the visible url")

	def test_wrap_is_transparent_where_links_are_refused(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False):
			self.assertEqual(
				hyperlink.wrap("https://e.com", "e.com", _cap(level="none")),
				"e.com")
			self.assertEqual(
				hyperlink.wrap("https://e.com", "e.com", _cap(plain=True)),
				"e.com")


class SupportedTests(unittest.TestCase):
	def test_a_colour_capable_posix_terminal_supports_links(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False):
			for level in ("16", "256", "true"):
				with self.subTest(level=level):
					self.assertTrue(hyperlink.supported(_cap(level=level)))

	def test_none_and_pipe_refuse_links(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False):
			self.assertFalse(hyperlink.supported(_cap(level="none")))
			self.assertFalse(hyperlink.supported(_cap(plain=True)))

	def test_windows_refuses_links(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", True):
			self.assertFalse(hyperlink.supported(_cap()))

	def test_a_clean_run_takes_the_capability_snapshot_once(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False), \
				mock.patch.object(caps, "detect", return_value=_cap()) as detect:
			self.assertTrue(hyperlink.supported())
		detect.assert_called_once_with()


class OpenableTests(unittest.TestCase):
	def test_web_and_mail_targets_are_openable(self):
		for url in ("http://example.com", "https://example.com/a?b=c",
					"HTTPS://EXAMPLE.COM", "mailto:me@example.com"):
			with self.subTest(url=url):
				self.assertTrue(hyperlink.is_openable(url))

	def test_everything_else_degrades_to_text(self):
		for url in ("", "#anchor", "/relative/path", "ftp://example.com",
					"https://a b", "https://a\tb", "https://a\nb",
					"https://a\x7fb", None, 7):
			with self.subTest(url=url):
				self.assertFalse(hyperlink.is_openable(url))


class PaintGateTests(unittest.TestCase):
	def test_unsupported_or_odd_targets_emit_nothing(self):
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False):
			self.assertFalse(hyperlink.paint(0, 0, "x", "https://e.com",
											 cap=_cap(level="none")))
			self.assertFalse(hyperlink.paint(0, 0, "x", "#anchor", cap=_cap()))
			self.assertFalse(hyperlink.paint(0, 0, "", "https://e.com",
											 cap=_cap()))


class _FakeCurses:
	"""Just enough curses for the raw re-emission seam."""

	A_BOLD = 1 << 1
	A_DIM = 1 << 2
	A_ITALIC = 1 << 3
	A_UNDERLINE = 1 << 4
	_CAPS = {"cup": b"CUP", "setaf": b"AF", "setab": b"AB", "sgr0": b"R",
			 "bold": b"B", "dim": b"D", "sitm": b"I", "smul": b"U"}

	def __init__(self, missing=()):
		self.missing = set(missing)
		self.writes = []

	def tigetstr(self, name):
		return None if name in self.missing else self._CAPS[name]

	def tparm(self, value, *args):
		return value + b"".join(str(arg).encode() for arg in args)

	def pair_content(self, pair):
		return (3, 1)

	def putp(self, data):
		self.writes.append(data)


class PaintTests(unittest.TestCase):
	def test_the_close_rides_in_the_same_write_as_the_open(self):
		fake = _FakeCurses()
		open_bytes = hyperlink._OPEN.format("https://example.com").encode()
		close_bytes = hyperlink._CLOSE.encode()
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False), \
				mock.patch.dict(sys.modules, {"curses": fake}):
			self.assertTrue(hyperlink.paint(2, 4, "example.com",
										    "https://example.com",
										    _FakeCurses.A_UNDERLINE, 3,
										    _cap()))
		payload, = fake.writes
		self.assertIn(open_bytes + b"example.com" + close_bytes, payload)
		self.assertEqual(payload.count(close_bytes), 1)
		self.assertTrue(payload.endswith(close_bytes + b"R"),
						"the reset follows the close in the same write")

	def test_a_missing_attribute_capability_emits_nothing(self):
		fake = _FakeCurses(missing=("smul",))
		with mock.patch.object(hyperlink, "_IS_WINDOWS", False), \
				mock.patch.dict(sys.modules, {"curses": fake}):
			self.assertFalse(hyperlink.paint(0, 0, "example.com",
										     "https://example.com",
										     _FakeCurses.A_UNDERLINE, 3,
										     _cap()))
		self.assertEqual(fake.writes, [])


class MdreaderCarriageTests(unittest.TestCase):
	def _mdreader(self):
		import mdreader
		return mdreader

	def test_a_link_segment_carries_its_target(self):
		mdreader = self._mdreader()
		if mdreader.Theme is None:
			self.skipTest("rich is not installed")
		doc = mdreader.process_markdown_rich(
			"see [the site](https://example.com) here", 60)
		segments = [seg for line in doc for seg in line.segments]
		links = [seg for seg in segments if seg.url]
		self.assertEqual([(seg.text, seg.url) for seg in links],
						 [("https://example.com", "https://example.com")])
		neighbours = [seg for seg in segments
					  if "see" in seg.text or "here" in seg.text]
		self.assertTrue(neighbours)
		self.assertTrue(all(seg.url is None for seg in neighbours))

	def test_a_code_span_is_not_a_link(self):
		mdreader = self._mdreader()
		if mdreader.Theme is None:
			self.skipTest("rich is not installed")
		doc = mdreader.process_markdown_rich("`[x](https://example.com)`", 60)
		self.assertEqual(
			[seg.url for line in doc for seg in line.segments if seg.url], [])

	def test_slicing_keeps_the_target_on_every_piece(self):
		mdreader = self._mdreader()
		seg = mdreader.Segment("abcdefgh", 0, 3, "https://example.com")
		pieces = mdreader.slice_line_segments([seg], 2, 3)
		self.assertEqual([(piece.text, piece.url) for piece in pieces],
						 [("cde", "https://example.com")])


class RenderWiringTests(unittest.TestCase):
	"""The reader's paint: curses draws visible cells, the link is overlaid."""

	def _paint(self, raw, supported=True):
		import mdreader

		stdscr = mock.Mock()
		stdscr.getmaxyx.return_value = (30, 60)
		stdscr.getch.side_effect = KeyboardInterrupt
		spy = mock.Mock(return_value=True)
		with mock.patch.object(mdreader.curses, "start_color"), \
				mock.patch.object(mdreader.curses, "use_default_colors"), \
				mock.patch.object(mdreader.curses, "curs_set"), \
				mock.patch.object(mdreader.curses, "color_pair", return_value=0), \
				mock.patch.object(mdreader, "init_theme_colors"), \
				mock.patch.object(mdreader, "get_directory_md_files",
								  return_value=(os.getcwd(), [])), \
				mock.patch.object(mdreader.tui.hyperlink, "supported",
								  return_value=supported), \
				mock.patch.object(mdreader.tui.hyperlink, "paint", spy):
			with self.assertRaises(KeyboardInterrupt):
				mdreader.render_reader(stdscr, "doc.md", raw)
		painted = [call.args[2] for call in stdscr.addstr.call_args_list]
		return painted, spy

	def test_no_escape_byte_ever_reaches_curses(self):
		painted, spy = self._paint(
			"[site](https://example.com/" + "long-path/" * 20 + ")\n")
		self.assertTrue(painted)
		self.assertFalse([text for text in painted if "\x1b" in text])
		self.assertTrue(spy.called, "the visible run must be re-emitted as a link")

	def test_each_visible_piece_is_re_emitted_inside_its_own_link(self):
		url = "https://example.com/" + "long-path/" * 20
		_painted, spy = self._paint("[site](%s)\n" % url)
		runs = [call.args for call in spy.call_args_list]
		self.assertTrue(runs)
		self.assertTrue(all(run[3] == url for run in runs),
						"every piece keeps the whole target")
		self.assertTrue(all(len(run[2]) < len(url) for run in runs),
						"the url is folded into several visible runs")
		self.assertEqual("".join(run[2] for run in runs), url,
						 "the pieces are the visible url, nothing else")
		# paint() writes open + text + close in one unit, so a run cut at the
		# right edge cannot lose its close (see PaintTests).
		columns = [run[1] for run in runs]
		self.assertEqual(columns, sorted(columns))

	def test_an_unsupported_terminal_keeps_plain_text(self):
		painted, spy = self._paint("[site](https://example.com)\n",
								   supported=False)
		self.assertTrue(any("example.com" in text for text in painted))
		self.assertFalse(spy.called)
