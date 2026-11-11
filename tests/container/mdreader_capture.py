# mdreader colour capture
"""
			MDREADER COLOUR CAPTURE
			=======================
Evidence tool for task 0041 batch C: runs `mdreader.py` for real on a pty and
turns what the program actually painted into per-cell
`(char, fg, bg, bold, underline)`.

Three sources are taken from one run and cross-checked, so a claim about colour
can never be a claim about the source:

	pty     the raw bytes the child wrote to the terminal, decoded here by a
	        small xterm subset parser (CSI cursor/erase/SGR, no scroll regions);
	model   the child's window proxy, which records every `addstr`/`bkgd`/`clear`
	        into a cell grid per `refresh`, plus `pair_content` for the pair's
	        slots;
	frames  one model dump per `refresh`, so a capture is the frame that was on
	        screen when the reader blocked on `getch`.

The decoder and the paint model must agree on every cell (character and
background everywhere, foreground/bold/underline on every non-blank cell); the
tool exits 1 when they do not, so a stale decoder cannot pass as evidence.
(`instr`/`inch` readback is deliberately not used: ncurses keeps a wide box
glyph as an opaque complex char, so readback returns truncated bytes and a
bogus pair for it.)

Fixture: h1-h4, body text, a code span, a link, a bullet, a numbered item, a
fenced block, a quote, an hr and a 3x3 table (header + zebra rows), at 100x30,
in all three looks. Needs a POSIX pty, so run it in the Linux image (that image
 ships no rich, hence the install; the capture exercises the reader's real Rich
 theme, not a stub):

	docker run --rm -v "$PWD":/app -w /app --entrypoint bash \
		catro-scripts-test:3.12-base -lc \
		"python -m pip install -q rich 2>/dev/null; python tests/container/mdreader_capture.py"

`--json path` writes the decoded cells and the mapping table; `--fixture path`
reads a different markdown file. Exits 2 when there is no pty to give.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
	sys.path.insert(0, ROOT)

ROWS, COLS = 30, 100
LOOKS = (("soft", "default"), ("contrast-light", "contrast-light"),
		 ("contrast-dark", "contrast-dark"))

FIXTURE = """# Heading one
## Heading two
### Heading three
#### Heading four

Body text with `inline code` and a link: [site](https://example.com)

- bullet item
1. numbered item

```
fenced code
```

> quoted line

---

| aa | bb | cc |
|----|----|----|
| 11 | 22 | 33 |
| 44 | 55 | 66 |
"""

# Element -> (substring identifying the cell run, search area). The tool fails
# an element when it is on neither captured view; the fixture then gets smaller,
# not the viewport. `content` is the reader's text area inside the frame.
ELEMENTS = (
	("h1", "Heading one", "content"),
	("h2", "Heading two", "content"),
	("h3", "Heading three", "content"),
	("h4", "Heading four", "content"),
	("body", "Body text", "content"),
	("code span", "inline code", "content"),
	("link", "https://example.com", "content"),
	("bullet", "\u2022", "content"),
	("number", "1 numbered", "content"),
	("fenced code", "fenced code", "content"),
	("quote", "quoted line", "content"),
	("hr", "-----", "content"),
	("table header", "aa", "content"),
	("table cell", "11", "content"),
	("table zebra", "44", "content"),
	("table border", "\u250c", "content"),
	("frame", "\u2554", "frame"),
	("scroll thumb", "#", "frame"),
	("eof marker", "end of file", "content"),
	("status bar", "* File:", "bars"),
	("shortcut bar", "[< / >]", "bars"),
)

# Search area name -> (first row, last row + 1, first column, last column).
AREAS = {
	"content": (2, ROWS - 3, 4, COLS - 4),
	"frame": (0, ROWS, 0, COLS),
	"bars": (ROWS - 4, ROWS - 2, 4, COLS - 4),
}

# The child: import the real reader, wrap its window so every paint call is
# recorded into a cell model, and let the parent drive the keys. `render_reader`
# is called exactly as `main()` calls it, with `tui.detect()`'s snapshot.
#
# Cells are modelled from `addstr`/`bkgd`/`clear` rather than read back with
# `instr`/`inch`: ncurses keeps a wide character as an opaque complex char, so a
# readback returns a truncated byte string and a bogus pair for every box glyph.
# The pty decode below is the independent truth; this model is the cross-check.
CHILD = r'''
import json, os, sys
sys.path.insert(0, os.getcwd())
import curses
import mdreader
import tui

PATH = os.environ["MDREADER_FIXTURE"]
OUT = os.environ["MDREADER_CELLS"]

FLAGS = (("bold", curses.A_BOLD), ("dim", curses.A_DIM),
         ("italic", getattr(curses, "A_ITALIC", 0)),
         ("underline", curses.A_UNDERLINE))


def pair_of(attr):
    if not attr:
        return 0
    return curses.pair_number(attr & curses.A_COLOR)


class Recorder:
    """Window proxy: delegate curses and model the cells the reader paints."""

    def __init__(self, win):
        object.__setattr__(self, "_win", win)
        object.__setattr__(self, "_frames", [])
        object.__setattr__(self, "_bkgd", 0)
        object.__setattr__(self, "_cells", None)

    def _grid(self):
        cells = object.__getattribute__(self, "_cells")
        if cells is None:
            rows, cols = self.getmaxyx()
            cells = grid(rows, cols, object.__getattribute__(self, "_bkgd"))
            object.__setattr__(self, "_cells", cells)
        return cells

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_win"), name)

    def bkgd(self, char, attr):
        object.__setattr__(self, "_bkgd", attr)
        rows, cols = self.getmaxyx()
        object.__setattr__(self, "_cells", grid(rows, cols, attr))
        return self._win.bkgd(char, attr)

    def clear(self):
        rows, cols = self.getmaxyx()
        object.__setattr__(self, "_cells",
                           grid(rows, cols, object.__getattribute__(self, "_bkgd")))
        return self._win.clear()

    def addstr(self, y, x, text, attr=0):
        cells = self._grid()
        rows = len(cells)
        cols = len(cells[0]) if rows else 0
        for offset, char in enumerate(text):
            if 0 <= y < rows and 0 <= x + offset < cols:
                cells[y][x + offset] = [char, pair_of(attr)] + [
                    bool(attr & bit) for _name, bit in FLAGS]
        return self._win.addstr(y, x, text, attr)

    def refresh(self):
        win = object.__getattribute__(self, "_win")
        win.refresh()
        cells = self._grid()
        pairs = {}
        for row in cells:
            for _char, pair, _b, _d, _i, _u in row:
                if pair and pair not in pairs:
                    pairs[pair] = list(curses.pair_content(pair))
        frames = object.__getattribute__(self, "_frames")
        frames.append({"cells": cells, "pairs": pairs})
        with open(OUT, "w", encoding="utf-8") as handle:
            json.dump(frames, handle)


def grid(rows, cols, attr):
    blank = [" "] + [pair_of(attr)] + [bool(attr & bit) for _n, bit in FLAGS]
    return [[list(blank) for _ in range(cols)] for _ in range(rows)]


raw = open(PATH, encoding="utf-8").read()
cap = tui.detect()
stdscr = curses.initscr()
try:
    curses.noecho()
    curses.cbreak()
    mdreader.render_reader(Recorder(stdscr), PATH, raw, cap)
finally:
    curses.endwin()
'''


# Decoder: the xterm subset ncurses writes for a full paint. Scroll regions are
# deliberately not modelled: the capture is the first frame, which clears and
# writes top-down.
def decode(data, rows=ROWS, cols=COLS):
	grid = [[[" ", None, None, False, False] for _ in range(cols)]
			for _ in range(rows)]
	pos = [0, 0]
	state = {"fg": None, "bg": None, "bold": False, "underline": False}

	def put(char):
		y, x = pos
		if 0 <= y < rows and 0 <= x < cols:
			grid[y][x] = [char, state["fg"], state["bg"], state["bold"],
						  state["underline"]]

	def blank(y, x):
		if 0 <= y < rows and 0 <= x < cols:
			grid[y][x] = [" ", None, state["bg"], False, False]

	def erase_row(y, start, end):
		for x in range(max(0, start), min(cols, end)):
			blank(y, x)

	i = 0
	while i < len(data):
		char = data[i]
		if char == "\x1b":
			if data[i + 1:i + 2] == "[":
				j = i + 2
				while j < len(data) and not ("\x40" <= data[j] <= "\x7e"):
					j += 1
				if j >= len(data):
					break
				params, final = data[i + 2:j], data[j]
				i = j + 1
				_csi(params, final, pos, state, grid, rows, cols, put, blank,
					 erase_row)
				continue
			if data[i + 1:i + 2] == "]":
				# OSC (endwin's palette reset): skip to BEL or ST.
				end = data.find("\x07", i)
				st = data.find("\x1b\\", i)
				if st >= 0 and (end < 0 or st < end):
					i = st + 2
				elif end >= 0:
					i = end + 1
				else:
					break
				continue
			if data[i + 1:i + 2] in ("(", ")", "#"):
				i += 3
				continue
			i += 2
			continue
		i += 1
		if char == "\r":
			pos[1] = 0
		elif char == "\n":
			pos[0] = min(rows - 1, pos[0] + 1)
		elif char == "\b":
			pos[1] = max(0, pos[1] - 1)
		elif char == "\t":
			pos[1] = min(cols - 1, (pos[1] // 8 + 1) * 8)
		elif char >= " ":
			if pos[1] >= cols:
				pos[1] = 0
				pos[0] = min(rows - 1, pos[0] + 1)
			put(char)
			pos[1] += 1
	return grid


def _numbers(params):
	if not params:
		return []
	return [int(p) if p.isdigit() else 0 for p in params.split(";")]


def _csi(params, final, pos, state, grid, rows, cols, put, blank, erase_row):
	nums = _numbers(params)
	first = nums[0] if nums else 0
	if final in ("H", "f"):
		pos[0] = max(0, (nums[0] if nums else 1) - 1)
		pos[1] = max(0, (nums[1] if len(nums) > 1 else 1) - 1)
	elif final == "A":
		pos[0] = max(0, pos[0] - max(1, first))
	elif final == "B":
		pos[0] = min(rows - 1, pos[0] + max(1, first))
	elif final == "C":
		pos[1] = min(cols - 1, pos[1] + max(1, first))
	elif final == "D":
		pos[1] = max(0, pos[1] - max(1, first))
	elif final == "G":
		pos[1] = max(0, first - 1)
	elif final == "d":
		pos[0] = max(0, first - 1)
	elif final == "J":
		if first == 2:
			for y in range(rows):
				erase_row(y, 0, cols)
		elif first == 0:
			erase_row(pos[0], pos[1], cols)
			for y in range(pos[0] + 1, rows):
				erase_row(y, 0, cols)
		elif first == 1:
			for y in range(0, pos[0]):
				erase_row(y, 0, cols)
			erase_row(pos[0], 0, pos[1] + 1)
	elif final == "K":
		if first == 0:
			erase_row(pos[0], pos[1], cols)
		elif first == 1:
			erase_row(pos[0], 0, pos[1] + 1)
		elif first == 2:
			erase_row(pos[0], 0, cols)
	elif final == "X":
		erase_row(pos[0], pos[1], pos[1] + max(1, first))
	elif final == "m":
		_sgr(nums or [0], state)


def _sgr(nums, state):
	index = 0
	while index < len(nums):
		code = nums[index]
		index += 1
		if code == 0:
			state.update(fg=None, bg=None, bold=False, underline=False)
		elif code == 1:
			state["bold"] = True
		elif code == 4:
			state["underline"] = True
		elif code == 24:
			state["underline"] = False
		elif code == 22:
			state["bold"] = False
		elif 30 <= code <= 37:
			state["fg"] = code - 30
		elif code == 39:
			state["fg"] = None
		elif 40 <= code <= 47:
			state["bg"] = code - 40
		elif code == 49:
			state["bg"] = None
		elif 90 <= code <= 97:
			state["fg"] = code - 90 + 8
		elif 100 <= code <= 107:
			state["bg"] = code - 100 + 8
		elif code in (38, 48) and index < len(nums):
			mode = nums[index]
			index += 1
			if mode == 5 and index < len(nums):
				value = nums[index]
				index += 1
			elif mode == 2 and index + 2 < len(nums):
				value = None
				index += 3
			else:
				value = None
			state["fg" if code == 38 else "bg"] = value


def compare(stream_cells, frames):
	"""Problems where the pty decode and the child's paint model disagree."""
	if not frames:
		return ["the child recorded no frame"]
	model = frames[-1]["cells"]
	pairs = frames[-1]["pairs"]
	problems = []
	for y in range(ROWS):
		for x in range(COLS):
			char, fg, bg, bold, underline = stream_cells[y][x]
			ref_char, pair, ref_bold = model[y][x][:3]
			ref_underline = model[y][x][5]
			ref_fg, ref_bg = pairs.get(str(pair), [None, None])
			where = "cell {},{}: ".format(y, x)
			if char != ref_char:
				problems.append(where + "pty {!r} != model {!r}".format(
					char, ref_char))
			if bg != ref_bg:
				problems.append(where + "bg pty {!r} != model {!r}".format(
					bg, ref_bg))
			if char != " " and (fg != ref_fg or bold != ref_bold
							   or underline != ref_underline):
				problems.append(
					where + "style pty ({!r}, bold={}, underline={}) != model "
					"({!r}, bold={}, underline={})"
					.format(fg, bold, underline, ref_fg, ref_bold,
							ref_underline))
	return problems


def find(grid, token, area):
	"""First match of `token` inside `area`, so the frame can't shadow the hr."""
	first, last, left, right = AREAS[area]
	for y in range(max(0, first), min(len(grid), last)):
		text = "".join(cell[0] for cell in grid[y])
		x = text.find(token, left, right)
		if x >= 0:
			return y, x
	return None


def mapping(views, colours):
	"""Element -> observed cell, first view that shows the element's token."""
	table = {}
	for element, token, area in ELEMENTS:
		for name, grid in views:
			spot = find(grid, token, area)
			if spot is None:
				continue
			y, x = spot
			cell = grid[y][x]
			table[element] = {
				"visible": True,
				"view": name,
				"at": [y, x],
				"char": cell[0],
				"fg": _hex(cell[1], colours),
				"bg": _hex(cell[2], colours),
				"bold": cell[3],
				"underline": cell[4],
			}
			break
		else:
			table[element] = {"visible": False}
	return table


def _hex(value, colours):
	if value is None:
		return None
	return colours.get(value, str(value))


def run_look(look, extra_keys=b"", fixture_text=None):
	import fcntl
	import pty
	import select
	import struct
	import subprocess
	import tempfile
	import termios
	import time

	fixture = os.path.join(tempfile.mkdtemp(prefix="mdreader-"), "fixture.md")
	with open(fixture, "w", encoding="utf-8") as handle:
		handle.write(FIXTURE if fixture_text is None else fixture_text)
	cells_path = fixture + ".json"

	master, slave = pty.openpty()
	fcntl.ioctl(slave, termios.TIOCSWINSZ,
				struct.pack("HHHH", ROWS, COLS, 0, 0))
	env = dict(os.environ, TERM="xterm-256color", COLUMNS=str(COLS),
			   LINES=str(ROWS), CATRO_THEME=look,
			   MDREADER_FIXTURE=fixture, MDREADER_CELLS=cells_path)
	env.pop("NO_COLOR", None)
	child = subprocess.Popen(
		[sys.executable, "-c", CHILD], cwd=ROOT, stdin=slave, stdout=slave,
		stderr=slave, env=env, close_fds=True, start_new_session=True)
	os.close(slave)

	output = []

	def drain(seconds):
		end = time.time() + seconds
		while time.time() < end:
			ready, _, _ = select.select([master], [], [], 0.05)
			if not ready:
				continue
			try:
				chunk = os.read(master, 65536)
			except OSError:
				return
			if not chunk:
				return
			output.append(chunk)

	drain(2.0)
	if extra_keys:
		os.write(master, extra_keys)
		drain(1.5)
	os.write(master, b"q")
	drain(2.0)
	try:
		child.wait(timeout=10)
	except subprocess.TimeoutExpired:
		child.kill()
		child.wait()
		os.close(master)
		raise SystemExit("mdreader did not exit on 'q'")
	os.close(master)

	raw = b"".join(output).decode("utf-8", "replace")
	stream = raw
	cut = stream.find("\x1b[?1049l")
	if cut >= 0:
		stream = stream[:cut]
	cells = decode(stream)

	if not os.path.exists(cells_path):
		print("child output tail: {!r}".format(raw[-1200:]))
		raise SystemExit("the child recorded no cells for " + look)

	with open(cells_path, encoding="utf-8") as handle:
		frames = json.load(handle)
	return cells, frames


def main(argv):
	if not hasattr(os, "fork") or os.name == "nt":
		print("SKIP: no pty on this platform (run inside the Linux container)")
		return 2
	json_path = None
	if "--json" in argv:
		json_path = argv[argv.index("--json") + 1]
	fixture_text = None
	if "--fixture" in argv:
		with open(argv[argv.index("--fixture") + 1], encoding="utf-8") as handle:
			fixture_text = handle.read()

	report = {}
	ok = True
	for look, theme_id in LOOKS:
		views = []
		problems = []
		for name, keys in (("top", b""), ("bottom", b"G")):
			cells, frames = run_look(look, keys, fixture_text)
			views.append((name, cells))
			if os.environ.get("MDREADER_DEBUG") and name == "top":
				for y in (11, 12, 13, 14, 15, 16, 17, 18, 19, 20):
					print("   row {:>2} {!r}".format(
						y, "".join(cell[0] for cell in cells[y][3:40])))
					print("        fg {}".format(
						[cells[y][x][1] for x in range(3, 20)]))
			problems.extend("{}/{}".format(name, problem)
							for problem in compare(cells, frames))
			if name == "top":
				colours = _slot_colours(theme_id, frames)
		table = mapping(views, colours)
		report[look] = {"mapping": table, "differences": problems[:20],
						"difference_count": len(problems)}
		print("== {} ({}) ==".format(look, theme_id))
		print("   pty/paint-model cell agreement: {}".format(
			"OK" if not problems else "{} mismatches".format(len(problems))))
		for element, seen in table.items():
			if not seen["visible"]:
				print("   {:<14} NOT ON SCREEN".format(element))
				ok = False
				continue
			print("   {:<14} {:<6} y{:>2} x{:>2} {:<3} fg {:<8} bg {:<8} {}{}".format(
				element, seen["view"], seen["at"][0], seen["at"][1],
				repr(seen["char"]), str(seen["fg"]), str(seen["bg"]),
				"bold" if seen["bold"] else "",
				" underline" if seen["underline"] else ""))
		if problems:
			ok = False
			print("   differences:")
			for problem in problems[:20]:
				print("     " + problem)
		print()

	print("RESULT:", "PASS" if ok else "FAIL")
	if json_path:
		with open(json_path, "w", encoding="utf-8") as handle:
			json.dump(report, handle, indent=1, sort_keys=True)
	return 0 if ok else 1


def _slot_colours(theme_id, frames):
	"""Slot number -> hex, from the child's pair table plus `PAIR_ROLES`.

	`PAIR_ROLES` fixes which semantic role each pair carries, so the slots the
	child actually initialised map back to palette hexes without assuming how
	`_colour_slots` allocated them.
	"""
	import mdreader

	colours = mdreader.tui.palette.palette(theme_id)
	roles = {pair: (fg, bg) for pair, fg, bg in mdreader.PAIR_ROLES}
	table = {}
	pairs = frames[0].get("pairs", {}) if frames else {}
	for pair_text, (fg_slot, bg_slot) in pairs.items():
		role = roles.get(int(pair_text))
		if not role:
			continue
		fg_role, bg_role = role
		if fg_slot >= 0:
			table.setdefault(fg_slot, colours[fg_role])
		if bg_slot >= 0:
			table.setdefault(bg_slot, colours[bg_role])
	return table


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
