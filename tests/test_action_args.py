# Regression tests for action.py extra-argument quoting
"""
                            ACTION ARG QUOTING TESTS
                            ========================
Issue #16: run_action() builds one shell string from the stored macro plus the
extra argv. Previously only args containing a space were quoted, so `a;echo`,
`$HOME`, `*.md` and `$(pwd)` reached the shell raw and were re-parsed.

These tests drive the real code path in a child process with ACTIONS_FILE
pointed at a throwaway file, so the repository's own actions.json is never read,
created or modified.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "action.py"

# True when the repo already ships actions.json - the tests must not change it.
ACTIONS_PRESENT = (REPO / "actions.json").exists()

# Runs action.py's main() against a caller-supplied ACTIONS_FILE.
# argv: <repo> <actions.json> <macro name> [extra args...]
DRIVER = """
import sys
sys.path.insert(0, sys.argv[1])
import action
action.ACTIONS_FILE = sys.argv[2]
sys.argv = ["action.py", "run", sys.argv[3], *sys.argv[4:]]
action.main()
"""

# Child macro body: echoes its own argv as JSON, or exits with a given code.
DUMP = """
import json
import sys
if "--exit" in sys.argv[1:]:
    sys.exit(int(sys.argv[sys.argv.index("--exit") + 1]))
print("ARGV=" + json.dumps(sys.argv[1:]))
"""

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Every one of these must arrive as exactly ONE literal argv element.
HOSTILE_ARGS = [
    "a b",
    "a;echo INJECTED",
    "a&echo INJECTED",
    "a|echo INJECTED",
    "$HOME",
    "$(pwd)",
    "`echo INJECTED`",
    "*.md",
]


class ActionArgQuotingTests(unittest.TestCase):
    """Issue #16: extra args must never be re-parsed by the platform shell."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.actions_file = self.tmp / "actions.json"
        self.dump = self.tmp / "dump_argv.py"
        self.dump.write_text(DUMP, encoding="utf-8")
        # A file that would satisfy the `*.md` glob if the arg were unquoted.
        (self.tmp / "marker.md").write_text("globbed\n", encoding="utf-8")
        self.base = f'"{sys.executable}" "{self.dump}"'
        self.actions_file.write_text(
            json.dumps(
                {
                    "dump": {"command": self.base, "description": "argv echo"},
                    "rc": {"command": f"{self.base} --exit 3", "description": "exit 3"},
                }
            ),
            encoding="utf-8",
        )

    def run_macro(self, name, extra_args):
        """Runs the macro through action.py's main() in a child process."""
        return subprocess.run(
            [sys.executable, "-c", DRIVER, str(REPO), str(self.actions_file), name]
            + list(extra_args),
            cwd=str(self.tmp),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )

    def argv_lines(self, stdout):
        """Returns the parsed ARGV= payloads printed by the child macro."""
        return [
            json.loads(line[len("ARGV=") :])
            for line in stdout.splitlines()
            if line.startswith("ARGV=")
        ]

    def test_each_hostile_arg_is_one_literal_element(self):
        """Metacharacters, spaces and globs stay inside a single argv entry."""
        for arg in HOSTILE_ARGS:
            with self.subTest(arg=arg):
                proc = self.run_macro("dump", [arg])
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(self.argv_lines(proc.stdout), [[arg]])
                self.assertNotIn(
                    "\nINJECTED", proc.stdout, "a second command was executed"
                )

    def test_mixed_args_keep_order_and_count(self):
        """A hostile arg never perturbs its neighbours."""
        args = ["one", "a b", "two;echo INJECTED", "three"]
        proc = self.run_macro("dump", args)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.argv_lines(proc.stdout), [args])

    def test_no_extra_args_leaves_command_string_untouched(self):
        """The stored macro is executed byte-identical when nothing is appended."""
        proc = self.run_macro("dump", [])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        command_lines = [
            ANSI.sub("", line)
            for line in proc.stdout.splitlines()
            if ANSI.sub("", line).startswith("Command:")
        ]
        self.assertEqual(command_lines, [f"Command: {self.base}"])

    def test_exit_code_propagates(self):
        """The child macro's exit code is still the process exit code."""
        proc = self.run_macro("rc", [])
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)

    def test_repo_actions_file_is_untouched(self):
        """The tests never create or modify the repository's actions.json."""
        self.run_macro("dump", ["a b"])
        self.assertEqual((REPO / "actions.json").exists(), ACTIONS_PRESENT)


if __name__ == "__main__":
    unittest.main()
