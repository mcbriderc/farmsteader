#!/usr/bin/env bash
#
# Upgrade an existing FarmSteader install in place:
#
#   sudo /opt/farmsteader/current/deploy/update.sh              # to the latest release
#   sudo /opt/farmsteader/current/deploy/update.sh --version 0.3.0
#
# Two stages. This copy (from the *installed* release) downloads and verifies
# the target release, then execs the target release's own update.sh with
# --activate, so the activation steps are always the ones that shipped with the
# code being activated -- a newer release can change how it installs itself.
#
# Activation takes a database dump, stops the services, migrates, switches the
# `current` symlink, restarts and health-checks. If migrations or the health
# check fail, the previous release and the pre-upgrade database are restored.
set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage: update.sh [--version X.Y.Z] [--base-url URL] [--dry-run]

  --version X.Y.Z   release to upgrade to (default: latest)
  --base-url URL    where releases are downloaded from (for testing a local build)
  --dry-run         download and verify, then print every change instead of making it
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

activate=""
while [ $# -gt 0 ]; do
    case "$1" in
        --version)  [ -n "${2:-}" ] || die "--version needs a value"; FS_VERSION=$2; shift 2 ;;
        --base-url) [ -n "${2:-}" ] || die "--base-url needs a value"; FS_BASE_URL=${2%/}; shift 2 ;;
        --dry-run)  FS_DRY_RUN=1; shift ;;
        --activate) [ -n "${2:-}" ] || die "--activate needs a version"; activate=$2; shift 2 ;;
        -h|--help)  usage; exit 0 ;;
        *)          usage >&2; die "unknown option: $1" ;;
    esac
done
export FS_VERSION FS_BASE_URL FS_DRY_RUN

# shellcheck source=deploy/lib/common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
fs_defaults
fs_require_root
fs_lock

# Stage 2: running from the target release.
if [ -n "$activate" ]; then
    fs_upgrade "$activate"
    exit 0
fi

# Stage 1: running from the installed release.
current=$(fs_current_version)
[ -n "$current" ] || die "no FarmSteader install found at $FS_CURRENT"
if [ "${FS_VERSION:-latest}" = latest ] && [ -n "${FS_BASE_URL:-}" ] \
    && [ "$FS_BASE_URL" != "https://github.com/mcbriderc/farmsteader/releases/download" ]; then
    die "--base-url needs an explicit --version"
fi
target=$(fs_resolve_version "$FS_VERSION")

if [ "$target" = "$current" ]; then
    fs_ok "already on $current; nothing to do"
    exit 0
fi
# Migrations only run forwards, so a downgrade cannot be done in place.
if [ "$(printf '%s\n%s\n' "$current" "$target" | sort -V | tail -1)" = "$current" ]; then
    die "$target is older than the installed $current; downgrades are not supported"
fi

fs_fetch_release "$target"
if [ "$FS_DRY_RUN" = 1 ]; then
    fs_info "dry run: would continue with $FS_RELEASES/$target/deploy/update.sh --activate $target"
    exit 0
fi
exec bash "$FS_RELEASES/$target/deploy/update.sh" --activate "$target"
