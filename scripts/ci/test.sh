#!/usr/bin/env bash
#
# The shared test body for .forgejo/workflows/ci.yml and (from Phase 2)
# release.yml. It lives here rather than being duplicated in YAML because the
# Podman-in-LXC runner cannot use reusable workflows -- those are resolved by a
# JavaScript action, and there is no node in the job container. Shell is the
# only dedup mechanism available.
#
# Expects to run from the repo root with the Python dependencies already
# installed and DATABASE_URL / REDIS_URL / SECRET_KEY pointing at live services.
set -Eeuo pipefail

cd "$(dirname "$0")/../.."

echo "==> Building Tailwind stylesheet"
# tests/test_theming.py asserts the compiled stylesheet carries the dark theme,
# and fails rather than skips when CI is set -- static/css/dist/ is gitignored,
# so without this step the suite fails on a fresh checkout.
#
# Phase 1 replaces this with scripts/build-css.sh, which drives the standalone
# binary directly and so needs neither a Django bootstrap nor SECRET_KEY.
python manage.py tailwind build --force

echo "==> Running tests"
pytest

echo "==> Checking production settings"
# Guards the §7 hardening against regression. Two things make this meaningful:
#
#   --fail-level WARNING, because every finding Django reports here is a
#   WARNING; at the default ERROR level the check passes unconditionally and
#   tests nothing.
#
#   FARMSTEADER_HTTPS=1, because the TLS settings are env-gated and default to
#   off for the plain-HTTP LAN install. That default is deliberate, but it also
#   trips W004/W008/W012/W016 -- so the configuration worth gating on is the
#   secure one, which is what a public deployment actually runs.
#
# The dummy values are inert: no connection is opened, but prod.py reads
# ALLOWED_HOSTS eagerly and W009 rejects a short SECRET_KEY.
DJANGO_SETTINGS_MODULE=config.settings.prod \
DATABASE_URL="${DATABASE_URL}" \
ALLOWED_HOSTS="farmsteader.example.com" \
SECRET_KEY="ci-deploy-check-placeholder-key-of-sufficient-length-0123456789" \
FARMSTEADER_HTTPS=1 \
    python manage.py check --deploy --fail-level WARNING

echo "==> OK"
