.PHONY: run celery tailwind tailwind-watch migrate

run:
	python manage.py runserver 0.0.0.0:8000

# Explicit: config/celery.py defaults to prod so a misconfigured production
# process fails loudly instead of booting with DEBUG=True. Unlike manage.py,
# the celery CLI has nowhere else to pick dev up from.
celery:
	DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config worker -l info

tailwind:
	python manage.py tailwind build --force

tailwind-watch:
	python manage.py tailwind watch

migrate:
	python manage.py migrate
