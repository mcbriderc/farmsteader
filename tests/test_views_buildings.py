import pytest

from apps.buildings.models import Building
from tests.factories import BuildingFactory


@pytest.mark.django_db
class TestBuildingViews:
    def test_list_requires_login(self, client):
        resp = client.get("/buildings/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        BuildingFactory(farm=farm)
        resp = farm_client.get("/buildings/")
        assert resp.status_code == 200

    def test_create_get(self, farm_client):
        resp = farm_client.get("/buildings/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        resp = farm_client.post("/buildings/add/", {
            "name": "Main Barn",
            "building_type": "barn",
        })
        assert resp.status_code == 302
        assert Building.objects.filter(farm=farm, name="Main Barn").exists()

    def test_detail(self, farm_client, farm):
        building = BuildingFactory(farm=farm)
        resp = farm_client.get(f"/buildings/{building.pk}/")
        assert resp.status_code == 200

    def test_detail_other_farm_returns_404(self, farm_client):
        other_building = BuildingFactory()
        resp = farm_client.get(f"/buildings/{other_building.pk}/")
        assert resp.status_code == 404

    def test_edit(self, farm_client, farm):
        building = BuildingFactory(farm=farm, name="Old Barn")
        resp = farm_client.post(f"/buildings/{building.pk}/edit/", {
            "name": "New Barn",
            "building_type": "barn",
        })
        assert resp.status_code == 302
        building.refresh_from_db()
        assert building.name == "New Barn"

    def test_delete(self, farm_client, farm):
        building = BuildingFactory(farm=farm)
        resp = farm_client.post(f"/buildings/{building.pk}/delete/")
        assert resp.status_code == 302
        assert not Building.objects.filter(pk=building.pk).exists()
