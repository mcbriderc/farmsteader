#!/usr/bin/env bash
#
# Recompile requirements/*.txt (exact pins) from requirements/*.in (ranges).
#
# Resolution runs inside python:3.13 rather than the local venv on purpose:
# 3.13 is what CI and the Debian 13 deploy target run, and a resolver answers
# for the interpreter it runs under -- a lock compiled on the 3.14 dev venv can
# pick a version, or a marker-gated dependency, that 3.13 then installs
# differently.
#
# Without arguments this is conservative: existing pins are kept and only what
# the .in files force to change moves. Pass pip-compile flags through to move
# deliberately:
#
#   scripts/lock-deps.sh                          # sync after editing a .in
#   scripts/lock-deps.sh --upgrade                # everything, within ceilings
#   scripts/lock-deps.sh --upgrade-package celery # one package
#
# base.txt is compiled first because dev.in and prod.in constrain against it.
set -Eeuo pipefail

PYTHON_IMAGE="docker.io/library/python:3.13-slim"
PIP_TOOLS_VERSION="7.6.1"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { echo "lock-deps: $*" >&2; exit 1; }

# Rootless podman maps the container's root onto the invoking user, so the
# lock files come out owned correctly. Docker needs --user for the same result.
if command -v podman >/dev/null 2>&1; then
    run=(podman run --rm)
elif command -v docker >/dev/null 2>&1; then
    run=(docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp)
else
    die "need podman or docker to run the resolver under python 3.13"
fi

# Passed as positional parameters rather than spliced into the string, so a
# flag value can never be reinterpreted by the inner shell.
# shellcheck disable=SC2016
inner='
set -eu
python -m pip install --quiet --disable-pip-version-check --no-warn-script-location --root-user-action=ignore --user "pip-tools==$PIP_TOOLS_VERSION"
export PATH="$HOME/.local/bin:$PATH"
for name in base dev prod; do
    echo "lock-deps: compiling requirements/$name.txt" >&2
    pip-compile --quiet --strip-extras --allow-unsafe --no-emit-index-url \
        --output-file "requirements/$name.txt" "$@" "requirements/$name.in"
done
'

"${run[@]}" \
    -v "$REPO_ROOT:/src:Z" -w /src \
    -e PIP_TOOLS_VERSION="$PIP_TOOLS_VERSION" \
    -e CUSTOM_COMPILE_COMMAND="scripts/lock-deps.sh" \
    "$PYTHON_IMAGE" sh -c "$inner" lock-deps "$@"
