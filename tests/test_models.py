import pytest
from django.utils import timezone

from tests.factories import (
    AnimalFactory,
    EquipmentFactory,
    FarmFactory,
    FieldFactory,
    FeedStockFactory,
    InventoryItemFactory,
    MaintenanceRecordFactory,
)


@pytest.mark.django_db
class TestInventoryItemModel:
    def test_is_low_stock_true_when_below_threshold(self):
        item = InventoryItemFactory(quantity=10, reorder_threshold=50)
        assert item.is_low_stock is True

    def test_is_low_stock_true_at_threshold(self):
        item = InventoryItemFactory(quantity=50, reorder_threshold=50)
        assert item.is_low_stock is True

    def test_is_low_stock_false_when_above_threshold(self):
        item = InventoryItemFactory(quantity=100, reorder_threshold=50)
        assert item.is_low_stock is False

    def test_is_low_stock_false_when_threshold_is_zero(self):
        item = InventoryItemFactory(quantity=0, reorder_threshold=0)
        assert item.is_low_stock is False


@pytest.mark.django_db
class TestFeedStockModel:
    def test_is_low_stock_when_below_threshold(self):
        stock = FeedStockFactory(quantity=10, reorder_threshold=100)
        assert stock.is_low_stock is True

    def test_not_low_stock_when_above_threshold(self):
        stock = FeedStockFactory(quantity=500, reorder_threshold=100)
        assert stock.is_low_stock is False


@pytest.mark.django_db
class TestFieldModel:
    def test_acreage_calculated_on_save(self):
        field = FieldFactory()
        assert field.acreage > 0

    def test_centroid_calculated_on_save(self):
        field = FieldFactory()
        assert field.centroid_lat != 0
        assert field.centroid_lon != 0

    def test_str(self):
        field = FieldFactory(name="North Pasture")
        assert "North Pasture" in str(field)


@pytest.mark.django_db
class TestAnimalModel:
    def test_days_in_current_field_none_when_no_field(self):
        animal = AnimalFactory(current_field=None)
        assert animal.days_in_current_field is None

    def test_str_uses_name_when_present(self):
        animal = AnimalFactory(name="Bessie", species="cattle")
        assert "Bessie" in str(animal)

    def test_str_uses_ear_tag_when_no_name(self):
        animal = AnimalFactory(name="", ear_tag="T001", species="cattle")
        assert "T001" in str(animal)


@pytest.mark.django_db
class TestEquipmentModel:
    def test_next_service_none_when_no_records(self):
        eq = EquipmentFactory()
        assert eq.next_service is None

    def test_next_service_returns_earliest_record(self, db):
        from datetime import date, timedelta
        eq = EquipmentFactory()
        farm = eq.farm
        soon = date.today() + timedelta(days=7)
        later = date.today() + timedelta(days=30)
        MaintenanceRecordFactory(farm=farm, equipment=eq, next_service_date=later)
        near = MaintenanceRecordFactory(farm=farm, equipment=eq, next_service_date=soon)
        assert eq.next_service.pk == near.pk

    def test_str_includes_name(self):
        eq = EquipmentFactory(name="John Deere 5075E")
        assert "John Deere 5075E" in str(eq)
