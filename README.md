# Catro-Scripts

**A collection of personal Python scripts for everyday chores: media files, images, git, networks and the terminal.**
- *Zero warranty! Use at your own peril.*

<img width="819" height="700" alt="scripts overview" src="https://github.com/user-attachments/assets/4a1d9f09-d711-4278-871b-5e0b4fd79278" />

## Installation

1. Install **Python 3.11 or newer** (tested on 3.11 and 3.12).
2. Clone this repository and add the folder to your `PATH` - it is highly recommended, because the scripts operate on the current working directory.
3. Run a script with the launcher for your platform:

```bash
catro-scripts <script> [arguments]    # Windows
catro-scripts <script> [arguments]    # Linux / macOS
```

Scripts are standard-library first. A few use optional packages (Pillow, pydub, piexif, decord, ffmpeg, git-filter-repo); `catro-scripts installdeps` installs the Python ones, and each script names what it needs in its own help.

## Help

Every script is self-documenting:

```bash
catro-scripts help            # list the scripts and how to use them
catro-scripts help <script>   # usage for one script
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
- **`image_resizer`** - batch-resizes images (fit, crop, pad or limit), including very large poster-sized sources.
- **`installdeps`** - finds and installs missing third-party Python packages.
- **`jsonl_monitor`** - watches JSONL files or streams and filters new entries.
- **`keygen`** - interactive random-key generator.
- **`list`** - table of the available scripts with sizes and descriptions.
- **`makewebp`** - turns a folder's images into one animated `.webp` with ffmpeg/libwebp (frame order, timing and colour filters are configurable), saved as `<folder>.webp` one level up, beside the input folder.
- **`mdreader`** - markdown reader for the terminal. Links emit as OSC 8 hyperlinks where the terminal supports them, so Ctrl-click opens them.
- **`netconfig`** - switches network adapters between DHCP and a static IP.
- **`newfile`** - creates files and folders from templates.
- **`oc`** - runs the `opencode` CLI non-interactively.
- **`randomsorter`** - renames and shuffles files into randomised names and folders.
- **`renamer`** - batch-renames files with prefixes, suffixes and sorting by name, modification date or creation date.
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
- **`videojoin`** - joins video files with FFmpeg. Every run with work shows one reused progress box (current operation + overall progress + growing ok/fail list); an existing output asks `File exists! Overwrite? ([y]es, [n]o, [Y]es to all, [r]ename, [R]ename all, [a]bort):` instead of silently writing `name (1).mp4` - `r` saves as `name (2).mp4`, `Y`/`R` apply to the rest, `a` stops the batch; off a terminal it skips instead of asking.
- **`videoloop`** - builds a seamless, crossfaded loop from a video. Same progress box (every mode, including a single file) and the same overwrite question as `videojoin`.
- **`videotweak`** - changes FPS, reverses, bounces or transcodes video. Same progress box and overwrite question as `videojoin`.

## Themes

Catro-Scripts has a minimal theme engine to style UI elements. To customize the look and make your own themes, simply use `catro-scripts theme edit`

<img width="923" height="766" alt="image" src="https://github.com/user-attachments/assets/fe373818-a43f-452a-bd9b-4589fb3832a1" />


## Development

Architecture notes, the terminal styling and theme system, the test suite and the container setup live in [DEVELOPMENT.md](DEVELOPMENT.md).
