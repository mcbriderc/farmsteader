"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# `config.settings` is a package with no settings in it -- pointing at it raises
# ImportError. Production is the only thing that loads this module through a
# WSGI server, so that is the right default; `manage.py` still defaults to dev.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')

application = get_wsgi_application()
