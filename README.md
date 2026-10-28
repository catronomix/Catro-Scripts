# Catro-Scripts

**Collection of personal Python scripts for whatevers. **
- Use at your own peril. I am using python 3.11+ (tested on 3.11 and 3.12)
- run catro-scripts.bat (windows) or catro-scripts.sh (linux) to get started
- It is highly recommended to add the install directory to your PATH, the scripts operate on the working directory by default

<img width="934" height="1014" alt="image" src="https://github.com/user-attachments/assets/24244c88-0ee7-40ae-afe1-dc0e7c67adbc" />


## Scripts Overview

- **`alias`**: create an alias for catro-scripts (.bat and .sh) for convenience/personalization

- **`action`**: macro runner for the commands stored in `actions.json`. Run a saved macro with `catro-scripts . <name> [args...]`, list them with `catro-scripts action list`, and add or remove them through an interactive mini-TUI. Each entry is `{"<name>": {"command": "<shell command>", "description": "<one line>"}}`; a malformed file is reported once with a non-zero exit, and an entry missing `command`/`description` only warns. `actions.json` itself is local and gitignored: `actions-template.json` is the tracked example and the bootstrap defaults written when the file is missing mirror it. Extra args are quoted per platform, so spaces, `;|&`, `$`, backticks and globs arrive literally; known limitation on Windows: `%VAR%` still expands even inside quotes.

- **`audiosplit`**: Splits multi-channel audio files into individual mono tracks. Supports multiple formats (MP3, WAV, FLAC, AAC, OGG, M4A, etc.) with batch processing, wildcard filtering, and interactive options.

- **`count`**: Display file counts and total size per file type found in a directory, with options to search for directory counts, set starting subdirectory and search depth.

- **`exifcopy`**: Copies EXIF metadata (camera settings, GPS, timestamps, etc.) from a source image to a target image. Supports JPEG and WebP formats. *Requires: piexif*

- **`fakeserver`**: A terminal screensaver that simulates hacker-style rapid typing with various code styles (Python, C++, or plaintext). Includes adjustable typing speed in WPM and interactive keyboard effects. Requires an interactive terminal: piping it exits 2 with a one-line message (there is no quit key off a tty), while `--help` still answers on any stream.

- **`getaudio`**: Extracts audio tracks from video files and saves them in various formats. Supports batch processing and format conversion with customizable quality settings.

- **`gitpush`**: Shorthand for quickly staging, committing and pushing to remote of a git repository.

- **`help`**: Displays help information and usage details for available scripts. A utility for exploring script functionality.

- **`image_generator`**: Generates a batch of timestamped images with solid background colors and noise patterns. Organizes files into timestamped directories and artificially distributes modification times for testing.

- **`image_resizer`**: Batch resizes all images in a working folder with configurable fitting options (resize, crop, pad, limit) and interpolation methods. Outputs resized images to a timestamped folder.

- **`installdeps`**: Automatically scans all Python files in the directory, identifies required third-party libraries, and installs missing dependencies via pip. Supports custom working directories and dry-run checks.

- **`jsonl_monitor`**: (New) A monitoring tool for JSONL log files and streams. Watches files for appended JSON lines, filters entries by criteria, and can print live summaries or forward matching entries to other tools.

- **`keygen`**: Interactive random-key generator. Opens on a default alphanumeric 32-character key, then lets you switch the algorithm (alphanumeric, uppercase, lowercase, hex, base64, printable ASCII, UUID) or key length via an arrow-key menu. Keys are cryptographically secure and shown with a live entropy readout. ENTER randomizes again; ESC or Q exits.

- **`list`**: Displays a formatted table of all Python scripts in the directory with file sizes and descriptions. Renders through the shared `tui` library, so it follows the configured theme and drops to plain tab-separated output on a pipe unless colour is explicitly forced.

- **`mdreader`**: (New) A lightweight markdown reader/renderer for terminal use. Supports rendering headers, code blocks, lists, and basic formatting for quick previews of README and notes files.

- **`netconfig`**: Network interface manager for **Windows (netsh)** and **Linux with NetworkManager (nmcli)** only. Toggle adapters between DHCP and Static IP modes, save manual configurations to a local JSON database, and perform quick adapter switching. Unsupported systems exit non-zero, and a missing `nmcli`/`ip` is reported as a failure naming the tool instead of a fake success.

- **`newfile`**: Creates new files with optional content templates and directory structure initialization.

- **`opencode`**: Wraps the `opencode` CLI for non-interactive runs (`opencode run "<instruction>"`). Shows install instructions when missing, lists models when called without arguments, supports `-m <provider/model[#variant]>` overrides, and persists a default model in `opencode.default`.

- **`randomsorter`**: Renames and distributes files in the current directory to anonymize them. It generates unique random identifiers (numeric or alphanumeric, with configurable length) and organizes files into subfolders.

- **`renamer`**: Renames files in the current directory sequentially. Supports custom prefixes, suffixes, and sorting methods while retaining media-type filters and safety checks.

- **`screensaver`**: A general terminal renderer and screensaver host that loads external screensaver modules (.screensaver files) and provides a high-performance double-buffered terminal canvas.

- **`sanitize`**: Rewrites full git history to replace a leaked secret with a placeholder (file contents + commit messages), then expires reflogs and GCs. Pre-checks history to avoid no-op rewrites and verifies afterwards. Run `sanitize "<secret>" ["<placeholder>"]`, or omit the secret on a terminal to be prompted with a masked (no-echo) prompt; the placeholder defaults to `<redacted>`. Off a terminal with no secret on argv it refuses with one error line and exit 2. *Requires: git + git-filter-repo*

- **`shutdown`**: Cross-platform interactive shutdown timer for Windows, macOS, and Linux. Accepts flexible time formats (e.g., 2h30m, 1d5h, 45m) and requires confirmation before scheduling. On Linux/macOS it uses `sudo` unless already root, finds `shutdown` on PATH or in `/sbin`/`/usr/sbin`, and exits 1 with one error line when the command is missing or fails.

- **`theme`**: Shows and changes the checkout-local terminal theme. A theme is one JSON file under `themes/` (three looks plus rendering properties); the gitignored `theme.ini` selects the theme name and the look. Commands: `theme` (overview), `theme <name>`, `theme list`, `theme soft|default|light|contrast-light|dark|contrast-dark|toggle`, `theme palette`, `theme set theme.name|theme.look|color.level|table.style <value>`, and `theme edit [name]` - the full-screen editor with Save/Load and a colour picker. Selecting a missing or invalid theme prints one line and exits 2. Rendering falls back to the shipped `themes/cozypurple.json`, which is the only copy of the built-in palette: if that file itself is missing or unreadable, the `theme` command reports it in one line and exits 2, and a rendering script stops with the same `ThemeError` naming the file rather than guessing a palette. `python -m tui` runs the same commands.

- **`timecopy`**: Copies file system timestamps (creation, modification, and access dates) from a source file to a target file. Windows supports creation time spoofing via kernel calls; Unix systems use conventional timestamp modification.

- **`ts_export`**: Exports a Typescript project that was created with *ts_setup* into a clean html+js format that can be loaded locally without security errors.

- **`ts_setup`**: Sets up a Typescript project folder and pre-generates some boilerplate html, ts and css to get started. It also runs commands to setup npm packages (requires node.js to be installed).

- **`venvreplicator`**: Replicates and manages Python virtual environments across different locations or systems. Allows cloning of venv dependencies and configurations for consistent development setups. `-i` writes `venv_info.txt` as TAB-separated plain records (no colour, no rules) so another tool can read it; the generated `recreate_venv.py` is deliberately plain text because it runs in the target project, outside `catro-scripts`, and cannot import `tui`.

- **`videofade`**: Adds smooth fade-in and fade-out effects to video clips. Supports customizable durations, various interpolation curves (like Ease-In-Out), and an "Append Mode" that freezes the last frame for a hold.

- **`videoframes`**: (New) Batch export of frames from a video as numbered images. Supports custom frame ranges, step sizes, and output naming templates for downstream processing.

- **`videojoin`**: Concatenates multiple video files using FFmpeg, leveraging Decord for efficient metadata analysis. Provides interactive codec selection and options to maintain audio sync.

- **`videoloop`**: Creates a seamless, crossfaded loop from a single video file by fading the end of the clip into the beginning. Features a "Timeline Shift" option to specify the starting position for the loop.

- **`videotweak`**: A versatile video processing tool for changing FPS, reversing, bouncing, time stretching and/or general transcoding. _Requires: decord, ffmpeg_


## Language Composition

- **Python**: 89.2%
- **Shell**: 5.9%
- **Batchfile**: 4.9%

## Usage

Once installed, you can run any Python script within the `Catro-Scripts` directory using the `catro-scripts` command, followed by the script name (without the `.py` extension) and any arguments it accepts.

```bash
catro-scripts [script_name] [arguments]
```

## Terminal styling (`tui/`)

The `tui/` package is the one place terminal presentation lives: capability
detection, the house palette, styled text, tables, prompts, screen primitives,
progress, paging and the frame loop that hosts `.screensaver` plugins. Scripts
import it instead of carrying their own escape codes, so colours, box glyphs and
pipe behaviour stay consistent.

Styling is resolved once per run, in this order: `NO_COLOR`,
`FORCE_COLOR`/`CLICOLOR_FORCE`, `CATRO_COLOR` (`none|16|256|true`), then
`config.ini`, then autodetection (terminal type, Windows console age, SSH, tty).
Colour and layout come from a named JSON theme under `themes/`
(`cozypurple.json` ships; `themes/README.md` documents the schema). Every theme
carries three hand-authored looks - `default` (shown as `soft`),
`contrast-light` and `contrast-dark` - plus rendering properties: header
alignment, border/table/button/scrollbar styles, focus style and zebra rows.
The gitignored `theme.ini` next to the wrappers selects the theme name and the
look, and every script shares both, so switching `theme` switches the whole
collection, never one script. `list`'s default appearance therefore changed
from the old purple-on-black to cozy purple; the checked-in golden fixture pins
the new default. Each colour is defined once and downgraded to the running
colour level, so a 16-colour terminal and a truecolor one show the same layout.

A page is composed from the shared chrome helpers rather than hand-printed
banners: `tui.header()` (title band plus rule), `tui.panel()` (framed block),
`tui.rule()`, `tui.field()` (key/value rows), `tui.status()` (`[ok]`/`[warn]`/
`[error]`/`[info]` lines), `tui.fill()` (a full-width background band) and
`tui.menu()`, on top of `tui.render_table()`/`print_table()`/`key_values()`/
`banner()`/`section()`. The frame is `border-fg`, headers and bars sit on
`bg-inside`, zebra rows and footer bars on `bg-stripe`, so a script that prints a
page looks like every other script. `mdreader` keeps its curses/rich renderer
but maps its three display modes onto the same three palettes (mode 0 `soft`,
mode 1 `contrast-light`, mode 2 `contrast-dark`) and paints its window
background, frame, status bar and shortcut bar from `bg`, `border-fg`,
`bg-inside` and `bg-stripe`.

A pipe stays plain by default: no ANSI escapes, no box glyphs, no padding - table
rows become TAB-separated fields, which keeps `list`, `count`, `action list` and
friends usable in scripts and `grep`. An explicit colour request on the pipe
(`FORCE_COLOR`/`CLICOLOR_FORCE`, or a real `CATRO_COLOR` level) turns plain off
instead: the pipe gets the full styled table - borders, padding, zebra rows and
escapes - so `FORCE_COLOR=3 list.py | cat` is both coloured and readable.
`NO_COLOR` still wins over any request. Turning colour off on a real terminal
(`NO_COLOR`, `TERM=dumb`, `theme set color.level none`) only removes the escapes:
the table keeps its borders, alignment and truncation.

Theme selection lives in `theme.ini` next to the wrappers (gitignored, one per
checkout); the colour level and table style stay in `config.ini`. Both are
managed with the `theme` command, which `python -m tui` also runs:

| command | effect |
|---|---|
| `theme` | overview: theme name, look, level, table style, paths, writability |
| `theme cozypurple` | select `themes/cozypurple.json`; exit 2 when missing or invalid |
| `theme list` | list the available themes |
| `theme soft` / `theme default` | the default look |
| `theme light` / `theme contrast-light` | the contrast-light look |
| `theme dark` / `theme contrast-dark` | the contrast-dark look |
| `theme toggle` | cycle soft -> light -> dark -> soft |
| `theme palette` | the active look's swatches |
| `theme set theme.name <name>` | select a theme by name |
| `theme set theme.look <look>` | select a look (short or long spelling) |
| `theme set color.level <level>` | `auto`, `none`, `16`, `256` or `true` |
| `theme set table.style <style>` | `auto`, `unicode` or `ascii` |
| `theme edit [name]` | full-screen editor (needs an interactive terminal) |

Piped, every page degrades to TAB-joined `key<TAB>value` rows with no escapes.
An unwritable `theme.ini`/`config.ini` prints one line naming the path and exits
1; `theme edit` off a terminal prints one line on stderr and exits 2.

`theme edit` opens the editor on the active theme, or on `<name>` when given. Its
three previews show the three looks live: Properties edits the nine rendering
properties, Colours opens a hex/HSV colour picker per palette key, and the
picker warns below WCAG AA (4.5:1 against `bg`/`bg-stripe`) but never blocks.
`Ctrl-S` saves atomically to `themes/<name>.json` (the filename is preseeded,
`.json` is implied, and an existing different file asks before it is
overwritten). A save only rewrites the lines you changed: the document's hex
spelling is kept, so re-saving an untouched theme leaves the file byte-identical.
Load lists every theme, marks the active one `*` and keeps an invalid file as an
`!` row. To share a theme, copy its JSON into `themes/`, keeping `name` equal to
the filename.

`CATRO_ASCII=1` forces ASCII box fallbacks, and
`CATRO_THEME=soft|contrast-light|contrast-dark` overrides the file for one run.

## Testing

Stdlib-only smoke suite, no installs needed: `python -m unittest discover -s tests -v`

Linux/POSIX compatibility is verified in a checked-in container instead of a
throwaway interpreter, because this host's only WSL distribution is
`docker-desktop` (no shell, no `python3`). Requires Docker:

```bash
python tests/container/run.py                    # both interpreters, stdlib + extras
python tests/container/run.py --python 3.12      # one interpreter
python tests/container/run.py --extras 0         # acceptance gate only
```

The runner builds `tests/container/Dockerfile` twice - `EXTRAS=0` (stdlib only,
the acceptance gate: every script must import cleanly and answer `--help`) and
`EXTRAS=1` (adds `pillow`, `piexif`, `pydub`) - then runs the smoke suite plus
the Linux column of the cross-platform sweep inside each image, read-only and
without network. Exit code is non-zero on a failing suite, a hanging or crashing
probe, or a probe that exits 0 after printing an error line. Evidence lands in
`.devteam/artifacts/container/` (`.devteam/` is not tracked). Details, including
the deliberately skipped `decord`/`ffmpeg` extras, are in
`tests/container/README.md`.

WSL is *not* covered: the container is the POSIX oracle, and the wrappers were
not exercised natively inside WSL.
