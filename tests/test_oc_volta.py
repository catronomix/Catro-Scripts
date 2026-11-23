# Regression tests for the opencode/Volta updater
"""
		OPENCODE / VOLTA UPDATER TESTS
		==============================
The updater's whole value is the last step: proving the binary the `opencode`
shim runs is the real one and not the postinstall placeholder. These tests pin
that contract without touching the network, Volta, npm or the local install:

	- the Volta root is discovered from the directories that exist,
	- the installed version comes from the image package.json,
	- a small placeholder is recognised as broken, a real binary is not,
	- an up-to-date and healthy install changes nothing,
	- an outdated install runs install -> postinstall -> verify in that order,
	- a verification mismatch fails the run instead of claiming success,
	- `--check` reports but never installs,
	- a machine without the package fails with the install hint.

Every seam (`installed_version`, `latest_version`, `install_version`,
`run_postinstall`, `probe_version`, `binary_is_stub`) is patched, so a run of
this module never invokes volta, npm or node.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for entry in (str(REPO), str(TESTS)):
	if entry not in sys.path:
		sys.path.insert(0, entry)

import oc_volta  # noqa: E402  (import after sys.path setup)
import tui  # noqa: E402


def caps():
	return tui.detect()


def make_package(root, version, binary_bytes=b'\x00' * 8192):
	"""Build a fake Volta image package under `root`; returns its directory."""
	package = Path(root) / 'tools' / 'image' / 'packages' / '@opencode' / 'cli' \
		/ 'node_modules' / '@opencode' / 'cli'
	(package / 'bin').mkdir(parents=True)
	(package / 'package.json').write_text(
		json.dumps({'name': '@opencode/cli', 'version': version}),
		encoding='utf-8')
	(package / 'bin' / ('opencode.exe' if os.name == 'nt' else 'opencode')) \
		.write_bytes(binary_bytes)
	(package / 'postinstall.mjs').write_text('', encoding='utf-8')
	return package


class DiscoveryTests(unittest.TestCase):
	"""Paths and versions are read from the image, not guessed."""

	def test_volta_home_prefers_a_directory_that_holds_the_image(self):
		with tempfile.TemporaryDirectory() as td:
			real = Path(td) / 'Volta'
			make_package(real, '1.0.0')
			empty = Path(td) / 'empty'
			empty.mkdir()
			with mock.patch.dict(os.environ,
								 {'VOLTA_HOME': str(empty),
								  'LOCALAPPDATA': str(td)}, clear=False):
				self.assertEqual(oc_volta.volta_home(), str(real))

	def test_configured_volta_home_wins_when_it_is_real(self):
		with tempfile.TemporaryDirectory() as td:
			make_package(td, '1.0.0')
			with mock.patch.dict(os.environ, {'VOLTA_HOME': td}, clear=False):
				self.assertEqual(oc_volta.volta_home(), td)

	def test_installed_version_reads_the_package_json(self):
		with tempfile.TemporaryDirectory() as td:
			package = make_package(td, '2.4.1')
			with mock.patch.object(oc_volta, 'package_dir',
								   return_value=str(package)):
				self.assertEqual(oc_volta.installed_version(), '2.4.1')

	def test_missing_package_reads_as_not_installed(self):
		with tempfile.TemporaryDirectory() as td:
			with mock.patch.object(oc_volta, 'package_dir',
								   return_value=os.path.join(td, 'nope')):
				self.assertIsNone(oc_volta.installed_version())


class BinaryHealthTests(unittest.TestCase):
	"""The placeholder is the bug; it must be detected, not tolerated."""

	def test_a_small_placeholder_counts_as_a_stub(self):
		with tempfile.TemporaryDirectory() as td:
			stub = Path(td) / 'opencode.exe'
			stub.write_text(
				'echo "Error: postinstall script was not run." >&2\n',
				encoding='utf-8')
			self.assertTrue(oc_volta.binary_is_stub(str(stub)))

	def test_a_real_sized_binary_is_not_a_stub(self):
		with tempfile.TemporaryDirectory() as td:
			real = Path(td) / 'opencode.exe'
			real.write_bytes(b'\x00' * oc_volta.STUB_MAX_BYTES)
			self.assertFalse(oc_volta.binary_is_stub(str(real)))

	def test_absent_binary_is_not_reported_as_a_stub(self):
		with tempfile.TemporaryDirectory() as td:
			self.assertFalse(oc_volta.binary_is_stub(
				str(Path(td) / 'missing.exe')))

	def test_probe_version_keeps_only_the_version_token(self):
		done = mock.Mock(returncode=0, stdout='opencode v2.4.1\n', stderr='')
		with tempfile.TemporaryDirectory() as td:
			binary = Path(td) / 'opencode'
			binary.write_bytes(b'\x00')
			with mock.patch.object(oc_volta, 'binary_path',
								   return_value=str(binary)), \
					mock.patch('subprocess.run', return_value=done):
				self.assertEqual(oc_volta.probe_version(), '2.4.1')

	def test_probe_version_returns_none_when_the_binary_fails(self):
		done = mock.Mock(returncode=1, stdout='', stderr='not compatible')
		with tempfile.TemporaryDirectory() as td:
			binary = Path(td) / 'opencode'
			binary.write_bytes(b'\x00')
			with mock.patch.object(oc_volta, 'binary_path',
								   return_value=str(binary)), \
					mock.patch('subprocess.run', return_value=done):
				self.assertIsNone(oc_volta.probe_version())


class UpgradeFlowTests(unittest.TestCase):
	"""Exit codes, ordering and the verify gate of the upgrade workflow."""

	def run_upgrade(self, argv, **seams):
		args = oc_volta.parse_args(argv)
		defaults = {'installed_version': mock.Mock(return_value='2.4.0'),
					'latest_version': mock.Mock(return_value='2.4.1'),
					'install_version': mock.Mock(return_value=(True, 'pkg@2.4.1')),
					'run_postinstall': mock.Mock(return_value=(True, 'ok')),
					'probe_version': mock.Mock(return_value='2.4.1'),
					'binary_is_stub': mock.Mock(return_value=False),
					'restart_service': mock.Mock(return_value=(True, 'ok'))}
		defaults.update(seams)
		patches = [mock.patch.object(oc_volta, name, value)
				   for name, value in defaults.items()]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		return oc_volta.upgrade(args, caps())

	def test_up_to_date_install_changes_nothing(self):
		seams = {'latest_version': mock.Mock(return_value='2.4.0'),
				 'probe_version': mock.Mock(return_value='2.4.0')}
		code = self.run_upgrade([], **seams)
		self.assertEqual(code, 0)
		oc_volta.install_version.assert_not_called()
		oc_volta.run_postinstall.assert_not_called()

	def test_outdated_install_runs_postinstall_and_verifies(self):
		code = self.run_upgrade([])
		self.assertEqual(code, 0)
		oc_volta.install_version.assert_called_once_with('2.4.1')
		oc_volta.run_postinstall.assert_called_once_with()
		oc_volta.probe_version.assert_called()

	def test_placeholder_with_current_version_is_repaired(self):
		# placeholder -> printed state -> repaired by postinstall
		seams = {'latest_version': mock.Mock(return_value='2.4.0'),
				 'probe_version': mock.Mock(return_value='2.4.0'),
				 'binary_is_stub': mock.Mock(side_effect=[True, True, False])}
		code = self.run_upgrade([], **seams)
		self.assertEqual(code, 0)
		oc_volta.install_version.assert_not_called()
		oc_volta.run_postinstall.assert_called_once_with()

	def test_verification_mismatch_fails_the_run(self):
		seams = {'probe_version': mock.Mock(return_value='2.4.0')}
		self.assertEqual(self.run_upgrade([], **seams), 1)

	def test_a_failed_postinstall_stops_before_verifying(self):
		# probe_version runs once for the health check before the install, so
		# the gate is "no second probe after the failure", not "never probed".
		seams = {'run_postinstall': mock.Mock(return_value=(False, 'boom')),
				 'probe_version': mock.Mock(return_value='2.4.0')}
		self.assertEqual(self.run_upgrade([], **seams), 1)
		oc_volta.probe_version.assert_called_once_with()

	def test_check_reports_without_installing(self):
		self.assertEqual(self.run_upgrade(['--check']), 0)
		oc_volta.install_version.assert_not_called()
		oc_volta.run_postinstall.assert_not_called()

	def test_pinned_version_overrides_the_registry(self):
		seams = {'install_version': mock.Mock(return_value=(True, 'pinned')),
				 'probe_version': mock.Mock(return_value='2.5.0')}
		code = self.run_upgrade(['--version', '2.5.0'], **seams)
		self.assertEqual(code, 0)
		oc_volta.install_version.assert_called_once_with('2.5.0')

	def test_force_reinstalls_even_when_versions_match(self):
		seams = {'latest_version': mock.Mock(return_value='2.4.0'),
				 'probe_version': mock.Mock(return_value='2.4.0')}
		code = self.run_upgrade(['--force'], **seams)
		self.assertEqual(code, 0)
		oc_volta.install_version.assert_called_once_with('2.4.0')

	def test_restart_only_runs_when_asked(self):
		self.assertEqual(self.run_upgrade([]), 0)
		oc_volta.restart_service.assert_not_called()
		self.assertEqual(self.run_upgrade(['--restart']), 0)
		oc_volta.restart_service.assert_called_once_with()

	def test_missing_package_fails_with_the_install_hint(self):
		seams = {'installed_version': mock.Mock(return_value=None)}
		self.assertEqual(self.run_upgrade([], **seams), 1)
		oc_volta.install_version.assert_not_called()

	def test_offline_with_a_healthy_install_is_not_a_failure(self):
		seams = {'latest_version': mock.Mock(return_value=None),
				 'probe_version': mock.Mock(return_value='2.4.0')}
		self.assertEqual(self.run_upgrade([], **seams), 0)
		oc_volta.install_version.assert_not_called()


if __name__ == '__main__':
	unittest.main()
