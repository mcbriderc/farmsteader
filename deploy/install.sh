#!/usr/bin/env bash
#
# Install FarmSteader on a fresh Debian 13 (or recent Ubuntu) machine,
# container or VM:
#
#   curl -fsSL https://raw.githubusercontent.com/mcbriderc/farmsteader/master/deploy/install.sh | sudo bash
#
# or, to pass options:
#
#   sudo bash install.sh --admin-email you@example.com --allowed-hosts farm.lan
#
# Non-interactive by default, so it works the same from a shell, Ansible or CI.
# Installs PostgreSQL + PostGIS, Redis, nginx and the app, starts everything,
# and only reports success once the site answers with the right version.
#
# This file is only a bootstrap. It downloads and verifies the release, then
# hands over to deploy/lib/common.sh *from that release*, so the install steps
# always match the code being installed.
set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage: install.sh [options]

  --version X.Y.Z          release to install (default: latest)
  --admin-user NAME        admin username (default: admin)
  --admin-email EMAIL      admin email address
  --admin-password PASS    admin password (default: generated, saved to /root/farmsteader.creds)
  --allowed-hosts LIST     comma-separated hostnames/IPs the site answers to
                           (default: localhost, this hostname, and its IPv4 addresses)
  --usda-key KEY           USDA NASS API key for crop price sync
  --sentry-dsn DSN         report errors to Sentry
  --no-nginx               do not install nginx; gunicorn listens on /run/farmsteader/gunicorn.sock
  --no-backups             do not install the nightly database backup
  --base-url URL           where releases are downloaded from (for testing a local build)
  --dry-run                download and verify, then print every change instead of making it
  -h, --help               show this help
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need_arg() { [ $# -ge 2 ] && [ -n "$2" ] || die "$1 needs a value"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --version)        need_arg "$@"; FS_VERSION=$2; shift 2 ;;
        --admin-user)     need_arg "$@"; FS_ADMIN_USER=$2; shift 2 ;;
        --admin-email)    need_arg "$@"; FS_ADMIN_EMAIL=$2; shift 2 ;;
        --admin-password) need_arg "$@"; FS_ADMIN_PASSWORD=$2; shift 2 ;;
        --allowed-hosts)  need_arg "$@"; FS_ALLOWED_HOSTS=$2; shift 2 ;;
        --usda-key)       need_arg "$@"; FS_USDA_KEY=$2; shift 2 ;;
        --sentry-dsn)     need_arg "$@"; FS_SENTRY_DSN=$2; shift 2 ;;
        --base-url)       need_arg "$@"; FS_BASE_URL=${2%/}; shift 2 ;;
        --no-nginx)       FS_NGINX=0; shift ;;
        --no-backups)     FS_BACKUPS=0; shift ;;
        --dry-run)        FS_DRY_RUN=1; shift ;;
        -h|--help)        usage; exit 0 ;;
        *)                usage >&2; die "unknown option: $1" ;;
    esac
done
export FS_VERSION FS_ADMIN_USER FS_ADMIN_EMAIL FS_ADMIN_PASSWORD FS_ALLOWED_HOSTS \
    FS_USDA_KEY FS_SENTRY_DSN FS_BASE_URL FS_NGINX FS_BACKUPS FS_DRY_RUN

[ "$(id -u)" = 0 ] || die "run as root (sudo bash install.sh ...)"

# The username is interpolated into a Django shell check; hold it to Django's
# own username alphabet.
if [ -n "${FS_ADMIN_USER:-}" ] && ! [[ $FS_ADMIN_USER =~ ^[A-Za-z0-9@.+_-]{1,150}$ ]]; then
    die "--admin-user may contain only letters, digits and @ . + - _"
fi

if [ -e /opt/farmsteader/current ]; then
    die "FarmSteader is already installed; to upgrade run /opt/farmsteader/current/deploy/update.sh"
fi

# --- Bootstrap: fetch and verify the release ---------------------------------
#
# Deliberately minimal and self-contained -- nothing else can be sourced yet.
# deploy/update.sh uses fs_fetch_release, which performs the same checks.

if ! command -v curl >/dev/null 2>&1; then
    echo "==> Installing curl"
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends ca-certificates curl
fi

base_url=${FS_BASE_URL:-https://github.com/mcbriderc/farmsteader/releases/download}
version=${FS_VERSION:-latest}
if [ "$version" = latest ]; then
    [ -z "${FS_BASE_URL:-}" ] || die "--base-url needs an explicit --version"
    version=$(curl -fsSL https://api.github.com/repos/mcbriderc/farmsteader/releases/latest \
        | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)
    [ -n "$version" ] || die "could not determine the latest release"
fi
version=${version#v}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || die "'$version' is not a release version"

stage=$(mktemp -d /tmp/farmsteader-install.XXXXXX)
trap 'rm -rf "$stage"' EXIT
name="farmsteader-$version.tar.gz"

echo "==> Downloading FarmSteader $version"
curl -fsSL -o "$stage/$name" "$base_url/v$version/$name" || die "download failed: $base_url/v$version/$name"
curl -fsSL -o "$stage/SHA256SUMS" "$base_url/v$version/SHA256SUMS" || die "download failed: SHA256SUMS"
grep -q " $name\$" "$stage/SHA256SUMS" || die "SHA256SUMS has no entry for $name"
(cd "$stage" && grep " $name\$" SHA256SUMS | sha256sum -c --quiet -) || die "checksum mismatch for $name"
echo "    ok: checksum verified"

mkdir "$stage/release"
tar -xzf "$stage/$name" -C "$stage/release" --strip-components=1 --no-same-owner
[ "$(tr -d '[:space:]' <"$stage/release/VERSION")" = "$version" ] || die "tarball VERSION does not match $version"
[ -f "$stage/release/deploy/lib/common.sh" ] || die "release $version has no deploy/lib/common.sh (too old for this installer)"

# --- Hand over to the release's own install logic ----------------------------

# shellcheck source=deploy/lib/common.sh
. "$stage/release/deploy/lib/common.sh"
fs_defaults
FS_BASE_URL=$base_url
fs_detect_os
fs_lock
fs_install "$version" "$stage/release"
