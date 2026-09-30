# AGENTS.md

This document provides instructions for AI agents working on the `catro-scripts` repository.

## Project Overview
`catro-scripts` is a cross-platform command-line tool wrapper that allows execution of various helper scripts from any location using the syntax: `catro-scripts <scriptname> <args>`.

## Core Components
- **Entrypoints**: The system is triggered via `catro-scripts.bat` (Windows) and `catro-scripts.sh` (Unix/macOS). These should be maintained for seamless cross-platform execution.
  - The system relies on thin wrappers to bridge the OS environment to the Python toolset.
  - **Windows (`catro-scripts.bat`)**: Uses `cmd.exe` batch syntax. Leverages `setlocal enabledelayedexpansion` and ANSI escape sequences. Sets `SCRIPT_DIR` to `%~dp0`, validates the existence of the requested Python file, and pipes execution to `python`. Supports `catro-scripts .` to invoke `action.py`.
  - **Unix/macOS (`catro-scripts.sh`)**: Uses Bash. Defines global ANSI variables. Detects `Darwin` (macOS) vs. `Linux` to provide accurate configuration instructions. Sets `SCRIPT_DIR` using `dirname`, validates existence, and uses `exec` to pass control to `python3`.
- **Screensaver**: This is a specialized module acting as a "wrapper-within-a-wrapper." Ensure any changes to the screensaver logic respect the recursive nature of its execution.
  - The screensaver system functions as a recursive wrapper:
    1. `screensaver.py` acts as the entrypoint for all `.screensaver` files.
    2. It parses the target file, which contains custom logic or configuration.
    3. The wrapper handles the lifecycle (start, run, stop) and standardizes display interactions.
  - **Rule**: Never modify core screensaver loop logic without ensuring backward compatibility for existing `.screensaver` files.

## Coding Standards & Conventions
- **House Style**: Scripts should utilize full-color text output (where applicable), clean terminal layouts, and structured tables for data representation.
  - To ensure a consistent user experience, all scripts must follow the visual identity defined in `list.py`.
  - **ANSI Color Palette**: Avoid hardcoding raw escape codes in every script. Standardize on the `Colors` class approach seen in `list.py`:
    ```python
    class Colors:
        PURPLE = '\033[38;2;170;0;255m'
        LIGHT_BLUE = '\033[38;2;173;216;230m'
        BG_BLACK = '\033[48;2;0;0;0m'
        BG_GREY = '\033[48;2;45;45;45m'
        BOLD = '\033[1m'
        END = '\033[0m'
    ```
  - **Visual Layout**:
    - **Tables**: Use Unicode box-drawing characters (`┌`, `─`, `┐`, `│`, etc.) for all data-heavy displays.
    - **Consistency**: Maintain a header/footer structure similar to `list.py`.
    - **Windows Compatibility**: When using colors in Python, ensure the console is initialized for ANSI:
      ```python
      if os.name == 'nt':
          os.system('')
      ```
- **Documentation**: 
  - Every script must have a clear title and a docstring using specific tab spacing for readability.
  - **Headers**: Every script must start with a descriptive comment title, followed by a Python docstring.
  - **Tabs/Spacing**: The docstring must use hard tabs for indentation as demonstrated in existing scripts to ensure proper alignment.
  - **Commenting**: Explain *logic flow* (how input translates to action), not *syntax*. Comment your code thoroughly to explain logic flows, especially within wrappers.
- **Dependency Management**: 
  - Minimize the introduction of new external dependencies.
  - **Strictly No External Deps**: If a library is not part of the standard Python library, justify its inclusion.
  - **Leverage Existing**: Use `os`, `sys`, `subprocess`, and `argparse` first. Prioritize leveraging libraries already present in the environment/repo before adding new ones.
  - **Setup**: If a script *requires* custom dependencies, include a `ts_setup.py` or logic in `installdeps.py`.
  - Keep the environment lightweight.

## Maintenance
- **README.md**: Whenever you add a new script or modify the core functionality, you are responsible for updating the `README.md` to reflect these changes.
- **Code Modification**: When suggesting or applying changes, use the provided toolset to ensure minimal, surgical edits. Use the "Apply" button or switch to Agent Mode for automatic updates.

## Workflow
1. Analyze the existing `catro-scripts` implementation before creating new scripts.
2. Adhere to the established command-line argument patterns.
3. Ensure cross-platform compatibility for all new scripts.
