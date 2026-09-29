import os

from celery import Celery
from celery.schedules import crontab

# This default decides the settings module for *every* entrypoint, not just
# celery: config/__init__.py imports this module, so it runs before the
# setdefault in wsgi.py/asgi.py and wins the race. Pointing it at dev would mean
# a gunicorn process started without DJANGO_SETTINGS_MODULE in its environment
# silently comes up with DEBUG=True and ALLOWED_HOSTS=["*"] -- failing open,
# which is far worse than not booting.
#
# Note that .env cannot influence this: django-environ reads that file from
# inside base.py, by which point the settings module has already been resolved.
# Dev entrypoints therefore have to say so themselves -- see manage.py and the
# celery target in the Makefile.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("farmsteader")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "sync-weather-every-6h": {
        "task": "apps.land.tasks.sync_all_weather",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "sync-crop-prices-daily": {
        "task": "apps.crops.tasks.sync_crop_prices",
        "schedule": crontab(minute=0, hour=2),
    },
    "sync-commodity-prices-daily": {
        "task": "apps.crops.tasks.sync_commodity_prices",
        "schedule": crontab(minute=0, hour=7),
    },
}
