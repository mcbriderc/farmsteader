import pytest

from apps.consumables.models import ConsumableType, InventoryItem
from tests.factories import ConsumableTypeFactory, InventoryItemFactory


@pytest.mark.django_db
class TestInventoryEditViews:
    def test_edit_get(self, farm_client, farm):
        item = InventoryItemFactory(farm=farm)
        resp = farm_client.get(f"/consumables/{item.pk}/edit/")
        assert resp.status_code == 200

    def test_edit_post(self, farm_client, farm):
        item = InventoryItemFactory(farm=farm, name="Old Diesel")
        resp = farm_client.post(f"/consumables/{item.pk}/edit/", {
            "consumable_type": item.consumable_type.pk,
            "name": "New Diesel",
            "quantity": item.quantity,
            "unit": item.unit,
            "reorder_threshold": item.reorder_threshold,
        })
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.name == "New Diesel"

    def test_transaction_create(self, farm_client, farm):
        item = InventoryItemFactory(farm=farm, quantity=200)
        resp = farm_client.post(f"/consumables/{item.pk}/transaction/add/", {
            "transaction_type": "use",
            "quantity": "-50",
            "date": "2026-01-15 08:00:00",
        })
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.quantity == 150


@pytest.mark.django_db
class TestConsumableTypeViews:
    def test_list(self, farm_client):
        ConsumableTypeFactory()
        resp = farm_client.get("/consumables/types/")
        assert resp.status_code == 200

    def test_detail(self, farm_client, farm):
        ct = ConsumableTypeFactory()
        resp = farm_client.get(f"/consumables/types/{ct.pk}/")
        assert resp.status_code == 200

    def test_create_get(self, farm_client):
        resp = farm_client.get("/consumables/types/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client):
        resp = farm_client.post("/consumables/types/add/", {
            "name": "Biodiesel",
            "category": "Fuel",
            "default_unit": "gallons",
        })
        assert resp.status_code == 302
        assert ConsumableType.objects.filter(name="Biodiesel").exists()

    def test_edit(self, farm_client):
        ct = ConsumableTypeFactory(name="Old Type")
        resp = farm_client.post(f"/consumables/types/{ct.pk}/edit/", {
            "name": "New Type",
            "category": ct.category,
            "default_unit": ct.default_unit,
        })
        assert resp.status_code == 302
        ct.refresh_from_db()
        assert ct.name == "New Type"

    def test_delete(self, farm_client):
        ct = ConsumableTypeFactory()
        resp = farm_client.post(f"/consumables/types/{ct.pk}/delete/")
        assert resp.status_code == 302
        assert not ConsumableType.objects.filter(pk=ct.pk).exists()
