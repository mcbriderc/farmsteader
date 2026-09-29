import pytest

from apps.produce.models import ProduceItem
from tests.factories import ProduceItemFactory, ProduceTransactionFactory


@pytest.mark.django_db
class TestProduceViews:
    def test_list_requires_login(self, client):
        resp = client.get("/produce/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        ProduceItemFactory(farm=farm)
        resp = farm_client.get("/produce/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        own = ProduceItemFactory(farm=farm)
        other = ProduceItemFactory()
        resp = farm_client.get("/produce/")
        pks = [i.pk for i in resp.context["items"]]
        assert own.pk in pks
        assert other.pk not in pks

    def test_create_get(self, farm_client):
        resp = farm_client.get("/produce/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        resp = farm_client.post("/produce/add/", {
            "name": "Farm Eggs",
            "source": "farm_animal",
            "storage_type": "fresh",
            "quantity": "24",
            "unit": "dozen",
        })
        assert resp.status_code == 302
        assert ProduceItem.objects.filter(farm=farm, name="Farm Eggs").exists()

    def test_detail(self, farm_client, farm):
        item = ProduceItemFactory(farm=farm)
        resp = farm_client.get(f"/produce/{item.pk}/")
        assert resp.status_code == 200

    def test_detail_other_farm_returns_404(self, farm_client):
        other = ProduceItemFactory()
        resp = farm_client.get(f"/produce/{other.pk}/")
        assert resp.status_code == 404

    def test_edit(self, farm_client, farm):
        item = ProduceItemFactory(farm=farm, name="Old Name")
        resp = farm_client.post(f"/produce/{item.pk}/edit/", {
            "name": "New Name",
            "source": item.source,
            "storage_type": item.storage_type,
            "quantity": item.quantity,
            "unit": item.unit,
        })
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.name == "New Name"

    def test_delete(self, farm_client, farm):
        item = ProduceItemFactory(farm=farm)
        resp = farm_client.post(f"/produce/{item.pk}/delete/")
        assert resp.status_code == 302
        assert not ProduceItem.objects.filter(pk=item.pk).exists()

    def test_transaction_create(self, farm_client, farm):
        item = ProduceItemFactory(farm=farm, quantity=10)
        resp = farm_client.post(f"/produce/{item.pk}/transaction/add/", {
            "transaction_type": "consume",
            "quantity": "-5",
            "date": "2026-01-15 08:00:00",
        })
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.quantity == 5
