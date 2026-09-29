#!/usr/bin/env bash
#
# Publish a release to the public mirror as a single snapshot commit.
#
# The mirror is a distribution channel, not a copy of the development repo.
# Each release becomes one commit holding that release's files, minus the paths
# listed in .forgejo/mirror-exclude, parented on the previous release's
# snapshot. History, commit messages and excluded files never leave Forgejo.
#
# Why snapshots and not a filtered history: a filter has to anticipate every
# past version of every file and every commit message, and anything it misses
# is public for good. A snapshot publishes exactly one tree per release, which
# is the only thing that can be audited in advance.
#
# The commit is deterministic -- fixed identity, dates taken from the tagged
# commit, parent taken from the mirror -- so re-running a release rebuilds the
# same commit ID and the push is a no-op. A tag that already exists on the
# mirror is never moved: if its tree matches, this exits cleanly; if not, it
# fails rather than rewrite a published release.
#
# Pushes are fast-forward only. Nothing here ever force-pushes.
#
# Usage: scripts/publish-snapshot.sh <mirror-url> <tag> [branch]
#   Run from a checkout of the tagged commit.
set -Eeuo pipefail

MIRROR_URL="${1:?usage: publish-snapshot.sh <mirror-url> <tag> [branch]}"
TAG="${2:?usage: publish-snapshot.sh <mirror-url> <tag> [branch]}"
BRANCH="${3:-master}"
EXCLUDE_FILE=".forgejo/mirror-exclude"

die() { echo "publish-snapshot: $*" >&2; exit 1; }

[ -f "$EXCLUDE_FILE" ] || die "$EXCLUDE_FILE is missing; refusing to publish an unfiltered tree"

# One path per line; blank lines and # comments ignored.
mapfile -t exclude < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^$/d' "$EXCLUDE_FILE")
[ "${#exclude[@]}" -gt 0 ] || die "$EXCLUDE_FILE lists nothing; refusing to publish an unfiltered tree"

# --- Build the filtered tree in a private index -----------------------------
index="$(mktemp)"
trap 'rm -f "$index"' EXIT
export GIT_INDEX_FILE="$index"
git read-tree HEAD
git rm -r -q --cached --ignore-unmatch -- "${exclude[@]}"
tree="$(git write-tree)"
unset GIT_INDEX_FILE

# Belt and braces: prove the excluded paths are really gone from the tree.
for p in "${exclude[@]}"; do
    if [ -n "$(git ls-tree -r --name-only "$tree" -- "$p")" ]; then
        die "excluded path '$p' is still present in the snapshot tree"
    fi
done

# --- Inspect the mirror ------------------------------------------------------
remote_tag="$(git ls-remote "$MIRROR_URL" "refs/tags/$TAG" | cut -f1)"
if [ -n "$remote_tag" ]; then
    git fetch -q "$MIRROR_URL" "refs/tags/$TAG"
    if [ "$(git rev-parse 'FETCH_HEAD^{tree}')" = "$tree" ]; then
        echo "publish-snapshot: $TAG is already on the mirror with this exact tree; nothing to do"
        exit 0
    fi
    die "$TAG already exists on the mirror with different content; published tags are never moved"
fi

parent=()
remote_head="$(git ls-remote "$MIRROR_URL" "refs/heads/$BRANCH" | cut -f1)"
if [ -n "$remote_head" ]; then
    git fetch -q "$MIRROR_URL" "refs/heads/$BRANCH"
    parent=(-p "$(git rev-parse FETCH_HEAD)")
fi

# --- Commit and push ---------------------------------------------------------
# A neutral identity, so no personal address is published, and the tagged
# commit's date, so the same release always yields the same commit ID.
date="$(git log -1 --format=%cI HEAD)"
export GIT_AUTHOR_NAME="FarmSteader Releases" GIT_AUTHOR_EMAIL="releases@farmsteader.invalid"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
export GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date"

commit="$(printf 'FarmSteader %s\n\nSource snapshot of release %s.\n' "$TAG" "$TAG" \
    | git commit-tree "$tree" "${parent[@]}")"

git push -q --atomic "$MIRROR_URL" "$commit:refs/heads/$BRANCH" "$commit:refs/tags/$TAG"
echo "publish-snapshot: published $TAG as $commit (tree $tree)"
