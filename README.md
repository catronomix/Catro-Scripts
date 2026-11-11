# Catro-Scripts

A collection of personal Python scripts for everyday chores: media files, images, git, networks and the terminal. Use at your own peril.

<img width="934" height="1014" alt="image" src="https://github.com/user-attachments/assets/24244c88-0ee7-40ae-afe1-dc0e7c67adbc" />

## Installation

1. Install **Python 3.11 or newer** (tested on 3.11 and 3.12).
2. Clone this repository and add the folder to your `PATH` - it is highly recommended, because the scripts operate on the current working directory.
3. Run a script with the launcher for your platform:

```bash
catro-scripts.bat <script> [arguments]    # Windows
catro-scripts.sh  <script> [arguments]    # Linux / macOS
```

Scripts are standard-library first. A few use optional packages (Pillow, pydub, piexif, decord, ffmpeg, git-filter-repo); `catro-scripts installdeps` installs the Python ones, and each script names what it needs in its own help.

## Help

Every script is self-documenting:

```bash
catro-scripts help            # list the scripts and how to use them
catro-scripts help <script>   # usage for one script
catro-scripts list            # the same catalogue with file sizes
```

## Scripts

- **`alias`** - creates a personal alias for the launcher (`.bat` and `.sh`).
- **`action`** - runs and manages saved shell macros from `actions.json`.
- **`audiosplit`** - splits multi-channel audio into separate mono tracks.
- **`count`** - counts files and their total size per file type.
- **`exifcopy`** - copies EXIF metadata from one image to another.
- **`fakeserver`** - screensaver that "types" fake hacker code.
- **`getaudio`** - extracts audio tracks from video files.
- **`gitpush`** - stages, commits and pushes in one step.
- **`help`** - shows help and usage for a script.
- **`image_generator`** - produces test images with solid colours and noise.
- **`image_resizer`** - batch-resizes images (fit, crop, pad or limit).
- **`installdeps`** - finds and installs missing third-party Python packages.
- **`jsonl_monitor`** - watches JSONL files or streams and filters new entries.
- **`keygen`** - interactive random-key generator.
- **`list`** - table of the available scripts with sizes and descriptions.
- **`mdreader`** - markdown reader for the terminal.
- **`netconfig`** - switches network adapters between DHCP and a static IP.
- **`newfile`** - creates files and folders from templates.
- **`opencode`** - runs the `opencode` CLI non-interactively.
- **`randomsorter`** - renames and shuffles files into randomised names and folders.
- **`renamer`** - batch-renames files with prefixes, suffixes and sorting.
- **`screensaver`** - host and renderer for `.screensaver` plugins.
- **`sanitize`** - scrubs a leaked secret from a repository's full git history.
- **`shutdown`** - interactive shutdown timer for Windows, macOS and Linux.
- **`theme`** - shows and changes the terminal theme.
- **`timecopy`** - copies file timestamps from one file to another.
- **`ts_export`** - exports a `ts_setup` project as plain local HTML and JavaScript.
- **`ts_setup`** - scaffolds a TypeScript project.
- **`venvreplicator`** - clones and manages Python virtual environments.
- **`videofade`** - adds fade-in and fade-out to video clips.
- **`videoframes`** - exports frames from a video as numbered images.
- **`videojoin`** - joins video files with FFmpeg.
- **`videoloop`** - builds a seamless, crossfaded loop from a video.
- **`videotweak`** - changes FPS, reverses, bounces or transcodes video.

## Development

Architecture notes, the terminal styling and theme system, the test suite and the container setup live in [DEVELOPMENT.md](DEVELOPMENT.md).
