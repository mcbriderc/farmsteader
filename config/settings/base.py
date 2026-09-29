import os
from pathlib import Path

import environ

from config.__version__ import __version__ as APP_VERSION

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")

# Scheme-qualified origins (https://farm.example.com), not bare hostnames --
# Django rejects the latter. The installer populates this alongside ALLOWED_HOSTS.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # Third-party
    "import_export",
    "django_tailwind_cli",
    # Local
    "apps.accounts",
    "apps.core",
    "apps.land",
    "apps.livestock",
    "apps.crops",
    "apps.equipment",
    "apps.buildings",
    "apps.consumables",
    "apps.employment",
    "apps.produce",
    "apps.data_io",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Must sit directly after SecurityMiddleware. Only used by the container
    # image, where Django serves its own static files; under the LXC/nginx
    # deployment nginx's /static/ alias intercepts before Django is reached,
    # so this is a no-op there.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.CurrentFarmMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.current_farm",
                "apps.core.context_processors.app_meta",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
# Default 0 (connection per request) so tests and the dev server are unaffected;
# prod.py raises it. CONN_HEALTH_CHECKS is what makes reuse safe -- without it a
# connection dropped by a Postgres restart is handed to the next request.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool("CONN_HEALTH_CHECKS", default=False)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Both roots are env-overridable so a deployment can put them outside the code
# directory (/var/lib/farmsteader/media). That is the prerequisite for replacing
# /opt/farmsteader wholesale on upgrade without destroying uploads.
STATIC_ROOT = Path(env.str("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))

MEDIA_URL = "media/"
MEDIA_ROOT = Path(env.str("MEDIA_ROOT", default=str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compressed, deliberately NOT CompressedManifestStaticFilesStorage: the
    # manifest variant hard-fails collectstatic on any url() it cannot resolve,
    # and vendored leaflet-draw CSS references sprite paths that do not resolve
    # from STATIC_ROOT. Compression alone gives the win without the fragility.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Shown as a "Source" link in the sidebar. AGPL section 13 obliges anyone running
# a *modified* copy as a network service to offer its users the corresponding
# source; an operator who forks must point this at their fork, not at upstream.
# Empty renders no link, so an unconfigured install advertises nothing.
FARMSTEADER_SOURCE_URL = env.str("FARMSTEADER_SOURCE_URL", default="")

# Largest uncompressed size accepted from an uploaded farm backup archive (zip-bomb guard).
FARMSTEADER_MAX_RESTORE_BYTES = env.int("FARMSTEADER_MAX_RESTORE_BYTES", default=2 * 1024**3)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.FarmUser"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# Tailwind CSS
# Pinned, not "latest": CI builds the stylesheet on every run, so an upstream
# release must not be able to change the output without a commit.
TAILWIND_CLI_VERSION = "4.3.3"
TAILWIND_CLI_AUTOMATIC_DOWNLOAD = True
TAILWIND_CLI_SRC_CSS = "assets/css/input.css"
TAILWIND_CLI_DIST_CSS = "css/dist/styles.css"

# External APIs
USDA_NASS_API_KEY = env("USDA_NASS_API_KEY", default="")

