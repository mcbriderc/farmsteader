import pytest

from apps.equipment.models import MaintenanceRecord
from tests.factories import EquipmentFactory, MaintenanceRecordFactory


@pytest.mark.django_db
class TestMaintenanceRecordViews:
    def test_create_get(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm)
        resp = farm_client.get(f"/equipment/{eq.pk}/maintenance/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm)
        resp = farm_client.post(f"/equipment/{eq.pk}/maintenance/add/", {
            "maintenance_type": "oil_change",
            "date": "2026-01-15",
            "description": "Regular oil change",
            "cost": "45.00",
        })
        assert resp.status_code == 302
        assert MaintenanceRecord.objects.filter(farm=farm, equipment=eq).exists()

    def test_edit_get(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm)
        record = MaintenanceRecordFactory(farm=farm, equipment=eq, date="2026-01-01")
        resp = farm_client.get(f"/equipment/{eq.pk}/maintenance/{record.pk}/edit/")
        assert resp.status_code == 200

    def test_edit_post(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm)
        record = MaintenanceRecordFactory(
            farm=farm, equipment=eq, date="2026-01-01",
            maintenance_type=MaintenanceRecord.MaintenanceType.OIL_CHANGE,
        )
        resp = farm_client.post(f"/equipment/{eq.pk}/maintenance/{record.pk}/edit/", {
            "maintenance_type": "tires",
            "date": "2026-02-01",
            "description": "Tire rotation",
            "cost": "0.00",
        })
        assert resp.status_code == 302
        record.refresh_from_db()
        assert record.maintenance_type == "tires"

    def test_other_farm_returns_404(self, farm_client):
        other_eq = EquipmentFactory()
        resp = farm_client.get(f"/equipment/{other_eq.pk}/maintenance/add/")
        assert resp.status_code == 404
