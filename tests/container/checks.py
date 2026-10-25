"""Linux acceptance checks that run *inside* tests/container/Dockerfile.

Two stages, both non-interactive and bounded:

1. the committed smoke suite (`python -m unittest discover -s tests -v`);
2. the Linux column of the cross-platform sweep (one safe probe per script,
   same manifest as `.devteam/artifacts/sweep-crossplatform`), each in its own
   temp cwd so the image is never mutated and nothing leaks into the repo.

Output contract for tests/container/run.py:
  stderr -> human-readable summary
  stdout -> one line `###JSON###` followed by a JSON document
Exit code: 0 only when the suite passes and no probe is HANG/FAIL.
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
JSON_MARK = "###JSON###"

# Outcomes accepted for a probe: a working path, a documented dependency gap,
# or the tty preflight refusing to run without a terminal.
OK_LABELS = {"PASS", "USAGE", "PASS:tty-guard", "DEP", "SKIP"}


def kill(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run(cmd, cwd, timeout):
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, start_new_session=True)
    timed = False
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed = True
        kill(p)
        try:
            out, err = p.communicate(timeout=10)
        except Exception:
            out, err = b"", b""
    dec = lambda b: ANSI.sub("", b.decode("utf-8", "replace"))
    return dict(rc=p.returncode, timeout=timed,
                out=dec(out)[-1500:], err=dec(err)[-1500:])


def classify(result):
    if result.get("skipped"):
        return "SKIP"
    err = result.get("err") or ""
    out = result.get("out") or ""
    text = err + out
    if result.get("timeout"):
        return "HANG"
    if "UnicodeEncodeError" in err:
        return "FAIL:encoding"
    if "Traceback (most recent call last)" in err:
        return "FAIL:crash"
    if result.get("rc") == 0 and "Error scanning directory" in text:
        return "FAIL:silent"
    if result.get("rc") == 0:
        return "PASS"
    if result.get("rc") == 2 and "interactive terminal" in text:
        return "PASS:tty-guard"
    if "python3: command not found" in err or "No such file or directory" in err:
        return "FAIL:no-python3"
    if "Usage:" in text or "usage:" in text:
        return "USAGE"
    if "not installed" in text:
        return "DEP"
    return "rc{}".format(result.get("rc"))


def run_suite(timeout=600):
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    print("[suite] " + " ".join(cmd), file=sys.stderr, flush=True)
    res = run(cmd, APP, timeout)
    combined = (res["out"] + res["err"]).strip()
    ok = res["rc"] == 0 and not res["timeout"] and "Ran " in combined
    print(combined, file=sys.stderr, flush=True)
    return dict(ok=ok, rc=res["rc"], timeout=res["timeout"],
                tail=combined[-4000:])


def run_sweep(manifest_path, timeout_scale=1.0):
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    results = []
    with tempfile.TemporaryDirectory(prefix="catro-probes-") as tmp:
        for item in manifest:
            name = item["name"]
            if item.get("skip"):
                results.append(dict(script=name, label="SKIP", why=item["why"]))
                continue
            cwd = os.path.join(tmp, name)
            os.makedirs(cwd, exist_ok=True)
            args = item["args"].split()
            cmd = ["/bin/bash", os.path.join(APP, "catro-scripts.sh"), name] + args
            timeout = 5 if name in ("keygen", "screensaver", "fakeserver") else (
                30 if name == "opencode" else 15)
            res = run(cmd, cwd, timeout * timeout_scale)
            res.update(script=name, args=item["args"], why=item["why"])
            res["label"] = classify(res)
            results.append(res)
            print("[sweep] {:<16} {:<14} rc={}".format(name, res["label"], res["rc"]),
                  file=sys.stderr, flush=True)
    return results


def run_extras_probe():
    """Prove the optional third-party libs actually work, not just import.

    The sweep cannot show this: every safe probe stops at the tty preflight or
    at --help, before Pillow/piexif/pydub are touched. Runs only in the extras
    layer, and writes exclusively inside a temp dir (the image is read-only).
    """
    from importlib import metadata
    doc = dict(ok=False, versions={}, error="", checks={})
    try:
        doc["versions"] = {pkg: metadata.version(pkg)
                           for pkg in ("pillow", "piexif", "pydub")}
        from PIL import Image
        import piexif
        from pydub import AudioSegment
    except Exception as exc:
        doc["error"] = repr(exc)
        return doc

    try:
        with tempfile.TemporaryDirectory(prefix="catro-extras-") as tmp:
            path = os.path.join(tmp, "probe.jpg")
            Image.new("RGB", (8, 8), (10, 20, 30)).save(path, "JPEG")
            exif = piexif.dump({"0th": {piexif.ImageIFD.Artist: b"catro-scripts"},
                                "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None})
            piexif.insert(exif, path)
            artist = piexif.load(path)["0th"].get(piexif.ImageIFD.Artist)
            doc["checks"]["pillow_jpeg"] = os.path.getsize(path) > 0
            doc["checks"]["piexif_roundtrip"] = artist == b"catro-scripts"
            doc["checks"]["pydub_silence"] = len(AudioSegment.silent(duration=50)) == 50
        doc["ok"] = all(doc["checks"].values())
    except Exception as exc:
        doc["error"] = repr(exc)
    return doc


def main():
    ap = argparse.ArgumentParser(description="Linux oracle checks for catro-scripts")
    ap.add_argument("--manifest", default=os.path.join(HERE, "manifest.json"))
    ap.add_argument("--no-suite", action="store_true", help="sweep only")
    ap.add_argument("--no-sweep", action="store_true", help="suite only")
    ap.add_argument("--label", default="", help="image label echoed into the JSON")
    ap.add_argument("--python-version", default="",
                    help="expected interpreter (major.minor[.patch]); empty = trust the image")
    ap.add_argument("--extras", default="unknown")
    args = ap.parse_args()

    suite = None if args.no_suite else run_suite()
    sweep = [] if args.no_sweep else run_sweep(args.manifest)
    extras_probe = run_extras_probe() if args.extras == "1" else None

    measured = ".".join(map(str, sys.version_info[:3]))
    version_match = not args.python_version or measured.startswith(
        args.python_version + ".")

    defects = [r for r in sweep if r["label"] not in OK_LABELS]
    counts = {}
    for r in sweep:
        counts[r["label"]] = counts.get(r["label"], 0) + 1

    ok = ((suite is None or suite["ok"]) and not defects
          and (extras_probe is None or extras_probe["ok"]) and version_match)
    doc = dict(label=args.label, python=args.python_version,
               python_measured=measured, version_match=version_match,
               extras=args.extras,
               image=os.environ.get("IMAGE_LABEL", ""),
               suite=suite, counts=counts, defects=[d["script"] for d in defects],
               extras_probe=extras_probe,
               results=sweep, ok=ok)

    print("\n[summary] python={} (measured {}) extras={} suite={} probes={} defects={}".format(
        args.python_version or "unchecked", measured, args.extras,
        "skipped" if suite is None else ("ok" if suite["ok"] else "FAILED"),
        len(sweep), len(defects)), file=sys.stderr, flush=True)
    if not version_match:
        print("[version] MISMATCH: asked for {}, image runs {}".format(
            args.python_version, measured), file=sys.stderr, flush=True)
    if extras_probe is not None:
        print("[extras] {} versions={} checks={} error={}".format(
            "ok" if extras_probe["ok"] else "FAILED",
            extras_probe["versions"], extras_probe["checks"],
            extras_probe["error"]), file=sys.stderr, flush=True)
    print("###JSON###")
    print(json.dumps(doc, indent=1, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
