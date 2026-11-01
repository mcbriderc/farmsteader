#!/usr/bin/env bash
#
# Build the container image from the release tarball.
#
# The build context is the unpacked tarball, not this checkout, so the image
# holds exactly what a release ships and none of the personal or development
# files sitting in the repo. See the header of deploy/container/Containerfile.
#
# Usage: scripts/build-image.sh [version]
#        defaults to the version in config/__version__.py
#
# Tags the result farmsteader:<version>. Uses podman, or whatever IMAGE_BUILDER
# names (CI sets buildah); both take the same `build` arguments.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

die() { echo "build-image: $*" >&2; exit 1; }

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' config/__version__.py)}"
[ -n "$VERSION" ] || die "could not determine version"
BUILDER="${IMAGE_BUILDER:-podman}"

bash scripts/build-tarball.sh "$VERSION"

CONTEXT="$(mktemp -d)"
trap 'rm -rf "$CONTEXT"' EXIT
tar -xzf "dist/farmsteader-${VERSION}.tar.gz" -C "$CONTEXT" --strip-components=1

echo "==> Building farmsteader:${VERSION} with ${BUILDER}"
"$BUILDER" build \
    --build-arg "VERSION=${VERSION}" \
    --tag "farmsteader:${VERSION}" \
    --file "$CONTEXT/deploy/container/Containerfile" \
    "$CONTEXT"
