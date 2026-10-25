"""Thin wrapper: the capability lives in the dev-team skill (tools/devcontainer.py).

The CLI and the output shape are unchanged: `up`, `shell` (`sh`), `run`,
`down`, `status`, `ci`, `--python`, `--cwd`, `--build`, `--no-extras`. `ci` is a
pass-through to the shared tool (it is not a dev-container command, but keeping
it here means one entrypoint per project); it exits with the image's exit code.
Mount detection, container naming, labels, safety flags, image tags and the
docker calls all come from the shared tool; this file only supplies the arg
parsing and a fallback copy of this project's settings.

`.devteam/config.json` is tracked on purpose (the one file in `.devteam/` that
is), so a clone carries the `container` settings. `PROJECT` below repeats them
and is used only when that file is missing; CLI flags override both.

The skill is found in this order:

1. ``DEVTEAM_TOOLS`` - an absolute path to the skill's ``tools/`` directory;
2. ``~/.config/opencode/skills/dev-team/tools`` - the default install.

Stdlib only; runs wherever the agent shell runs (Windows PowerShell, POSIX).
"""

import argparse
import os
import sys


# Mirror of the `container` block in the tracked `.devteam/config.json`, used
# only when that file is absent (a CI image that excludes `.devteam/`, or a
# hand-copied tree). Keep the two in sync.
PROJECT = {
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
}


def skill_tools():
    """Directory containing devcontainer.py, or exit 2 with the fix."""
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
    sys.stderr.write("dev.py: dev-team skill not found; set DEVTEAM_TOOLS to "
                     "<skill>/tools\n")
    raise SystemExit(2)


def load_shared():
    tools = skill_tools()
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import devcontainer  # noqa: E402 - resolved at runtime, not installed
    return devcontainer


def project_defaults(shared):
    """This project's settings as a Config the shared tool layers under."""
    return shared.Config(**PROJECT)


def shared_argv(args):
    """The shared tool's argv for this subcommand, flags before the command."""
    argv = [args.command]
    if args.python is not None:
        argv += ["--python", args.python]
    if getattr(args, "cwd", None):
        argv += ["--cwd", args.cwd]
    if getattr(args, "build", False):
        argv.append("--build")
    if getattr(args, "no_extras", False):
        argv.append("--no-extras")
    if args.command == "down" and args.all:
        argv.append("--all")
    if args.command in ("run", "ci"):
        cmd = list(args.cmd)
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        argv += ["--"] + cmd
    return argv


def build_parser():
    """The same CLI as before; `--python` defaults to None so PROJECT decides."""
    ap = argparse.ArgumentParser(
        description="Interactive Linux dev container for catro-scripts",
        epilog="Run from the checkout or worktree you want mounted.")
    sub = ap.add_subparsers(dest="command")

    def common_flags(p):
        p.add_argument("--python", default=None,
                       help="interpreter version for the dev image (default: 3.12)")
        p.add_argument("--cwd", default=None,
                       help="detect the mount root here instead of the current cwd")

    p = sub.add_parser("up", help="build if needed and start the container")
    common_flags(p)
    p.add_argument("--build", action="store_true", help="rebuild the image first")
    p.add_argument("--no-extras", action="store_true",
                   help="stdlib-only image (no pillow/piexif/pydub)")

    p = sub.add_parser("shell", aliases=["sh"],
                       help="interactive bash in the container")
    common_flags(p)

    p = sub.add_parser("run", help="run one command, propagate its exit code")
    common_flags(p)
    p.add_argument("cmd", nargs=argparse.REMAINDER,
                   help="command; use `run -- <cmd>` so flags are not parsed here")

    p = sub.add_parser("down", help="stop and remove the container")
    common_flags(p)
    p.add_argument("--all", action="store_true",
                   help="remove every dev container of this repo (all worktrees)")

    p = sub.add_parser("status", help="list this repo's dev containers")
    common_flags(p)

    p = sub.add_parser("ci", help="build and run the CI image, propagate its exit code")
    p.add_argument("--python", default=None,
                   help="interpreter version for the CI image (default: 3.12)")
    p.add_argument("--build", action="store_true", help="rebuild the image first")
    p.add_argument("--no-extras", action="store_true",
                   help="stdlib-only image (no pillow/piexif/pydub)")
    p.add_argument("cmd", nargs=argparse.REMAINDER,
                   help="command; default: the image's own entrypoint")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help()
        return 0
    shared = load_shared()
    return shared.main(shared_argv(args), defaults=project_defaults(shared))


if __name__ == "__main__":
    sys.exit(main())
