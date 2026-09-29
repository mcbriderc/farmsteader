"""Health probe behaviour.

These are less about the views themselves -- they are ten lines each -- and more
about the three-way coupling that makes them work: the URL must be registered
without a trailing slash, the path must be exempt in CurrentFarmMiddleware, and
readyz must actually report failure rather than swallowing it. Break any one and
the endpoint still returns something that looks fine to a naive checker, which
is exactly the failure mode a health probe is supposed to prevent.
"""

import json
from unittest import mock

import pytest
from django.conf import settings

from config.__version__ import __version__


@pytest.mark.django_db
def test_healthz_is_reachable_without_authentication(client):
    """No login, no farm in session, still 200 -- not a redirect.

    CurrentFarmMiddleware redirects unauthenticated requests to the login page,
    so this fails the moment /healthz drops out of EXEMPT_PATHS.
    """
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_healthz_reports_the_application_version(client):
    body = json.loads(client.get("/healthz").content)

    assert body["status"] == "ok"
    assert body["version"] == __version__


@pytest.mark.django_db
def test_healthz_is_not_cached(client):
    """A cached 200 outlives the outage it is supposed to report."""
    response = client.get("/healthz")

    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_healthz_does_not_redirect_for_a_trailing_slash(client):
    """The probe path must be final.

    APPEND_SLASH would 301 /healthz -> /healthz/ if the route were registered
    with a slash; a checker following redirects would then report success based
    on whatever answered the second request.
    """
    response = client.get("/healthz")

    assert response.status_code == 200
    assert not response.has_header("Location")


@pytest.mark.django_db
def test_healthz_rejects_post(client):
    """SonarQube python:S3752 -- every view declares its methods."""
    assert client.post("/healthz").status_code == 405


@pytest.mark.django_db
def test_readyz_reports_ok_when_dependencies_answer(client):
    """Redis is not running in the test environment, so it is stubbed."""
    with mock.patch("redis.from_url") as from_url:
        response = client.get("/readyz")

    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "redis": "ok"}
    from_url.assert_called_once()


@pytest.mark.django_db
def test_readyz_uses_the_configured_broker_url(client):
    with mock.patch("redis.from_url") as from_url:
        client.get("/readyz")

    assert from_url.call_args.args[0] == settings.CELERY_BROKER_URL


@pytest.mark.django_db
def test_readyz_returns_503_when_redis_is_down(client):
    """503, not 200 -- a readiness probe that cannot fail is decoration."""
    with mock.patch("redis.from_url", side_effect=OSError("connection refused")):
        response = client.get("/readyz")

    assert response.status_code == 503
    body = json.loads(response.content)
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "error"
    # The database is still fine and must be reported as such, so an operator
    # can tell which dependency to go and look at.
    assert body["checks"]["database"] == "ok"


@pytest.mark.django_db
def test_readyz_returns_503_when_the_database_is_down(client):
    with mock.patch("redis.from_url"), mock.patch(
        "django.db.connection.cursor", side_effect=OSError("server closed the connection")
    ):
        response = client.get("/readyz")

    assert response.status_code == 503
    body = json.loads(response.content)
    assert body["checks"]["database"] == "error"


@pytest.mark.django_db
def test_readyz_is_reachable_without_authentication(client):
    with mock.patch("redis.from_url"):
        response = client.get("/readyz")

    assert response.status_code == 200


@pytest.mark.django_db
def test_readyz_rejects_post(client):
    assert client.post("/readyz").status_code == 405


def test_settings_expose_the_version():
    """The views read settings.APP_VERSION; base.py must actually define it."""
    assert settings.APP_VERSION == __version__
