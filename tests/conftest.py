# Suite-wide guards: the test process may read the checkout, never write it
"""
This conftest exists so the checkout is protected by *being in the suite*, not
by every module remembering to redirect its seams (issue #39).

`repository_write_guard` is a session autouse fixture, so pytest applies it to
every collected item - `unittest.TestCase` methods included, which is what the
suite is written in. It:

	1. snapshots `themes/*.json`, `theme.ini`, `config.ini` and
	   `tests/fixtures/**` (sha256 + mtime_ns) before the first test,
	2. installs `support.install_repo_write_guard()`, which refuses any write
	   whose resolved target is inside the repository (temp folder unaffected),
	3. restores the writers and asserts the snapshot is unchanged at session
	   end, so even a rewrite a test later undoes is reported.

The guard lives only in this process: a real `cs theme ...` run still writes
the project's `theme.ini`/`config.ini`.
"""

import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
for entry in (str(REPO), str(TESTS)):
	if entry not in sys.path:
		sys.path.insert(0, entry)

import support  # noqa: E402  (test helper, not production)


@pytest.fixture(scope="session", autouse=True)
def repository_write_guard():
	"""Refuse checkout writes and prove the suite left the data as found."""
	before = support.snapshot_checkout()
	uninstall = support.install_repo_write_guard()
	try:
		yield
	finally:
		uninstall()
		support.assert_checkout_unchanged(before)
