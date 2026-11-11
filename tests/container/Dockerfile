# syntax=docker/dockerfile:1
# One file, two images for catro-scripts. Both are built from the same context
# (the repository root) and the same interpreter argument.
#
#   dev stage  - interactive Linux workspace for agents and humans. The project
#                (or the current git worktree) is bind-mounted at /work by
#                tests/container/dev.py; this stage only supplies the tools.
#   test stage - the acceptance oracle. Sources are COPYed in, it runs
#                non-interactive checks and is the default build target.
#
# Build the test matrix (tests/container/run.py does this for you):
#   docker build -f tests/container/Dockerfile --target test \
#     --build-arg PYTHON_VERSION=3.12 --build-arg EXTRAS="" \
#     -t catro-scripts-test:3.12-base .
#
# Build the dev image (tests/container/dev.py does this for you):
#   docker build -f tests/container/Dockerfile --target dev \
#     --build-arg PYTHON_VERSION=3.12 -t catro-scripts-dev:3.12 .
#
# Shared build-arg contract (tools/devcontainer.py in the dev-team skill):
#   --build-arg PYTHON_VERSION=3.12
#   --build-arg EXTRAS="pillow piexif pydub"   test stage; empty = stdlib
#   --build-arg DEV_EXTRAS="pillow piexif pydub"  dev stage; empty = stdlib
#   --build-arg ENTRYPOINTS="name=target"      newline-separated dev shims
# decord (no cp311/cp312 manylinux wheel) and ffmpeg (system binary) are
# deliberately not installed in either stage; see tests/container/README.md.
#
# mounts, not COPY, for dev: edits on the host are live in the container and
# nothing the container writes lands anywhere except the mounted project and
# its own temp space.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# dev: interactive workspace, no project baked in
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS dev

ARG PYTHON_VERSION=3.12
ARG DEV_EXTRAS="pillow piexif pydub"
ARG ENTRYPOINTS="catro-scripts=/work/catro-scripts.sh"

LABEL org.opencontainers.image.title="catro-scripts linux dev container"
LABEL org.opencontainers.image.description="bind-mount workspace with bash, git, less, nano and the catro-scripts shim"
LABEL dev.python-version="${PYTHON_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    HOME=/home/dev \
    GIT_OPTIONAL_LOCKS=0

# bash is already in the slim image; git for history/diff, less + nano so a
# human can actually read and edit the mount. No compilers, no curl, no ssh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        less \
        nano \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Optional libraries; the project lists them in container.extras. Empty means
# a stdlib-only playground.
RUN if [ -n "$DEV_EXTRAS" ]; then \
        pip install --no-cache-dir $DEV_EXTRAS; \
    fi

# A bind mount carries whatever uid the host uses. Create a world-writable home
# so a mapped non-root uid still has a writable HOME, and let git trust the
# mount instead of failing with "dubious ownership".
RUN mkdir -p /home/dev \
    && chmod 0777 /home/dev \
    && git config --system --add safe.directory '*'

# `catro-scripts <script>` must work from any cwd, not just ./catro-scripts.sh.
# The shim is deliberately thin: the wrapper resolves the repo from its own
# path, so it keeps working wherever the mount lives. ENTRYPOINTS carries the
# same contract as the shared template; the default keeps a hand-run
# `docker build` useful.
RUN if [ -n "$ENTRYPOINTS" ]; then \
        printf '%s\n' "$ENTRYPOINTS" | while IFS='=' read -r name target; do \
            [ -n "$name" ] || continue; \
            printf '#!/bin/sh\nexec %s "$@"\n' "$target" > "/usr/local/bin/$name"; \
            chmod 0755 "/usr/local/bin/$name"; \
        done; \
    fi

WORKDIR /work

# Root by default so a Windows/Docker Desktop bind mount stays writable. On a
# POSIX host, tests/container/dev.py maps the invoking uid/gid instead. Both
# routes are documented in tests/container/README.md.
CMD ["sleep", "infinity"]

# ---------------------------------------------------------------------------
# test: acceptance oracle (default target; sources baked in, non-root)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS test

ARG PYTHON_VERSION=3.12
ARG EXTRAS=""

LABEL org.opencontainers.image.title="catro-scripts linux test oracle"
LABEL org.opencontainers.image.description="stdlib (+optional third-party) image used to run tests/ and the Linux sweep"
LABEL test.python-version="${PYTHON_VERSION}"
LABEL test.extras="${EXTRAS}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY . /app

# Optional extras layer. Keep this list to wheel-installable, no-native-build
# packages; anything skipped is documented in tests/container/README.md.
RUN if [ -n "$EXTRAS" ]; then \
        pip install --no-cache-dir $EXTRAS; \
    fi

# Non-root; /app must stay readable, /tmp writable (probes run in temp dirs).
RUN useradd --create-home --uid 10001 tester \
    && chown -R tester:tester /app

USER tester

ENTRYPOINT ["python", "tests/container/checks.py"]
