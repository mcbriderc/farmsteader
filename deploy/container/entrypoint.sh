#!/usr/bin/env bash
#
# Container entry point: one image, one role per container.
#
#   web | worker | beat     long-running services; wait for a migrated database
#   migrate                 apply migrations once and exit
#   manage <args>           any manage.py command, e.g. manage createsuperuser
#   shell                   Django shell
#
# Anything else is run as given.
set -Eeuo pipefail

die() { echo "entrypoint: $*" >&2; exit 1; }

# Not pg_isready: the image has no PostgreSQL client.
wait_for_db() {
    python - <<'PY' || die "database did not answer within 120 seconds"
import os, socket, sys, time
from urllib.parse import urlsplit

url = urlsplit(os.environ["DATABASE_URL"])
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        socket.create_connection((url.hostname, url.port or 5432), timeout=3).close()
        sys.exit(0)
    except OSError:
        time.sleep(2)
sys.exit(1)
PY
}

# Compose gates on the migrate service too, but not every engine honours that
# condition. Only the migrate service ever applies migrations: several replicas
# racing `migrate` can corrupt a schema, so everything else just waits for it.
wait_for_migrations() {
    local attempt
    for attempt in $(seq 1 60); do
        python manage.py migrate --check >/dev/null 2>&1 && return 0
        [ "$attempt" = 1 ] && echo "entrypoint: waiting for database migrations"
        sleep 5
    done
    die "database migrations were not applied within 5 minutes; check the migrate service's logs"
}

role=${1:-web}
[ "$#" -gt 0 ] && shift

case "$role" in
    web)
        wait_for_db
        wait_for_migrations
        # /dev/shm: gunicorn's worker heartbeat file stalls workers on a slow
        # overlay filesystem.
        exec gunicorn config.wsgi:application -c deploy/gunicorn.conf.py --worker-tmp-dir /dev/shm "$@"
        ;;
    worker)
        wait_for_db
        wait_for_migrations
        # --max-tasks-per-child: see deploy/systemd/farmsteader-celery.service.
        exec celery -A config worker --loglevel=info \
            --concurrency="${CELERY_CONCURRENCY:-2}" --max-tasks-per-child=50 "$@"
        ;;
    beat)
        wait_for_db
        wait_for_migrations
        # On a volume: losing this file makes beat forget when each task last
        # ran and re-fire daily jobs. No pidfile: a stale one blocks a restart.
        exec celery -A config beat --loglevel=info \
            --schedule=/data/beat/celerybeat-schedule --pidfile= "$@"
        ;;
    migrate)
        wait_for_db
        exec python manage.py migrate --noinput "$@"
        ;;
    manage)
        exec python manage.py "$@"
        ;;
    shell)
        exec python manage.py shell "$@"
        ;;
    *)
        exec "$role" "$@"
        ;;
esac
