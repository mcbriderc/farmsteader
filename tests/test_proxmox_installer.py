"""The Proxmox host installer (ct/farmsteader.sh), exercised without a cluster.

FARMSTEADER_DRY_RUN=1 swaps pct/pveam/pvesm/pvesh/pveversion for stubs that
print what would run and return canned output shaped like the real tools, so
the whole host-side flow runs here. What these pin down is the part that is
expensive to get wrong on someone's real node: the exact `pct create` line,
the template and storage choices, and that cancelling a menu creates nothing.

The container-side half runs FarmSteader's own deploy/install.sh, which is
tested for real (install, upgrade, rollback) in Incus -- see DOCS.md.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "ct" / "farmsteader.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def run_ct(**env):
    full_env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", "/tmp"),
        "FARMSTEADER_DRY_RUN": "1",
        **env,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def pct_create_args(result):
    lines = [
        line.split("[dry-run] ", 1)[1]
        for line in (result.stdout + result.stderr).splitlines()
        if "[dry-run] pct create" in line
    ]
    assert len(lines) == 1, result.stdout + result.stderr
    return lines[0].split()


def test_default_install_creates_the_expected_container():
    result = run_ct(FS_CT_DEFAULTS="1")

    assert result.returncode == 0, result.stderr
    assert pct_create_args(result) == [
        "pct", "create", "105",
        "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst",
        "--hostname", "farmsteader",
        "--cores", "2",
        "--memory", "2048",
        "--swap", "1024",
        "--rootfs", "local-lvm:10",
        "--net0", "name=eth0,bridge=vmbr0,ip=dhcp",
        "--features", "nesting=1",
        "--unprivileged", "1",
        "--onboot", "1",
        "--ostype", "debian",
        "--timezone", "host",
        "--tags", "farmsteader",
    ]


def test_template_is_the_newest_debian_13_not_a_hardcoded_name():
    """The stub offers 12.12, 13.0 and 13.1; only 13.1 is right.

    A pinned template filename is the most common way these installers rot:
    Proxmox publishes point releases and removes the old file.
    """
    result = run_ct(FS_CT_DEFAULTS="1")

    template = pct_create_args(result)[3]
    assert template == "local:vztmpl/debian-13-standard_13.1-2_amd64.tar.zst"


def test_template_store_and_disk_store_are_chosen_separately():
    """Templates live on `local` (dir), disks on `local-lvm`; one store for both fails."""
    args = pct_create_args(run_ct(FS_CT_DEFAULTS="1"))

    assert args[3].startswith("local:vztmpl/")
    assert args[args.index("--rootfs") + 1] == "local-lvm:10"


def test_settings_can_be_preset_for_unattended_runs():
    result = run_ct(
        FS_CT_DEFAULTS="1",
        CT_HOSTNAME="barn",
        var_ram="4096",
        NET="192.168.1.40/24",
        GATE="192.168.1.1",
        VLAN="20",
    )

    args = pct_create_args(result)
    assert args[args.index("--hostname") + 1] == "barn"
    assert args[args.index("--memory") + 1] == "4096"
    assert args[args.index("--net0") + 1] == (
        "name=eth0,bridge=vmbr0,ip=192.168.1.40/24,gw=192.168.1.1,tag=20"
    )


def test_cancelling_a_menu_creates_nothing():
    """Prompts run in $(...), where a bare `exit` only leaves the subshell.

    Without the dedicated cancel code the installer would carry on with an
    empty answer and reach `pct create`.
    """
    result = run_ct(FARMSTEADER_DRY_RUN_WT_RC="1")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "cancelled -- nothing was created" in output
    assert "pct create" not in output


def test_answers_reach_the_container_as_a_private_file_not_argv():
    """The admin password must never appear on a command line."""
    result = run_ct(FS_CT_DEFAULTS="1", FS_ADMIN_PASSWORD="s3cret $pace'd")

    output = result.stdout + result.stderr
    assert "s3cret" not in output
    assert "/root/farmsteader.vars --perms 0600" in output


def test_uses_the_shared_installer_rather_than_its_own_copy():
    """One install procedure: the container runs deploy/install.sh."""
    result = run_ct(FS_CT_DEFAULTS="1")
    output = result.stdout + result.stderr

    assert "farmsteader-deploy-install.sh /root/farmsteader-deploy-install.sh" in output
    container_side = (REPO / "install" / "farmsteader-install.sh").read_text()
    assert "bash /root/farmsteader-deploy-install.sh" in container_side
