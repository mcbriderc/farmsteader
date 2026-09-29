from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405

# --- TLS -------------------------------------------------------------------
#
# All of this is gated on one switch. A default LAN install (the Proxmox LXC
# case) terminates plain HTTP on nginx port 80, so every one of these must be
# off or the app infinite-redirects: SECURE_SSL_REDIRECT sends the browser to
# https://, nginx does not listen there, and nothing ever resolves.
#
# Turning on TLS is then a single env var, FARMSTEADER_HTTPS=1, with individual
# overrides available for anything unusual (TLS terminated further upstream,
# say). Each setting is still independently addressable so the installer's
# Let's Encrypt path does not have to understand the grouping.
_https = env.bool("FARMSTEADER_HTTPS", default=False)  # noqa: F405

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=_https)  # noqa: F405
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=_https)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=_https)  # noqa: F405
SECURE_HSTS_SECONDS = env.int(  # noqa: F405
    "SECURE_HSTS_SECONDS", default=31536000 if _https else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(  # noqa: F405
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=_https
)
# Adds the `preload` directive, which does nothing until the domain is actually
# submitted to the browser preload lists -- but that submission is effectively
# irreversible, so leave it off (SECURE_HSTS_PRELOAD=0) if any subdomain might
# ever need plain HTTP.
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=_https)  # noqa: F405

# Safe to trust unconditionally because nginx *sets* (not appends)
# `X-Forwarded-Proto $scheme` on every proxied request, overwriting whatever the
# client sent. Set USE_PROXY_SSL_HEADER=0 if the app is ever exposed without a
# proxy in front, where a client could forge the header to fake HTTPS.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env.bool("USE_PROXY_SSL_HEADER", default=True)  # noqa: F405
    else None
)

# --- Headers ---------------------------------------------------------------
#
# SECURE_BROWSER_XSS_FILTER is deliberately absent: it emitted X-XSS-Protection,
# which every current browser ignores and which Django deprecated.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Database --------------------------------------------------------------
#
# Persistent connections: gunicorn gthread workers handle many short requests,
# and a PostGIS connect is not cheap. The health check costs one round trip on
# reuse and is what keeps a restarted Postgres from poisoning live workers.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool(  # noqa: F405
    "CONN_HEALTH_CHECKS", default=True
)

# --- Static ----------------------------------------------------------------
#
# The release tarball and container image both ship a pre-built stylesheet, so
# no production host should ever reach for the 120 MB standalone binary -- which
# it would do at the worst possible moment, mid-deploy, over the internet.
TAILWIND_CLI_AUTOMATIC_DOWNLOAD = False

# --- Logging ---------------------------------------------------------------
#
# gunicorn and celery both run under systemd with stdout/stderr wired to the
# journal, so logging to the console is logging to journald. Without this dict
# Django's default swallows app-level logging outside of request errors, and
# `journalctl -u farmsteader-web` shows nothing useful when something breaks.
LOG_LEVEL = env.str("LOG_LEVEL", default="INFO").upper()  # noqa: F405

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Every disallowed Host header logs at ERROR by default, which turns a
        # port scan into log spam. The 400 is still returned.
        "django.security.DisallowedHost": {"handlers": ["console"], "level": "CRITICAL"},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# --- Error reporting -------------------------------------------------------
#
# Entirely opt-in: no DSN, no import, no network egress. The ImportError guard
# means prod settings still load when sentry-sdk is absent, which is what lets
# CI run `manage.py check --deploy` against this module with only dev deps.
SENTRY_DSN = env.str("SENTRY_DSN", default="")  # noqa: F405

if SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            release=APP_VERSION,  # noqa: F405
            environment=env.str("SENTRY_ENVIRONMENT", default="production"),  # noqa: F405
            traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),  # noqa: F405
            # Farm data is the user's own; do not ship it to a third party.
            send_default_pii=False,
        )
    except ImportError:  # pragma: no cover - depends on install profile
        import warnings

        warnings.warn("SENTRY_DSN is set but sentry-sdk is not installed", stacklevel=2)
