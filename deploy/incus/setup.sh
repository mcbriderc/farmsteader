#!/usr/bin/env bash
# FarmSteader LXC provisioning script for Debian 13 (Trixie)
# Usage: incus exec farmsteader -- bash < setup.sh
#
# Prerequisites:
#   incus launch images:debian/13 farmsteader
#   incus config set farmsteader security.nesting=true
set -euo pipefail

APP_USER="farmsteader"
APP_DIR="/opt/farmsteader"
VENV_DIR="$APP_DIR/.venv"
DB_NAME="farmsteader"
DB_USER="farmsteader"
DB_PASS="$(openssl rand -base64 24)"
SECRET_KEY="$(openssl rand -base64 48)"

echo "==> Installing system packages..."
apt-get update
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip \
    postgresql postgresql-contrib postgis \
    redis-server \
    nginx \
    gdal-bin libgdal-dev libgeos-dev libproj-dev \
    build-essential git curl \
    certbot python3-certbot-nginx

echo "==> Creating app user..."
useradd --system --shell /bin/bash --home "$APP_DIR" --create-home "$APP_USER" || true

echo "==> Setting up PostgreSQL..."
systemctl enable --now postgresql
su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\" | grep -q 1 || psql -c \"CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASS';\""
su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\" | grep -q 1 || psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""
su - postgres -c "psql -d $DB_NAME -c 'CREATE EXTENSION IF NOT EXISTS postgis;'"

echo "==> Setting up Redis..."
systemctl enable --now redis-server

echo "==> Deploying application code..."
# In production, this would be a git clone or rsync from host
# For now, assumes code is already at $APP_DIR
if [ ! -f "$APP_DIR/manage.py" ]; then
    echo "WARNING: No application code found at $APP_DIR"
    echo "Copy your code: incus file push -r /path/to/farmsteader/ farmsteader/opt/"
fi

echo "==> Creating Python venv and installing deps..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip wheel
if [ -f "$APP_DIR/requirements/base.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements/base.txt"
fi
if [ -f "$APP_DIR/requirements/prod.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements/prod.txt"
fi
# Ensure gunicorn is installed
"$VENV_DIR/bin/pip" install gunicorn

echo "==> Writing .env file..."
cat > "$APP_DIR/.env" <<ENVEOF
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$SECRET_KEY
DATABASE_URL=postgis://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
REDIS_URL=redis://localhost:6379/0
USDA_NASS_API_KEY=
ALLOWED_HOSTS=*
# AGPL "Source" link in the sidebar. Correct for the unmodified code this script
# installs; if you modify FarmSteader, point it at your own fork instead.
FARMSTEADER_SOURCE_URL=https://github.com/mcbriderc/farmsteader
ENVEOF
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

echo "==> Running migrations, building CSS and collecting static..."
su - "$APP_USER" -c "cd $APP_DIR && $VENV_DIR/bin/python manage.py migrate --noinput"
# static/css/dist/ is gitignored, so the stylesheet does not exist in a fresh
# checkout. It must be built BEFORE collectstatic or the site ships unstyled.
su - "$APP_USER" -c "cd $APP_DIR && $VENV_DIR/bin/python manage.py tailwind build --force"
su - "$APP_USER" -c "cd $APP_DIR && $VENV_DIR/bin/python manage.py collectstatic --noinput"

echo "==> Installing systemd services..."
cp "$APP_DIR/deploy/incus/farmsteader-web.service" /etc/systemd/system/
cp "$APP_DIR/deploy/incus/farmsteader-celery.service" /etc/systemd/system/
cp "$APP_DIR/deploy/incus/farmsteader-celerybeat.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now farmsteader-web farmsteader-celery farmsteader-celerybeat

echo "==> Installing Nginx config..."
cp "$APP_DIR/deploy/incus/farmsteader.nginx.conf" /etc/nginx/sites-available/farmsteader
ln -sf /etc/nginx/sites-available/farmsteader /etc/nginx/sites-enabled/farmsteader
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl enable --now nginx && systemctl reload nginx

echo "==> Setting up nightly backup cron..."
mkdir -p /var/backups/farmsteader
cat > /etc/cron.d/farmsteader-backup <<'CRONEOF'
0 2 * * * postgres pg_dump farmsteader | gzip > /var/backups/farmsteader/farmsteader-$(date +\%Y\%m\%d).sql.gz
7 2 * * * root find /var/backups/farmsteader -name "*.sql.gz" -mtime +14 -delete
CRONEOF

echo "==> Setting permissions..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
mkdir -p "$APP_DIR/media"
chown "$APP_USER:$APP_USER" "$APP_DIR/media"

echo ""
echo "============================================"
echo "  FarmSteader deployed successfully!"
echo "============================================"
echo "  DB password: $DB_PASS"
echo "  Secret key:  $SECRET_KEY"
echo "  App dir:     $APP_DIR"
echo ""
echo "  Create a superuser:"
echo "    incus exec farmsteader -- su - $APP_USER -c \\"
echo "      'cd $APP_DIR && $VENV_DIR/bin/python manage.py createsuperuser'"
echo ""
echo "  View logs:"
echo "    incus exec farmsteader -- journalctl -u farmsteader-web -f"
echo "============================================"
