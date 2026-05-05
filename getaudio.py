# Extract or convert audio from video and audio files using ffmpeg
"""
			GET AUDIO (EXTRACTOR & CONVERTER)
			================================
A utility to extract audio from video files or convert existing audio files.
Supports batch processing, recursive scanning, and interactive re-encoding.

Usage:
	catro-scripts getaudio <files> [flags]

Flags:
	-a, --all      : Process all video/audio files in the working directory.
	-e, --ext      : Process all files with a specific extension (e.g., .mp4).
	-d, --dir      : Process all subdirectories in the working directory.
	-c, --codec    : Interactive menu to change codec, bit depth, and sample rate.
	-o, --output   : Set custom output filename (increments if multiple files).
	-p, --prefix   : Add prefix to output filename.
	-s, --suffix   : Add suffix to output filename.

Note: If audio files are provided as input, the -c flag is automatically implied.

Requirements:
	- ffmpeg must be installed and available in the system PATH.
"""

import os
import sys
import subprocess
import argparse
import json

# Extensions to look for when using --all
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.m4v'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.opus', '.wma'}
ALL_EXTENSIONS = VIDEO_EXTENSIONS.union(AUDIO_EXTENSIONS)

def get_audio_info(filepath):
    """Probes the file using ffprobe to get current audio properties."""
    # Use -select_streams a to get any audio stream, and include format info
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', 
        '-show_streams', '-show_format', '-select_streams', 'a', filepath
    ]
    try:
        result = subprocess.check_output(cmd).decode('utf-8')
        data = json.loads(result)
        
        # Priority 1: Use stream data
        if 'streams' in data and len(data['streams']) > 0:
            s = data['streams'][0]
            return {
                'codec': s.get('codec_name', 'unknown'),
                'sample_rate': s.get('sample_rate', '44100'),
                'bit_rate': s.get('bit_rate') or data.get('format', {}).get('bit_rate') or '128000',
                'channels': s.get('channels', 2)
            }
        # Priority 2: Use format data if streams are obscured
        elif 'format' in data:
            return {
                'codec': 'unknown',
                'sample_rate': '44100',
                'bit_rate': data['format'].get('bit_rate', '128000'),
                'channels': 2
            }
    except Exception:
        pass
    return None

def get_unique_filename(base_path):
    """If file exists, appends (2), (3), etc."""
    if not os.path.exists(base_path):
        return base_path
    
    directory = os.path.dirname(base_path)
    filename = os.path.basename(base_path)
    name, ext = os.path.splitext(filename)
    
    counter = 2
    while True:
        new_name = f"{name} ({counter}){ext}"
        new_path = os.path.join(directory, new_name)
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def prompt_codec_settings(defaults):
    """Interactive menu for codec settings."""
    print("\n--- Audio Encoding Settings ---")
    
    formats = {
        '1': ('mp3', 'libmp3lame', '.mp3'),
        '2': ('aac', 'aac', '.m4a'),
        '3': ('wav', 'pcm_s16le', '.wav'),
        '4': ('flac', 'flac', '.flac')
    }
    
    print("Select Target Format:")
    for k, v in formats.items():
        print(f"  {k}. {v[0]}")
    
    choice = input("Choice (default=wav): ").strip() or '3'
    fmt_name, codec, ext = formats.get(choice, formats['3'])

    sample_rate = input(f"Sample rate (default={defaults['sample_rate']}): ").strip() or defaults['sample_rate']
    
    bit_settings = {}
    if fmt_name in ['mp3', 'aac']:
        # Estimate default bitrate
        try:
            source_br = int(defaults.get('bit_rate', 192000))
            default_br = "320k" if source_br > 320000 else "192k"
        except (ValueError, TypeError):
            default_br = "192k"
            
        br = input(f"Bitrate (e.g., 128k, 192k, 320k) [default={default_br}]: ").strip() or default_br
        bit_settings = ['-b:a', br]
    elif fmt_name == 'wav':
        print("Select Bit Depth:\n  1. 16-bit\n  2. 24-bit\n  3. 32-bit")
        depth = input("Choice (default=1): ").strip() or '1'
        depth_map = {'1': 'pcm_s16le', '2': 'pcm_s24le', '3': 'pcm_s32le'}
        codec = depth_map.get(depth, 'pcm_s16le')

    return {
        'codec': codec,
        'ext': ext,
        'sample_rate': sample_rate,
        'extra_args': bit_settings
    }

def process_file(file_path, args, codec_settings, index=0):
    info = get_audio_info(file_path)
    
    # If we aren't re-encoding and can't find a stream, we must skip
    if not info and not codec_settings:
        print(f"[Skip] Could not find audio stream in: {file_path}")
        return

    # Determine base output name
    if args.output:
        out_name = f"{args.output}_{index}" if index > 0 else args.output
    else:
        out_name = os.path.splitext(os.path.basename(file_path))[0]

    # Apply prefix/suffix
    final_name = f"{args.prefix or ''}{out_name}{args.suffix or ''}"
    
    # Extension logic
    if codec_settings:
        target_ext = codec_settings['ext']
    else:
        # Fallback to .m4a if codec info is missing
        source_codec = info.get('codec', 'unknown') if info else 'unknown'
        ext_map = {'mp3': '.mp3', 'aac': '.m4a', 'flac': '.flac', 'vorbis': '.ogg', 'opus': '.opus'}
        target_ext = ext_map.get(source_codec, '.m4a')

    out_path = os.path.join(os.path.dirname(file_path), final_name + target_ext)
    
    # Prevent overwriting the source if converting in-place with same extension
    if out_path.lower() == file_path.lower():
        out_path = os.path.splitext(out_path)[0] + "_new" + target_ext

    out_path = get_unique_filename(out_path)

    cmd = ['ffmpeg', '-i', file_path, '-vn']
    
    if codec_settings:
        cmd += ['-acodec', codec_settings['codec'], '-ar', codec_settings['sample_rate']]
        if codec_settings['extra_args']:
            cmd += codec_settings['extra_args']
    else:
        # If we failed to probe but didn't choose a codec, we try to copy as a last resort
        cmd += ['-acodec', 'copy']

    cmd.append(out_path)

    print(f"[Processing] {os.path.basename(file_path)} -> {os.path.basename(out_path)}")
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    except subprocess.CalledProcessError:
        if not codec_settings:
            print("  - Stream copy failed. Falling back to AAC re-encoding...")
            out_path = os.path.splitext(out_path)[0] + ".m4a"
            out_path = get_unique_filename(out_path)
            cmd = ['ffmpeg', '-i', file_path, '-vn', '-acodec', 'aac', out_path]
            subprocess.run(cmd, check=True, stderr=subprocess.PIPE)

def main():
    parser = argparse.ArgumentParser(description="Extract or convert audio.")
    parser.add_argument('files', nargs='*', help="List of files to process.")
    parser.add_argument('-a', '--all', action='store_true', help="Process all supported files in working directory.")
    parser.add_argument('-e', '--ext', help="Process all files with specific extension.")
    parser.add_argument('-d', '--dir', action='store_true', help="Process subdirectories.")
    parser.add_argument('-c', '--codec', action='store_true', help="Interactive codec settings.")
    parser.add_argument('-o', '--output', help="Custom output filename.")
    parser.add_argument('-p', '--prefix', help="Prefix for output.")
    parser.add_argument('-s', '--suffix', help="Suffix for output.")
    
    args = parser.parse_args()
    files_to_process = []
    has_audio_input = False

    def is_audio(f):
        return os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS

    # Build file list
    if args.all or args.ext or args.dir:
        search_ext = args.ext.lower() if args.ext else None
        if search_ext and not search_ext.startswith('.'):
            search_ext = '.' + search_ext

        root_dir = os.getcwd()
        if args.dir:
            for root, _, files in os.walk(root_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if (search_ext and ext == search_ext) or (not search_ext and ext in ALL_EXTENSIONS):
                        files_to_process.append(os.path.join(root, f))
                        if ext in AUDIO_EXTENSIONS: has_audio_input = True
        else:
            for f in os.listdir(root_dir):
                if os.path.isfile(f):
                    ext = os.path.splitext(f)[1].lower()
                    if (search_ext and ext == search_ext) or (not search_ext and ext in ALL_EXTENSIONS):
                        files_to_process.append(os.path.abspath(f))
                        if ext in AUDIO_EXTENSIONS: has_audio_input = True
    
    for f in args.files:
        if os.path.exists(f):
            files_to_process.append(os.path.abspath(f))
            if is_audio(f): has_audio_input = True

    if not files_to_process:
        print("No valid files found to process.")
        return

    # Automatically imply -c if audio files are present
    if has_audio_input and not args.codec:
        print("Audio files detected. Enabling interactive conversion mode.")
        args.codec = True

    codec_settings = None
    if args.codec:
        # Use first file to get default probe info, but provide safe fallback if probe fails
        first_info = get_audio_info(files_to_process[0]) or {'sample_rate': '44100', 'bit_rate': '192000'}
        codec_settings = prompt_codec_settings(first_info)

    print(f"Found {len(files_to_process)} file(s). Starting...")

    for i, file_path in enumerate(files_to_process):
        process_file(file_path, args, codec_settings, index=i)

    print("\nDone.")

if __name__ == "__main__":
    main()