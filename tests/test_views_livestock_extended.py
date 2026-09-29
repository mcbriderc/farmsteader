import pytest

from apps.livestock.models import FeedStock, FeedType, VetRecord
from tests.factories import (
    AnimalFactory,
    FeedLogFactory,
    FeedStockFactory,
    FeedTypeFactory,
    FieldFactory,
    VetRecordFactory,
)


@pytest.mark.django_db
class TestVetRecordViews:
    def test_create_get(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        resp = farm_client.get(f"/livestock/{animal.pk}/vet/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        resp = farm_client.post(f"/livestock/{animal.pk}/vet/add/", {
            "record_type": "exam",
            "date": "2026-01-15",
            "description": "Annual checkup",
            "cost": "75.00",
        })
        assert resp.status_code == 302
        assert VetRecord.objects.filter(animal=animal).exists()

    def test_edit(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        record = VetRecordFactory(farm=farm, animal=animal, date="2026-01-01")
        resp = farm_client.post(f"/livestock/{animal.pk}/vet/{record.pk}/edit/", {
            "record_type": "immunization",
            "date": "2026-02-01",
            "description": "Annual vaccines",
            "cost": "50.00",
        })
        assert resp.status_code == 302
        record.refresh_from_db()
        assert record.record_type == "immunization"


@pytest.mark.django_db
class TestFeedTypeViews:
    def test_list(self, farm_client):
        FeedTypeFactory()
        resp = farm_client.get("/livestock/feed/types/")
        assert resp.status_code == 200

    def test_detail(self, farm_client, farm):
        ft = FeedTypeFactory()
        resp = farm_client.get(f"/livestock/feed/types/{ft.pk}/")
        assert resp.status_code == 200

    def test_create_get(self, farm_client):
        resp = farm_client.get("/livestock/feed/types/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client):
        resp = farm_client.post("/livestock/feed/types/add/", {
            "name": "Custom Hay Blend",
            "category": FeedType.Category.HAY,
            "default_unit": "bales",
        })
        assert resp.status_code == 302
        assert FeedType.objects.filter(name="Custom Hay Blend").exists()

    def test_edit(self, farm_client):
        ft = FeedTypeFactory(name="Old Hay")
        resp = farm_client.post(f"/livestock/feed/types/{ft.pk}/edit/", {
            "name": "New Hay",
            "category": FeedType.Category.HAY,
            "default_unit": "bales",
        })
        assert resp.status_code == 302
        ft.refresh_from_db()
        assert ft.name == "New Hay"

    def test_delete(self, farm_client):
        ft = FeedTypeFactory()
        resp = farm_client.post(f"/livestock/feed/types/{ft.pk}/delete/")
        assert resp.status_code == 302
        assert not FeedType.objects.filter(pk=ft.pk).exists()


@pytest.mark.django_db
class TestFeedStockViews:
    def test_list(self, farm_client, farm):
        FeedStockFactory(farm=farm)
        resp = farm_client.get("/livestock/feed/")
        assert resp.status_code == 200

    def test_list_filter_by_source(self, farm_client, farm):
        FeedStockFactory(farm=farm, restock_source=FeedStock.RestockSource.PURCHASED)
        FeedStockFactory(farm=farm, restock_source=FeedStock.RestockSource.FARM_HAY)
        resp = farm_client.get("/livestock/feed/?source=purchased")
        assert resp.status_code == 200
        stocks = list(resp.context["stocks"])
        for s in stocks:
            assert s.restock_source == "purchased"

    def test_create_get(self, farm_client):
        resp = farm_client.get("/livestock/feed/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        ft = FeedTypeFactory()
        resp = farm_client.post("/livestock/feed/add/", {
            "feed_type": ft.pk,
            "name": "Barn Hay",
            "quantity": "300",
            "unit": "lbs",
            "reorder_threshold": "50",
            "restock_source": FeedStock.RestockSource.FARM_HAY,
        })
        assert resp.status_code == 302
        assert FeedStock.objects.filter(farm=farm, name="Barn Hay").exists()

    def test_detail(self, farm_client, farm):
        stock = FeedStockFactory(farm=farm)
        resp = farm_client.get(f"/livestock/feed/{stock.pk}/")
        assert resp.status_code == 200

    def test_edit(self, farm_client, farm):
        stock = FeedStockFactory(farm=farm, name="Old Hay")
        resp = farm_client.post(f"/livestock/feed/{stock.pk}/edit/", {
            "feed_type": stock.feed_type.pk,
            "name": "New Hay",
            "quantity": stock.quantity,
            "unit": stock.unit,
            "reorder_threshold": stock.reorder_threshold,
            "restock_source": stock.restock_source,
        })
        assert resp.status_code == 302
        stock.refresh_from_db()
        assert stock.name == "New Hay"

    def test_feeding_log_create(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        stock = FeedStockFactory(farm=farm)
        resp = farm_client.post(f"/livestock/{animal.pk}/feed/add/", {
            "feed_stock": stock.pk,
            "quantity": "10",
            "unit": "lbs",
            "date": "2026-01-15 08:00:00",
        })
        assert resp.status_code == 302


@pytest.mark.django_db
class TestMovementViews:
    def test_movement_create_get(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        resp = farm_client.get(f"/livestock/{animal.pk}/move/")
        assert resp.status_code == 200

    def test_movement_create_post(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        to_field = FieldFactory(farm=farm)
        resp = farm_client.post(f"/livestock/{animal.pk}/move/", {
            "to_field": to_field.pk,
            "date": "2026-01-15",
        })
        assert resp.status_code == 302
        animal.refresh_from_db()
        assert animal.current_field == to_field
