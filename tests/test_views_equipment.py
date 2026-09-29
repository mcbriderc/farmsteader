import pytest

from apps.equipment.models import Equipment
from tests.factories import EquipmentFactory


@pytest.mark.django_db
class TestEquipmentViews:
    def test_list_requires_login(self, client):
        resp = client.get("/equipment/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        EquipmentFactory(farm=farm)
        resp = farm_client.get("/equipment/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        other_eq = EquipmentFactory()
        resp = farm_client.get("/equipment/")
        assert resp.status_code == 200
        assert other_eq not in resp.context["equipment"]

    def test_create_get(self, farm_client):
        resp = farm_client.get("/equipment/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        resp = farm_client.post("/equipment/add/", {
            "name": "Big Tractor",
            "status": "active",
        })
        assert resp.status_code == 302
        assert Equipment.objects.filter(farm=farm, name="Big Tractor").exists()

    def test_detail(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm)
        resp = farm_client.get(f"/equipment/{eq.pk}/")
        assert resp.status_code == 200

    def test_detail_other_farm_returns_404(self, farm_client):
        other_eq = EquipmentFactory()
        resp = farm_client.get(f"/equipment/{other_eq.pk}/")
        assert resp.status_code == 404

    def test_edit(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm, name="Old Name")
        resp = farm_client.post(f"/equipment/{eq.pk}/edit/", {
            "name": "New Name",
            "status": "active",
        })
        assert resp.status_code == 302
        eq.refresh_from_db()
        assert eq.name == "New Name"

    def test_delete(self, farm_client, farm):
        eq = EquipmentFactory(farm=farm)
        resp = farm_client.post(f"/equipment/{eq.pk}/delete/")
        assert resp.status_code == 302
        assert not Equipment.objects.filter(pk=eq.pk).exists()
