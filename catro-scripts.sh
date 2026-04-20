#!/bin/bash

# CATRO SCRIPTS WRAPPER (UNIX/macOS)
# ----------------------------------
# DISCLAIMER: This script was generated with Gemini 3.

# ANSI Color Codes
C_RESET='\033[0m'
C_HEADER='\033[95m'
C_CYAN='\033[96m'
C_YELLOW='\033[93m'
C_GREEN='\033[92m'
C_RED='\033[91m'
C_BOLD='\033[1m'

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
        python3 "$SCRIPT_DIR/list.py"
    else
        echo -e "${C_CYAN}Available scripts in folder:${C_RESET}"
        ls "$SCRIPT_DIR"/*.py 2>/dev/null | xargs -n 1 basename | sed 's/\.py$//'
    fi
    exit 0
fi

SCRIPT_NAME="$1"
FULL_PATH="$SCRIPT_DIR/$SCRIPT_NAME.py"

# Check if the .py file exists
if [ ! -f "$FULL_PATH" ]; then
    echo -e "${C_RED}Error: Script \"$SCRIPT_NAME.py\" not found in $SCRIPT_DIR${C_RESET}"
    exit 1
fi

# Shift the arguments so we can pass the rest to python
shift

# Run the python script with all remaining arguments
python3 "$FULL_PATH" "$@"