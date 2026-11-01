"""The container image and its compose file.

These pin what the image build cannot check for itself. The image is exercised
for real by scripts/build-image.sh plus `compose up`, see "Container" in DOCS.md.
"""

import importlib
import pathlib
import re
import subprocess

import pytest
import yaml
from django.test import override_settings
from django.urls import clear_url_caches

CONTAINER = pathlib.Path("deploy/container")
CONTAINERFILE = (CONTAINER / "Containerfile").read_text()
ENTRYPOINT = (CONTAINER / "entrypoint.sh").read_text()
COMPOSE = yaml.safe_load((CONTAINER / "compose.yaml").read_text())
SERVICES = COMPOSE["services"]
APP_SERVICES = ("migrate", "web", "worker", "beat")


class TestImage:
    def test_only_a_release_tarball_can_be_the_build_context(self):
        """VERSION exists only in a tarball, so a checkout (with its personal
        files) fails to build rather than ending up in a public image.
        """
        assert "COPY VERSION /app/VERSION" in CONTAINERFILE
        assert subprocess.run(["git", "ls-files", "--error-unmatch", "VERSION"], capture_output=True).returncode != 0
        assert "scripts/build-tarball.sh" in pathlib.Path("scripts/build-image.sh").read_text()

    def test_the_container_files_ship_in_the_tarball(self):
        attributes = pathlib.Path(".gitattributes").read_text()
        assert not re.search(r"^/deploy\S*\s+export-ignore", attributes, re.M)

    def test_runs_as_an_unprivileged_user(self):
        assert CONTAINERFILE.rstrip().splitlines().count("USER 10001") == 1

    def test_uses_fully_qualified_base_images(self):
        """Podman has no default registry."""
        for image in re.findall(r"^FROM (\S+)", CONTAINERFILE, re.M):
            assert image.startswith("docker.io/")

    def test_serves_its_own_uploads_and_trusts_no_proxy_by_default(self):
        assert "FARMSTEADER_SERVE_MEDIA=1" in CONTAINERFILE
        assert "USE_PROXY_SSL_HEADER=0" in CONTAINERFILE

    def test_entry_point_has_every_role(self):
        for role in ("web", "worker", "beat", "migrate", "manage", "shell"):
            assert re.search(rf"^    {role}\)$", ENTRYPOINT, re.M)

    def test_only_the_migrate_role_applies_migrations(self):
        assert len(re.findall(r"manage\.py migrate --noinput", ENTRYPOINT)) == 1
        assert ENTRYPOINT.count("        wait_for_migrations\n") == 3


class TestCompose:
    def test_every_image_is_fully_qualified(self):
        for name, service in SERVICES.items():
            assert re.match(r"(docker\.io|\$\{FARMSTEADER_IMAGE:-ghcr\.io)/", service["image"]), name

    def test_migrations_run_once_before_the_app_starts(self):
        assert SERVICES["migrate"]["restart"] == "no"
        for name in ("web", "worker", "beat"):
            assert SERVICES[name]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"

    def test_secrets_have_no_default(self):
        """A compose file with a default password runs with that password forever."""
        env = SERVICES["web"]["environment"]
        assert "${SECRET_KEY:?" in env["SECRET_KEY"]
        assert "${DB_PASSWORD:?" in env["DATABASE_URL"]
        assert "${DB_PASSWORD:?" in SERVICES["db"]["environment"]["POSTGRES_PASSWORD"]

    def test_app_services_share_one_environment(self):
        for name in APP_SERVICES:
            assert SERVICES[name]["environment"]["DATABASE_URL"] == SERVICES["web"]["environment"]["DATABASE_URL"]

    def test_health_check_host_is_always_allowed(self):
        """Without it, the probe gets a 400 and the service never reports healthy."""
        assert SERVICES["web"]["environment"]["ALLOWED_HOSTS"].startswith("localhost,")
        assert "localhost:8000/readyz" in " ".join(SERVICES["web"]["healthcheck"]["test"])

    def test_source_link_is_set_for_the_published_image(self):
        """AGPL section 13: settings default it to empty, so the deployer must set it."""
        assert "github.com/mcbriderc/farmsteader" in SERVICES["web"]["environment"]["FARMSTEADER_SOURCE_URL"]

    def test_uploads_reach_every_service_that_handles_them(self):
        for name in ("web", "worker"):
            assert "media:/data/media" in SERVICES[name]["volumes"]

    def test_beat_keeps_its_schedule_on_a_volume(self):
        assert "beat:/data/beat" in SERVICES["beat"]["volumes"]
        assert "--schedule=/data/beat/" in ENTRYPOINT


class TestReleaseJob:
    def test_a_failed_image_cannot_hold_up_the_release(self):
        workflow = yaml.safe_load(pathlib.Path(".forgejo/workflows/release.yml").read_text())
        assert workflow["jobs"]["image"]["needs"] == "release"
        assert workflow["jobs"]["release"]["needs"] == "test"


@pytest.fixture
def reload_urls():
    """config.urls decides at import whether to add the media route."""
    import config.urls

    def reload():
        clear_url_caches()
        importlib.reload(config.urls)

    yield reload
    reload()


@pytest.fixture
def uploaded_file(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "photo.txt").write_text("a photo")
    return "/media/photo.txt"


@pytest.mark.django_db
class TestMediaServing:
    def _enabled(self, reload_urls):
        with override_settings(FARMSTEADER_SERVE_MEDIA=True):
            reload_urls()

    def test_served_when_switched_on(self, farm_client, uploaded_file, reload_urls):
        self._enabled(reload_urls)
        response = farm_client.get(uploaded_file)
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"a photo"

    def test_requires_a_login(self, client, uploaded_file, reload_urls):
        self._enabled(reload_urls)
        response = client.get(uploaded_file)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_cannot_escape_the_media_directory(self, farm_client, uploaded_file, reload_urls):
        self._enabled(reload_urls)
        assert farm_client.get("/media/../../etc/passwd").status_code in (400, 404)

    def test_off_by_default(self, farm_client, uploaded_file, reload_urls):
        reload_urls()
        assert farm_client.get(uploaded_file).status_code == 404
