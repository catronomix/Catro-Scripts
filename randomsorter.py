# Randomize filenames and distribute in subfolders
"""
            RANDOM FILE SORTER
            ------------------
This script renames and distributes files within the current working directory. 
It renames them to unique random identifiers (numbers or alphanumeric) to 
anonymize/shuffle them, and then moves/copies them into subfolders.

USAGE:
    1. Open a terminal/command prompt in the folder containing your files.
    2. Run the script followed by the number of files you want in each subfolder.
        Example: python randomsorter.py 10 5 20
        (If no numbers are provided, all matching files go into one subfolder)

OPTIONS:
    -d, --digits N     Number of digits/characters for the random name (default: 12)
    --scramble         Use random alphanumeric characters instead of just numbers
    -p, --prefix STR   Prefix for the subfolders (default: 'batch')
    -k, --keep         Keep original files in place (copy instead of move)
    -t, --type TYPE    Filter by 'image', 'video', or 'audio'
    -e, --ext EXT      Filter for a specific extension only
    -a, --all          Include all files, ignoring safety filters (requires confirmation)
"""

import os
import random
import argparse
import sys
import shutil
import string

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
        return [f for f in all_files if f.lower().endswith(allowed_extensions)]
    
    if not include_all:
        return [f for f in all_files if not f.lower().endswith(FORBIDDEN_EXTENSIONS)]
    
    return all_files

def generate_random_name(length, scramble):
    """Generates a random string of numbers or alphanumeric characters."""
    if scramble:
        chars = string.ascii_letters + string.digits
    else:
        chars = string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def distribute_files(folder_path, counts, allowed_extensions, include_all, prefix, keep, digit_count, scramble):
    """Shuffles, renames, and distributes files into subfolders."""
    files = get_target_files(folder_path, allowed_extensions, include_all)
    
    if not files:
        print("No matching files found. Nothing to do.")
        return

    random.shuffle(files)
    
    if not counts:
        counts = [len(files)]

    used_names = set()
    file_idx = 0

    for i, count in enumerate(counts):
        if file_idx >= len(files):
            break

        subfolder_name = f"{prefix}{i + 1:02d}"
        subfolder_path = os.path.join(folder_path, subfolder_name)
        
        os.makedirs(subfolder_path, exist_ok=True)
        print(f"\nProcessing {subfolder_name}...")
        
        for _ in range(count):
            if file_idx < len(files):
                filename = files[file_idx]
                extension = os.path.splitext(filename)[1]
                
                # Generate unique random name
                new_name = f"{generate_random_name(digit_count, scramble)}{extension}"
                while new_name in used_names or os.path.exists(os.path.join(subfolder_path, new_name)):
                    new_name = f"{generate_random_name(digit_count, scramble)}{extension}"
                
                used_names.add(new_name)
                old_path = os.path.join(folder_path, filename)
                new_dest_path = os.path.join(subfolder_path, new_name)

                if keep:
                    shutil.copy2(old_path, new_dest_path)
                    print(f"Copied: {filename} -> {subfolder_name}/{new_name}")
                else:
                    os.rename(old_path, new_dest_path)
                    print(f"Moved: {filename} -> {subfolder_name}/{new_name}")
                
                file_idx += 1
            else:
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename and distribute files into subfolders.")
    
    parser.add_argument("counts", metavar="N", type=int, nargs="*", 
                        help="Number of files per subfolder.")
    
    parser.add_argument("-e", "--ext", type=str, 
                        help="Filter for a specific extension only.")
    
    parser.add_argument("-t", "--type", type=str, choices=['image', 'video', 'audio'],
                        help="Filter by category: 'image', 'video', or 'audio'")

    parser.add_argument("-p", "--prefix", type=str, default="batch",
                        help="Prefix for the subfolders (default: 'batch')")

    parser.add_argument("-k", "--keep", action="store_true",
                        help="Keep original files in place (copy instead of move)")

    parser.add_argument("-d", "--digits", type=int, default=12,
                        help="Number of random digits/characters for the filename (default: 12)")

    parser.add_argument("--scramble", action="store_true",
                        help="Use alphanumeric characters for names instead of just numbers")

    parser.add_argument("-a", "--all", action="store_true",
                        help="Include all files, ignoring safety filters (requires confirmation)")
    
    args = parser.parse_args()

    if args.all:
        confirm = input("WARNING: You are using the --all flag. This will process system files and scripts.\nAre you sure? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            sys.exit()

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

    current_folder = os.getcwd()
    distribute_files(
        current_folder, args.counts, allowed, args.all, 
        args.prefix, args.keep, args.digits, args.scramble
    )
    
    print("\nProcessing complete.")