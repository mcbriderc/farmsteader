#!/usr/bin/env bash
#
# Build the release tarball: dist/farmsteader-<version>.tar.gz plus a
# dist/SHA256SUMS entry.
#
# The archive comes from `git archive`, not `tar` over the working tree. That is
# the whole safety argument: the content is drawn from a tree object, so no
# untracked file, no .venv, no stray .env and no editor backup can be swept into
# a published artifact even if one is sitting in the directory. The exclusion
# list lives in .gitattributes as export-ignore.
#
# Two things are added afterwards, because neither is tracked: the compiled
# stylesheet (static/css/dist/ is git-ignored) and a VERSION file (generated, so
# it cannot drift from the tag).
#
# Usage: scripts/build-tarball.sh [version]
#        defaults to the version in config/__version__.py
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

die() { echo "build-tarball: $*" >&2; exit 1; }

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' config/__version__.py)}"
[ -n "$VERSION" ] || die "could not determine version"

PREFIX="farmsteader-${VERSION}"
DIST="dist"
TARBALL="${DIST}/${PREFIX}.tar.gz"
CSS="static/css/dist/styles.css"

mkdir -p "$DIST"

echo "==> Building stylesheet"
bash scripts/build-css.sh
[ -s "$CSS" ] || die "$CSS missing or empty after build"

echo "==> Archiving tracked content at HEAD"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git archive --format=tar --prefix="${PREFIX}/" HEAD > "${WORK}/base.tar"

echo "==> Adding generated files"
# Staged under the archive prefix so tar --append places them at the right paths.
mkdir -p "${WORK}/stage/${PREFIX}/$(dirname "$CSS")"
printf '%s\n' "$VERSION" > "${WORK}/stage/${PREFIX}/VERSION"
cp "$CSS" "${WORK}/stage/${PREFIX}/${CSS}"

# Reproducibility: identical inputs should give a byte-identical tarball, so a
# rebuild can be checked against a published checksum. Ownership and mtime are
# the usual sources of noise -- mtime is pinned to the commit date rather than
# now, and gzip -n omits its own timestamp header.
SOURCE_EPOCH="$(git log -1 --format=%ct HEAD)"
tar --append --file="${WORK}/base.tar" \
    --directory="${WORK}/stage" \
    --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime="@${SOURCE_EPOCH}" \
    "${PREFIX}/VERSION" "${PREFIX}/${CSS}"

gzip -9nc "${WORK}/base.tar" > "$TARBALL"

# --- Assertions -------------------------------------------------------------
#
# These live in the script rather than in the workflow so that a local build and
# a CI build are held to the same standard, and so `bash scripts/build-tarball.sh`
# on a laptop catches a packaging mistake before it is ever published.
echo "==> Verifying archive"
contents="$(tar tzf "$TARBALL")"

grep -qx "${PREFIX}/VERSION" <<<"$contents" \
    || die "VERSION missing from archive"
grep -qx "${PREFIX}/${CSS}" <<<"$contents" \
    || die "compiled stylesheet missing from archive"
grep -qx "${PREFIX}/manage.py" <<<"$contents" \
    || die "manage.py missing from archive -- is HEAD what you think it is?"

# Legal, not cosmetic. AGPL section 4 requires the licence to be conveyed with
# the program, and the vendored Leaflet/Alpine/Turf copies are MIT/BSD, which
# require their notices to accompany a redistribution. A tarball missing either
# is one we must not publish, so this fails the build rather than warning.
grep -qx "${PREFIX}/LICENSE" <<<"$contents" \
    || die "LICENSE missing from archive -- AGPL-3.0 requires it to ship"
grep -qx "${PREFIX}/THIRD-PARTY-NOTICES.md" <<<"$contents" \
    || die "THIRD-PARTY-NOTICES.md missing from archive -- vendored MIT/BSD notices must ship"

# Exactly one top-level directory: installers extract with a known prefix and
# `cd` into it, so a second root would silently break them.
roots="$(cut -d/ -f1 <<<"$contents" | sort -u)"
[ "$(wc -l <<<"$roots")" -eq 1 ] && [ "$roots" = "$PREFIX" ] \
    || die "expected a single root directory named $PREFIX, got: $(tr '\n' ' ' <<<"$roots")"

# Nothing that should never be published. export-ignore is what keeps these out;
# this is the check that the export-ignore rules actually took effect.
#
# Note the anchors: `\.env$` must not also match `.env.example`, which ships on
# purpose because the installers reference it.
leak_re="^${PREFIX}/(\.git|\.venv|tests|scripts|\.forgejo|\.idea)/"
leak_re+="|(^|/)(\.env|coverage\.xml|db\.sqlite3|sonar-project\.properties)\$"
leak_re+="|(^|/)(__pycache__|\.pytest_cache|node_modules)/"
leak_re+="|\.(pyc|pyo)\$"

if leaked="$(grep -E "$leak_re" <<<"$contents" || true)"; [ -n "$leaked" ]; then
    # shellcheck disable=SC2001  # per-line prefix; parameter expansion cannot
    die "archive contains files that must not ship:
$(sed 's/^/  /' <<<"$leaked")"
fi

# --- Checksum ---------------------------------------------------------------
#
# Rewritten rather than appended, so rebuilding a version twice cannot leave two
# conflicting lines for the same file -- `sha256sum -c` would then verify the
# stale one and pass against the wrong bytes.
SUMS="${DIST}/SHA256SUMS"
if [ -f "$SUMS" ]; then
    grep -v " ${PREFIX}.tar.gz\$" "$SUMS" > "${SUMS}.tmp" || true
    mv "${SUMS}.tmp" "$SUMS"
fi
(cd "$DIST" && sha256sum "${PREFIX}.tar.gz") >> "$SUMS"
sort -k2 -o "$SUMS" "$SUMS"

echo
echo "==> Built $TARBALL"
echo "    version : $VERSION"
echo "    size    : $(du -h "$TARBALL" | cut -f1)"
echo "    files   : $(wc -l <<<"$contents")"
echo "    sha256  : $(grep " ${PREFIX}.tar.gz\$" "$SUMS" | cut -d' ' -f1)"
