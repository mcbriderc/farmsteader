import pytest
from django.urls import reverse

from tests.factories import AnimalFactory, EquipmentFactory, FieldFactory, TaskFactory


@pytest.mark.django_db
class TestDashboard:
    def test_requires_login(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp["Location"]

    def test_dashboard_renders(self, farm_client):
        resp = farm_client.get("/")
        assert resp.status_code == 200

    def test_dashboard_shows_counts(self, farm_client, farm):
        FieldFactory(farm=farm)
        FieldFactory(farm=farm)
        AnimalFactory(farm=farm)
        resp = farm_client.get("/")
        assert resp.status_code == 200
        assert resp.context["field_count"] == 2
        assert resp.context["animal_count"] == 1

    def test_dashboard_counts_exclude_other_farms(self, farm_client, farm, other_farm):
        FieldFactory(farm=farm)
        FieldFactory(farm=other_farm)  # should not be counted
        resp = farm_client.get("/")
        assert resp.context["field_count"] == 1

    def test_action_items_in_context(self, farm_client):
        resp = farm_client.get("/")
        assert "action_items" in resp.context


@pytest.mark.django_db
class TestSourceLink:
    """AGPL section 13's "Source" link in the sidebar footer.

    Rendered only when FARMSTEADER_SOURCE_URL is set. An operator running a
    modified copy must point it at their own fork -- so the default is empty
    rather than upstream, and an unconfigured install advertises no URL.
    """

    def test_absent_when_unset(self, farm_client, settings):
        settings.FARMSTEADER_SOURCE_URL = ""
        html = farm_client.get(reverse("core:dashboard")).content.decode()
        assert ">Source</a>" not in html

    def test_rendered_when_set(self, farm_client, settings):
        settings.FARMSTEADER_SOURCE_URL = "https://example.com/my-fork"
        html = farm_client.get(reverse("core:dashboard")).content.decode()
        assert 'href="https://example.com/my-fork"' in html
        assert ">Source</a>" in html

    def test_version_always_shown(self, farm_client, settings):
        settings.FARMSTEADER_SOURCE_URL = ""
        html = farm_client.get(reverse("core:dashboard")).content.decode()
        assert f"v{settings.APP_VERSION}" in html
