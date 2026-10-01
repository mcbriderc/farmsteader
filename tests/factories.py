from datetime import timezone

import factory
from django.contrib.gis.geos import GEOSGeometry, Point

from apps.accounts.models import Farm, FarmMembership, FarmUser
from apps.buildings.models import Building, BuildingMaintenanceRecord
from apps.consumables.models import ConsumableType, InventoryItem, InventoryTransaction
from apps.crops.models import CropType, HarvestRecord
from apps.employment.models import Employee, Task, TimeEntry
from apps.equipment.models import Equipment, MaintenanceRecord
from apps.land.models import CropRecord, Field, Parcel, SoilSample
from apps.livestock.models import Animal, FeedLog, FeedStock, FeedType, VetRecord
from apps.produce.models import ProduceItem, ProduceTransaction

# A small polygon in central Iowa (valid SRID 4326)
_POLYGON = GEOSGeometry(
    '{"type":"Polygon","coordinates":[[[-93.6,41.6],[-93.61,41.6],[-93.61,41.61],[-93.6,41.61],[-93.6,41.6]]]}',
    srid=4326,
)
_POINT = Point(-93.6, 41.6, srid=4326)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FarmUser

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "password")


class FarmFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Farm

    name = factory.Sequence(lambda n: f"Test Farm {n}")


class FarmMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FarmMembership

    user = factory.SubFactory(UserFactory)
    farm = factory.SubFactory(FarmFactory)
    role = FarmMembership.Role.OWNER


class FieldFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Field

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Field {n}")
    boundary = _POLYGON
    color = "#22c55e"


class ParcelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parcel

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Parcel {n}")
    boundary = _POLYGON
    color = "#f59e0b"


class AnimalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Animal

    farm = factory.SubFactory(FarmFactory)
    ear_tag = factory.Sequence(lambda n: f"TAG{n:04d}")
    name = factory.Sequence(lambda n: f"Bessie {n}")
    species = Animal.Species.CATTLE
    gender = Animal.Gender.FEMALE
    status = Animal.Status.ACTIVE


class FeedTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeedType

    name = factory.Sequence(lambda n: f"Feed Type {n}")
    category = FeedType.Category.HAY
    default_unit = "lbs"


class FeedStockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeedStock

    farm = factory.SubFactory(FarmFactory)
    feed_type = factory.SubFactory(FeedTypeFactory)
    name = factory.Sequence(lambda n: f"Hay Bale {n}")
    quantity = 500
    unit = "lbs"
    reorder_threshold = 100


class VetRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VetRecord

    farm = factory.SubFactory(FarmFactory)
    animal = factory.SubFactory(AnimalFactory)
    record_type = VetRecord.RecordType.EXAM
    date = factory.Faker("date_this_year")
    description = "Routine checkup"


class EquipmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Equipment

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Tractor {n}")
    status = Equipment.Status.ACTIVE


class MaintenanceRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MaintenanceRecord

    farm = factory.SubFactory(FarmFactory)
    equipment = factory.SubFactory(EquipmentFactory)
    maintenance_type = MaintenanceRecord.MaintenanceType.OIL_CHANGE
    date = factory.Faker("date_this_year")
    description = "Regular oil change"


class BuildingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Building

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Barn {n}")
    building_type = Building.BuildingType.BARN
    location = _POINT


class BuildingMaintenanceRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BuildingMaintenanceRecord

    farm = factory.SubFactory(FarmFactory)
    building = factory.SubFactory(BuildingFactory)
    maintenance_type = BuildingMaintenanceRecord.MaintenanceType.ROOF
    date = factory.Faker("date_this_year")
    description = "Roof inspection"


class ConsumableTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ConsumableType

    name = factory.Sequence(lambda n: f"Consumable {n}")
    category = "Fuel"
    default_unit = "gallons"


class InventoryItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryItem

    farm = factory.SubFactory(FarmFactory)
    consumable_type = factory.SubFactory(ConsumableTypeFactory)
    name = factory.Sequence(lambda n: f"Diesel {n}")
    quantity = 200
    unit = "gallons"
    reorder_threshold = 50


class EmployeeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Employee

    farm = factory.SubFactory(FarmFactory)
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    status = Employee.Status.ACTIVE


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task

    farm = factory.SubFactory(FarmFactory)
    title = factory.Sequence(lambda n: f"Task {n}")
    status = Task.Status.TODO
    priority = Task.Priority.MEDIUM


class CropTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CropType

    name = factory.Sequence(lambda n: f"Crop {n}")
    default_unit = "bushels"


class HarvestRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HarvestRecord

    farm = factory.SubFactory(FarmFactory)
    field = factory.SubFactory(FieldFactory)
    crop_type = factory.SubFactory(CropTypeFactory)
    harvest_date = factory.Faker("date_this_year")
    yield_amount = 250
    yield_unit = "bushels"


class CropRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CropRecord

    farm = factory.SubFactory(FarmFactory)
    field = factory.SubFactory(FieldFactory)
    crop_type = factory.SubFactory(CropTypeFactory)
    season = "2026-Spring"
    status = CropRecord.Status.PLANNED


class SoilSampleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SoilSample

    farm = factory.SubFactory(FarmFactory)
    field = factory.SubFactory(FieldFactory)
    source = SoilSample.Source.MANUAL
    depth_cm = 30


class FeedLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeedLog

    farm = factory.SubFactory(FarmFactory)
    animal = factory.SubFactory(AnimalFactory)
    feed_stock = factory.SubFactory(FeedStockFactory)
    quantity = 10
    date = factory.Faker("date_time_this_year", tzinfo=timezone.utc)


class InventoryTransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryTransaction

    farm = factory.SubFactory(FarmFactory)
    item = factory.SubFactory(InventoryItemFactory)
    transaction_type = InventoryTransaction.TransactionType.PURCHASE
    quantity = 50
    date = factory.Faker("date_time_this_year", tzinfo=timezone.utc)


class ProduceItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProduceItem

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Eggs {n}")
    source = ProduceItem.Source.FARM_ANIMAL
    storage_type = ProduceItem.StorageType.FRESH
    quantity = 24
    unit = "dozen"


class ProduceTransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProduceTransaction

    farm = factory.SubFactory(FarmFactory)
    item = factory.SubFactory(ProduceItemFactory)
    transaction_type = ProduceTransaction.TransactionType.HARVEST
    quantity = 12
    date = factory.Faker("date_time_this_year", tzinfo=timezone.utc)


class TimeEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TimeEntry

    farm = factory.SubFactory(FarmFactory)
    employee = factory.SubFactory(EmployeeFactory)
    date = factory.Faker("date_this_year")
    hours = 8
