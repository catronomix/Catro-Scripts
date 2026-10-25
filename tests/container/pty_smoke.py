# POSIX pty smoke for the full-screen paths
"""
			PTY SMOKE
			=========
The unit tests drive `tui.keys`, `tui.screen` and `tui.pager` with fakes, which
cannot prove that a *real* terminal behaves: raw mode has to be entered, keys
have to arrive without Enter, the alternate screen has to be left again, and the
terminal settings have to be the same afterwards as before.

This probe runs the two interactive surfaces end to end under a real pty
(`pty.openpty()`), sends the actual escape bytes, and asserts:

	menu   : screensaver.py paints, ESC exits 0, alt screen entered and left
	pager  : tui.pager.page pages, 'q' exits 0, no leftover "-- more" prompt
	pager  : a forwards key (space) advances before 'q'
	both   : ICANON/ECHO are restored on the pty after the child exits

Needs a POSIX host (or the Linux container): `pty` does not exist on Windows.

	docker run --rm -v "$PWD":/app -w /app --entrypoint python \
		catro-scripts-test:3.12-base tests/container/pty_smoke.py

Exits 0 when every check passes, 1 otherwise, and 2 when there is no pty to
give (so a Windows run is a skip, not a failure).
"""

import os
import pty
import select
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

ALT_ON = "\x1b[?1049h"
ALT_OFF = "\x1b[?1049l"


def _drain(master, seconds):
	"""Read whatever the child writes for `seconds`; returns text."""
	deadline = time.time() + seconds
	chunks = []
	while time.time() < deadline:
		ready, _, _ = select.select([master], [], [], 0.05)
		if not ready:
			continue
		try:
			data = os.read(master, 4096)
		except OSError:
			break
		if not data:
			break
		chunks.append(data)
	return b"".join(chunks).decode("utf-8", "replace")


def _modes(fd):
	"""The terminal flags this probe cares about: line discipline + echo."""
	try:
		attributes = termios.tcgetattr(fd)
	except termios.error:
		return None
	return bool(attributes[3] & termios.ICANON), bool(attributes[3] & termios.ECHO)


def run_case(name, argv, keys, expect=()):
	"""Spawn `argv` on a pty, feed `keys` (bytes), assert exit 0 and markers."""
	master, slave = pty.openpty()
	before = _modes(slave)
	env = dict(os.environ, TERM="xterm-256color", COLUMNS="80", LINES="24")
	env.pop("NO_COLOR", None)
	child = subprocess.Popen(argv, cwd=ROOT, stdin=slave, stdout=slave,
							 stderr=slave, env=env, close_fds=True,
							 start_new_session=True)
	seen = _drain(master, 1.2)
	for key in keys:
		os.write(master, key)
		seen += _drain(master, 1.2)
	try:
		code = child.wait(timeout=10)
	except subprocess.TimeoutExpired:
		child.kill()
		child.wait()
		os.close(master)
		os.close(slave)
		print("  {:<26} FAIL hung".format(name))
		return False
	after = _modes(slave)
	os.close(master)
	os.close(slave)

	ok = code == 0
	problems = [] if ok else ["exit {!r}".format(code)]
	for marker in expect:
		if marker not in seen:
			ok = False
			problems.append("missing {!r}".format(marker))
	if before != after:
		ok = False
		problems.append("terminal modes changed {} -> {}".format(before, after))
	print("  {:<26} {} {}".format(name, "PASS" if ok else "FAIL",
								  "; ".join(problems)))
	if not ok:
		print("     tail: {!r}".format(seen[-300:]))
	return ok


def main():
	if not hasattr(pty, "openpty") or os.name == "nt":
		print("SKIP: no pty on this platform (run inside the Linux container)")
		return 2
	results = [
		run_case("screensaver menu + ESC",
				 [sys.executable, "screensaver.py"], [b"\x1b"],
				 expect=(ALT_ON, ALT_OFF, "Use UP/DOWN")),
		run_case("screensaver menu + DOWN",
				 [sys.executable, "screensaver.py"], [b"\x1b[B", b"\x1b"],
				 expect=(ALT_ON, ALT_OFF)),
		run_case("pager + q",
				 [sys.executable, "-c", PAGE], [b"q"],
				 expect=(ALT_ON, ALT_OFF, "line 01", "-- more")),
		run_case("pager + space + q",
				 [sys.executable, "-c", PAGE], [b" ", b"q"],
				 expect=(ALT_ON, ALT_OFF, "line 06")),
		run_case("pager + pgdown + q",
				 [sys.executable, "-c", PAGE], [b"\x1b[6~", b"q"],
				 expect=(ALT_ON, ALT_OFF, "line 06")),
	]
	print("RESULT:", "PASS" if all(results) else "FAIL")
	return 0 if all(results) else 1


PAGE = (
	"from tui.pager import page\n"
	"page(['line {:02d}'.format(n) for n in range(1, 31)], page_size=5)\n"
)


if __name__ == "__main__":
	sys.exit(main())
