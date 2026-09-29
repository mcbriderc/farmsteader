#!/usr/bin/env bash
#
# Create a FarmSteader container on a Proxmox VE host. In the node's shell:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/mcbriderc/farmsteader/master/ct/farmsteader.sh)"
#
# Asks a few questions (or none, with the defaults), creates an unprivileged
# Debian 13 container, and runs FarmSteader's own installer inside it
# (deploy/install.sh -- the same one used on any Debian machine). Run it again
# to update an existing FarmSteader container in place.
#
# Environment:
#   FS_CT_DEFAULTS=1       no menus: take every default (for scripting)
#   FARMSTEADER_DRY_RUN=1  stub out pct/pveam/pvesm and print what would run
#   FUNC_BASE_URL          where the helper scripts are fetched from
#   var_cpu var_ram var_disk   override the default container size
set -Eeuo pipefail

APP="FarmSteader"
: "${FUNC_BASE_URL:=https://raw.githubusercontent.com/mcbriderc/farmsteader/master}"
: "${var_cpu:=2}" "${var_ram:=2048}" "${var_disk:=10}"
: "${FS_CT_DEFAULTS:=0}" "${FARMSTEADER_DRY_RUN:=0}"

# From a checkout (bash ct/farmsteader.sh) use the neighbouring files, so the
# scripts under test are the ones on disk; from curl, fetch them.
SRC_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SRC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
    [ -f "$SRC_DIR/misc/build.func" ] || SRC_DIR=""
fi

fetch() {  # repo-path dest
    if [ -n "$SRC_DIR" ]; then
        cp "$SRC_DIR/$1" "$2"
    else
        curl -fsSL "$FUNC_BASE_URL/$1" -o "$2" || { echo "could not download $FUNC_BASE_URL/$1" >&2; exit 1; }
    fi
}

WORK=$(mktemp -d /tmp/farmsteader-ct.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
fs_on_exit() { rm -rf "$WORK"; }   # catch_errors replaces the trap above
fetch misc/build.func "$WORK/build.func"
# shellcheck source=misc/build.func
. "$WORK/build.func"

# --- Settings ----------------------------------------------------------------

# Every value can be preset in the environment, which is how FS_CT_DEFAULTS=1
# runs are customised without menus (e.g. CT_HOSTNAME=barn FS_ADMIN_EMAIL=...).
default_settings() {
    CTID=${CTID:-$(get_valid_nextid)}
    CT_HOSTNAME=${CT_HOSTNAME:-farmsteader}
    CORES=$var_cpu RAM=$var_ram DISK=$var_disk
    BRIDGE=${BRIDGE:-vmbr0} NET=${NET:-dhcp} GATE=${GATE:-} VLAN=${VLAN:-} ROOT_PW=${ROOT_PW:-}
    ROOTFS_STORE=${ROOTFS_STORE:-$(select_storage rootdir)}
    TMPL_STORE=${TMPL_STORE:-$(select_storage vztmpl)}
    FS_VERSION=${FS_VERSION:-latest} FS_ADMIN_USER=${FS_ADMIN_USER:-admin}
    FS_ADMIN_EMAIL=${FS_ADMIN_EMAIL:-} FS_ADMIN_PASSWORD=${FS_ADMIN_PASSWORD:-}
    FS_ALLOWED_HOSTS=${FS_ALLOWED_HOSTS:-} FS_USDA_KEY=${FS_USDA_KEY:-}
    FS_SENTRY_DSN=${FS_SENTRY_DSN:-} FS_BACKUPS=${FS_BACKUPS:-1}
}

advanced_settings() {
    default_settings
    local ans
    CTID=$(wt_input "Container ID" "Container ID:" "$CTID")
    CT_HOSTNAME=$(wt_input "Hostname" "Hostname (also how the LAN will reach it by name):" "$CT_HOSTNAME")
    CORES=$(wt_input "CPU" "CPU cores (2 minimum):" "$CORES")
    RAM=$(wt_input "Memory" "RAM in MB (2048 minimum, 4096 recommended):" "$RAM")
    DISK=$(wt_input "Disk" "Disk size in GB (10 recommended):" "$DISK")
    BRIDGE=$(wt_input "Network" "Bridge:" "$BRIDGE")
    NET=$(wt_input "Network" "IPv4: 'dhcp', or a static address in CIDR form (192.168.1.40/24):" "$NET")
    if [ "$NET" != dhcp ]; then
        GATE=$(wt_input "Network" "Gateway:" "")
    fi
    VLAN=$(wt_input "Network" "VLAN tag (blank for none):" "")
    ROOT_PW=$(wt_password "Root password" "Container root password (blank: none; use 'pct enter $CTID'):")

    FS_ADMIN_USER=$(wt_input "Admin account" "FarmSteader admin username:" "$FS_ADMIN_USER")
    FS_ADMIN_EMAIL=$(wt_input "Admin account" "Admin email (optional):" "")
    FS_ADMIN_PASSWORD=$(wt_password "Admin account" "Admin password (blank: generate one and show it at the end):")
    if [ -n "$FS_ADMIN_PASSWORD" ]; then
        ans=$(wt_password "Admin account" "Repeat the admin password:")
        [ "$ans" = "$FS_ADMIN_PASSWORD" ] || die "admin passwords did not match"
    fi
    FS_ALLOWED_HOSTS=$(wt_input "Site address" \
        "Extra hostnames/IPs the site should answer to, comma-separated.\nBlank: the container's own IP and hostname (recommended)." "")
    FS_USDA_KEY=$(wt_input "Integrations" "USDA NASS API key (optional; crop price sync is skipped without it):" "")
    if wt_yesno "Backups" "Install a nightly database backup (kept 14 days)?"; then FS_BACKUPS=1; else FS_BACKUPS=0; fi
    FS_VERSION=$(wt_input "Version" "FarmSteader version to install ('latest' or e.g. 0.3.0):" "latest")
}

show_settings() {
    cat <<EOF
  Container ${BOLD}$CTID${CL} ($CT_HOSTNAME): $CORES cores, ${RAM} MB RAM, ${DISK} GB on $ROOTFS_STORE
  Network:   $BRIDGE, ${NET}${GATE:+ via $GATE}${VLAN:+, VLAN $VLAN}
  Template:  newest Debian 13 standard, stored on $TMPL_STORE
  App:       FarmSteader $FS_VERSION, admin '$FS_ADMIN_USER', backups $([ "$FS_BACKUPS" = 1 ] && echo on || echo off)
EOF
}

# --- Create ------------------------------------------------------------------

build_container() {
    msg_info "Updating the template list"
    pveam update >/dev/null
    TEMPLATE=$(latest_template)
    [ -n "$TEMPLATE" ] || die "no debian-13-standard template is available from pveam"
    msg_ok "template: $TEMPLATE"

    if ! pveam list "$TMPL_STORE" | grep -F "$TEMPLATE" >/dev/null; then
        msg_info "Downloading $TEMPLATE"
        pveam download "$TMPL_STORE" "$TEMPLATE" >/dev/null
        msg_ok "downloaded $TEMPLATE"
    fi

    local net="name=eth0,bridge=$BRIDGE,ip=$NET"
    [ -n "$GATE" ] && net+=",gw=$GATE"
    [ -n "$VLAN" ] && net+=",tag=$VLAN"
    # nesting=1 keeps systemd and journald happy in an unprivileged container.
    # (keyctl is a Docker/Podman requirement, not ours.) Swap lets the one
    # memory spike -- the price-sync task importing pandas -- swap instead of
    # the OOM killer taking PostgreSQL.
    local args=(create "$CTID" "$TMPL_STORE:vztmpl/$TEMPLATE"
        --hostname "$CT_HOSTNAME" --cores "$CORES" --memory "$RAM" --swap 1024
        --rootfs "$ROOTFS_STORE:$DISK" --net0 "$net"
        --features nesting=1 --unprivileged 1 --onboot 1
        --ostype debian --timezone host --tags farmsteader)
    [ -n "$ROOT_PW" ] && args+=(--password "$ROOT_PW")

    msg_info "Creating container $CTID"
    pct "${args[@]}" >/dev/null
    CT_CREATED=1
    msg_ok "created container $CTID"

    msg_info "Starting container $CTID"
    pct start "$CTID"
    # Templates come up slower than `pct start` returns; wait for real DNS.
    local i
    for i in $(seq 1 30); do
        pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1 && break
        [ "$i" = 30 ] && die "container $CTID has no network after 60s (check bridge '$BRIDGE' and DHCP)"
        sleep 2
    done
    msg_ok "container $CTID is up and online"
}

# The answers go in as a 0600 file written with %q quoting, not as a command
# line: passwords may contain spaces or $, and argv is visible to `ps`.
install_app() {
    fetch install/farmsteader-install.sh "$WORK/farmsteader-install.sh"
    fetch misc/install.func "$WORK/farmsteader-install.func"
    fetch deploy/install.sh "$WORK/farmsteader-deploy-install.sh"
    (
        umask 077
        {
            printf 'FS_VERSION=%q\n' "$FS_VERSION"
            printf 'FS_ADMIN_USER=%q\n' "$FS_ADMIN_USER"
            printf 'FS_ADMIN_EMAIL=%q\n' "$FS_ADMIN_EMAIL"
            printf 'FS_ADMIN_PASSWORD=%q\n' "$FS_ADMIN_PASSWORD"
            printf 'FS_ALLOWED_HOSTS=%q\n' "$FS_ALLOWED_HOSTS"
            printf 'FS_USDA_KEY=%q\n' "$FS_USDA_KEY"
            printf 'FS_SENTRY_DSN=%q\n' "$FS_SENTRY_DSN"
            printf 'FS_BACKUPS=%q\n' "$FS_BACKUPS"
        } >"$WORK/farmsteader.vars"
    )
    local f
    for f in farmsteader-install.sh farmsteader-install.func farmsteader-deploy-install.sh; do
        pct push "$CTID" "$WORK/$f" "/root/$f"
    done
    pct push "$CTID" "$WORK/farmsteader.vars" /root/farmsteader.vars --perms 0600

    echo
    printf ' Installing FarmSteader inside container %s (a few minutes):\n\n' "$CTID"
    pct exec "$CTID" -- bash /root/farmsteader-install.sh
}

finish() {
    local ip creds_user creds_pw
    ip=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')
    creds_user=$(pct exec "$CTID" -- cat /root/farmsteader.creds 2>/dev/null | sed -n 's/^  user: *//p')
    creds_pw=$(pct exec "$CTID" -- cat /root/farmsteader.creds 2>/dev/null | sed -n 's/^  password: *//p')
    pct set "$CTID" --description "FarmSteader -- http://${ip:-<container-ip>}/
Update: run the installer again on this node and choose this container.
Admin credentials: /root/farmsteader.creds inside the container." >/dev/null
    cat <<EOF

 ${GN}${BOLD}FarmSteader is ready.${CL}

   Open:    ${BOLD}http://${ip:-<container-ip>}/${CL}
EOF
    if [ -n "$creds_pw" ]; then
        printf '   Login:   %s / %s\n' "$creds_user" "$creds_pw"
        printf '            (saved in the container at /root/farmsteader.creds -- change it after signing in)\n'
    fi
    cat <<EOF
   Shell:   pct enter $CTID
   Update:  run this installer again on this node and choose "Update"

EOF
}

# --- Update ------------------------------------------------------------------

# Delegates to the installed release's own updater, so the upgrade procedure
# always matches the version being upgraded (and rolls back on failure).
update_container() {  # ctid
    local id=$1 used
    pct exec "$id" -- test -x /opt/farmsteader/current/deploy/update.sh \
        || die "container $id has no FarmSteader 0.3.0+ install (no /opt/farmsteader/current/deploy/update.sh)"
    used=$(pct exec "$id" -- df --output=pcent / | tail -1 | tr -dc '0-9')
    if [ -n "$used" ] && [ "$used" -gt 80 ]; then
        msg_warn "container $id's disk is ${used}% full; an upgrade needs room for a second release and a database dump"
    fi
    echo
    pct exec "$id" -- /opt/farmsteader/current/deploy/update.sh
}

# --- Main --------------------------------------------------------------------

header
[ "$FARMSTEADER_DRY_RUN" = 1 ] && msg_warn "DRY RUN: Proxmox commands are stubbed; nothing will be created"
catch_errors
root_check
pve_check
arch_check

if [ "$FS_CT_DEFAULTS" != 1 ]; then
    mapfile -t existing < <(farmsteader_containers)
    if [ "${#existing[@]}" -gt 0 ]; then
        opts=(new "Create a new FarmSteader container")
        for line in "${existing[@]}"; do
            opts+=("${line%% *}" "Update ${line#* } (container ${line%% *})")
        done
        choice=$(wt_menu "$APP" "FarmSteader containers already exist on this node:" "${opts[@]}")
        if [ "$choice" != new ]; then
            update_container "$choice"
            exit 0
        fi
    fi
fi

if [ "$FS_CT_DEFAULTS" = 1 ]; then
    default_settings
else
    mode=$(wt_menu "$APP" "Set up a new FarmSteader container:" \
        default "Default settings (2 CPU, 2 GB RAM, 10 GB, DHCP)" \
        advanced "Advanced settings")
    if [ "$mode" = advanced ]; then advanced_settings; else default_settings; fi
fi

echo
show_settings
echo
if [ "$FS_CT_DEFAULTS" != 1 ]; then
    wt_yesno "$APP" "Create container $CTID with these settings?\n\n$(show_settings | sed 's/\x1b\[[0-9;]*m//g')" \
        || { echo; msg_warn "cancelled -- nothing was created"; exit 0; }
fi

build_container
install_app
finish
