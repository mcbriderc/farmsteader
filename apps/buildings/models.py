from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin


class Building(FarmOwnedModel, NotesMixin):
    class BuildingType(models.TextChoices):
        BARN = "barn", "Barn"
        SHED = "shed", "Shed"
        SILO = "silo", "Silo"
        GARAGE = "garage", "Garage"
        GREENHOUSE = "greenhouse", "Greenhouse"
        COOP = "coop", "Coop"
        STABLE = "stable", "Stable"
        SHOP = "shop", "Shop"
        HOUSE = "house", "House"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200)
    building_type = models.CharField(max_length=20, choices=BuildingType.choices, default=BuildingType.OTHER)
    location = gis_models.PointField(srid=4326, null=True, blank=True)
    year_built = models.IntegerField(null=True, blank=True)
    square_feet = models.IntegerField(null=True, blank=True)
    assessed_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    insurance_policy = models.CharField(max_length=100, blank=True)
    insurance_annual = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Annual insurance cost")
    tax_annual = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Annual property tax")
    photo = models.ImageField(upload_to="buildings/photos/", blank=True)

    class Meta:
        db_table = "building"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_building_type_display()})"

    @property
    def lat(self):
        return self.location.y if self.location else None

    @property
    def lon(self):
        return self.location.x if self.location else None


class BuildingMaintenanceRecord(FarmOwnedModel, NotesMixin, CostMixin):
    class MaintenanceType(models.TextChoices):
        ROOF = "roof", "Roof"
        ELECTRICAL = "electrical", "Electrical"
        PLUMBING = "plumbing", "Plumbing"
        STRUCTURAL = "structural", "Structural"
        PAINTING = "painting", "Painting"
        HVAC = "hvac", "HVAC"
        PEST_CONTROL = "pest_control", "Pest Control"
        OTHER = "other", "Other"

    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="maintenance_records")
    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices)
    date = models.DateField()
    description = models.TextField()
    contractor = models.CharField(max_length=200, blank=True)
    next_due_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "building_maintenance_record"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.building.name} — {self.get_maintenance_type_display()} ({self.date})"
