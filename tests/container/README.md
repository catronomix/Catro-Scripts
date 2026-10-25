# Linux containers for catro-scripts

Two things live here, both driven from the host and both built from the same
`Dockerfile`:

| script | image stage | purpose |
|---|---|---|
| `run.py` | `test` | non-interactive acceptance oracle: builds 3.11/3.12 x stdlib/extras, runs the smoke suite and the Linux sweep, exits with a CI code |
| `dev.py` | `dev` | long-lived workspace: bind-mounts the checkout/worktree you are in at `/work`, gives you `catro-scripts`, bash, git, less, nano |

WSL is not a target. Windows is covered natively by the smoke suite; Linux is
covered by these containers.

## Dev container (agents and humans)

```bash
python tests/container/dev.py up        # build if needed, start detached
python tests/container/dev.py shell     # interactive bash, cwd = /work
python tests/container/dev.py run -- python -m unittest discover -s tests
python tests/container/dev.py run -- catro-scripts list
python tests/container/dev.py status    # this repo's containers + mounts
python tests/container/dev.py down      # this worktree only
python tests/container/dev.py down --all
```

Flags: `--python 3.11` (default 3.12), `--build` (rebuild the image) and
`--no-extras` (stdlib-only image, no pillow/piexif/pydub) belong to `up` and
`ci`;
`--cwd <dir>` works on every dev-container subcommand and mounts that
checkout/worktree instead of the current cwd - useful before this file exists in
`main`, or from a wrapper script reporting on a different worktree. `ci` has no
mount, so it has no `--cwd`.

The wrapper carries a fallback copy of this project's container settings in code
(`PROJECT` in `tests/container/dev.py`): `tests/container/Dockerfile`, python
3.12, the `catro-scripts-dev` image prefix, `catro-dev` container names,
`catro.dev` labels, the `catro-scripts` shim, the optional
`pillow`/`piexif`/`pydub` extras and the CI default (the image's own
entrypoint). They normally come from `.devteam/config.json` - the one `.devteam/`
file that is tracked, so a clone carries them; the code copy covers the case
where the file is missing. `--python` and `--no-extras` override both.

`up` is idempotent and self-correcting: a running container is reused, a stopped
one is started, and the container is recreated when the image was rebuilt
(`--build`) or the `--python` version changed - a container pins the image and
interpreter it was created from, so reuse would otherwise silently keep the old
one. `run` and `shell` resolve the container the same way (and recreate it if
`--python` disagrees with the label), so an agent loop only needs
`dev.py run -- <cmd>`; `--build` and `--no-extras` belong to `up` and `ci`.

How the mount is chosen:

- the root is `git rev-parse --show-toplevel` of the caller's cwd, so running
  from a worktree mounts that worktree, never the main checkout;
- the container is `catro-dev-<slug>-<sha1(path)[:8]>`, so parallel worktrees
  get independent containers and never collide;
- `run` and `shell` start the container if it is missing, and `docker start` it
  if it is stopped;
- every subcommand calls `docker version` first, so a dead daemon is a clear
  error instead of a bogus "no dev containers for ...".

Inside, `catro-scripts <script>` resolves through
`/usr/local/bin/catro-scripts` -> `/work/catro-scripts.sh`, so it works from any
cwd, not just the mount root. `git` works too: a normal checkout mounts its
`.git` read-write; a linked worktree has its `.git` file pointing at an absolute
host path, so `dev.py` mounts the shared git dir read-only at `/git-meta` and
sets `GIT_DIR`/`GIT_COMMON_DIR`/`GIT_WORK_TREE` for the container. Read-only git
(`status`, `diff`, `show`, `ls-files`) therefore works in a worktree; commits
must be made on the host, which is where the branch lives anyway.

### Root, mounts and side effects

- The container runs as **root** by default. On this Windows host a Docker
  Desktop bind mount stays writable either way, and most images expect root;
  the tradeoff is that files created inside the mount are owned by the host
  account through the Windows filesystem layer, so no host-visible ownership
  surprise appears. On a POSIX host, `dev.py` detects the invoking uid/gid and
  passes `--user <uid>:<gid>` instead, with a writable `/home/dev`, so files
  created in the mount belong to you.
- No `--privileged`, no docker socket, no host secrets or home directories:
  the only host paths are the project (read-write) and, for a worktree, the
  git directory (read-only).
- Capabilities are dropped (`--cap-drop ALL`, `no-new-privileges`).
- `down` removes the container; the bind mount means nothing else is left
  behind.
- The Docker CLI exports the client's `HOME` into `exec` sessions (a backslash
  path on Windows), which breaks git and some tools. `dev.py` pins
  `HOME=/home/dev` on every exec for that reason.
- The dev image is ~351 MB for 3.12 (`docker images`; 3.11 measures 361 MB),
  with git + perl the bulk of it above the 179 MB slim base; a cold build takes
  ~30-40 s, seconds when cached. Each interpreter has its own image, and one
  container per mount path: `--python` switches by recreating that container.

## Test oracle (CI)

```bash
python tests/container/run.py                  # default: 3.11 and 3.12, both layers
python tests/container/run.py --python 3.12    # one interpreter
python tests/container/run.py --extras 0       # acceptance gate only
python tests/container/run.py --no-build       # rerun with existing images
```

`dev.py ci` runs the image's default entrypoint (`checks.py`); pass `-- <args>`
for checks.py flags. run.py stays the matrix runner.

Results land in `.devteam/artifacts/container/` (untracked: `.devteam/` is
excluded through `.git/info/exclude`): `res-<python>-<layer>.json` plus
`summary.md`. Exit code is non-zero when the smoke suite fails, when a sweep
probe is `HANG` / `FAIL:*`, when the extras probe fails, or when the image
interpreter does not match the requested version.

### Two layers, one Dockerfile

| layer | build arg | contents | purpose |
|---|---|---|---|
| base | `EXTRAS=""` | `python:<version>-slim`, stdlib only | acceptance gate: every script must import cleanly, `--help`/usage must work, missing optional dependencies must produce a friendly message |
| extras | `EXTRAS="pillow piexif pydub"` | `+ pillow piexif pydub` | exercise the deep paths of the image/video/exif tools |

`decord` and `ffmpeg` are deliberately **not** installed: decord publishes no
cp311/cp312 manylinux wheel and ffmpeg is a system binary, so those scripts stay
ownership-gated (`--help` works, real runs print the dependency message). That
is documented rather than forced, per goal 3 in `.devteam/goals.md`.

Only wheel-installable, native-build-free packages belong in the extras layer.
`curses` is part of the CPython build on Linux, so `mdreader` is not an extra.

## What runs inside

`checks.py` (the image entrypoint) runs, in order:

1. `python -m unittest discover -s tests -v` - the committed smoke suite;
2. every non-`SKIP` probe of `manifest.json` through `./catro-scripts.sh`, each
   in its own temp cwd, bounded by a timeout, with the same classifications as
   the host sweep (`PASS`, `USAGE`, `PASS:tty-guard`, `DEP`, `SKIP`, plus the
   failing kinds). Non-interactive by construction: stdin is `/dev/null`;
3. in the extras layer only, a dependency probe that does real work with the
   third-party libs: Pillow writes and reopens a JPEG, piexif inserts and reads
   back an EXIF tag, pydub builds 50 ms of silence. The sweep cannot show the
   difference between the layers because every safe probe stops at the tty
   preflight or at `--help`, before those imports happen.

The container runs `--network none`, `--read-only` with a `/tmp` tmpfs, drops
capabilities and uses uid 10001, so it cannot reach the network and cannot write
to the image or the host. The source is copied into the image at build time
(never bind-mounted), so nothing is written back into the working tree.

`test_cs_index_is_lf` skips inside the image: `git` is intentionally absent and
`.git` is excluded from the build context. `test_tty_preflight_exit_2` also
skips `mdreader.py`: it auto-installs `rich`/`windows-curses` at import time, so
the suite only exercises it where both already import (tracker #0011). Run both
on the host instead.

Probes marked `"skip": true` in `manifest.json` are never executed; the flag is
deliberate data, not a keyword match on the `why` text.

## Commands behind the wrapper

```bash
docker build -f tests/container/Dockerfile --target test \
  --build-arg PYTHON_VERSION=3.12 --build-arg EXTRAS="" \
  -t catro-scripts-test:3.12-base .

docker run --rm --network none --read-only --tmpfs /tmp:rw,size=256m \
  --cap-drop ALL catro-scripts-test:3.12-base \
  --python-version 3.12 --extras 0
```

The dev container is the same idea with a mount instead of a COPY:

```bash
docker build -f tests/container/Dockerfile --target dev \
  --build-arg PYTHON_VERSION=3.12 -t catro-scripts-dev:3.12 .

docker run -d --name catro-dev-example --cap-drop ALL \
  --security-opt no-new-privileges -w /work \
  -v "$PWD:/work" catro-scripts-dev:3.12 sleep infinity

docker exec -it -e HOME=/home/dev -w /work catro-dev-example bash
```

`--python-version` is optional: omit it to trust whichever interpreter the image
carries (the measured version is always recorded as `python_measured`); pass it
and a mismatch fails the run instead of silently passing.

`.dockerignore` keeps `.git`, `.devteam`, caches, local data (`networks.json`,
`actions.json`), bundled Windows binaries and credential-shaped files (`.env*`,
`*.pem`, `*.key`, `netrc`) out of the context.

## Last verified

2026-10-25, Docker 29.9.1 (linux/amd64), host Windows 10:

| python | layer | suite | probes | HANG | FAIL | extras probe | build | image |
|---|---|---|---|---|---|---|---|---|
| 3.11 | base | ok (11 tests) | 33 | 0 | 0 | - | 3.4 s | 188.5 MB |
| 3.11 | extras | ok (11 tests) | 33 | 0 | 0 | ok | 6.1 s | 219.6 MB |
| 3.12 | base | ok (11 tests) | 33 | 0 | 0 | - | 2.9 s | 178.8 MB |
| 3.12 | extras | ok (11 tests) | 33 | 0 | 0 | ok | 5.7 s | 209.7 MB |

Measured interpreters: 3.11.17 and 3.12.15 (`python_measured` in the JSON, so a
tag that does not match the requested version fails the run).
Extras verified: pillow 13.0.0, piexif 1.1.3, pydub 0.25.1.

Dev container verified the same day: `catro-scripts-dev:3.12` is 351 MB
(`3.11` is 361 MB); from both a linked worktree and the main checkout,
`catro-scripts list` and `catro-scripts help list` exit 0, `python -m unittest
discover -s tests` is green (11 tests, mdreader skipped as documented in #0011),
`run -- bash -c 'exit 7'` returns 7, `run --python 3.11` recreates the container
and reports 3.11.17, a file written inside `/work` appears on the host with no
restart, `git status`/`ls-files`/`log` work in the worktree while
`touch /git-meta/x` fails with "Read-only file system", `up --build` recreates
the container, `down` removes only its own container, `down --all` removes the
rest. The transcript is `.devteam/artifacts/dev-container/proof.txt`.
