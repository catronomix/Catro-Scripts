# Macro Action Runner and Manager
"""
                        CATRO-SCRIPTS ACTION MACRO RUNNER
                        =================================
This utility manages and executes persistent command-line macros stored in 'actions.json'.

Features:
        - Save and execute single-string commands with dynamic appended arguments.
        - Formatted ASCII box-drawing table listing all saved actions.
        - Interactive mini-TUI for adding, editing (pre-populating existing data), and deleting macros.
        - Alternating row backgrounds (Black/Dark Grey) with Light Blue text.
        - Cross-platform support (Windows, macOS, Linux).

Usage:
        python action.py                             # List all saved actions
        python action.py list                        # List all saved actions
        python action.py run <name> [extra_args...] # Run a macro with optional arguments
        catro-scripts . <name> [extra_args...]     # Shortcut to run a macro
        python action.py add [name]                  # Interactive mini-TUI to add/edit macro
        python action.py remove [name]               # Interactive mini-TUI to delete macro
"""

import os
import re
import sys
import json
import subprocess
import shlex

import tui

# Fixed table layout. The widths and the truncation rule are the ones the
# hand-built table used, so the terminal output keeps its exact shape.
COLUMN_WIDTHS = [2, 13, 30, 34]
COMMAND_WIDTH = 30
DESCRIPTION_WIDTH = 34


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_FILE = os.path.join(SCRIPT_DIR, "actions.json")

# Bootstrap actions written when actions.json does not exist yet. The tracked
# actions-template.json is the example file and must stay identical to this.
DEFAULT_ACTIONS = {
    "ping": {
        "command": "ping 127.0.0.1",
        "description": "Ping local loopback interface",
    },
    "echo-test": {
        "command": "echo Macro system operational!",
        "description": "Test command output",
    },
}


def _capabilities(cap=None):
    """The resolved capabilities, detecting once when a caller did not thread it."""
    return cap if cap is not None else tui.detect()


def warn_malformed(actions, cap=None):
    """Warns about entries that cannot be run, instead of crashing on them."""
    cap = _capabilities(cap)
    for name, details in actions.items():
        if not isinstance(details, dict):
            print(
                tui.style(f"Warning: action '{name}' is not an object with "
                          f"'command' and 'description'; it will be skipped.",
                          fg="fg-warn", cap=cap),
                file=sys.stderr,
            )
            continue
        missing = [
            key
            for key in ("command", "description")
            if not isinstance(details.get(key), str) or not details.get(key).strip()
        ]
        if missing:
            print(
                tui.style(f"Warning: action '{name}' is missing "
                          f"{', '.join(missing)}.", fg="fg-warn", cap=cap),
                file=sys.stderr,
            )


def load_actions(cap=None):
    """Loads macros from the actions.json file.

    A missing file is bootstrapped from DEFAULT_ACTIONS. A file that is not
    readable JSON, or whose top level is not an object, is a hard error: one
    clear message and exit 1, never a traceback or a silently empty menu.
    Entries missing 'command'/'description' only warn; they still list.
    """
    cap = _capabilities(cap)
    if not os.path.exists(ACTIONS_FILE):
        # Default initial template actions if file doesn't exist
        save_actions(DEFAULT_ACTIONS, cap)
        return {name: dict(details) for name, details in DEFAULT_ACTIONS.items()}

    try:
        with open(ACTIONS_FILE, "r", encoding="utf-8") as f:
            actions = json.load(f)
    except (OSError, ValueError) as e:
        print(
            tui.status("error", f"Error: cannot read '{ACTIONS_FILE}': {e}",
                       cap=cap),
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(actions, dict):
        print(
            tui.status("error",
                       f"Error: '{ACTIONS_FILE}' must contain a JSON object "
                       f"mapping action names to {{command, description}}.",
                       cap=cap),
            file=sys.stderr,
        )
        sys.exit(1)

    warn_malformed(actions, cap)
    return actions


def save_actions(actions, cap=None):
    """Saves the actions dictionary to actions.json formatted cleanly."""
    cap = _capabilities(cap)
    try:
        with open(ACTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(actions, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(tui.status("error", f"Error saving actions to file: {e}", cap=cap))
        return False


# cmd.exe syntax characters: an extra arg containing any of them must be
# wrapped in double quotes or the shell would split / re-interpret it.
# '%' is intentionally absent - cmd expands %VAR% even inside double quotes, so
# quoting cannot fix it. That is the documented Windows limitation in README.md.
_WINDOWS_SHELL_META = re.compile(r'[\s"&|<>^()!]')


def quote_extra_arg(arg):
    """Quotes one extra CLI arg so the platform shell passes it through verbatim.

    The stored macro base string is never touched: it deliberately keeps its own
    shell syntax. Only the args appended by the caller are quoted.
    """
    if os.name == "nt":
        if not arg:
            return '""'
        if not _WINDOWS_SHELL_META.search(arg):
            return arg
        # Escape like subprocess.list2cmdline: a run of backslashes is literal
        # unless it precedes a double quote. Before a quote emit 2n+1
        # backslashes (n literal + the quote's escape), and double the trailing
        # run so the closing quote is not swallowed. Doubling quotes instead
        # would hand the child a literal quote char and lose trailing
        # backslashes - see tests/test_action_args.py.
        out = []
        backslashes = 0
        for char in arg:
            if char == "\\":
                backslashes += 1
                continue
            if char == '"':
                out.append("\\" * (backslashes * 2 + 1) + '"')
            else:
                out.append("\\" * backslashes + char)
            backslashes = 0
        return '"' + "".join(out) + "\\" * (backslashes * 2) + '"'
    return shlex.quote(arg)


def run_action(action_name, extra_args, cap=None):
    """Looks up and executes a macro command string with extra CLI args appended."""
    cap = _capabilities(cap)
    actions = load_actions(cap)

    if action_name not in actions:
        print(
            tui.status("error",
                       f"Error: Action '{action_name}' not found in actions.json.",
                       cap=cap)
        )
        print(
            "Use {} to view available macros.".format(
                tui.style("python action.py list", fg="border-fg", cap=cap))
        )
        sys.exit(1)

    entry = actions.get(action_name)
    base_command = entry.get("command") if isinstance(entry, dict) else None
    if not isinstance(base_command, str) or not base_command.strip():
        print(
            tui.status("error", f"Error: Action '{action_name}' has no command.",
                       cap=cap)
            + " Fix it with "
            + tui.style(f"python action.py add {action_name}", fg="border-fg", cap=cap)
            + "."
        )
        sys.exit(1)
    base_command = base_command.strip()

    # Append extra CLI args passed during invocation. Every arg is quoted for
    # the platform shell: shell metacharacters, spaces and globs inside an arg
    # must reach the child as one literal argument, never as new syntax.
    if extra_args:
        formatted_args = " ".join(quote_extra_arg(arg) for arg in extra_args)
        full_command = f"{base_command} {formatted_args}"
    else:
        full_command = base_command

    print()
    print(tui.header(f"--- EXECUTING MACRO: {action_name} ---", cap=cap))
    # The command line stays a `key value` sentence on a pipe (its bytes are
    # pinned by test_action_args); a terminal gets the chrome field.
    if cap.plain:
        print("Command: {}\n".format(full_command))
    else:
        print(tui.field("Command:", full_command, cap=cap))
        print()

    try:
        # Run the command in the active shell environment
        result = subprocess.run(full_command, shell=True)
        print()
        print(tui.status(
            "ok" if result.returncode == 0 else "error",
            "Macro finished (exit code {}).".format(result.returncode),
            cap=cap))
        print()
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print()
        print(tui.status("warn", "Macro execution interrupted by user", cap=cap))
        sys.exit(130)
    except Exception as e:
        print(tui.status("error", f"Execution error: {e}", cap=cap))
        sys.exit(1)


def list_actions(cap=None):
    """Displays all saved macros in the house table."""
    cap = _capabilities(cap)
    actions = load_actions(cap)

    print()
    print(tui.header("--- ACTION MACRO DIRECTORY SCAN ---",
                     "Storage File: " + ACTIONS_FILE, cap=cap))
    print()

    if not actions:
        print(tui.status("warn", "No actions currently stored in actions.json.",
                         cap=cap))
        print("Run {} to create your first macro.\n".format(
            tui.style("python action.py add", fg="fg", cap=cap)))
        return

    rows = []
    for i, (name, details) in enumerate(actions.items(), 1):
        # A malformed entry still lists; load_actions() already warned about it.
        entry = details if isinstance(details, dict) else {}
        cmd = entry.get("command", "") or ""
        desc = entry.get("description", "") or "No description"

        # Truncate long strings for tabular layout. This is the table's own
        # rule, so the renderer must not truncate the cells a second time.
        cmd_disp = (cmd[: COMMAND_WIDTH - 2] + "..") if len(cmd) > COMMAND_WIDTH else cmd
        desc_disp = ((desc[: DESCRIPTION_WIDTH - 2] + "..")
                     if len(desc) > DESCRIPTION_WIDTH else desc)

        rows.append((i, name, cmd_disp, desc_disp))

    tui.print_table(["ID", "Action Name", "Command", "Description"], rows,
                    widths=COLUMN_WIDTHS, truncate=False, cap=cap)
    print(tui.section("Total macros saved: {}".format(len(actions)), cap=cap))
    print()


def prompt_input_with_default(prompt_str, default_value="", cap=None):
    """Helper for mini-TUI to allow editing existing values or keeping default.

    Deliberately not tui.ask_text(): the readline branch pre-fills the editing
    buffer with the current value, and ask_text has no equivalent, so replacing
    it would change what an operator sees and can edit.
    """
    cap = _capabilities(cap)
    if default_value:
        # Try using GNU readline if available for pre-filled buffer on Linux/macOS
        try:
            import readline

            readline.set_startup_hook(lambda: readline.insert_text(default_value))
            try:
                return input(prompt_str).strip()
            finally:
                readline.set_startup_hook()
        except ImportError:
            # Fallback prompt showing current value for Windows/systems without readline
            disp_prompt = "{} [{}]: ".format(
                prompt_str, tui.style(default_value, fg="fg-warn", cap=cap))
            val = input(disp_prompt).strip()
            return val if val else default_value
    else:
        return input(prompt_str).strip()


def interactive_add(target_name=None, cap=None):
    """Mini-TUI interface to add a new action or edit an existing one."""
    cap = _capabilities(cap)
    actions = load_actions(cap)

    print()
    print(tui.header("=== ACTION MACRO MANAGER: ADD / EDIT ===", cap=cap))

    # Determine action name
    if not target_name:
        target_name = input(
            tui.style("Enter action name (ID key): ", fg="fg", cap=cap)
        ).strip()

    if not target_name:
        print(tui.status("error", "Action name cannot be empty. Cancelled.",
                         cap=cap))
        print()
        return

    is_edit = target_name in actions
    existing = actions.get(target_name) if is_edit else {}
    existing = existing if isinstance(existing, dict) else {}
    existing_cmd = existing.get("command", "") or ""
    existing_desc = existing.get("description", "") or ""

    if is_edit:
        print(tui.status(
            "warn",
            f"Editing existing macro '{target_name}'... "
            f"(Press Enter to keep current values)", cap=cap))
    else:
        print(tui.status("ok", f"Creating new macro '{target_name}'...", cap=cap))

    # Command input
    print()
    print(tui.section("Executable Command String:", cap=cap))
    cmd = prompt_input_with_default(
        tui.style("Command > ", fg="fg", cap=cap), existing_cmd, cap
    )

    if not cmd:
        print(tui.status("error", "Command string cannot be empty. Cancelled.",
                         cap=cap))
        print()
        return

    # Description input
    print()
    print(tui.section("Description:", cap=cap))
    desc = prompt_input_with_default(
        tui.style("Description > ", fg="fg", cap=cap), existing_desc, cap
    )

    # Save updated action
    actions[target_name] = {
        "command": cmd,
        "description": desc or "No description provided",
    }

    if save_actions(actions, cap):
        state = "updated" if is_edit else "added"
        print()
        print(tui.panel("ACTION SAVED", [
            "Name:        {} ({})".format(target_name, state),
            "Command:     {}".format(cmd),
            "Description: {}".format(actions[target_name]["description"]),
        ], cap=cap))
        print()


def interactive_remove(target_name=None, cap=None):
    """Mini-TUI interface to delete an existing action."""
    cap = _capabilities(cap)
    actions = load_actions(cap)

    if not actions:
        print(tui.status("error", "No actions available to remove.", cap=cap))
        print()
        return

    print()
    print(tui.header("=== ACTION MACRO MANAGER: REMOVE ===", cap=cap))

    if not target_name:
        list_actions(cap)
        target_name = input(
            tui.style("Enter action name to delete (or 'q' to cancel): ",
                      fg="fg", cap=cap)
        ).strip()

    if target_name.lower() == "q" or not target_name:
        print("Operation cancelled.")
        return

    if target_name not in actions:
        print(tui.status("error", f"Action '{target_name}' does not exist.",
                         cap=cap))
        print()
        return

    confirm = (
        input(
            tui.style(f"Are you sure you want to delete '{target_name}'? (y/N): ",
                      fg="fg-warn", cap=cap)
        )
        .strip()
        .lower()
    )

    if confirm == "y":
        del actions[target_name]
        if save_actions(actions):
            print()
            print(tui.panel("ACTION DELETED",
                            ["Name:    {}".format(target_name),
                             "Storage: {}".format(ACTIONS_FILE)], cap=cap))
            print()
    else:
        print("Cancelled deletion.")


def main():
    args = sys.argv[1:]
    cap = tui.detect()

    # Handle redundant 'action' prefix when invoked via wrapper (e.g. `catro-scripts action <macro>`)
    actions = load_actions(cap)
    if args and args[0].lower() == "action" and args[0] not in actions:
        args = args[1:]

    if not args or args[0] in ["list", "--help", "-h"]:
        list_actions(cap)
        return

    subcommand = args[0].lower()

    if subcommand == "add":
        target = args[1] if len(args) > 1 else None
        interactive_add(target, cap)
    elif subcommand in ["remove", "rm", "delete"]:
        target = args[1] if len(args) > 1 else None
        interactive_remove(target, cap)
    elif subcommand == "run":
        if len(args) < 2:
            print(tui.status(
                "error",
                "Usage: python action.py run <action_name> [optional flags/args]",
                cap=cap))
            sys.exit(1)
        action_name = args[1]
        extra_args = args[2:]
        run_action(action_name, extra_args, cap)
    else:
        # Direct shortcut execution: python action.py <action_name> [extra args...]
        action_name = args[0]
        extra_args = args[1:]
        run_action(action_name, extra_args, cap)


if __name__ == "__main__":
    try:
        main()
        sys.stdout.flush()
    except BrokenPipeError:
        # Downstream reader closed the pipe; exit quietly and point stdout at
        # devnull so the interpreter's shutdown flush cannot raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
