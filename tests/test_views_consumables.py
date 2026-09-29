import pytest

from apps.consumables.models import InventoryItem
from tests.factories import ConsumableTypeFactory, InventoryItemFactory


@pytest.mark.django_db
class TestInventoryViews:
    def test_list_requires_login(self, client):
        resp = client.get("/consumables/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        InventoryItemFactory(farm=farm)
        resp = farm_client.get("/consumables/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        other_item = InventoryItemFactory()
        resp = farm_client.get("/consumables/")
        assert other_item not in resp.context["items"]

    def test_create_post(self, farm_client, farm):
        ct = ConsumableTypeFactory()
        resp = farm_client.post("/consumables/add/", {
            "consumable_type": ct.pk,
            "name": "Premium Diesel",
            "quantity": "500",
            "unit": "gallons",
            "reorder_threshold": "100",
        })
        assert resp.status_code == 302
        assert InventoryItem.objects.filter(farm=farm, name="Premium Diesel").exists()

    def test_detail(self, farm_client, farm):
        item = InventoryItemFactory(farm=farm)
        resp = farm_client.get(f"/consumables/{item.pk}/")
        assert resp.status_code == 200

    def test_detail_other_farm_returns_404(self, farm_client):
        other_item = InventoryItemFactory()
        resp = farm_client.get(f"/consumables/{other_item.pk}/")
        assert resp.status_code == 404

    def test_delete(self, farm_client, farm):
        item = InventoryItemFactory(farm=farm)
        resp = farm_client.post(f"/consumables/{item.pk}/delete/")
        assert resp.status_code == 302
        assert not InventoryItem.objects.filter(pk=item.pk).exists()
