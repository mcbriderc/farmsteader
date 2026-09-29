from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos.error import GEOSException
from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget, Widget

from apps.buildings.models import Building, BuildingMaintenanceRecord
from apps.consumables.models import ConsumableType, InventoryItem, InventoryTransaction
from apps.crops.models import CropType, HarvestRecord, MarketPrice
from apps.employment.models import Employee, Task, TimeEntry
from apps.equipment.models import Equipment, MaintenanceRecord
from apps.produce.models import ProduceItem, ProduceTransaction
from apps.land.models import CropRecord, Field, SoilSample
from apps.livestock.models import Animal, FeedLog, FeedStock, FeedType, FieldMovement, VetRecord


# ---------------------------------------------------------------------------
# Shared base classes and widgets
# ---------------------------------------------------------------------------

class FarmScopedModelResource(resources.ModelResource):
    """Confines every lookup to one farm.

    Without this, django-import-export resolves ``import_id_fields`` against
    ``Model.objects.all()``. Since exports include ``id``, a file exported by one farm and
    imported by another would update the *original* rows and reassign them to the importing
    farm. The farm is passed in by the view; ``none()`` is the safe default so a resource
    constructed without one can never reach across farms.
    """

    def __init__(self, farm=None, **kwargs):
        super().__init__(**kwargs)
        self.farm = farm

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(farm=self.farm) if self.farm is not None else qs.none()

    def before_save_instance(self, instance, row, **kwargs):
        """Stamp the importing farm on, and discard any primary key from another farm.

        ``farm`` is deliberately absent from every ``Meta.fields`` so it cannot be set from the
        uploaded file — which also means it has to be set here, or the insert trips the NOT NULL
        constraint.

        ``id`` *is* exported, so a file from another farm carries that farm's primary keys.
        ``get_queryset()`` already stops those rows being updated; clearing the pk turns them
        into clean new rows for this farm instead of an insert that collides with someone
        else's id.
        """
        super().before_save_instance(instance, row, **kwargs)
        if self.farm is not None:
            instance.farm = self.farm
        if instance.pk and not self.get_queryset().filter(pk=instance.pk).exists():
            instance.pk = None


class FarmScopedForeignKeyWidget(ForeignKeyWidget):
    """Resolves a related object by name *within the importing farm*.

    A plain ForeignKeyWidget searches every farm, so importing a row that names a field
    "North Pasture" could link it to another farm's field of the same name. The view injects a
    ``farm`` column into every farm-scoped row (see ``_inject_farm_column``), which is what
    scopes the lookup here.
    """

    def get_queryset(self, value, row, *args, **kwargs):
        qs = super().get_queryset(value, row, *args, **kwargs)
        farm_id = (row or {}).get("farm")
        return qs.filter(farm_id=farm_id) if farm_id else qs.none()


class EmployeeNameWidget(FarmScopedForeignKeyWidget):
    """Matches an employee by "First Last" — last name alone is not unique."""

    def __init__(self, **kwargs):
        super().__init__(Employee, field="last_name", **kwargs)

    def render(self, value, obj=None, **kwargs):
        return f"{value.first_name} {value.last_name}".strip() if value else ""

    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        first, _, last = str(value).strip().rpartition(" ")
        qs = self.get_queryset(value, row, **kwargs).filter(last_name=last)
        if first:
            qs = qs.filter(first_name=first)
        return qs.first()


class GeometryWidget(Widget):
    """Carries PostGIS geometry through CSV/XLSX as WKT, accepting WKT or GeoJSON on import."""

    def __init__(self, srid=4326):
        self.srid = srid

    def render(self, value, obj=None, **kwargs):
        return value.wkt if value else ""

    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        try:
            return GEOSGeometry(str(value).strip(), srid=self.srid)
        except (GEOSException, ValueError, TypeError) as exc:
            raise ValueError(f"Could not read geometry {value!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Land
# ---------------------------------------------------------------------------

class FieldResource(FarmScopedModelResource):
    boundary = fields.Field(
        column_name="boundary", attribute="boundary", widget=GeometryWidget(),
    )

    class Meta:
        model = Field
        # acreage/centroid are editable=False, so import-export skips them; Field.save()
        # recomputes them from the boundary above.
        fields = (
            "id", "name", "boundary", "acreage", "centroid_lat", "centroid_lon",
            "soil_type", "color", "timezone", "notes",
        )
        export_order = fields


class SoilSampleResource(FarmScopedModelResource):
    field_name = fields.Field(
        column_name="field_name",
        attribute="field",
        widget=FarmScopedForeignKeyWidget(Field, field="name"),
    )

    class Meta:
        model = SoilSample
        fields = (
            "id", "field_name", "source", "sample_date", "depth_cm",
            "ph", "organic_carbon_pct", "nitrogen_ppm",
            "sand_pct", "silt_pct", "clay_pct", "texture_class", "cec", "notes",
        )
        export_order = fields


class CropRecordResource(FarmScopedModelResource):
    field_name = fields.Field(
        column_name="field_name",
        attribute="field",
        widget=FarmScopedForeignKeyWidget(Field, field="name"),
    )

    class Meta:
        model = CropRecord
        fields = (
            "id", "field_name", "crop_name", "variety", "season", "status",
            "planted_date", "harvest_date", "yield_amount", "yield_unit",
            "cost", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Livestock
# ---------------------------------------------------------------------------

class AnimalResource(FarmScopedModelResource):
    current_field_name = fields.Field(
        column_name="current_field",
        attribute="current_field",
        widget=FarmScopedForeignKeyWidget(Field, field="name"),
    )
    sire_tag = fields.Field(
        column_name="sire_ear_tag",
        attribute="sire",
        widget=FarmScopedForeignKeyWidget(Animal, field="ear_tag"),
    )
    dam_tag = fields.Field(
        column_name="dam_ear_tag",
        attribute="dam",
        widget=FarmScopedForeignKeyWidget(Animal, field="ear_tag"),
    )

    class Meta:
        model = Animal
        fields = (
            "id", "ear_tag", "name", "species", "breed", "gender",
            "repro_status", "status", "date_of_birth", "date_acquired",
            "purchase_price", "weight_kg", "current_field_name",
            "sire_tag", "dam_tag", "notes",
        )
        export_order = fields
        import_id_fields = ["ear_tag"]


class VetRecordResource(FarmScopedModelResource):
    animal_ear_tag = fields.Field(
        column_name="animal_ear_tag",
        attribute="animal",
        widget=FarmScopedForeignKeyWidget(Animal, field="ear_tag"),
    )

    class Meta:
        model = VetRecord
        fields = (
            "id", "animal_ear_tag", "record_type", "date", "description",
            "veterinarian", "cost", "next_due_date", "notes",
        )
        export_order = fields


class FieldMovementResource(FarmScopedModelResource):
    animal_ear_tag = fields.Field(
        column_name="animal_ear_tag",
        attribute="animal",
        widget=FarmScopedForeignKeyWidget(Animal, field="ear_tag"),
    )
    from_field_name = fields.Field(
        column_name="from_field",
        attribute="from_field",
        widget=FarmScopedForeignKeyWidget(Field, field="name"),
    )
    to_field_name = fields.Field(
        column_name="to_field",
        attribute="to_field",
        widget=FarmScopedForeignKeyWidget(Field, field="name"),
    )

    class Meta:
        model = FieldMovement
        fields = (
            "id", "animal_ear_tag", "from_field_name", "to_field_name",
            "date", "reason", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------


class FeedTypeResource(resources.ModelResource):
    class Meta:
        model = FeedType
        fields = ("id", "name", "category", "default_unit")
        export_order = fields


class FeedStockResource(FarmScopedModelResource):
    feed_type_name = fields.Field(
        column_name="feed_type",
        attribute="feed_type",
        widget=ForeignKeyWidget(FeedType, field="name"),
    )

    class Meta:
        model = FeedStock
        fields = (
            "id", "feed_type_name", "name", "quantity", "unit",
            "restock_source", "reorder_threshold", "unit_cost",
            "storage_location", "notes",
        )
        export_order = fields


class FeedLogResource(FarmScopedModelResource):
    animal_ear_tag = fields.Field(
        column_name="animal_ear_tag",
        attribute="animal",
        widget=FarmScopedForeignKeyWidget(Animal, field="ear_tag"),
    )
    feed_stock_name = fields.Field(
        column_name="feed_stock",
        attribute="feed_stock",
        widget=FarmScopedForeignKeyWidget(FeedStock, field="name"),
    )

    class Meta:
        model = FeedLog
        fields = (
            "id", "animal_ear_tag", "feed_stock_name", "quantity",
            "unit", "date", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Crops
# ---------------------------------------------------------------------------

class CropTypeResource(resources.ModelResource):
    class Meta:
        model = CropType
        fields = ("id", "name", "usda_code", "category", "default_unit")
        export_order = fields
        import_id_fields = ["name"]


class MarketPriceResource(resources.ModelResource):
    crop_type_name = fields.Field(
        column_name="crop_type",
        attribute="crop_type",
        widget=ForeignKeyWidget(CropType, field="name"),
    )

    class Meta:
        model = MarketPrice
        fields = (
            "id", "crop_type_name", "year", "state",
            "price_per_unit", "unit", "source",
        )
        export_order = fields


class HarvestRecordResource(FarmScopedModelResource):
    field_name = fields.Field(
        column_name="field_name",
        attribute="field",
        widget=FarmScopedForeignKeyWidget(Field, field="name"),
    )
    crop_type_name = fields.Field(
        column_name="crop_type",
        attribute="crop_type",
        widget=ForeignKeyWidget(CropType, field="name"),
    )

    class Meta:
        model = HarvestRecord
        fields = (
            "id", "field_name", "crop_type_name", "harvest_date",
            "yield_amount", "yield_unit", "moisture_pct", "quality_grade",
            "cost", "revenue", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------

class EquipmentResource(FarmScopedModelResource):
    class Meta:
        model = Equipment
        fields = (
            "id", "name", "brand", "model_name", "year", "serial_number",
            "status", "hours", "purchase_price", "purchase_date", "notes",
        )
        export_order = fields


class MaintenanceRecordResource(FarmScopedModelResource):
    equipment_name = fields.Field(
        column_name="equipment",
        attribute="equipment",
        widget=FarmScopedForeignKeyWidget(Equipment, field="name"),
    )

    class Meta:
        model = MaintenanceRecord
        fields = (
            "id", "equipment_name", "maintenance_type", "date", "description",
            "performed_by", "hours_at_service", "cost",
            "next_service_date", "next_service_hours", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

class BuildingResource(FarmScopedModelResource):
    location = fields.Field(
        column_name="location", attribute="location", widget=GeometryWidget(),
    )

    class Meta:
        model = Building
        fields = (
            "id", "name", "building_type", "location", "year_built", "square_feet",
            "assessed_value", "insurance_policy", "insurance_annual",
            "tax_annual", "notes",
        )
        export_order = fields


class BuildingMaintenanceRecordResource(FarmScopedModelResource):
    building_name = fields.Field(
        column_name="building",
        attribute="building",
        widget=FarmScopedForeignKeyWidget(Building, field="name"),
    )

    class Meta:
        model = BuildingMaintenanceRecord
        fields = (
            "id", "building_name", "maintenance_type", "date", "description",
            "contractor", "cost", "next_due_date", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Consumables
# ---------------------------------------------------------------------------

class ConsumableTypeResource(resources.ModelResource):
    class Meta:
        model = ConsumableType
        fields = ("id", "name", "category", "default_unit")
        export_order = fields
        import_id_fields = ["name"]


class InventoryItemResource(FarmScopedModelResource):
    consumable_type_name = fields.Field(
        column_name="consumable_type",
        attribute="consumable_type",
        widget=ForeignKeyWidget(ConsumableType, field="name"),
    )

    class Meta:
        model = InventoryItem
        fields = (
            "id", "consumable_type_name", "name", "quantity", "unit",
            "reorder_threshold", "unit_cost", "storage_location", "notes",
        )
        export_order = fields


class InventoryTransactionResource(FarmScopedModelResource):
    item_name = fields.Field(
        column_name="item",
        attribute="item",
        widget=FarmScopedForeignKeyWidget(InventoryItem, field="name"),
    )

    class Meta:
        model = InventoryTransaction
        fields = (
            "id", "item_name", "transaction_type", "quantity", "date",
            "unit_cost", "reference", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Employment
# ---------------------------------------------------------------------------

class EmployeeResource(FarmScopedModelResource):
    class Meta:
        model = Employee
        fields = (
            "id", "first_name", "last_name", "email", "phone",
            "role", "status", "hire_date", "hourly_rate", "notes",
        )
        export_order = fields


class TaskResource(FarmScopedModelResource):
    assigned_to_name = fields.Field(
        column_name="assigned_to",
        attribute="assigned_to",
        widget=EmployeeNameWidget(),
    )

    class Meta:
        model = Task
        fields = (
            "id", "title", "description", "assigned_to_name",
            "priority", "status", "due_date", "completed_at", "notes",
        )
        export_order = fields


class TimeEntryResource(FarmScopedModelResource):
    employee_name = fields.Field(
        column_name="employee",
        attribute="employee",
        widget=EmployeeNameWidget(),
    )
    task_title = fields.Field(
        column_name="task",
        attribute="task",
        widget=FarmScopedForeignKeyWidget(Task, field="title"),
    )

    class Meta:
        model = TimeEntry
        fields = (
            "id", "employee_name", "task_title", "date", "hours", "description", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Produce
# ---------------------------------------------------------------------------

class ProduceItemResource(FarmScopedModelResource):
    class Meta:
        model = ProduceItem
        fields = (
            "id", "name", "source", "storage_type", "quantity", "unit",
            "expiry_date", "storage_location", "notes",
        )
        export_order = fields


class ProduceTransactionResource(FarmScopedModelResource):
    item_name = fields.Field(
        column_name="item",
        attribute="item",
        widget=FarmScopedForeignKeyWidget(ProduceItem, field="name"),
    )

    class Meta:
        model = ProduceTransaction
        fields = (
            "id", "item_name", "transaction_type", "quantity", "date",
            "cost", "notes",
        )
        export_order = fields


# ---------------------------------------------------------------------------
# Registry — used by views to look up resources by key
# ---------------------------------------------------------------------------

RESOURCE_REGISTRY = {
    # Land
    "fields": ("Fields", FieldResource, Field),
    "soil_samples": ("Soil Samples", SoilSampleResource, SoilSample),
    "crop_records": ("Crop Records", CropRecordResource, CropRecord),
    # Livestock
    "animals": ("Animals", AnimalResource, Animal),
    "vet_records": ("Vet Records", VetRecordResource, VetRecord),
    "field_movements": ("Field Movements", FieldMovementResource, FieldMovement),
    # Feed
    "feed_types": ("Feed Types", FeedTypeResource, FeedType),
    "feed_stocks": ("Feed Stocks", FeedStockResource, FeedStock),
    "feed_logs": ("Feed Logs", FeedLogResource, FeedLog),
    # Crops
    "crop_types": ("Crop Types", CropTypeResource, CropType),
    "market_prices": ("Market Prices", MarketPriceResource, MarketPrice),
    "harvest_records": ("Harvest Records", HarvestRecordResource, HarvestRecord),
    # Equipment
    "equipment": ("Equipment", EquipmentResource, Equipment),
    "maintenance_records": ("Maintenance Records", MaintenanceRecordResource, MaintenanceRecord),
    # Buildings
    "buildings": ("Buildings", BuildingResource, Building),
    "building_maintenance": ("Building Maintenance", BuildingMaintenanceRecordResource, BuildingMaintenanceRecord),
    # Consumables
    "consumable_types": ("Consumable Types", ConsumableTypeResource, ConsumableType),
    "inventory_items": ("Inventory Items", InventoryItemResource, InventoryItem),
    "inventory_transactions": ("Inventory Transactions", InventoryTransactionResource, InventoryTransaction),
    # Employment
    "employees": ("Employees", EmployeeResource, Employee),
    "tasks": ("Tasks", TaskResource, Task),
    "time_entries": ("Time Entries", TimeEntryResource, TimeEntry),
    # Produce
    "produce_items": ("Produce Items", ProduceItemResource, ProduceItem),
    "produce_transactions": ("Produce Transactions", ProduceTransactionResource, ProduceTransaction),
}

# Models that are farm-scoped (need queryset filtering)
FARM_SCOPED_KEYS = {
    k for k, (_, _, model) in RESOURCE_REGISTRY.items()
    if hasattr(model, "farm_id")
}
