# Catro-Scripts

**Collection of personal Python scripts for whatevers. **
- Use at your own peril. I am using python 3.12.5
- run catro-scripts.bat (windows) or catro-scripts.sh (linux) to get started
- It is highly recommended to add the install directory to your PATH, the scripts operate on the working directory by default

<img width="934" height="1014" alt="image" src="https://github.com/user-attachments/assets/24244c88-0ee7-40ae-afe1-dc0e7c67adbc" />


## Scripts Overview

- **`alias`**: create an alias for catro-scripts (.bat and .sh) for convenience/personalization

- **`audiosplit`**: Splits multi-channel audio files into individual mono tracks. Supports multiple formats (MP3, WAV, FLAC, AAC, OGG, M4A, etc.) with batch processing, wildcard filtering, and interactive options.

- **`count`**: Display file counts and total size per file type found in a directory, with options to search for directory counts, set starting subdirectory and search depth.

- **`exifcopy`**: Copies EXIF metadata (camera settings, GPS, timestamps, etc.) from a source image to a target image. Supports JPEG and WebP formats. *Requires: piexif*

- **`extractframe`**: Extracts a single frame from a video file, saving it as a PNG image. Leverages Decord for efficient seeking, allowing extraction by frame index or timestamp.

- **`fakeserver`**: A terminal screensaver that simulates hacker-style rapid typing with various code styles (Python, C++, or plaintext). Includes adjustable typing speed in WPM and interactive keyboard effects.

- **`getaudio`**: Extracts audio tracks from video files and saves them in various formats. Supports batch processing and format conversion with customizable quality settings.

- **`help`**: Displays help information and usage details for available scripts. A utility for exploring script functionality.

- **`image_generator`**: Generates a batch of timestamped images with solid background colors and noise patterns. Organizes files into timestamped directories and artificially distributes modification times for testing.

- **`image_resizer`**: Batch resizes all images in a working folder with configurable fitting options (resize, crop, pad, limit) and interpolation methods. Outputs resized images to a timestamped folder.

- **`installdeps`**: Automatically scans all Python files in the directory, identifies required third-party libraries, and installs missing dependencies via pip. Supports custom working directories and dry-run checks.

- **`jsonl_monitor`**: (New) A monitoring tool for JSONL log files and streams. Watches files for appended JSON lines, filters entries by criteria, and can print live summaries or forward matching entries to other tools.

- **`list`**: Displays a formatted table of all Python scripts in the directory with file sizes and descriptions. Features a purple/green color-coded layout.

- **`mdreader`**: (New) A lightweight markdown reader/renderer for terminal use. Supports rendering headers, code blocks, lists, and basic formatting for quick previews of README and notes files.

- **`netconfig`**: Cross-platform network interface manager. Seamlessly toggle adapters between DHCP and Static IP modes, save manual configurations to a local JSON database, and perform quick adapter switching.

- **`newfile`**: Creates new files with optional content templates and directory structure initialization.

- **`randomsorter`**: Renames and distributes files in the current directory to anonymize them. It generates unique random identifiers (numeric or alphanumeric, with configurable length) and organizes files into subfolders.

- **`renamer`**: Renames files in the current directory sequentially. Supports custom prefixes, suffixes, and sorting methods while retaining media-type filters and safety checks.

- **`screensaver`**: A general terminal renderer and screensaver host that loads external screensaver modules (.screensaver files) and provides a high-performance double-buffered terminal canvas.

- **`shutdown`**: Cross-platform interactive shutdown timer for Windows, macOS, and Linux. Accepts flexible time formats (e.g., 2h30m, 1d5h, 45m) and requires confirmation before scheduling.

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
