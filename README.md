# Catro-Scripts

Collection of personal Python scripts for whatevers.  
Use at your own peril. I am using python 3.11.9
run catro-scripts.bat (windows) or catro-scripts.sh (linux) to get started

## Scripts Overview

- **`alias`**: create an alias for catro-scripts (.bat and .sh) for convenience.

- **`audiosplit`**: Splits multi-channel audio files into individual mono tracks. Supports multiple formats (MP3, WAV, FLAC, AAC, OGG, M4A, etc.) with batch processing, wildcard filtering, and interactive codec selection. *Requires: pydub, ffmpeg*

- **`count`**: Display file counts and total size per file type found in a directory, with options to search for directory counts, set starting subdirectory and search depth. Has nice rainbow colors.

- **`exifcopy`**: Copies EXIF metadata (camera settings, GPS, timestamps, etc.) from a source image to a target image. Supports JPEG and WebP formats. *Requires: piexif*

- **`extractframe`**: This utility extracts a single frame from a video file, saving it as a PNG image. It leverages the Decord library for efficient seeking, allowing extraction by frame index, timestamp, or percentile position.

- **`fakeserver`**: A terminal screensaver that simulates hacker-style rapid typing with various code styles (Python, C++, or plaintext). Includes adjustable typing speed in WPM and interactive keyboard controls. *Requires: pynput*

- **`getaudio`**: Extracts audio tracks from video files and saves them in various formats. Supports batch processing and format conversion with customizable quality settings.

- **`help`**: Displays help information and usage details for available scripts. A utility for exploring script functionality.

- **`image_generator`**: Generates a batch of timestamped images with solid background colors and noise patterns. Organizes files into timestamped directories and artificially distributes modification times.

- **`image_resizer`**: Batch resizes all images in a working folder with configurable fitting options (resize, crop, pad, limit) and interpolation methods. Outputs resized images to a timestamped directory.

- **`installdeps`**: Automatically scans all Python files in the directory, identifies required third-party libraries, and installs missing dependencies via pip. Supports custom working directories.

- **`list`**: Displays a formatted table of all Python scripts in the directory with file sizes and descriptions. Features a purple/green color-coded layout.

- **`netconfig`**: Cross-platform network interface manager. Seamlessly toggle adapters between DHCP and Static IP modes, save manual configurations to a local JSON database, and perform quick adapter restarts. Requires administrative privileges.

- **`newfile`**: Creates new files with optional content templates and directory structure initialization.

- **`randomsorter`**: Renames and distributes files in the current directory to anonymize them. It generates unique random identifiers (numeric or alphanumeric, with configurable length) and organizes them into subdirectories.

- **`renamer`**: This script renames files in the current directory sequentially. It supports custom prefixes, suffixes, and sorting methods while retaining the media filters and safety features of the codebase.

- **`screensaver`**: A general terminal renderer and screensaver host that loads external screensaver modules (.screensaver files) and provides them with a high-performance double-buffered terminal drawing API. Features an interactive menu system with keyboard controls. *Supports custom screensaver plugins*

- **`shutdown`**: Cross-platform interactive shutdown timer for Windows, macOS, and Linux. Accepts flexible time formats (e.g., 2h30m, 1d5h, 45m) and requires confirmation before scheduling. May require administrative privileges.

- **`timecopy`**: Copies file system timestamps (creation, modification, and access dates) from a source file to a target file. Windows supports creation time spoofing via kernel calls; Unix systems work with modification and access times.

- **`ts_export`**: Exports a Typescript project that was created with *ts_setup* into a clean html+js format that can be loaded locally without security errors.

- **`ts_setup`**: Sets up a Typescript project folder and pre-generates some boilerplate html, ts and css to get started. It also runs commands to setup npm packages (requires node.js to be installed).

- **`venvreplicator`**: Replicates and manages Python virtual environments across different locations or systems. Allows cloning of venv dependencies and configurations for consistent development environments.

- **`videofade`**: Adds smooth fade-in and fade-out effects to video clips. Supports customizable durations, various interpolation curves (like Ease-In-Out), and a special "Append Mode" that freezes frames.

- **`videojoin`**: This utility concatenates multiple video files using FFmpeg, leveraging Decord for efficient metadata analysis. It provides advanced features such as interactive codec selection and seamless transitions.

- **`videoloop`**: Creates a seamless, crossfaded loop from a single video file by fading the end of the clip into the beginning. Features a "Timeline Shift" option to specify the starting position of the loop.

- **`videotweak`**: Advanced video editing utility for applying filters, adjustments, and effects to video files. Supports color correction, bitrate adjustment, and various video transformations.

- **`videotweak`**: A versatile video processing tool for changing FPS, reversing, bouncing, time stretching and/or general transcoding. _Requires: decord, ffmpeg_

## Language Composition

- **Python**: 89.2%
- **Shell**: 5.9%
- **Batchfile**: 4.9%

## Usage

Once installed, you can run any Python script within the `Catro-Scripts` directory using the `catro-scripts` command, followed by the script name (without the `.py` extension) and any arguments it may require.

```bash
catro-scripts [script_name] [arguments]
```
