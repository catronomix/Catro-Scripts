# Sequential file renamer with filtering and safety
"""
            SEQUENTIAL FILE RENAMER
            -----------------------
This script renames files in the current directory sequentially. 
It supports custom prefixes, suffixes, and sorting methods while 
retaining the media filters and safety features of the random sorter.

USAGE:
    python renamer.py -p "holiday_" -s "_draft"
    python renamer.py -f --type image
    python renamer.py --type image --sort date_asc

OPTIONS:
    -p, --prefix STR   Text to put before the number
    -f, --folder       Use the parent folder's name as the prefix
    -s, --suffix STR   Text to put after the number (before extension)
    -d, --digits N     Number of digits for padding (default: auto-calculated)
    --sort METHOD      Sorting: 'name_asc' (default), 'name_desc', 'date_asc', 'date_desc'
    -k, --keep         Keep original files in place (copy instead of move)
    -t, --type TYPE    Filter by 'image', 'video', or 'audio'
    -e, --ext EXT      Filter for a specific extension only
    -a, --all          Include all files, ignoring safety filters (requires confirmation)
"""

import os
import argparse
import sys
import shutil

# Predefined extension groups
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.svg', '.heic', '.jfif')
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v')
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.aiff')

# Safety list: common non-media extensions to ignore by default
FORBIDDEN_EXTENSIONS = (
    '.exe', '.dll', '.sys', '.ini', '.bat', '.cmd', '.sh', '.ps1', '.vbs', # Executables/Scripts
    '.py', '.js', '.ts', '.html', '.css', '.json', '.xml',                # Dev files
    '.lnk', '.url', '.alias',                                             # Shortcuts
    '.db', '.sqlite', '.sql', '.log',                                     # Data/Logs
    '.msi', '.pkg', '.dmg', '.iso', '.bin',                               # Installers
    '.inf', '.config', '.yaml', '.yml'                                    # Configuration
)

def get_target_files(folder_path, allowed_extensions, include_all):
    """Returns a list of files to process based on filters and safety rules."""
    script_name = os.path.basename(sys.argv[0])
    all_files = [f for f in os.listdir(folder_path) 
                 if os.path.isfile(os.path.join(folder_path, f)) and f != script_name]
    
    if allowed_extensions:
        files = [f for f in all_files if f.lower().endswith(allowed_extensions)]
    elif not include_all:
        files = [f for f in all_files if not f.lower().endswith(FORBIDDEN_EXTENSIONS)]
    else:
        files = all_files
        
    return files

def sort_files(folder_path, files, method):
    """Sorts files based on the chosen method."""
    if method == 'name_asc':
        files.sort()
    elif method == 'name_desc':
        files.sort(reverse=True)
    elif method == 'date_asc':
        files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)))
    elif method == 'date_desc':
        files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)), reverse=True)
    return files

def rename_files(folder_path, prefix, suffix, digit_count, keep, files):
    """Performs the sequential renaming/copying."""
    if not files:
        print("No matching files found. Nothing to do.")
        return

    # Auto-calculate digits if not provided
    if digit_count is None:
        digit_count = len(str(len(files)))
        print(f"Auto-calculated digit padding: {digit_count}")

    print(f"Processing {len(files)} files...\n")

    for i, filename in enumerate(files, start=1):
        extension = os.path.splitext(filename)[1]
        
        # Build new filename
        number_str = str(i).zfill(digit_count)
        new_name = f"{prefix}{number_str}{suffix}{extension}"
        
        old_path = os.path.join(folder_path, filename)
        new_path = os.path.join(folder_path, new_name)

        # Basic collision check
        if os.path.exists(new_path):
            print(f"Skipping: {new_name} already exists.")
            continue

        if keep:
            shutil.copy2(old_path, new_path)
            print(f"Copied: {filename} -> {new_name}")
        else:
            os.rename(old_path, new_path)
            print(f"Renamed: {filename} -> {new_name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sequentially rename files in the current folder.")
    
    parser.add_argument("-p", "--prefix", type=str, default="",
                        help="Prefix for the new filename.")

    parser.add_argument("-f", "--folder", action="store_true",
                        help="Use the current folder name as the prefix.")
    
    parser.add_argument("-s", "--suffix", type=str, default="",
                        help="Suffix for the new filename (before extension).")
    
    parser.add_argument("-d", "--digits", type=int,
                        help="Number of digits for numbering (e.g. 3 for 001). Defaults to fit file count.")
    
    parser.add_argument("--sort", type=str, choices=['name_asc', 'name_desc', 'date_asc', 'date_desc'],
                        default='name_asc', help="Sorting method (default: name_asc)")

    parser.add_argument("-k", "--keep", action="store_true",
                        help="Keep original files in place (copy instead of move)")

    parser.add_argument("-t", "--type", type=str, choices=['image', 'video', 'audio'],
                        help="Filter by category: 'image', 'video', or 'audio'")

    parser.add_argument("-e", "--ext", type=str, 
                        help="Filter for a specific extension only.")

    parser.add_argument("-a", "--all", action="store_true",
                        help="Include all files, ignoring safety filters (requires confirmation)")

    args = parser.parse_args()

    # Handle confirmation for --all flag
    if args.all:
        confirm = input("WARNING: You are using the --all flag. This will process system files and scripts.\nAre you sure? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            sys.exit()

    # Determine prefix
    current_folder = os.getcwd()
    final_prefix = args.prefix
    if args.folder:
        # Get base name of the current directory
        final_prefix = os.path.basename(current_folder)

    # Determine extension filter
    allowed = None
    if args.ext:
        target_ext = args.ext if args.ext.startswith('.') else f".{args.ext}"
        allowed = (target_ext.lower(),)
    elif args.type == 'image':
        allowed = IMAGE_EXTENSIONS
    elif args.type == 'video':
        allowed = VIDEO_EXTENSIONS
    elif args.type == 'audio':
        allowed = AUDIO_EXTENSIONS
    
    # Get and sort target files
    target_files = get_target_files(current_folder, allowed, args.all)
    sorted_files = sort_files(current_folder, target_files, args.sort)
    
    # Execute renaming
    rename_files(current_folder, final_prefix, args.suffix, args.digits, args.keep, sorted_files)
    
    print("\nProcessing complete.")