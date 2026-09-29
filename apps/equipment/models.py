from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin


class Equipment(FarmOwnedModel, NotesMixin):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "In Maintenance"
        RETIRED = "retired", "Retired"
        SOLD = "sold", "Sold"

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True, verbose_name="Model")
    year = models.IntegerField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    hours = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True, help_text="Current hour meter reading")
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to="equipment/photos/", blank=True)

    class Meta:
        db_table = "equipment"
        ordering = ["name"]

    def __str__(self):
        parts = [self.name]
        if self.brand:
            parts.append(self.brand)
        if self.model_name:
            parts.append(self.model_name)
        return " — ".join(parts)

    @property
    def next_service(self):
        """Return the nearest upcoming maintenance record by next_service_date."""
        return self.maintenance_records.filter(
            next_service_date__isnull=False,
        ).order_by("next_service_date").first()


class MaintenanceRecord(FarmOwnedModel, NotesMixin, CostMixin):
    class MaintenanceType(models.TextChoices):
        OIL_CHANGE = "oil_change", "Oil Change"
        FILTER = "filter", "Filter Replacement"
        TIRES = "tires", "Tires"
        REPAIR = "repair", "Repair"
        INSPECTION = "inspection", "Inspection"
        WINTERIZATION = "winterization", "Winterization"
        OTHER = "other", "Other"

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="maintenance_records")
    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices)
    date = models.DateField()
    description = models.TextField()
    performed_by = models.CharField(max_length=200, blank=True)
    hours_at_service = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)
    next_service_hours = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)

    class Meta:
        db_table = "maintenance_record"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.equipment.name} — {self.get_maintenance_type_display()} ({self.date})"
