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

- **`fakeserver`**: A terminal screensaver that simulates hacker-style rapid typing with various code styles (Python, C++, or plaintext). Includes adjustable typing speed in WPM and interactive keyboard effects.

- **`getaudio`**: Extracts audio tracks from video files and saves them in various formats. Supports batch processing and format conversion with customizable quality settings.

- **`gitpush`**: Shorthand for quickly staging, committing and pushing to remote of a git repository.

- **`help`**: Displays help information and usage details for available scripts. A utility for exploring script functionality.

- **`image_generator`**: Generates a batch of timestamped images with solid background colors and noise patterns. Organizes files into timestamped directories and artificially distributes modification times for testing.

- **`image_resizer`**: Batch resizes all images in a working folder with configurable fitting options (resize, crop, pad, limit) and interpolation methods. Outputs resized images to a timestamped folder.

- **`installdeps`**: Automatically scans all Python files in the directory, identifies required third-party libraries, and installs missing dependencies via pip. Supports custom working directories and dry-run checks.

- **`jsonl_monitor`**: (New) A monitoring tool for JSONL log files and streams. Watches files for appended JSON lines, filters entries by criteria, and can print live summaries or forward matching entries to other tools.

- **`keygen`**: Interactive random-key generator. Opens on a default alphanumeric 32-character key, then lets you switch the algorithm (alphanumeric, uppercase, lowercase, hex, base64, printable ASCII, UUID) or key length via an arrow-key menu. Keys are cryptographically secure and shown with a live entropy readout. ENTER randomizes again; ESC or Q exits.

- **`list`**: Displays a formatted table of all Python scripts in the directory with file sizes and descriptions. Renders through the shared `tui` library, so it follows the configured theme and switches to plain tab-separated output when piped.

- **`mdreader`**: (New) A lightweight markdown reader/renderer for terminal use. Supports rendering headers, code blocks, lists, and basic formatting for quick previews of README and notes files.

- **`netconfig`**: Network interface manager for **Windows (netsh)** and **Linux with NetworkManager (nmcli)** only. Toggle adapters between DHCP and Static IP modes, save manual configurations to a local JSON database, and perform quick adapter switching. Unsupported systems exit non-zero, and a missing `nmcli`/`ip` is reported as a failure naming the tool instead of a fake success.

- **`newfile`**: Creates new files with optional content templates and directory structure initialization.

- **`opencode`**: Wraps the `opencode` CLI for non-interactive runs (`opencode run "<instruction>"`). Shows install instructions when missing, lists models when called without arguments, supports `-m <provider/model[#variant]>` overrides, and persists a default model in `opencode.default`.

- **`randomsorter`**: Renames and distributes files in the current directory to anonymize them. It generates unique random identifiers (numeric or alphanumeric, with configurable length) and organizes files into subfolders.

- **`renamer`**: Renames files in the current directory sequentially. Supports custom prefixes, suffixes, and sorting methods while retaining media-type filters and safety checks.

- **`screensaver`**: A general terminal renderer and screensaver host that loads external screensaver modules (.screensaver files) and provides a high-performance double-buffered terminal canvas.

- **`sanitize`**: Rewrites full git history to replace a leaked secret with a placeholder (file contents + commit messages), then expires reflogs and GCs. Pre-checks history to avoid no-op rewrites and verifies afterwards. *Requires: git + git-filter-repo*

- **`shutdown`**: Cross-platform interactive shutdown timer for Windows, macOS, and Linux. Accepts flexible time formats (e.g., 2h30m, 1d5h, 45m) and requires confirmation before scheduling. On Linux/macOS it uses `sudo` unless already root, finds `shutdown` on PATH or in `/sbin`/`/usr/sbin`, and exits 1 with one error line when the command is missing or fails.

- **`theme`**: Shows and changes the checkout-local terminal preferences in `config.ini`: `theme` (overview), `theme dark|light|toggle`, `theme set <key> <value>` (`theme.mode`, `color.level`, `table.style`), and `theme palette`. The same commands are available as `python -m tui`. When the file cannot be written it prints one line naming the path and exits 1.

- **`timecopy`**: Copies file system timestamps (creation, modification, and access dates) from a source file to a target file. Windows supports creation time spoofing via kernel calls; Unix systems use conventional timestamp modification.

- **`ts_export`**: Exports a Typescript project that was created with *ts_setup* into a clean html+js format that can be loaded locally without security errors.

- **`ts_setup`**: Sets up a Typescript project folder and pre-generates some boilerplate html, ts and css to get started. It also runs commands to setup npm packages (requires node.js to be installed).

- **`venvreplicator`**: Replicates and manages Python virtual environments across different locations or systems. Allows cloning of venv dependencies and configurations for consistent development setups.

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
Two themes are available, `dark` (default) and `light`; each colour is defined
once and downgraded to the running colour level, so a 16-colour terminal and a
truecolor one show the same layout.

Anything on a pipe is plain on purpose: no ANSI escapes, no box glyphs, no
padding - table rows become TAB-separated fields. That makes `list`, `count`,
`action list` and friends usable in scripts and `grep`.

Settings live in `config.ini` next to the wrappers (gitignored), managed with the
`theme` command:

```bash
catro-scripts theme                      # show mode, level, table style, path
catro-scripts theme light                # or dark / toggle
catro-scripts theme set color.level 256  # auto | none | 16 | 256 | true
catro-scripts theme set table.style ascii
catro-scripts theme palette              # list the active palette
```

`CATRO_ASCII=1` forces ASCII box fallbacks, and `CATRO_THEME=dark|light`
overrides the file for one run.

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
