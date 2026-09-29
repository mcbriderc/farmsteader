import pytest

from apps.buildings.models import BuildingMaintenanceRecord
from tests.factories import BuildingFactory, BuildingMaintenanceRecordFactory


@pytest.mark.django_db
class TestBuildingMaintenanceViews:
    def test_create_get(self, farm_client, farm):
        building = BuildingFactory(farm=farm)
        resp = farm_client.get(f"/buildings/{building.pk}/maintenance/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        building = BuildingFactory(farm=farm)
        resp = farm_client.post(f"/buildings/{building.pk}/maintenance/add/", {
            "maintenance_type": "roof",
            "date": "2026-03-01",
            "description": "Roof patch",
            "cost": "250.00",
        })
        assert resp.status_code == 302
        assert BuildingMaintenanceRecord.objects.filter(farm=farm, building=building).exists()

    def test_edit_get(self, farm_client, farm):
        building = BuildingFactory(farm=farm)
        record = BuildingMaintenanceRecordFactory(
            farm=farm, building=building, date="2026-01-01",
        )
        resp = farm_client.get(f"/buildings/{building.pk}/maintenance/{record.pk}/edit/")
        assert resp.status_code == 200

    def test_edit_post(self, farm_client, farm):
        building = BuildingFactory(farm=farm)
        record = BuildingMaintenanceRecordFactory(
            farm=farm, building=building, date="2026-01-01",
        )
        resp = farm_client.post(f"/buildings/{building.pk}/maintenance/{record.pk}/edit/", {
            "maintenance_type": "electrical",
            "date": "2026-04-01",
            "description": "Panel upgrade",
            "cost": "800.00",
        })
        assert resp.status_code == 302
        record.refresh_from_db()
        assert record.maintenance_type == "electrical"

    def test_other_farm_building_returns_404(self, farm_client):
        other_building = BuildingFactory()
        resp = farm_client.get(f"/buildings/{other_building.pk}/maintenance/add/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestBuildingGeoJSONView:
    def test_geojson(self, farm_client, farm):
        BuildingFactory(farm=farm)
        resp = farm_client.get("/buildings/geojson/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
