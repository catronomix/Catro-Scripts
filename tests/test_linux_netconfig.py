# Linux/POSIX netconfig contract and actions.json robustness tests
"""
		NETCONFIG PLATFORM + ACTIONS.JSON SCHEMA TESTS
		==============================================
Regression net for task #21. Nothing here touches the host network: every
external call is faked, so no `netsh`, `nmcli`, `ip`, `ethtool` or `iw` command
ever runs.

Covered:
	- an unsupported OS makes netconfig exit non-zero and issue no command,
	- a missing nmcli/ip is a red failure naming the tool, never a green
	  "set to DHCP" / "DNS set" / "Restart command issued" line,
	- the POSIX path accepts a dotted mask (converted to a prefix length) and
	  sends DNS to nmcli as one comma-separated list,
	- a malformed actions.json exits 1 with one clear message, while a single
	  bad entry only warns (and errors when actually run),
	- actions-template.json mirrors the bootstrap defaults in action.py.

Run from the repo root:
	python -m unittest discover -s tests -v
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parent))

import action
import netconfig
import tui
from support import clean_env  # noqa: E402  (test helper, not production)


class NetconfigPlatformTests(unittest.TestCase):
	"""netconfig must be honest about what it can do on which OS."""

	def setUp(self):
		self.stdout = io.StringIO()
		self.stderr = io.StringIO()

	def call(self, func, *args):
		"""Runs a netconfig function with sleep/output captured."""
		with mock.patch.object(netconfig.time, "sleep"), \
				redirect_stdout(self.stdout), redirect_stderr(self.stderr):
			return func(*args)

	def platform(self, system):
		return mock.patch.object(netconfig.platform, "system", return_value=system)

	def test_unsupported_os_exits_non_zero_and_runs_nothing(self):
		"""Darwin is not a target: exit non-zero, no command, explicit message."""
		with self.platform("Darwin"), mock.patch.object(netconfig, "run_cmd") as run_cmd:
			rc = self.call(netconfig.main)
		self.assertEqual(rc, 1, "main() must return a non-zero code on darwin")
		run_cmd.assert_not_called()
		self.assertIn("not supported on darwin", self.stderr.getvalue())

	def test_missing_nmcli_fails_loudly(self):
		"""A write path without nmcli must fail and print no green success line."""
		issued = []
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value=None), \
				mock.patch.object(netconfig, "run_cmd",
								  side_effect=lambda cmd: issued.append(cmd) or ("", None)):
			self.assertFalse(self.call(netconfig.apply_config, "eth0", "dhcp"))
			self.assertFalse(self.call(netconfig.apply_dns, "eth0", "auto"))
			self.assertFalse(self.call(netconfig.restart_adapter, "eth0"))
		self.assertEqual(issued, [], "a missing nmcli must not be called anyway")
		output = self.stdout.getvalue()
		self.assertNotIn("set to DHCP", output)
		self.assertNotIn("DNS set to", output)
		self.assertNotIn("Restart command issued", output)
		self.assertIn("'nmcli'", self.stderr.getvalue())

	def test_missing_ip_fails_loudly(self):
		"""Interface discovery without `ip` reports the tool and returns nothing."""
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value=None), \
				mock.patch.object(netconfig, "run_cmd") as run_cmd:
			interfaces = self.call(netconfig.get_interfaces)
		self.assertEqual(interfaces, [])
		run_cmd.assert_not_called()
		self.assertIn("'ip'", self.stderr.getvalue())

	def test_command_failure_is_not_green(self):
		"""A non-zero command must return False and keep the success line away."""
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value="/usr/bin/nmcli"), \
				mock.patch.object(netconfig, "run_cmd", return_value=(None, "nmcli: device not found")):
			ok = self.call(netconfig.apply_config, "eth0", "dhcp")
		self.assertFalse(ok)
		self.assertNotIn("set to DHCP", self.stdout.getvalue())
		self.assertIn("device not found", self.stderr.getvalue())

	def test_success_paths_return_true(self):
		"""With nmcli present and commands succeeding, the green lines do appear."""
		issued = []
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value="/usr/bin/nmcli"), \
				mock.patch.object(netconfig, "run_cmd",
								  side_effect=lambda cmd: issued.append(cmd) or ("", None)):
			self.assertTrue(self.call(netconfig.apply_config, "eth0", "dhcp"))
			self.assertTrue(self.call(netconfig.apply_dns, "eth0", "manual", ["1.1.1.1"]))
			self.assertTrue(self.call(netconfig.restart_adapter, "eth0"))
		self.assertIn("set to DHCP", self.stdout.getvalue())
		self.assertIn("DNS set to Manual", self.stdout.getvalue())
		self.assertIn("Restart command issued", self.stdout.getvalue())
		self.assertTrue(any("ipv4.method auto" in cmd for cmd in issued))
		self.assertTrue(any("nmcli device connect eth0" == cmd for cmd in issued))

	def test_static_mask_becomes_prefix(self):
		"""A dotted mask must turn into a CIDR prefix for `ipv4.addresses`."""
		issued = []
		config = {"ip": "10.0.0.5", "mask": "255.255.255.0", "gw": "10.0.0.1"}
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value="/usr/bin/nmcli"), \
				mock.patch.object(netconfig, "run_cmd",
								  side_effect=lambda cmd: issued.append(cmd) or ("", None)):
			self.assertTrue(self.call(netconfig.apply_config, "eth0", "static", config))
		self.assertTrue(any("10.0.0.5/24" in cmd for cmd in issued),
						"dotted mask was not converted: {}".format(issued))

	def test_prefix_input_is_accepted(self):
		"""A prefix length typed instead of a mask must pass through unchanged."""
		issued = []
		config = {"ip": "10.0.0.5", "mask": "16", "gw": "10.0.0.1"}
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value="/usr/bin/nmcli"), \
				mock.patch.object(netconfig, "run_cmd",
								  side_effect=lambda cmd: issued.append(cmd) or ("", None)):
			self.assertTrue(self.call(netconfig.apply_config, "eth0", "static", config))
		self.assertTrue(any("10.0.0.5/16" in cmd for cmd in issued))

	def test_invalid_mask_is_rejected(self):
		"""A non-contiguous mask fails before anything is sent to nmcli."""
		config = {"ip": "10.0.0.5", "mask": "255.0.255.0", "gw": "10.0.0.1"}
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value="/usr/bin/nmcli"), \
				mock.patch.object(netconfig, "run_cmd") as run_cmd:
			ok = self.call(netconfig.apply_config, "eth0", "static", config)
		self.assertFalse(ok)
		run_cmd.assert_not_called()
		self.assertIn("not a valid subnet mask", self.stderr.getvalue())

	def test_dns_is_one_comma_separated_list(self):
		"""nmcli takes one comma-separated ipv4.dns value, not space-separated."""
		issued = []
		with self.platform("Linux"), \
				mock.patch.object(netconfig.shutil, "which", return_value="/usr/bin/nmcli"), \
				mock.patch.object(netconfig, "run_cmd",
								  side_effect=lambda cmd: issued.append(cmd) or ("", None)):
			self.assertTrue(self.call(netconfig.apply_dns, "eth0", "manual",
									  ["1.1.1.1", "8.8.8.8"]))
		self.assertTrue(any("ipv4.dns '1.1.1.1,8.8.8.8'" in cmd for cmd in issued),
						"DNS list was not comma-joined: {}".format(issued))

	def test_mask_to_prefix_table(self):
		cases = {
			"255.255.255.0": 24,
			"255.255.0.0": 16,
			"255.255.255.255": 32,
			"0.0.0.0": 0,
			"24": 24,
			"8": 8,
			"255.0.255.0": None,
			"33": None,
			"not-a-mask": None,
		}
		for mask, expected in cases.items():
			with self.subTest(mask=mask):
				self.assertEqual(netconfig.mask_to_prefix(mask), expected)


class NetconfigPageFrameTests(unittest.TestCase):
	"""Issue #43: both netconfig pages are one framed page, not bare rows."""

	def cap(self, plain=False):
		return tui.Capabilities(level="none", unicode=False, width=None,
								isatty=not plain, plain=plain, reason="test")

	def test_page_frame_wraps_title_subtitle_and_menu(self):
		cap = self.cap()
		glyphs = tui.table.glyphs_for(cap)
		lines = netconfig.page("Available Interfaces", "Select adapter number",
							   ["eth0", "Quit"], cap=cap).splitlines()
		self.assertTrue(lines[0].startswith(glyphs["tl"]),
						"page must open on a box top edge: {!r}".format(lines[0]))
		self.assertTrue(lines[-1].startswith(glyphs["bl"]))
		self.assertIn("Available Interfaces", lines[0])
		self.assertIn("Select adapter number", lines[1])
		for label in ("1. eth0", "2. Quit"):
			row = next(line for line in lines if label in line)
			self.assertTrue(row.startswith(glyphs["v"]) and row.endswith(glyphs["v"]),
							"menu row is outside the frame: {!r}".format(row))

	def test_pipe_page_drops_the_frame(self):
		page = netconfig.page("Managing: eth0", "Network adapter menu",
							  ["Show Network Info", "Exit"], cap=self.cap(plain=True))
		self.assertEqual(page.splitlines(),
						 ["Managing: eth0", "Network adapter menu",
						  "1. Show Network Info", "2. Exit"])


class ActionsFileTests(unittest.TestCase):
	"""actions.json schema handling: warn per bad entry, fail once per bad file."""

	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.dir = Path(self.tmp.name)
		shutil.copy2(str(REPO / "action.py"), str(self.dir / "action.py"))
		# action.py now renders through the sibling `tui` package, so a copy
		# taken out of the checkout has to carry the library with it.
		shutil.copytree(REPO / "tui", self.dir / "tui",
						ignore=shutil.ignore_patterns("__pycache__"))
		# ... and the shipped theme document, which is the built-in fallback.
		shutil.copytree(REPO / "themes", self.dir / "themes")

	def tearDown(self):
		self.tmp.cleanup()

	def write_actions(self, data):
		path = self.dir / "actions.json"
		path.write_text(data if isinstance(data, str) else json.dumps(data),
						encoding="utf-8")
		return path

	def run_action(self, *args):
		# Force UTF-8 so the table does not depend on the console code page;
		# the wrappers set the same mode in real use.
		env = clean_env(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
		return subprocess.run(
			[sys.executable, "action.py"] + list(args),
			cwd=str(self.dir),
			env=env,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			timeout=60,
		)

	def run_text(self, proc):
		return ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace")

	def test_malformed_file_exits_one_with_one_message(self):
		self.write_actions('{"broken": ')
		proc = self.run_action("list")
		output = self.run_text(proc)
		self.assertEqual(proc.returncode, 1,
						 "malformed actions.json exited {}\n{}".format(
							 proc.returncode, output[-800:]))
		self.assertIn("cannot read", output)
		self.assertNotIn("Traceback", output)

	def test_non_object_file_exits_one(self):
		self.write_actions([1, 2, 3])
		proc = self.run_action("list")
		output = self.run_text(proc)
		self.assertEqual(proc.returncode, 1,
						 "non-object actions.json exited {}\n{}".format(
							 proc.returncode, output[-800:]))
		self.assertIn("must contain a JSON object", output)
		self.assertNotIn("Traceback", output)

	def test_entry_missing_description_only_warns(self):
		self.write_actions({"only-command": {"command": "echo hi"}})
		proc = self.run_action("list")
		output = self.run_text(proc)
		self.assertEqual(proc.returncode, 0,
						 "a single incomplete entry must not abort the list\n{}".format(
							 output[-800:]))
		self.assertIn("Warning", output)
		self.assertIn("description", output)
		self.assertIn("only-command", self.run_text(proc))
		self.assertNotIn("Traceback", output)

	def test_entry_without_command_fails_when_run(self):
		self.write_actions({"broken": {"description": "no command here"}})
		proc = self.run_action("run", "broken")
		output = self.run_text(proc)
		self.assertEqual(proc.returncode, 1,
						 "running a command-less entry exited {}\n{}".format(
							 proc.returncode, output[-800:]))
		self.assertIn("has no command", output)
		self.assertNotIn("Traceback", output)

	def test_template_matches_bootstrap_defaults(self):
		"""The tracked template is the example the bootstrap defaults mirror."""
		template = json.loads((REPO / "actions-template.json").read_text(encoding="utf-8"))
		self.assertEqual(template, action.DEFAULT_ACTIONS)
		# A first run in an empty directory must reproduce the template exactly.
		proc = self.run_action("list")
		self.assertEqual(proc.returncode, 0, self.run_text(proc)[-800:])
		bootstrapped = json.loads((self.dir / "actions.json").read_text(encoding="utf-8"))
		self.assertEqual(bootstrapped, template)


if __name__ == "__main__":
	unittest.main()
