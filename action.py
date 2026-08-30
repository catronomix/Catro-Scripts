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
import sys
import json
import subprocess
import shlex

# Enable ANSI colors on Windows consoles
if os.name == "nt":
    os.system("")


# ANSI Color Codes (TrueColor support matching catro-scripts palette)
class Colors:
    PURPLE = "\033[38;2;170;0;255m"
    LIGHT_BLUE = "\033[38;2;173;216;230m"  # Light Blue foreground
    GREEN = "\033[38;2;80;250;123m"  # Accent Green
    RED = "\033[38;2;255;85;85m"  # Accent Red
    YELLOW = "\033[38;2;241;250;140m"  # Accent Yellow
    BG_BLACK = "\033[48;2;0;0;0m"  # Black background
    BG_GREY = "\033[48;2;45;45;45m"  # Dark Grey background
    BOLD = "\033[1m"
    END = "\033[0m"


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_FILE = os.path.join(SCRIPT_DIR, "actions.json")


def load_actions():
    """Loads macros from the actions.json file."""
    if not os.path.exists(ACTIONS_FILE):
        # Default initial template actions if file doesn't exist
        default_actions = {
            "ping": {
                "command": "ping 127.0.0.1",
                "description": "Ping local loopback interface",
            },
            "echo-test": {
                "command": "echo Macro system operational!",
                "description": "Test command output",
            },
        }
        save_actions(default_actions)
        return default_actions

    try:
        with open(ACTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"{Colors.RED}Error loading '{ACTIONS_FILE}': {e}{Colors.END}")
        return {}


def save_actions(actions):
    """Saves the actions dictionary to actions.json formatted cleanly."""
    try:
        with open(ACTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(actions, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"{Colors.RED}Error saving actions to file: {e}{Colors.END}")
        return False


def run_action(action_name, extra_args):
    """Looks up and executes a macro command string with extra CLI args appended."""
    actions = load_actions()

    if action_name not in actions:
        print(
            f"{Colors.RED}Error: Action '{action_name}' not found in actions.json.{Colors.END}"
        )
        print(
            f"Use {Colors.PURPLE}python action.py list{Colors.END} to view available macros."
        )
        sys.exit(1)

    base_command = actions[action_name]["command"].strip()

    # Append extra CLI args passed during invocation
    if extra_args:
        formatted_args = " ".join(
            [shlex.quote(arg) if " " in arg else arg for arg in extra_args]
        )
        full_command = f"{base_command} {formatted_args}"
    else:
        full_command = base_command

    print(
        f"\n{Colors.PURPLE}{Colors.BOLD}--- EXECUTING MACRO: {action_name} ---{Colors.END}"
    )
    print(f"{Colors.LIGHT_BLUE}Command:{Colors.END} {full_command}\n")

    try:
        # Run the command in the active shell environment
        result = subprocess.run(full_command, shell=True)
        print(
            f"\n{Colors.PURPLE}--- MACRO FINISHED (Exit Code: {result.returncode}) ---{Colors.END}\n"
        )
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[Macro execution interrupted by user]{Colors.END}")
        sys.exit(130)
    except Exception as e:
        print(f"{Colors.RED}Execution error: {e}{Colors.END}")
        sys.exit(1)


def list_actions():
    """Displays all saved macros in a catro-scripts styled ASCII box table."""
    actions = load_actions()

    print(
        f"\n{Colors.PURPLE}{Colors.BOLD}--- ACTION MACRO DIRECTORY SCAN ---{Colors.END}"
    )
    print(f"{Colors.PURPLE}Storage File:{Colors.END} {ACTIONS_FILE}\n")

    if not actions:
        print(
            f"{Colors.PURPLE}No actions currently stored in actions.json.{Colors.END}"
        )
        print(
            f"Run {Colors.LIGHT_BLUE}python action.py add{Colors.END} to create your first macro.\n"
        )
        return

    # Column widths
    w_id = 4
    w_name = 18
    w_cmd = 35
    w_desc = 35

    # Box Drawing Characters
    tl, tr, bl, br = "┌", "┐", "└", "┘"
    h, v = "─", "│"
    t_join, b_join, l_join, r_join, cross = "┬", "┴", "├", "┤", "┼"

    def make_divider(left, mid, right, cross_char):
        return (
            f"{Colors.PURPLE}{left}{h * (w_id + 2)}{cross_char}{h * (w_name + 2)}{cross_char}"
            f"{h * (w_cmd + 2)}{cross_char}{h * (w_desc + 2)}{right}{Colors.END}"
        )

    top_border = make_divider(tl, t_join, tr, t_join)
    mid_border = make_divider(l_join, cross, r_join, cross)
    bot_border = make_divider(bl, b_join, br, b_join)

    print(top_border)
    header = (
        f"{Colors.PURPLE}{v}{Colors.BOLD} {'ID':<{w_id}} {v} {'Action Name':<{w_name}} {v} "
        f"{'Command':<{w_cmd}} {v} {'Description':<{w_desc}} {v}{Colors.END}"
    )
    print(header)
    print(mid_border)

    for i, (name, details) in enumerate(actions.items(), 1):
        cmd = details.get("command", "")
        desc = details.get("description", "No description")

        # Truncate long strings for tabular layout
        cmd_disp = (cmd[: w_cmd - 2] + "..") if len(cmd) > w_cmd else cmd
        desc_disp = (desc[: w_desc - 2] + "..") if len(desc) > w_desc else desc

        bg = Colors.BG_BLACK if i % 2 != 0 else Colors.BG_GREY
        row_style = Colors.LIGHT_BLUE + bg

        row = (
            f"{Colors.PURPLE}{v}{row_style} {i:<{w_id}} {Colors.PURPLE}{v}{row_style} {name:<{w_name}} "
            f"{Colors.PURPLE}{v}{row_style} {cmd_disp:<{w_cmd}} {Colors.PURPLE}{v}{row_style} {desc_disp:<{w_desc}} "
            f"{Colors.END}{Colors.PURPLE}{v}{Colors.END}"
        )
        print(row)

    print(bot_border)
    print(
        f"{Colors.PURPLE}{Colors.BOLD}Total macros saved:{Colors.END} {len(actions)}\n"
    )


def prompt_input_with_default(prompt_str, default_value=""):
    """Helper for mini-TUI to allow editing existing values or keeping default."""
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
            disp_prompt = f"{prompt_str} [{Colors.YELLOW}{default_value}{Colors.END}]: "
            val = input(disp_prompt).strip()
            return val if val else default_value
    else:
        return input(prompt_str).strip()


def interactive_add(target_name=None):
    """Mini-TUI interface to add a new action or edit an existing one."""
    actions = load_actions()

    print(
        f"\n{Colors.PURPLE}{Colors.BOLD}=== ACTION MACRO MANAGER: ADD / EDIT ==={Colors.END}"
    )

    # Determine action name
    if not target_name:
        target_name = input(
            f"{Colors.LIGHT_BLUE}Enter action name (ID key): {Colors.END}"
        ).strip()

    if not target_name:
        print(f"{Colors.RED}Action name cannot be empty. Cancelled.{Colors.END}\n")
        return

    is_edit = target_name in actions
    existing_cmd = actions[target_name]["command"] if is_edit else ""
    existing_desc = actions[target_name]["description"] if is_edit else ""

    if is_edit:
        print(
            f"{Colors.YELLOW}Editing existing macro '{target_name}'... (Press Enter to keep current values){Colors.END}"
        )
    else:
        print(f"{Colors.GREEN}Creating new macro '{target_name}'...{Colors.END}")

    # Command input
    print(f"\n{Colors.PURPLE}Executable Command String:{Colors.END}")
    cmd = prompt_input_with_default(
        f"{Colors.LIGHT_BLUE}Command > {Colors.END}", existing_cmd
    )

    if not cmd:
        print(f"{Colors.RED}Command string cannot be empty. Cancelled.{Colors.END}\n")
        return

    # Description input
    print(f"\n{Colors.PURPLE}Description:{Colors.END}")
    desc = prompt_input_with_default(
        f"{Colors.LIGHT_BLUE}Description > {Colors.END}", existing_desc
    )

    # Save updated action
    actions[target_name] = {
        "command": cmd,
        "description": desc or "No description provided",
    }

    if save_actions(actions):
        status = "updated" if is_edit else "added"
        print(
            f"\n{Colors.GREEN}[Success] Action '{target_name}' successfully {status}!{Colors.END}\n"
        )


def interactive_remove(target_name=None):
    """Mini-TUI interface to delete an existing action."""
    actions = load_actions()

    if not actions:
        print(f"{Colors.RED}No actions available to remove.{Colors.END}\n")
        return

    print(
        f"\n{Colors.PURPLE}{Colors.BOLD}=== ACTION MACRO MANAGER: REMOVE ==={Colors.END}"
    )

    if not target_name:
        list_actions()
        target_name = input(
            f"{Colors.LIGHT_BLUE}Enter action name to delete (or 'q' to cancel): {Colors.END}"
        ).strip()

    if target_name.lower() == "q" or not target_name:
        print("Operation cancelled.")
        return

    if target_name not in actions:
        print(f"{Colors.RED}Action '{target_name}' does not exist.{Colors.END}\n")
        return

    confirm = (
        input(
            f"{Colors.YELLOW}Are you sure you want to delete '{target_name}'? (y/N): {Colors.END}"
        )
        .strip()
        .lower()
    )

    if confirm == "y":
        del actions[target_name]
        if save_actions(actions):
            print(
                f"\n{Colors.GREEN}[Success] Action '{target_name}' has been deleted.{Colors.END}\n"
            )
    else:
        print("Cancelled deletion.")


def main():
    args = sys.argv[1:]

    # Handle redundant 'action' prefix when invoked via wrapper (e.g. `catro-scripts action <macro>`)
    actions = load_actions()
    if args and args[0].lower() == "action" and args[0] not in actions:
        args = args[1:]

    if not args or args[0] in ["list", "--help", "-h"]:
        list_actions()
        return

    subcommand = args[0].lower()

    if subcommand == "add":
        target = args[1] if len(args) > 1 else None
        interactive_add(target)
    elif subcommand in ["remove", "rm", "delete"]:
        target = args[1] if len(args) > 1 else None
        interactive_remove(target)
    elif subcommand == "run":
        if len(args) < 2:
            print(
                f"{Colors.RED}Usage: python action.py run <action_name> [optional flags/args]{Colors.END}"
            )
            sys.exit(1)
        action_name = args[1]
        extra_args = args[2:]
        run_action(action_name, extra_args)
    else:
        # Direct shortcut execution: python action.py <action_name> [extra args...]
        action_name = args[0]
        extra_args = args[1:]
        run_action(action_name, extra_args)


if __name__ == "__main__":
    main()
