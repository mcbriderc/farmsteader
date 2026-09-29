from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
except ImportError:
    pass

INTERNAL_IPS = ["127.0.0.1"]

# WhiteNoise is in the shared middleware stack so dev exercises the same chain
# as prod, but STATIC_ROOT only exists after collectstatic -- which nobody runs
# locally. Serving through the staticfiles finders instead keeps it quiet and
# picks up edits without a restart.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
