#!/bin/bash

# CATRO SCRIPTS WRAPPER (UNIX/macOS)
# ----------------------------------
# DISCLAIMER: This script was generated with Gemini 3.

# Force UTF-8 for the child Python process, so piped or redirected output
# stays UTF-8 regardless of the caller's locale.
export PYTHONUTF8=1

# ANSI Color Codes
C_RESET='\033[0m'
C_HEADER='\033[95m'
C_CYAN='\033[96m'
C_YELLOW='\033[93m'
C_GREEN='\033[92m'
C_RED='\033[91m'
C_BOLD='\033[1m'

# Get the directory where this script is located.
# $0 may be a symlink (an `ln -s` install, a PATH shim), so walk the link
# chain before taking the directory: otherwise the scripts are looked for next
# to the link instead of next to the real file. Only plain `readlink` is used
# (no -f) and the walk is bounded, because macOS bash 3.2 and busybox readlink
# lack -f and a looping link must not hang the wrapper.
SELF="$0"
HOPS=0
while [ -L "$SELF" ] && [ "$HOPS" -lt 40 ]; do
    LINK="$(readlink "$SELF")"
    case "$LINK" in
        /*) SELF="$LINK" ;;                         # absolute target
        *) SELF="$(dirname "$SELF")/$LINK" ;;       # relative to the link
    esac
    HOPS=$((HOPS + 1))
done
SCRIPT_DIR="$(cd -P "$(dirname "$SELF")" && pwd)"
unset LINK HOPS

# Resolve the Python interpreter once instead of assuming "python3" exists.
# Prefer "python3", then fall back to "python". Used for every call below.
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Error: no Python interpreter found. Install Python 3.11+ and make sure either python3 or python is on your PATH."
    exit 127
fi

# Identify OS for tailored instructions
OS_TYPE="$(uname)"
if [ "$OS_TYPE" = "Darwin" ]; then
    OS_NAME="macOS"
    SHELL_CONFIG=".zshrc or .bash_profile"
else
    OS_NAME="Linux"
    SHELL_CONFIG=".bashrc or .zshrc"
fi

# Check if an argument was provided
if [ -z "$1" ]; then
    echo -e "${C_BOLD}${C_HEADER}============================================================${C_RESET}"
    echo -e "                ${C_BOLD}CATRO SCRIPTS SETUP & USAGE (${OS_NAME})${C_RESET}"
    echo -e "${C_BOLD}${C_HEADER}============================================================${C_RESET}"
    echo -e "${C_YELLOW}SETUP:${C_RESET}"
    echo -e "1. Ensure this folder is in your PATH."
    echo -e "   Add this to your ${C_BOLD}${SHELL_CONFIG}${C_RESET}:"
    echo -e "   ${C_CYAN}export PATH=\"\$PATH:${SCRIPT_DIR}\"${C_RESET}"
    echo -e "2. Make sure this script is executable:"
    echo -e "   ${C_CYAN}chmod +x catro-scripts.sh${C_RESET}"
    echo -e ""
    echo -e "${C_YELLOW}USAGE:${C_RESET}"
    echo -e "${C_BOLD}catro-scripts${C_RESET} [script_name] [arguments]"
    echo -e ""
    echo -e "${C_YELLOW}EXAMPLES:${C_RESET}"
    echo -e "${C_GREEN}catro-scripts randomsorter 10 5 --ext .png${C_RESET}"
    echo -e "${C_GREEN}catro-scripts list${C_RESET}"
    echo -e "${C_BOLD}${C_HEADER}============================================================${C_RESET}"

    # Use the list utility if it exists
    if [ -f "$SCRIPT_DIR/list.py" ]; then
        "$PYTHON" "$SCRIPT_DIR/list.py"
    else
        echo -e "${C_CYAN}Available scripts in folder:${C_RESET}"
        ls "$SCRIPT_DIR"/*.py 2>/dev/null | xargs -n 1 basename | sed 's/\.py$//'
    fi
    exit 0
fi

# Check for shorthand '.' to invoke the 'action' script with a 'run' command.
# The resolved path is exec'd so the shorthand still works through a symlink.
if [ "$1" = "." ]; then
    shift # remove the '.'
    exec "$SELF" action run "$@"
fi

SCRIPT_NAME="$1"
FULL_PATH="$SCRIPT_DIR/$SCRIPT_NAME.py"

# Check if the .py file exists. An exact-case match is the normal path and
# keeps its output byte-identical. Linux filesystems are case-sensitive while
# Windows is not, so a typed "List" misses list.py here; fall back to a
# case-insensitive scan of the script directory and report the real name.
# `tr` lowercases instead of bash 4's case-modification expansion, which
# macOS bash 3.2 does not support.
if [ ! -f "$FULL_PATH" ]; then
    WANT="$(printf '%s' "$SCRIPT_NAME.py" | tr '[:upper:]' '[:lower:]')"
    HITS=0
    MATCH=""
    MATCHES=""
    for CANDIDATE in "$SCRIPT_DIR"/*.py; do
        [ -f "$CANDIDATE" ] || continue
        BASE="${CANDIDATE##*/}"
        if [ "$(printf '%s' "$BASE" | tr '[:upper:]' '[:lower:]')" = "$WANT" ]; then
            HITS=$((HITS + 1))
            MATCH="$CANDIDATE"
            MATCHES="$MATCHES $BASE"
        fi
    done

    if [ "$HITS" -eq 1 ]; then
        # One case variant: run it, but say so on stderr so a script that
        # breaks under Linux's case rules is easy to spot. Scripts are named
        # without the .py suffix on the command line, so report the stem.
        MATCHED_NAME="${MATCH##*/}"
        MATCHED_NAME="${MATCHED_NAME%.py}"
        echo "note: \"$SCRIPT_NAME\" matched \"$MATCHED_NAME\"" >&2
        FULL_PATH="$MATCH"
    elif [ "$HITS" -gt 1 ]; then
        echo -e "${C_RED}Error: \"$SCRIPT_NAME.py\" matches more than one script:$MATCHES${C_RESET}" >&2
        exit 1
    else
        echo -e "${C_RED}Error: Script \"$SCRIPT_NAME.py\" not found in $SCRIPT_DIR${C_RESET}"
        exit 1
    fi
    unset WANT HITS MATCH MATCHES CANDIDATE BASE MATCHED_NAME
fi

# Shift the arguments so we can pass the rest to python
# The first argument is the script name (or '.'), so we shift it off.
shift 
 
# Run the python script with all remaining arguments.
# The python script itself is responsible for parsing its own arguments.
"$PYTHON" "$FULL_PATH" "$@"