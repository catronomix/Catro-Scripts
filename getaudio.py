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
	- ffmpeg and ffprobe must be available: in the system PATH, or placed next
	  to this script (getaudio.py).

Exit status:
	0 = every requested file was processed.
	1 = a required binary is missing, or at least one file failed.
"""

import os
import sys
import subprocess
import argparse
import json

import tui

# Extensions to look for when using --all
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.m4v'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.opus', '.wma'}
ALL_EXTENSIONS = VIDEO_EXTENSIONS.union(AUDIO_EXTENSIONS)

def get_bin_path(name):
    """Returns the path to a binary, prioritizing the script's directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(script_dir, name)
    if os.name == 'nt' and not local_path.lower().endswith('.exe'):
        local_path += '.exe'
    if os.path.exists(local_path) and os.access(local_path, os.X_OK):
        return local_path
    return name

FFMPEG_BIN = get_bin_path('ffmpeg')
FFPROBE_BIN = get_bin_path('ffprobe')

def check_bin(binary):
    """Checks if a binary is available in the system path or program dir."""
    try:
        subprocess.run([binary, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False

def check_requirements(cap=None):
    """Preflights ffmpeg/ffprobe; returns False and reports what is missing."""
    cap = cap or tui.detect()
    missing = [name for name, binary in (('ffmpeg', FFMPEG_BIN), ('ffprobe', FFPROBE_BIN))
               if not check_bin(binary)]
    if not missing:
        return True
    print(tui.style(f"Error: {' and '.join(missing)} not installed or not found. "
                    "Place the binary in the script folder or add it to PATH.",
                    fg="error", cap=cap), file=sys.stderr)
    return False

def _error_tail(stderr, fallback):
    """Returns the last non-empty stderr line, or fallback when there is none."""
    if isinstance(stderr, bytes):
        stderr = stderr.decode('utf-8', 'replace')
    lines = [line.strip() for line in (stderr or '').splitlines() if line.strip()]
    return lines[-1] if lines else fallback

def _unknown_info():
    """Safe probe defaults used when ffprobe cannot describe the file."""
    return {'codec': 'unknown', 'sample_rate': '44100', 'bit_rate': '128000', 'channels': 2}

def get_audio_info(filepath, cap=None):
    """Probes the file using ffprobe to get current audio properties."""
    cap = cap or tui.detect()
    # Use -select_streams a to get any audio stream, and include format info
    cmd = [
        FFPROBE_BIN, '-v', 'quiet', '-print_format', 'json', 
        '-show_streams', '-show_format', '-select_streams', 'a', filepath
    ]
    # A probe fault must not be confused with "this file has no audio": report it
    # once on stderr and hand the caller opaque defaults so it still tries to
    # process the file instead of skipping it.
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        print(tui.style(f"Warning: could not run {os.path.basename(FFPROBE_BIN)}: "
                        f"{_error_tail(getattr(exc, 'stderr', None), exc)}",
                        fg="warn", cap=cap), file=sys.stderr)
        return _unknown_info()

    if result.returncode != 0:
        print(tui.style(f"Warning: {os.path.basename(FFPROBE_BIN)} could not probe "
                        f"{os.path.basename(filepath)}: "
                        f"{_error_tail(result.stderr, f'exit status {result.returncode}')}",
                        fg="warn", cap=cap), file=sys.stderr)
        return _unknown_info()

    try:
        data = json.loads(result.stdout.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        print(tui.style(f"Warning: could not read {os.path.basename(FFPROBE_BIN)} output "
                        f"for {os.path.basename(filepath)}", fg="warn", cap=cap),
              file=sys.stderr)
        return _unknown_info()

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

def prompt_codec_settings(defaults, cap=None):
    """Interactive menu for codec settings."""
    # Prompts come from tui.prompts: blank input yields the default there, so
    # the menu keeps its "press enter for the suggested value" behaviour.
    cap = cap or tui.detect()
    print()
    print(tui.section("Audio Encoding Settings", cap=cap))

    formats = {
        '1': ('mp3', 'libmp3lame', '.mp3'),
        '2': ('aac', 'aac', '.m4a'),
        '3': ('wav', 'pcm_s16le', '.wav'),
        '4': ('flac', 'flac', '.flac')
    }

    print(tui.style("Select Target Format:", fg="fg", cap=cap))
    for k, v in formats.items():
        print(f"  {k}. {v[0]}")

    choice = tui.ask_text("Choice (default=wav): ", '3')
    fmt_name, codec, ext = formats.get(choice, formats['3'])

    sample_rate = tui.ask_text(
        f"Sample rate (default={defaults['sample_rate']}): ", defaults['sample_rate'])
    
    bit_settings = {}
    if fmt_name in ['mp3', 'aac']:
        # Estimate default bitrate
        try:
            source_br = int(defaults.get('bit_rate', 192000))
            default_br = "320k" if source_br > 320000 else "192k"
        except (ValueError, TypeError):
            default_br = "192k"
            
        br = tui.ask_text(f"Bitrate (e.g., 128k, 192k, 320k) [default={default_br}]: ",
                          default_br)
        bit_settings = ['-b:a', br]
    elif fmt_name == 'wav':
        print(tui.style("Select Bit Depth:\n  1. 16-bit\n  2. 24-bit\n  3. 32-bit",
                        fg="fg", cap=cap))
        depth = tui.ask_text("Choice (default=1): ", '1')
        depth_map = {'1': 'pcm_s16le', '2': 'pcm_s24le', '3': 'pcm_s32le'}
        codec = depth_map.get(depth, 'pcm_s16le')

    return {
        'codec': codec,
        'ext': ext,
        'sample_rate': sample_rate,
        'extra_args': bit_settings
    }

def process_file(file_path, args, codec_settings, index=0, cap=None):
    """Extracts or converts one file; True when handled (processed or skipped)."""
    cap = cap or tui.detect()
    info = get_audio_info(file_path, cap)

    # If we aren't re-encoding and can't find a stream, we must skip
    if not info and not codec_settings:
        print(tui.style(f"[Skip] Could not find audio stream in: {file_path}",
                        fg="warn", cap=cap))
        return True

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

    cmd = [FFMPEG_BIN, '-i', file_path, '-vn']
    
    if codec_settings:
        cmd += ['-acodec', codec_settings['codec'], '-ar', codec_settings['sample_rate']]
        if codec_settings['extra_args']:
            cmd += codec_settings['extra_args']
    else:
        # If we failed to probe but didn't choose a codec, we try to copy as a last resort
        cmd += ['-acodec', 'copy']

    cmd.append(out_path)

    print(tui.style(f"[Processing] {os.path.basename(file_path)} -> "
                    f"{os.path.basename(out_path)}", fg="accent", cap=cap))
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, OSError) as exc:
        encode_error = _error_tail(getattr(exc, 'stderr', None), exc)

    # Only a stream copy gets a second chance; an explicit codec choice is final.
    if codec_settings:
        print(tui.style(f"  - Error: could not convert {os.path.basename(file_path)}: "
                        f"{encode_error}", fg="error", cap=cap), file=sys.stderr)
        return False

    print(tui.style("  - Stream copy failed. Falling back to AAC re-encoding...",
                    fg="warn", cap=cap))
    out_path = os.path.splitext(out_path)[0] + ".m4a"
    out_path = get_unique_filename(out_path)
    cmd = [FFMPEG_BIN, '-i', file_path, '-vn', '-acodec', 'aac', out_path]
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, OSError) as exc:
        print(tui.style(f"  - Error: could not extract audio from "
                        f"{os.path.basename(file_path)}: "
                        f"{_error_tail(getattr(exc, 'stderr', None), exc)}",
                        fg="error", cap=cap), file=sys.stderr)
        return False

def main(argv=None):
    # One capability record for the run: colour level, glyphs and pipe mode.
    tui.init_ansi()
    cap = tui.detect()

    parser = argparse.ArgumentParser(description="Extract or convert audio.")
    parser.add_argument('files', nargs='*', help="List of files to process.")
    parser.add_argument('-a', '--all', action='store_true', help="Process all supported files in working directory.")
    parser.add_argument('-e', '--ext', help="Process all files with specific extension.")
    parser.add_argument('-d', '--dir', action='store_true', help="Process subdirectories.")
    parser.add_argument('-c', '--codec', action='store_true', help="Interactive codec settings.")
    parser.add_argument('-o', '--output', help="Custom output filename.")
    parser.add_argument('-p', '--prefix', help="Prefix for output.")
    parser.add_argument('-s', '--suffix', help="Suffix for output.")
    
    args = parser.parse_args(argv)
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
        print(tui.style("No valid files found to process.", fg="warn", cap=cap))
        return 0

    # Nothing below can work without both binaries, so fail once and clearly.
    if not check_requirements(cap):
        return 1

    # Automatically imply -c if audio files are present
    if has_audio_input and not args.codec:
        print(tui.style("Audio files detected. Enabling interactive conversion mode.",
                        fg="muted", cap=cap))
        args.codec = True

    codec_settings = None
    if args.codec:
        # Use first file to get default probe info, but provide safe fallback if probe fails
        first_info = get_audio_info(files_to_process[0], cap) or {'sample_rate': '44100', 'bit_rate': '192000'}
        codec_settings = prompt_codec_settings(first_info, cap)

    print(tui.style(f"Found {len(files_to_process)} file(s). Starting...",
                    fg="header", cap=cap))

    failures = 0
    for i, file_path in enumerate(files_to_process):
        if not process_file(file_path, args, codec_settings, index=i, cap=cap):
            failures += 1

    print()
    print(tui.style("Done.", fg="success", cap=cap))
    if failures:
        print(tui.style(f"{failures} file(s) failed.", fg="error", cap=cap),
              file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())