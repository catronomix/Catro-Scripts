"""Host-only checks that the container wrapper carries this project's settings.

No docker, no network, no git: the wrapper is loaded from its path and only its
project defaults, its config layering and its argv mapping are asserted.

The module skips when the dev-team skill is not installed (`DEVTEAM_TOOLS`, else
`~/.config/opencode/skills/dev-team/tools`); the container image has neither, so
it skips there.

Run with:
    python -m unittest discover -s tests -v
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WRAPPER = os.path.join(HERE, "container", "dev.py")


def skill_tools():
    """The shared tool's directory, or None when the skill is not installed."""
    candidates = []
    env = os.environ.get("DEVTEAM_TOOLS")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(
        os.path.expanduser("~"), ".config", "opencode", "skills", "dev-team",
        "tools"))
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, "devcontainer.py")):
            return os.path.abspath(path)
    return None


TOOLS = skill_tools()
if TOOLS is None:
    raise unittest.SkipTest("dev-team skill not installed; skipped on hosts "
                            "without it (e.g. inside the CI image)")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import devcontainer as shared  # noqa: E402 - resolved from the skill install

_spec = importlib.util.spec_from_file_location("catro_container_dev", WRAPPER)
dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev)


class ProjectTest(unittest.TestCase):
    def test_project_matches_the_wrapper_contract(self):
        self.assertEqual(dev.PROJECT, {
            "dockerfile": "tests/container/Dockerfile",
            "dev_target": "dev",
            "ci_target": "test",
            "python": "3.12",
            "image_prefix": "catro-scripts-dev",
            "name_prefix": "catro-dev",
            "label_prefix": "catro.dev",
            "user": "host",
            "entrypoints": {"catro-scripts": "/work/catro-scripts.sh"},
            "extras": ["pillow", "piexif", "pydub"],
            "ci_command": "",
            "cli_hint": "python tests/container/dev.py",
        })


class DefaultsTest(unittest.TestCase):
    def test_no_devteam_dir_still_has_project_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(os.path.exists(os.path.join(root, ".devteam")))
            cfg = shared.load_config(root, defaults=dev.project_defaults(shared))
            self.assertEqual(cfg.python, "3.12")
            self.assertEqual(cfg.name_prefix, "catro-dev")
            self.assertEqual(cfg.label_prefix, "catro.dev")
            self.assertEqual(cfg.entrypoints,
                             {"catro-scripts": "/work/catro-scripts.sh"})
            self.assertEqual(shared.image_tag(cfg, "3.12", cfg.extras),
                             "catro-scripts-dev:3.12")
            self.assertTrue(
                shared.container_name(root, cfg).startswith("catro-dev-"))

    def test_a_local_config_file_still_wins(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, ".devteam", "config.json")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"container": {"python": "3.11"}}, handle)
            cfg = shared.load_config(root, defaults=dev.project_defaults(shared))
        self.assertEqual(cfg.python, "3.11")
        self.assertEqual(cfg.name_prefix, "catro-dev")


class SharedArgvTest(unittest.TestCase):
    def shared_argv(self, argv):
        return dev.shared_argv(dev.build_parser().parse_args(argv))

    def test_flags_and_commands_pass_through(self):
        cases = [
            ["up", "--build", "--no-extras"],
            ["run", "--", "python", "-V"],
            ["run", "--python", "3.11", "--", "x"],
        ]
        for argv in cases:
            self.assertEqual(self.shared_argv(argv), argv)


if __name__ == "__main__":
    unittest.main()
