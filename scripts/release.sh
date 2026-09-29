#!/usr/bin/env bash
#
# Cut a release commit and tag locally.
#
#   scripts/release.sh 0.3.0
#
# Rewrites config/__version__.py, promotes the CHANGELOG's [Unreleased] section
# to the new version, commits, and tags.
#
# It never pushes. Pushing is what triggers the release workflow, which publishes
# to Forgejo and mirrors to a public GitHub repo -- an irreversible, outward
# facing act that should be a deliberate second command, not a side effect of
# running a version-bump helper. The push command is printed at the end.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

die() { echo "release: $*" >&2; exit 1; }

VERSION="${1:-}"
[ -n "$VERSION" ] || die "usage: scripts/release.sh <version>   (e.g. 0.3.0, 0.3.0-rc1)"

# Same grammar the release workflow gates the tag on. Checking it here means a
# malformed version is caught before a tag exists, rather than after CI rejects
# it and the tag has to be deleted from two forges.
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    die "'$VERSION' is not a valid version (expected X.Y.Z or X.Y.Z-prerelease)"
fi

TAG="v${VERSION}"
VERSION_FILE="config/__version__.py"
CHANGELOG="CHANGELOG.md"
TODAY="$(date +%Y-%m-%d)"

# --- Preflight --------------------------------------------------------------

# Releases are cut from master, always. The release workflow publishes the
# tagged tree as a public snapshot and release; a tag made on a feature branch
# would publish a commit that is not on master, dragging unmerged work into a
# public release. Enforced rather than left as a convention, because
# the consequence only shows up after publication.
RELEASE_BRANCH="${FS_RELEASE_BRANCH:-master}"
branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" != "$RELEASE_BRANCH" ]; then
    die "releases are cut from '$RELEASE_BRANCH', but HEAD is on '$branch'.
  Merge first, or set FS_RELEASE_BRANCH=$branch if you really mean to."
fi

[ -z "$(git status --porcelain)" ] \
    || die "working tree is not clean -- commit or stash first:
$(git status --short | sed 's/^/  /')"

! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null \
    || die "tag ${TAG} already exists"

current="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$VERSION_FILE")"
[ -n "$current" ] || die "could not parse the current version from $VERSION_FILE"
[ "$current" != "$VERSION" ] || die "$VERSION_FILE is already at $VERSION"

# Decide what the changelog needs *before* touching anything. Validating up
# front is what keeps a rejected release from leaving a half-rewritten working
# tree behind -- which would then trip the clean-tree check above on the next
# attempt, reporting a confusing problem two steps removed from the real one.
if grep -q "^## \[${VERSION}\]" "$CHANGELOG"; then
    # Already written by hand -- the case for the first release, where the
    # section predates this script. Leave it alone rather than producing a
    # duplicate heading that the workflow's awk extraction would then split.
    promote_changelog=0
else
    promote_changelog=1
    body="$(awk '
        /^## \[Unreleased\]/ { grabbing = 1; next }
        /^## \[/ && grabbing  { exit }
        grabbing              { print }
    ' "$CHANGELOG")"

    # A release with no changelog entry is almost always a mistake, and it is
    # much cheaper to catch here than after the tag is public: the workflow
    # refuses to publish a version with no section, so this would fail anyway.
    [ -n "$(tr -d '[:space:]' <<<"$body")" ] \
        || die "the [Unreleased] section is empty -- nothing to release"
fi

echo "==> Releasing $current -> $VERSION"

# Everything below mutates tracked files. Restore them on any failure so a
# partial run never leaves the tree in a state the next run has to be talked
# out of.
rollback() { git checkout -- "$VERSION_FILE" "$CHANGELOG" 2>/dev/null || true; }
trap 'rollback' ERR

# --- Version module ---------------------------------------------------------
# Rewritten with the exact single-line form the CI gate greps for.
printf '%s\n' "$(sed "s/^__version__ = \".*\"$/__version__ = \"${VERSION}\"/" "$VERSION_FILE")" > "$VERSION_FILE"
[ "$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$VERSION_FILE")" = "$VERSION" ] \
    || die "failed to rewrite $VERSION_FILE"

# --- Changelog --------------------------------------------------------------
if [ "$promote_changelog" -eq 0 ]; then
    echo "==> CHANGELOG already has a [$VERSION] section, leaving it as-is"
else
    echo "==> Promoting [Unreleased] to [$VERSION] - $TODAY"
    # The blank line that followed [Unreleased] is deliberately left to flow
    # through: it becomes the separator under the new version heading, which is
    # what Keep a Changelog expects before the first ### section.
    awk -v ver="$VERSION" -v today="$TODAY" '
        /^## \[Unreleased\]/ {
            print "## [Unreleased]"
            print ""
            print "## [" ver "] - " today
            next
        }
        { print }
    ' "$CHANGELOG" > "${CHANGELOG}.tmp"
    mv "${CHANGELOG}.tmp" "$CHANGELOG"
fi

# Refresh the comparison links at the foot of the file so [Unreleased] points at
# the new tag instead of the previous one.
if grep -q "^\[Unreleased\]:" "$CHANGELOG"; then
    repo_url="$(sed -n 's|^\[Unreleased\]: \(https://[^/]*/[^/]*/[^/]*\)/compare/.*|\1|p' "$CHANGELOG")"
    if [ -n "$repo_url" ]; then
        sed -i \
            -e "s|^\[Unreleased\]: .*|[Unreleased]: ${repo_url}/compare/${TAG}...HEAD|" \
            "$CHANGELOG"
        grep -q "^\[${VERSION}\]:" "$CHANGELOG" \
            || printf '[%s]: %s/releases/tag/%s\n' "$VERSION" "$repo_url" "$TAG" >> "$CHANGELOG"
    fi
fi

# --- Commit and tag ---------------------------------------------------------
git add "$VERSION_FILE" "$CHANGELOG"
git commit -q -m "Release ${TAG}"

# Past the commit the rollback would be wrong -- it would discard committed
# content rather than restore it.
trap - ERR

# Annotated, not lightweight: the release workflow reads the tag, and annotated
# tags carry a date and author that a lightweight ref does not.
# Stops at a link-reference definition as well as the next heading: the newest
# version is the last ## section, so otherwise this runs to EOF and pulls the
# trailing [x.y.z]: https://... definitions into the tag annotation.
notes="$(awk -v ver="$VERSION" '
    $0 ~ "^## \\[" ver "\\]"                 { grabbing = 1; next }
    grabbing && (/^## \[/ || /^\[[^]]+\]: /) { exit }
    grabbing                                 { print }
' "$CHANGELOG")"
#
# --cleanup=verbatim matters: git's default strips every line beginning with
# '#', which would silently eat the "### Added" / "### Fixed" headings and
# leave an annotation that is just a list of unlabelled bullets.
git tag -a --cleanup=verbatim "$TAG" -m "FarmSteader ${TAG}
${notes}"

echo
echo "==> Committed and tagged ${TAG}"
echo
echo "Nothing has been pushed. To publish:"
echo
echo "    git push origin $(git rev-parse --abbrev-ref HEAD)"
echo "    git push origin ${TAG}"
echo
echo "To undo:"
echo
echo "    git tag -d ${TAG} && git reset --hard HEAD~1"
