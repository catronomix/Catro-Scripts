# Catro-Scripts

Collection of personal scripts for whatevers.  
Use at your own peril.

## Scripts Overview

- **`alias`**: create an alias for catro-scripts (.bat and .sh) for convenience.

- **`count`**: Display file counts and total size per file type found in a directory, with options to search for directory counts, set starting subdirectory and search depth. Has nice rainbow colors.

- **`exifcopy`**: Copies EXIF metadata (camera settings, GPS, timestamps, etc.) from a source image to a target image. Supports JPEG and WebP formats. *Requires: piexif*

- **`extractframe`**: This utility extracts a single frame from a video file, saving it as a PNG image. It leverages the Decord library for efficient seeking, allowing extraction by frame index, 'first', or 'last', with an option for keyframe snapping.

- **`help`**: Displays help information and usage details for available scripts. A utility for exploring script functionality.

- **`image_generator`**: Generates a batch of timestamped images with solid background colors and noise patterns. Organizes files into timestamped directories and artificially distributes modification times across a specified window (10:00 - 17:00). *Requires: Pillow (PIL)*

- **`image_resizer`**: Batch resizes all images in a working folder with configurable fitting options (resize, crop, pad, limit) and interpolation methods. Outputs resized images to a timestamped subfolder with a colorful progress bar. *Requires: Pillow (PIL)*

- **`installdeps`**: Automatically scans all Python files in the directory, identifies required third-party libraries, and installs missing dependencies via pip. Supports custom working directories via `-workdir` argument. Includes manual mapping for common import name discrepancies.

- **`list`**: Displays a formatted table of all Python scripts in the directory with file sizes and descriptions. Features a purple/green color-coded layout.

- **`randomsorter`**: Renames and distributes files in the current directory to anonymize them. It generates unique random identifiers (numeric or alphanumeric, with configurable length) and organizes them into numbered subfolders (e.g., `batch01`, `batch02`) based on user-specified quantities. Supports filtering by file type (image, video, audio) or specific extension, and can copy files instead of moving them. *Supports common image, video, and audio formats.*

- **`renamer`**: This script renames files in the current directory sequentially. It supports custom prefixes, suffixes, and sorting methods while retaining the media filters and safety features of the random sorter.

- **`shutdown`**: Cross-platform interactive shutdown timer for Windows, macOS, and Linux. Accepts flexible time formats (e.g., 2h30m, 1d5h, 45m) and requires confirmation before scheduling. May require sudo/admin privileges on Unix systems.

- **`timecopy`**: Copies file system timestamps (creation, modification, and access dates) from a source file to a target file. Windows supports creation time spoofing via kernel calls; Unix systems support modification and access times.

- **`videofade`**: Adds smooth fade-in and fade-out effects to video clips. Supports customizable durations, various interpolation curves (like Ease-In-Out), and a special "Append Mode" that freezes the edges of the video for the duration of the fade. _Requires: decord, ffmpeg_

- **`videojoin`**: This utility concatenates multiple video files using FFmpeg, leveraging Decord for efficient metadata analysis. It provides advanced features such as interactive codec selection, various resizing methods (crop, fit, stretch, limit), and options to skip the last frame or join all videos in a directory.

- **`videolooper`**: Creates a seamless, crossfaded loop from a single video file by fading the end of the clip into the beginning. Features a "Timeline Shift" option to specify the starting position of the final loop and handles silent videos gracefully. _Requires: decord, ffmpeg_


## Language Composition

- **Python**: 89.2%
- **Shell**: 5.9%
- **Batchfile**: 4.9%

## Usage

Once installed, you can run any Python script within the `Catro-Scripts` directory using the `catro-scripts` command, followed by the script name (without the `.py` extension) and any arguments it needs:

```bash
catro-scripts [script_name] [arguments]
