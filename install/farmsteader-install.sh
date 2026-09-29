#!/usr/bin/env bash
#
# Runs inside the new container, pushed there by ct/farmsteader.sh together
# with misc/install.func, deploy/install.sh and the answers file.
#
# Thin on purpose: container preparation, then FarmSteader's own installer --
# the same deploy/install.sh used on any Debian machine, so there is exactly
# one install procedure to test and maintain.

# shellcheck source=misc/install.func
. /root/farmsteader-install.func
catch_errors

# The answers, written by the host with %q quoting. Exported, not passed as
# flags, so the admin password never appears in a process list.
if [ ! -f /root/farmsteader.vars ]; then
    echo "missing /root/farmsteader.vars (this script is run by ct/farmsteader.sh)" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. /root/farmsteader.vars
set +a
# The password must not outlive the install, whatever happens next.
trap 'rm -f /root/farmsteader.vars' EXIT

setting_up_container
network_check
update_os

bash /root/farmsteader-deploy-install.sh

motd_ssh
customize
rm -f /root/farmsteader-install.sh /root/farmsteader-install.func /root/farmsteader-deploy-install.sh
msg_ok "container setup complete"
