"""Regression tests for getaudio.py missing-binary and encode-failure handling.

Hermetic by default: the subprocess cases run with PATH="" so neither ffmpeg nor
ffprobe can resolve. Anything that needs a real ffmpeg is skipped with a reason
instead of silently passing.
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "getaudio.py"

sys.path.insert(0, str(REPO))


def child_env(path=""):
    """Returns an environment with a controlled PATH (and no bypass variables)."""
    env = os.environ.copy()
    env["PATH"] = path
    # Python needs its own directory on PATH on Windows for DLL resolution in
    # some layouts; keep the interpreter usable without exposing ffmpeg.
    env.pop("PYTHONPATH", None)
    return env


def run(args, cwd, env, script=SCRIPT):
    """Runs getaudio.py (or a copy of it) and returns the completed process."""
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )


class MissingBinaryTests(unittest.TestCase):
    """Issue #15: a missing ffmpeg/ffprobe must never produce a traceback."""

    def test_help_works_without_binaries(self):
        """--help is a pure argparse path and must not need ffmpeg or ffprobe."""
        proc = run(["--help"], REPO, child_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usage:", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)

    def test_missing_binaries_exit_1_with_hint(self):
        """No ffmpeg/ffprobe: one friendly stderr line, rc 1, no traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "clip.mp4"
            clip.write_bytes(b"not really a video")
            # Run a copy of the script: get_bin_path() also looks next to the
            # script, so an operator's local ffmpeg.exe would otherwise make
            # this "both binaries missing" case non-hermetic.
            script = Path(tmp) / "getaudio.py"
            shutil.copy2(SCRIPT, script)
            # getaudio.py renders through the sibling `tui` package, so the
            # copy carries its own sibling library instead of borrowing the
            # checkout's.
            shutil.copytree(REPO / "tui", Path(tmp) / "tui",
                            ignore=shutil.ignore_patterns("__pycache__"))
            proc = run(["clip.mp4", "-c"], tmp, child_env(), script=script)

        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, combined)
        self.assertNotIn("Traceback", combined)
        self.assertIn("not installed", proc.stderr)
        self.assertIn("ffmpeg", proc.stderr)
        self.assertIn("ffprobe", proc.stderr)
        # The hint tells the operator where to put the binary.
        self.assertIn("PATH", proc.stderr)
        self.assertIn("script folder", proc.stderr)
        # A missing probe is not "this file has no audio".
        self.assertNotIn("[Skip] Could not find audio stream", combined)

    def test_missing_ffprobe_only_is_named(self):
        """ffmpeg present, ffprobe missing: name ffprobe, claim nothing about audio."""
        import getaudio

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "clip.mp4").write_bytes(b"not really a video")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(getaudio, "FFMPEG_BIN", sys.executable), \
                        mock.patch.object(getaudio, "FFPROBE_BIN", "no-such-ffprobe"):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        rc = getaudio.main(["clip.mp4", "-c"])
            finally:
                os.chdir(cwd)

        self.assertEqual(rc, 1)
        self.assertIn("ffprobe", stderr.getvalue())
        self.assertNotIn("ffmpeg not installed", stderr.getvalue())
        self.assertNotIn("[Skip] Could not find audio stream", stdout.getvalue())


class EncodeFailureTests(unittest.TestCase):
    """A failing ffmpeg must be reported once, never raised at the user."""

    def test_copy_and_fallback_both_fail_exit_1(self):
        """ffmpeg 'present' but every call fails: one clear error, rc 1, no traceback."""
        import getaudio

        def fake_run(cmd, *args, **kwargs):
            if cmd[1] == "-version":
                return subprocess.CompletedProcess(cmd, 0, b"", b"")
            if "-print_format" in cmd:  # probe: real failure semantics, rc 1
                return subprocess.CompletedProcess(cmd, 1, b"", b"invalid data")
            raise subprocess.CalledProcessError(
                1, cmd, output=b"", stderr=b"boom: encoder not found"
            )

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "clip.mp4").write_bytes(b"not really a video")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(getaudio.subprocess, "run", fake_run):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        rc = getaudio.main(["clip.mp4"])
            finally:
                os.chdir(cwd)

        out, err = stdout.getvalue(), stderr.getvalue()
        combined = out + err
        self.assertEqual(rc, 1, combined)
        self.assertNotIn("Traceback", combined)
        self.assertIn("boom: encoder not found", err)
        self.assertIn("Stream copy failed", out)
        self.assertIn("1 file(s) failed.", err)

    def test_copy_fails_but_aac_fallback_succeeds_exit_0(self):
        """Unchanged behaviour: a successful AAC fallback is rc 0 with an output file."""
        import getaudio

        def fake_run(cmd, *args, **kwargs):
            if cmd[1] == "-version":
                return subprocess.CompletedProcess(cmd, 0, b"", b"")
            if "-print_format" in cmd:  # probe: one audio stream
                payload = (
                    b'{"streams": [{"codec_name": "aac", "sample_rate": "48000",'
                    b' "bit_rate": "128000", "channels": 2}]}'
                )
                return subprocess.CompletedProcess(cmd, 0, payload, b"")
            if "copy" in cmd:  # stream copy is not possible for this file
                raise subprocess.CalledProcessError(1, cmd, output=b"", stderr=b"copy failed")
            Path(cmd[-1]).write_bytes(b"encoded")  # the AAC fallback succeeds
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "clip.mp4").write_bytes(b"not really a video")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(getaudio.subprocess, "run", fake_run):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        rc = getaudio.main(["clip.mp4"])
            finally:
                os.chdir(cwd)

            outputs = sorted(p.name for p in Path(tmp).iterdir() if p.name != "clip.mp4")

        self.assertEqual(rc, 0, stderr.getvalue())
        self.assertIn("Stream copy failed. Falling back to AAC re-encoding...", stdout.getvalue())
        self.assertIn("Done.", stdout.getvalue())
        self.assertEqual(outputs, ["clip.m4a"])


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "needs a real ffmpeg and ffprobe on PATH",
)
class SuccessfulRunTests(unittest.TestCase):
    """Behaviour that must not change: naming, stdout lines, rc 0."""

    def test_stream_copy_run_keeps_names_and_rc_0(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as work:
            source = Path(src) / "clip.mkv"
            make = subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=32x32:rate=5:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-shortest", str(source),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(make.returncode, 0, make.stderr)
            shutil.copy(source, Path(work) / "clip.mkv")

            proc = run(["clip.mkv"], work, child_env(os.environ.get("PATH", "")))

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("[Processing] clip.mkv -> clip.", proc.stdout)
            self.assertIn("Done.", proc.stdout)
            produced = [p for p in Path(work).iterdir() if p.name != "clip.mkv"]
            self.assertEqual(len(produced), 1, proc.stdout)
            self.assertGreater(produced[0].stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
