# Catro-Scripts

Collection of personal scripts for whatevers.  
Use at your own peril.

## Scripts Overview

- **`exifcopy`**: Copies EXIF metadata (camera settings, GPS, timestamps, etc.) from a source image to a target image. Supports JPEG and WebP formats. *Requires: piexif*

- **`help`**: Displays help information and usage details for available scripts. A utility for exploring script functionality.

- **`image_generator`**: Generates a batch of timestamped images with solid background colors and noise patterns. Organizes files into timestamped directories and artificially distributes modification times across a specified window (10:00 - 17:00). *Requires: Pillow (PIL)*

- **`image_resizer`**: Batch resizes all images in a working folder with configurable fitting options (resize, crop, pad, limit) and interpolation methods. Outputs resized images to a timestamped subfolder with a colorful progress bar. *Requires: Pillow (PIL)*

- **`installdeps`**: Automatically scans all Python files in the directory, identifies required third-party libraries, and installs missing dependencies via pip. Supports custom working directories via `-workdir` argument. Includes manual mapping for common import name discrepancies.

- **`list`**: Displays a formatted table of all Python scripts in the directory with file sizes and descriptions. Features a purple/green color-coded layout.

- **`randomsorter`**: Renames and distributes images in the current directory to anonymize them. Generates random 6-digit identifiers for each image and organizes them into numbered subfolders (reeks1, reeks2, etc.) based on user-specified quantities. Supports filtering by file extension. *Supported: .jpg, .jpeg, .png, .webp, .gif, .bmp, .tiff*

- **`shutdown`**: Cross-platform interactive shutdown timer for Windows, macOS, and Linux. Accepts flexible time formats (e.g., 2h30m, 1d5h, 45m) and requires confirmation before scheduling. May require sudo/admin privileges on Unix systems.

- **`timecopy`**: Copies file system timestamps (creation, modification, and access dates) from a source file to a target file. Windows supports creation time spoofing via kernel calls; Unix systems support modification and access times.

## Language Composition

- **Python**: 88.4%
- **Shell**: 6.4%
- **Batchfile**: 5.2%

## Usage

Once installed, you can run any Python script within the `Catro-Scripts` directory using the `catro-scripts` command, followed by the script name (without the `.py` extension) and any arguments it needs:

```bash
catro-scripts [script_name] [arguments]
