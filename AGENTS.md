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
    3. The wrapper handles the lifecycle (start, run, stop) and standardizes display interactions: plugins receive a `tui.TerminalRenderer` and must keep working through `draw_char`/`draw_text`/`render`/`clear`.
  - **Rule**: Never modify core screensaver loop logic without ensuring backward compatibility for existing `.screensaver` files.

## Coding Standards & Conventions
- **House Style**: Scripts should utilize full-color text output (where applicable), clean terminal layouts, and structured tables for data representation.
  - Terminal presentation lives in the `tui/` package. Its behavior is pinned by
    the `tui` feature contract (`.devteam/contracts/tui.md`, local dev-team
    tooling, not tracked); read it before changing anything in `tui/` and treat
    it as the source of truth for detection precedence, the palette, table
    composition and pipe behavior.
  - **No private ANSI**: Do not hardcode escape codes or define a local `Colors`
    class in a script. Use `tui.style()`/`tui.prefix()` with semantic palette
    keys (`header`, `border`, `fg`, `muted`, `success`, `warn`, `error`, ...),
    and `tui.init_ansi()` for the Windows console bootstrap.
  - **Detection once per run**: `tui.detect()` (and `tui.theme()`) re-read
    `config.ini`, so resolve `cap = tui.detect()` once in `main()` and pass it to
    the helpers instead of calling per line.
  - **Visual Layout**:
    - **Page chrome**: a script that prints a page composes it from the shared
      helpers - `tui.header()` for the title band, `tui.panel()` for a framed
      block, `tui.rule()` for a divider, `tui.field()` for key/value rows,
      `tui.status()` for `[ok]`/`[warn]`/`[error]`/`[info]` lines, `tui.fill()`
      for a full-width background band and `tui.menu()` for numbered choices.
      Never print a bare heading, a hand-drawn divider or a private colour:
      `tests/test_scripts_tui.py::ThemedOutputTest` fails an in-scope script
      that calls none of the chrome/table helpers (`PENDING_THEMING` is the
      shrinking close-out list, not an escape hatch for new code).
    - **Tables**: Use `tui.render_table()`/`print_table()` (box glyphs, ASCII
      fallback) or `tui.key_values()`/`banner()`/`section()` instead of drawing
      borders by hand. Keep the header/footer structure seen in `list.py`.
    - **Pipes**: stdout that is not a tty gets plain TAB-separated output by
      default - no ANSI, glyphs or padding - unless the run explicitly asks for
      colour (`FORCE_COLOR`/`CLICOLOR_FORCE`/`CATRO_COLOR`), which gets the full
      styled table; `NO_COLOR` still wins. Do not special-case `isatty()` in a
      script: `cap.plain` already encodes this.
    - **Themes**: `soft` (default, cozy purple), `contrast-light` and
      `contrast-dark` are all first class
      (`theme soft|contrast-light|contrast-dark|toggle`); colors come from the
      palette so every colour level (`16`/`256`/`true`) downgrades
      automatically.
  - **Automation**: When a script needs styled output and the helpers do not
    cover it, add the seam to `tui/` (with a test in `tests/test_tui_*.py`)
    rather than growing a private renderer.
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

## OpenCode Skill
- For any use/run/explain task involving catro-scripts tools, load skill `catro-scripts` via the skill tool first, then follow it (`cs list`, `cs help <script>` before use).
