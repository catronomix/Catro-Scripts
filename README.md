# Catro-Scripts
Collection of personal scripts for whatevers.
Use at your own peril.

## Scripts Overview

- **`exifcopy`**:

- **`image_generator`**:

- **`image_resizer`**:

- **`installdeps`**:

- **`list`**:

- **`pdfconvert`**:

- **`randomsorter`**:

- **`shutdown`**:

- **`timecopy`**:



## Usage

Once installed, you can run any Python script within the `Catro-Scripts` directory using the `catro-scripts` command, followed by the script name (without the `.py` extension) and any arguments it requires.

```bash
catro-scripts [script_name] [arguments]
```


## Installation

To use the `catro-scripts` wrapper conveniently from any directory, you need to add its location to your system's PATH environment variable.

### Unix/macOS Installation

1.  **Add to PATH:** Add the directory containing `catro-scripts.sh` to your system's PATH environment variable.
    *   Open your shell configuration file (e.g., `~/.zshrc` or `~/.bash_profile`).
    *   Add the following line, replacing `/path/to/Catro-Scripts` with the actual path to this directory (e.g., `~/GITHUB/Catro-Scripts`):
        ```bash
        export PATH="$PATH:/path/to/Catro-Scripts"
        ```
    *   Save the file and reload your shell configuration (e.g., `source ~/.zshrc` or `source ~/.bash_profile`).
2.  **Make Executable:** Ensure the main script is executable.
    ```bash
    chmod +x /path/to/Catro-Scripts/catro-scripts.sh
    ```

### Windows Installation

1.  **Add to PATH:** Add the directory containing `catro-scripts.bat` to your Windows PATH environment variable.
    *   Search for "Environment Variables" in the Windows search bar and select "Edit the system environment variables".
    *   Click "Environment Variables...".
    *   Under "System variables" or "User variables for <YourUser>", find the `Path` variable and click "Edit...".
    *   Click "New" and add the full path to the `Catro-Scripts` directory (e.g., `C:\GITHUB\Catro-Scripts`).
    *   Click "OK" on all windows to save the changes.

## Usage
### Examples

*   **Run `randomsorter.py`:**
    ```bash
    catro-scripts randomsorter 10 5 --ext .png
    ```
*   **List available scripts:**
    ```bash
    catro-scripts list
    ```
No Copyright Innocent Coppieters
☕Buy me a coffee if you find out how.☕