# shellcheck shell=bash
#
# FarmSteader install/upgrade library. Every entry point -- deploy/install.sh,
# deploy/update.sh, and the Proxmox installer -- is a thin shim over these
# functions, so there is exactly one implementation of each step.
#
# This file ships inside the release tarball, and entry points source the copy
# from the release being installed. The procedure that installs a version is
# therefore always the one that shipped with it.
#
# Layout on the target (what makes atomic upgrade and rollback possible):
#
#   /opt/farmsteader/releases/<version>/   one extracted release each, root-owned,
#                                          with its own .venv and staticfiles/
#   /opt/farmsteader/current -> releases/<version>   swapped atomically
#   /etc/farmsteader/env                   config (0640 root:farmsteader);
#                                          each release's .env symlinks here
#   /var/lib/farmsteader/                  media/, celerybeat-schedule
#   /var/log/farmsteader/  /var/backups/farmsteader/
#
# Configuration comes from FS_* variables (see fs_defaults). FS_DRY_RUN=1 prints
# every state-changing command instead of running it.
#
# Output goes through fs_info/fs_ok/fs_warn/fs_die so the Proxmox installer can
# redefine them with its spinner UI without touching any logic here.

# --- Output (overridable) ----------------------------------------------------

fs_info() { printf '==> %s\n' "$*"; }
fs_ok()   { printf '    ok: %s\n' "$*"; }
fs_warn() { printf 'WARNING: %s\n' "$*" >&2; }
fs_die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- Configuration -----------------------------------------------------------

fs_defaults() {
    : "${FS_VERSION:=latest}"
    : "${FS_BASE_URL:=https://github.com/mcbriderc/farmsteader/releases/download}"
    : "${FS_LATEST_URL:=https://api.github.com/repos/mcbriderc/farmsteader/releases/latest}"
    : "${FS_SOURCE_URL:=https://github.com/mcbriderc/farmsteader}"
    : "${FS_ADMIN_USER:=admin}"
    : "${FS_ADMIN_EMAIL:=}"
    : "${FS_ADMIN_PASSWORD:=}"
    : "${FS_ALLOWED_HOSTS:=}"
    : "${FS_USDA_KEY:=}"
    : "${FS_SENTRY_DSN:=}"
    : "${FS_BACKUPS:=1}"
    : "${FS_NGINX:=1}"
    : "${FS_KEEP_RELEASES:=2}"
    : "${FS_DRY_RUN:=0}"

    FS_USER=farmsteader
    FS_DB=farmsteader
    FS_ROOT=/opt/farmsteader
    FS_RELEASES=$FS_ROOT/releases
    FS_CURRENT=$FS_ROOT/current
    FS_ETC=/etc/farmsteader
    FS_ENV=$FS_ETC/env
    FS_DATA=/var/lib/farmsteader
    FS_LOGDIR=/var/log/farmsteader
    FS_BACKUP_DIR=/var/backups/farmsteader
    FS_CREDS=/root/farmsteader.creds
    FS_INSTALL_LOG=/var/log/farmsteader-install.log
    FS_UNITS=(farmsteader-web farmsteader-celery farmsteader-celerybeat)
}

# --- Primitives --------------------------------------------------------------

# Run a state-changing command, or print it under FS_DRY_RUN=1.
fs_run() {
    if [ "$FS_DRY_RUN" = 1 ]; then
        printf '    [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# Run a chatty command (apt, pip, migrate) with its output in FS_INSTALL_LOG.
# On failure, show the log's tail and return the status -- callers that can
# recover (an upgrade rolling back) need the status rather than an exit.
fs_logged() {
    if [ "$FS_DRY_RUN" = 1 ]; then
        fs_run "$@"
        return
    fi
    printf '\n$ %s\n' "$*" >>"$FS_INSTALL_LOG"
    local rc=0
    "$@" >>"$FS_INSTALL_LOG" 2>&1 || rc=$?
    if [ "$rc" != 0 ]; then
        fs_warn "command failed: $*"
        tail -n 25 "$FS_INSTALL_LOG" >&2
        fs_warn "full output in $FS_INSTALL_LOG"
    fi
    return "$rc"
}

# fs_logged for steps with no recovery: failure ends the run.
fs_quiet() {
    fs_logged "$@" || exit 1
}

# Write stdin to a file with the given mode and owner, or describe it.
fs_write() {  # path mode owner
    local path=$1 mode=$2 owner=$3
    if [ "$FS_DRY_RUN" = 1 ]; then
        printf '    [dry-run] write %s (%s %s)\n' "$path" "$mode" "$owner"
        cat >/dev/null
        return
    fi
    local tmp
    tmp=$(mktemp "${path}.XXXXXX")
    cat >"$tmp"
    chmod "$mode" "$tmp"
    chown "$owner" "$tmp"
    mv -f "$tmp" "$path"
}

# Hex only: unambiguously safe in a postgis:// URL, a systemd EnvironmentFile
# and django-environ's KEY=value parsing. base64 was not -- its + / = broke
# DATABASE_URL.
fs_gen_secret() { openssl rand -hex "${1:-32}"; }

fs_require_root() { [ "$(id -u)" = 0 ] || fs_die "must run as root"; }

fs_detect_os() {
    [ -r /etc/os-release ] || fs_die "cannot read /etc/os-release"
    # Read in a subshell: os-release defines VERSION, ID, NAME... as globals.
    local id pretty
    # shellcheck disable=SC1091
    id=$(. /etc/os-release && echo "${ID:-}")
    # shellcheck disable=SC1091
    pretty=$(. /etc/os-release && echo "${PRETTY_NAME:-}")
    case "$id" in
        debian|ubuntu) ;;
        *) fs_die "unsupported OS '${id:-unknown}' -- Debian 13 or a recent Ubuntu is required" ;;
    esac
    fs_ok "OS: ${pretty:-$id}"
}

# Serialize installs and upgrades; two at once would race on the symlink.
# FS_LOCK_HELD lets update.sh keep its lock across the exec into the new
# release's update.sh: fd 9 is inherited, and reopening it would drop the lock.
fs_lock() {
    [ "$FS_DRY_RUN" = 1 ] && return
    [ "${FS_LOCK_HELD:-0}" = 1 ] && return
    mkdir -p /run/lock
    exec 9>/run/lock/farmsteader.lock
    flock -n 9 || fs_die "another FarmSteader install or update is running"
    export FS_LOCK_HELD=1
}

# Python's json module, not jq: python3 is installed anyway, one fewer package.
fs_json_get() {  # key -- reads JSON on stdin
    python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"
}

fs_current_version() {
    [ -f "$FS_CURRENT/VERSION" ] && tr -d '[:space:]' <"$FS_CURRENT/VERSION"
}

# --- Releases ----------------------------------------------------------------

fs_resolve_version() {
    local v=${1:-$FS_VERSION}
    if [ "$v" = latest ]; then
        # sed, not fs_json_get: this runs from the bootstrap, before python3
        # is guaranteed to be installed.
        v=$(curl -fsSL "$FS_LATEST_URL" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1) \
            || fs_die "could not look up the latest release at $FS_LATEST_URL"
        [ -n "$v" ] || fs_die "no published release found at $FS_LATEST_URL"
    fi
    v=${v#v}
    [[ $v =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || fs_die "'$v' is not a release version"
    printf '%s\n' "$v"
}

# Download, verify against SHA256SUMS, and extract into releases/<version>.
fs_fetch_release() {  # version
    local v=$1 dest=$FS_RELEASES/$1 tmp name="farmsteader-$1.tar.gz"
    if [ "$(fs_current_version)" = "$v" ]; then
        fs_ok "release $v is already installed and current"
        return
    fi
    fs_info "Fetching FarmSteader $v"
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/$name" "$FS_BASE_URL/v$v/$name" || fs_die "download failed: $FS_BASE_URL/v$v/$name"
    curl -fsSL -o "$tmp/SHA256SUMS" "$FS_BASE_URL/v$v/SHA256SUMS" || fs_die "download failed: SHA256SUMS"
    # Check the one line for our file. A plain `sha256sum -c` would also pass
    # vacuously if the file were missing from the list.
    grep -q " $name\$" "$tmp/SHA256SUMS" || fs_die "SHA256SUMS has no entry for $name"
    (cd "$tmp" && grep " $name\$" SHA256SUMS | sha256sum -c --quiet -) || fs_die "checksum mismatch for $name"
    fs_ok "checksum verified"
    fs_run rm -rf "$dest"
    fs_run mkdir -p "$dest"
    fs_run tar -xzf "$tmp/$name" -C "$dest" --strip-components=1 --no-same-owner
    if [ "$FS_DRY_RUN" != 1 ]; then
        [ "$(tr -d '[:space:]' <"$dest/VERSION")" = "$v" ] || fs_die "tarball VERSION does not match $v"
    fi
    rm -rf "$tmp"
    fs_ok "extracted to $dest"
}

# Keep the newest FS_KEEP_RELEASES directories, and never the current one.
fs_prune_releases() {
    local cur keep=$FS_KEEP_RELEASES n=0 d
    cur=$(readlink -f "$FS_CURRENT" 2>/dev/null || true)
    while IFS= read -r d; do
        n=$((n + 1))
        [ "$n" -le "$keep" ] && continue
        [ "$(readlink -f "$d")" = "$cur" ] && continue
        fs_run rm -rf "$d"
        fs_ok "pruned old release $(basename "$d")"
    done < <(find "$FS_RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
}

# --- System setup (install only) ---------------------------------------------

fs_install_packages() {
    fs_info "Installing system packages"
    export DEBIAN_FRONTEND=noninteractive
    fs_quiet apt-get update -qq
    # Deliberately absent: build-essential and *-dev (every dependency ships a
    # wheel for this Python), git (we install from a tarball), certbot.
    local pkgs=(ca-certificates curl tar gzip openssl cron
                python3 python3-venv gdal-bin binutils
                postgresql redis-server)
    [ "$FS_NGINX" = 1 ] && pkgs+=(nginx)
    fs_quiet apt-get install -y -qq --no-install-recommends "${pkgs[@]}"

    # PostGIS is versioned by the PostgreSQL major, which the distro decides.
    # Resolve it after installing postgresql rather than hardcoding it, so a
    # Debian bump to a new PostgreSQL does not break the installer.
    local pg
    pg=$(fs_pg_major)
    fs_quiet apt-get install -y -qq --no-install-recommends \
        "postgresql-$pg-postgis-3" "postgresql-$pg-postgis-3-scripts"
    fs_ok "packages installed (PostgreSQL $pg)"
}

fs_pg_major() {
    local d
    d=$(find /usr/lib/postgresql -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -n | tail -1)
    [ -n "$d" ] || { [ "$FS_DRY_RUN" = 1 ] && { echo NN; return; }; fs_die "PostgreSQL is not installed"; }
    echo "$d"
}

fs_create_user_and_dirs() {
    fs_info "Creating service user and directories"
    if ! id "$FS_USER" >/dev/null 2>&1; then
        fs_run useradd --system --home-dir "$FS_DATA" --no-create-home \
            --shell /usr/sbin/nologin "$FS_USER"
    fi
    fs_run install -d -m 0755 -o root -g root "$FS_ROOT" "$FS_RELEASES"
    fs_run install -d -m 0750 -o root -g "$FS_USER" "$FS_ETC"
    # 0755 so nginx (www-data) can read and serve media/ directly.
    fs_run install -d -m 0755 -o "$FS_USER" -g "$FS_USER" "$FS_DATA" "$FS_DATA/media" "$FS_LOGDIR"
    fs_run install -d -m 0750 -o postgres -g root "$FS_BACKUP_DIR"
    fs_ok "user '$FS_USER' and directories ready"
}

# Creates the role and database, and sets the role's password. Idempotent.
fs_setup_postgres() {  # db-password
    fs_info "Configuring PostgreSQL"
    fs_quiet systemctl enable --now postgresql
    local exists verb=CREATE
    exists=$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$FS_USER'" 2>/dev/null || true)
    [ "$exists" = 1 ] && verb=ALTER
    # The password goes in on stdin, never argv, where any user could read it
    # from the process list -- and never into dry-run output.
    if [ "$FS_DRY_RUN" = 1 ]; then
        fs_run "psql: $verb ROLE $FS_USER WITH LOGIN PASSWORD <hidden>"
    else
        printf "%s ROLE %s WITH LOGIN PASSWORD '%s';\n" "$verb" "$FS_USER" "$1" \
            | runuser -u postgres -- psql -q -v ON_ERROR_STOP=1 >/dev/null
    fi
    exists=$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='$FS_DB'" 2>/dev/null || true)
    if [ "$exists" != 1 ]; then
        fs_run runuser -u postgres -- createdb -O "$FS_USER" "$FS_DB"
    fi
    fs_run runuser -u postgres -- psql -q -d "$FS_DB" -c 'CREATE EXTENSION IF NOT EXISTS postgis'
    fs_ok "database '$FS_DB' with PostGIS"
}

fs_setup_redis() {
    fs_info "Configuring Redis"
    local conf=/etc/redis/redis.conf
    # Redis is only the task broker here; periodic RDB snapshots of it are pure
    # disk churn. An explicit `save ""` is needed -- with no save line at all,
    # modern Redis falls back to its built-in snapshot schedule.
    if [ -f "$conf" ] && ! grep -qx 'save ""' "$conf"; then
        fs_run sed -i -e 's/^save /# save /' "$conf"
        if [ "$FS_DRY_RUN" = 1 ]; then
            fs_run "append 'save \"\"' to $conf"
        else
            printf '\n# FarmSteader: broker only, no snapshots\nsave ""\n' >>"$conf"
        fi
    fi
    fs_quiet systemctl enable redis-server
    fs_run systemctl restart redis-server
    fs_ok "redis running without snapshots"
}

# --- Configuration file ------------------------------------------------------

# Web workers and celery concurrency from RAM. /proc/meminfo reports the
# container's limit under lxcfs, which is the number that matters.
fs_sizing() {
    local mem_mb
    mem_mb=$(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo)
    if [ "$mem_mb" -le 2304 ]; then
        FS_WEB_WORKERS=2 FS_CELERY_CONCURRENCY=1
    elif [ "$mem_mb" -le 4352 ]; then
        FS_WEB_WORKERS=3 FS_CELERY_CONCURRENCY=2
    else
        FS_WEB_WORKERS=4 FS_CELERY_CONCURRENCY=2
    fi
    fs_ok "sizing for ${mem_mb} MB RAM: $FS_WEB_WORKERS web workers, celery concurrency $FS_CELERY_CONCURRENCY"
}

# localhost and 127.0.0.1 are mandatory -- the health probe uses them and would
# otherwise get a 400 -- plus this machine's hostname and IPv4 addresses, so it
# is reachable on the LAN by name or IP out of the box.
fs_default_allowed_hosts() {
    local hosts=(localhost 127.0.0.1) h ip
    h=$(hostname 2>/dev/null || true)
    [ -n "$h" ] && hosts+=("$h" "$h.local")
    for ip in $(hostname -I 2>/dev/null); do
        case "$ip" in *:*) ;; *) hosts+=("$ip") ;; esac
    done
    local IFS=,
    printf '%s\n' "${hosts[*]}"
}

# Written once, at install. Upgrades never rewrite it; fs_env_ensure adds keys
# that a newer release introduces without touching what the operator changed.
fs_write_env() {  # db-password
    local allowed=${FS_ALLOWED_HOSTS:-$(fs_default_allowed_hosts)}
    fs_info "Writing $FS_ENV"
    fs_write "$FS_ENV" 0640 "root:$FS_USER" <<EOF
# FarmSteader configuration. Read by systemd (EnvironmentFile) and by Django.
# Restart after editing:  systemctl restart ${FS_UNITS[*]}

DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$(fs_gen_secret 32)
DATABASE_URL=postgis://$FS_USER:$1@localhost:5432/$FS_DB
REDIS_URL=redis://localhost:6379/0

# Hostnames and IPs this site may be reached by (comma-separated).
# Must keep localhost and 127.0.0.1 for the health check.
ALLOWED_HOSTS=$allowed

# Serving over HTTPS (behind a TLS proxy, or with certbot)? Set this to 1.
FARMSTEADER_HTTPS=0

MEDIA_ROOT=$FS_DATA/media

# Sized from RAM at install time.
GUNICORN_WORKERS=$FS_WEB_WORKERS
CELERY_CONCURRENCY=$FS_CELERY_CONCURRENCY

# Optional integrations.
USDA_NASS_API_KEY=$FS_USDA_KEY
SENTRY_DSN=$FS_SENTRY_DSN

# AGPL "Source" link in the sidebar. Correct for the unmodified release this
# installer deploys; if you modify FarmSteader, point it at your own fork.
FARMSTEADER_SOURCE_URL=$FS_SOURCE_URL
EOF
    fs_ok "configuration written"
}

fs_env_ensure() {  # key value
    grep -q "^$1=" "$FS_ENV" 2>/dev/null && return
    if [ "$FS_DRY_RUN" = 1 ]; then
        fs_run "append $1=$2 to $FS_ENV"
    else
        printf '%s=%s\n' "$1" "$2" >>"$FS_ENV"
    fi
}

# --- Per-release activation --------------------------------------------------

fs_manage() {  # release-dir args...
    local dir=$1
    shift
    if [ "$FS_DRY_RUN" = 1 ]; then
        fs_run manage.py "$@"
        return
    fi
    # Output goes to the install log; on failure its tail is shown and the
    # status returned, so an upgrade can still roll back.
    fs_logged env -C "$dir" DJANGO_SETTINGS_MODULE=config.settings.prod \
        "$dir/.venv/bin/python" manage.py "$@"
}

# Everything that can be prepared without touching the running site: venv,
# config link, static files, and a settings sanity check.
fs_prepare_release() {  # version
    local dir=$FS_RELEASES/$1
    fs_info "Preparing release $1"
    fs_run python3 -m venv "$dir/.venv"
    fs_quiet "$dir/.venv/bin/pip" install --quiet --no-cache-dir --disable-pip-version-check \
        -r "$dir/requirements/prod.txt"
    fs_ok "python dependencies installed"
    fs_run ln -sfn "$FS_ENV" "$dir/.env"
    # `check` imports every app, so a missing GDAL or a broken setting fails
    # here, before the site is stopped, rather than after. The HTTPS WARNINGs a
    # plain-HTTP LAN install always raises stay in the log.
    fs_manage "$dir" check --deploy --fail-level ERROR
    fs_manage "$dir" collectstatic --noinput
    fs_ok "static files collected"
}

fs_install_units() {  # release-dir
    local dir=$1 u
    for u in "${FS_UNITS[@]}"; do
        fs_run install -m 0644 "$dir/deploy/systemd/$u.service" "/etc/systemd/system/$u.service"
    done
    if [ "$FS_NGINX" = 1 ]; then
        fs_run install -m 0644 "$dir/deploy/nginx/farmsteader.conf" /etc/nginx/sites-available/farmsteader
        fs_run ln -sfn /etc/nginx/sites-available/farmsteader /etc/nginx/sites-enabled/farmsteader
        fs_run rm -f /etc/nginx/sites-enabled/default
        fs_run nginx -t -q
    fi
    fs_run systemctl daemon-reload
}

# Atomic: build the new link beside the old one, then rename over it.
fs_switch_current() {  # version
    fs_run ln -sfn "releases/$1" "$FS_CURRENT.new"
    fs_run mv -Tf "$FS_CURRENT.new" "$FS_CURRENT"
}

fs_start_services() {
    fs_run systemctl enable --quiet "${FS_UNITS[@]}"
    fs_run systemctl restart "${FS_UNITS[@]}"
    if [ "$FS_NGINX" = 1 ]; then
        fs_run systemctl enable --quiet nginx
        fs_run systemctl reload-or-restart nginx
    fi
}

fs_stop_services() {
    fs_run systemctl stop "${FS_UNITS[@]}" 2>/dev/null || true
}

# The install must not report success unless the app actually answers, with
# the expected version and its database and broker reachable.
fs_wait_healthy() {  # expected-version
    [ "$FS_DRY_RUN" = 1 ] && { fs_run "poll /healthz for version $1, then /readyz"; return 0; }
    local curl_args=(-fsS --max-time 5) base=http://127.0.0.1 i got=""
    if [ "$FS_NGINX" != 1 ]; then
        curl_args+=(--unix-socket /run/farmsteader/gunicorn.sock)
        base=http://localhost
    fi
    fs_info "Waiting for FarmSteader to answer"
    for i in $(seq 1 45); do
        got=$(curl "${curl_args[@]}" "$base/healthz" 2>/dev/null | fs_json_get version 2>/dev/null || true)
        [ "$got" = "$1" ] && break
        sleep 2
    done
    if [ "$got" != "$1" ]; then
        fs_warn "the web service did not report version $1 (last answer: '${got:-none}')"
        journalctl -u farmsteader-web -n 40 --no-pager >&2 || true
        return 1
    fi
    if ! curl "${curl_args[@]}" "$base/readyz" >/dev/null; then
        fs_warn "/readyz reports a problem:"
        curl -sS "${curl_args[@]}" "$base/readyz" >&2 || true
        return 1
    fi
    fs_ok "healthy: version $1 is serving (after ${i}x2s)"
}

# --- Admin user, backups, credentials ----------------------------------------

fs_create_superuser() {  # release-dir
    local dir=$1
    if (cd "$dir" && DJANGO_SETTINGS_MODULE=config.settings.prod "$dir/.venv/bin/python" manage.py shell -c \
        "import sys; from django.contrib.auth import get_user_model as g; sys.exit(0 if g().objects.filter(username='$FS_ADMIN_USER').exists() else 1)") \
        >/dev/null 2>&1; then
        fs_ok "admin user '$FS_ADMIN_USER' already exists"
        FS_ADMIN_PASSWORD=""
        return
    fi
    : "${FS_ADMIN_PASSWORD:=$(fs_gen_secret 12)}"
    if [ "$FS_DRY_RUN" = 1 ]; then
        fs_run "createsuperuser --username $FS_ADMIN_USER"
        return
    fi
    (cd "$dir" && DJANGO_SUPERUSER_PASSWORD="$FS_ADMIN_PASSWORD" \
        DJANGO_SETTINGS_MODULE=config.settings.prod "$dir/.venv/bin/python" manage.py createsuperuser --noinput \
        --username "$FS_ADMIN_USER" --email "$FS_ADMIN_EMAIL" >/dev/null)
    fs_ok "admin user '$FS_ADMIN_USER' created"
}

fs_setup_backups() {
    [ "$FS_BACKUPS" = 1 ] || { fs_ok "nightly backups disabled"; return; }
    fs_write /etc/cron.d/farmsteader-backup 0644 root:root <<EOF
# FarmSteader nightly database dump, kept for 14 days.
0 2 * * * postgres pg_dump -Fc $FS_DB > $FS_BACKUP_DIR/farmsteader-\$(date +\%Y\%m\%d).dump
30 2 * * * root find $FS_BACKUP_DIR -name 'farmsteader-*.dump' -mtime +14 -delete
# Pre-upgrade dumps are kept longer: they are the way back from a bad release.
35 2 * * * root find $FS_BACKUP_DIR -name 'pre-upgrade-*.dump' -mtime +90 -delete
EOF
    fs_ok "nightly database backups to $FS_BACKUP_DIR"
}

fs_write_creds() {
    [ -n "$FS_ADMIN_PASSWORD" ] || return 0
    fs_write "$FS_CREDS" 0600 root:root <<EOF
FarmSteader admin login
  user:     $FS_ADMIN_USER
  password: $FS_ADMIN_PASSWORD
Change it after first login. Database credentials are in $FS_ENV.
EOF
}

# --- Upgrade safety net ------------------------------------------------------

fs_dump_db() {  # label -> prints dump path
    local out
    out="$FS_BACKUP_DIR/pre-upgrade-$1-$(date +%Y%m%d%H%M%S).dump"
    if [ "$FS_DRY_RUN" = 1 ]; then
        fs_run "pg_dump -Fc $FS_DB > $out" >&2
    else
        runuser -u postgres -- pg_dump -Fc "$FS_DB" >"$out" || fs_die "pre-upgrade database dump failed"
    fi
    printf '%s\n' "$out"
}

fs_restore_db() {  # dump
    fs_warn "restoring the database from $1"
    fs_run runuser -u postgres -- dropdb --if-exists "$FS_DB"
    fs_run runuser -u postgres -- createdb -O "$FS_USER" "$FS_DB"
    fs_run runuser -u postgres -- pg_restore --exit-on-error -d "$FS_DB" "$1"
}

# Put the previous release back exactly: link, units, database.
fs_rollback() {  # old-version dump
    fs_warn "rolling back to $1"
    fs_stop_services
    fs_switch_current "$1"
    fs_install_units "$FS_RELEASES/$1"
    [ -n "$2" ] && fs_restore_db "$2"
    fs_start_services
    if fs_wait_healthy "$1"; then
        fs_warn "rolled back: $1 is serving again"
    else
        fs_warn "rollback to $1 did not come back healthy -- check journalctl -u farmsteader-web"
    fi
}

# --- Top-level flows ---------------------------------------------------------

# Fresh install. The bootstrap in install.sh has already downloaded, verified
# and unpacked the release into a staging directory (it had to, to get this
# file); it is moved into place once the directories exist.
fs_install() {  # version staged-dir
    local v=$1 dir=$FS_RELEASES/$1 dbpass
    fs_install_packages
    fs_create_user_and_dirs
    fs_run rm -rf "$dir"
    fs_run mv "$2" "$dir"
    fs_sizing
    if [ -f "$FS_ENV" ]; then
        # A re-run after a failed install: keep the existing secrets.
        dbpass=$(sed -n "s|^DATABASE_URL=postgis://$FS_USER:\([0-9a-f]*\)@.*|\1|p" "$FS_ENV")
        [ -n "$dbpass" ] || fs_die "$FS_ENV exists but its DATABASE_URL is not one this installer wrote"
        fs_ok "reusing existing $FS_ENV"
    else
        dbpass=$(fs_gen_secret 24)
        fs_write_env "$dbpass"
    fi
    fs_setup_postgres "$dbpass"
    fs_setup_redis
    fs_prepare_release "$v"
    fs_info "Migrating the database"
    fs_manage "$dir" migrate --noinput
    fs_ok "database migrated"
    fs_create_superuser "$dir"
    fs_install_units "$dir"
    fs_switch_current "$v"
    fs_start_services
    fs_wait_healthy "$v" || fs_die "FarmSteader $v installed but is not healthy (see above)"
    fs_setup_backups
    fs_write_creds
    fs_print_summary "$v"
}

# Upgrade the running install to a release already extracted into releases/<v>.
# Anything that fails after the database is touched restores the pre-upgrade
# dump and the previous release.
fs_upgrade() {  # version
    local v=$1 dir=$FS_RELEASES/$1 old dump
    old=$(fs_current_version)
    [ -n "$old" ] || fs_die "no current install found at $FS_CURRENT"
    fs_sizing
    fs_env_ensure GUNICORN_WORKERS "$FS_WEB_WORKERS"
    fs_env_ensure CELERY_CONCURRENCY "$FS_CELERY_CONCURRENCY"
    fs_env_ensure MEDIA_ROOT "$FS_DATA/media"
    fs_prepare_release "$v"

    fs_info "Upgrading $old -> $v"
    dump=$(fs_dump_db "$old-to-$v")
    fs_ok "pre-upgrade dump: $dump"
    fs_stop_services
    if ! fs_manage "$dir" migrate --noinput; then
        fs_warn "migrations failed"
        fs_rollback "$old" "$dump"
        fs_die "upgrade to $v failed; $old restored"
    fi
    fs_ok "database migrated"
    fs_install_units "$dir"
    fs_switch_current "$v"
    fs_start_services
    if ! fs_wait_healthy "$v"; then
        fs_rollback "$old" "$dump"
        fs_die "upgrade to $v failed its health check; $old restored"
    fi
    fs_prune_releases
    fs_ok "upgraded to $v (previous release kept for rollback)"
}

fs_print_summary() {  # version
    if [ "$FS_DRY_RUN" = 1 ]; then
        printf '\nDry run complete: the commands above were NOT run, and nothing was changed.\n'
        return
    fi
    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    cat <<EOF

============================================================
  FarmSteader $1 is installed and healthy.

  Open:   http://${ip:-<this-machine>}/
EOF
    if [ -n "$FS_ADMIN_PASSWORD" ]; then
        cat <<EOF
  Login:  $FS_ADMIN_USER / $FS_ADMIN_PASSWORD
          (also saved to $FS_CREDS -- change it after first login)
EOF
    fi
    cat <<EOF

  Config:   $FS_ENV
  Logs:     journalctl -u farmsteader-web -f
  Upgrade:  $FS_CURRENT/deploy/update.sh
============================================================
EOF
}
