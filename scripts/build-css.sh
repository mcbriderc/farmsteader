#!/usr/bin/env bash
#
# Build the Tailwind stylesheet by driving the standalone binary directly.
#
# Deliberately not `manage.py tailwind build`: that route boots Django, which
# means it needs SECRET_KEY, a parseable DATABASE_URL and -- because
# config.settings imports django.contrib.gis -- a working GDAL. None of that has
# anything to do with compiling CSS. Going straight to the binary is what lets
# the release job run in a bare debian:13-slim with no Python at all, and lets
# the container image build CSS in a stage that never sees the app's
# dependencies.
#
# Usage: scripts/build-css.sh [output-path]
set -Eeuo pipefail

# Pinned, not "latest". CI builds the stylesheet on every run and
# tests/test_theming.py asserts against the compiled output, so an upstream
# release must never be able to change what we ship without a commit.
TAILWIND_VERSION="4.3.3"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SRC_CSS="assets/css/input.css"
OUT_CSS="${1:-static/css/dist/styles.css}"
CACHE_DIR=".django_tailwind_cli"

die() { echo "build-css: $*" >&2; exit 1; }

# --- Guard against the pin drifting away from Django's copy -----------------
#
# django-tailwind-cli reads TAILWIND_CLI_VERSION from settings for `make
# tailwind`, and this script hardcodes its own. If they disagree, a developer's
# local build and the released artifact are compiled by different compilers --
# which is exactly the kind of difference nobody thinks to check.
settings_version="$(sed -n 's/^TAILWIND_CLI_VERSION = "\(.*\)"$/\1/p' config/settings/base.py)"
if [ -n "$settings_version" ] && [ "$settings_version" != "$TAILWIND_VERSION" ]; then
    die "version pin mismatch: base.py says $settings_version, this script says $TAILWIND_VERSION"
fi

# --- Work out which binary this machine needs -------------------------------
case "$(uname -s)" in
    Linux) os="linux" ;;
    Darwin) os="macos" ;;
    *) die "unsupported OS: $(uname -s)" ;;
esac

case "$(uname -m)" in
    x86_64 | amd64) arch="x64" ;;
    aarch64 | arm64) arch="arm64" ;;
    *) die "unsupported architecture: $(uname -m)" ;;
esac

# Alpine and friends need the musl build. Without this check the glibc binary
# downloads happily and then fails to exec with "no such file or directory",
# naming a file that is plainly right there -- one of the more baffling errors
# to land in a build log.
libc=""
# grep without -q: under pipefail, -q can exit before ldd finishes writing, and
# the SIGPIPE it hands ldd would fail the pipeline -- reporting "not musl" on
# exactly the systems that are.
if [ "$os" = "linux" ] && ldd --version 2>&1 | grep -i musl >/dev/null; then
    libc="-musl"
fi

asset="tailwindcss-${os}-${arch}${libc}"

# Upstream's own checksums, taken verbatim from
# https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/sha256sums.txt
# Replace every line in this block together with TAILWIND_VERSION above; a
# stale entry here fails closed (refuses to run) rather than silently building
# with an unverified compiler.
case "$asset" in
    tailwindcss-linux-x64)        expected_sha="dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a" ;;
    tailwindcss-linux-x64-musl)   expected_sha="a04d34ceacc8f52cbe8920ad846cdeb61d3d0021dba32db0d1f77c9d9fad7a6c" ;;
    tailwindcss-linux-arm64)      expected_sha="55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195" ;;
    tailwindcss-linux-arm64-musl) expected_sha="71ea4be79c9de9827545682df3e040053fb535d37c71ed2cfdedf9385a0868e0" ;;
    tailwindcss-macos-arm64)      expected_sha="cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9d" ;;
    tailwindcss-macos-x64)        expected_sha="7922e0953f2110c05976e3bf58f14e643d90427575e766b7d433f5f80cbee7e1" ;;
    *) die "no pinned checksum for $asset" ;;
esac

BIN="${CACHE_DIR}/${asset}-${TAILWIND_VERSION}"

# --- Download if we do not already have a verified copy ---------------------
if [ ! -x "$BIN" ]; then
    mkdir -p "$CACHE_DIR"
    url="https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/${asset}"
    echo "build-css: downloading $asset v$TAILWIND_VERSION"

    # Download to a temporary name and only move it into place once verified,
    # so an interrupted download cannot leave a truncated binary in the cache
    # that every later run treats as good.
    tmp="${BIN}.download.$$"
    trap 'rm -f "$tmp"' EXIT
    curl -fsSL --retry 3 --retry-delay 2 -o "$tmp" "$url" \
        || die "download failed: $url"

    echo "${expected_sha}  ${tmp}" | sha256sum -c - >/dev/null 2>&1 \
        || die "checksum mismatch for $asset -- refusing to use it
  expected $expected_sha
  actual   $(sha256sum "$tmp" | cut -d' ' -f1)"

    chmod +x "$tmp"
    mv "$tmp" "$BIN"
    trap - EXIT
fi

mkdir -p "$(dirname "$OUT_CSS")"

echo "build-css: $SRC_CSS -> $OUT_CSS"
exec "./$BIN" --input "$SRC_CSS" --output "$OUT_CSS" --minify
