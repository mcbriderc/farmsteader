from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin

_LAND_FIELD = "land.Field"


class Animal(FarmOwnedModel, NotesMixin):
    class Species(models.TextChoices):
        CATTLE = "cattle", "Cattle"
        SHEEP = "sheep", "Sheep"
        GOAT = "goat", "Goat"
        PIG = "pig", "Pig"
        HORSE = "horse", "Horse"
        CHICKEN = "chicken", "Chicken"
        DUCK = "duck", "Duck"
        TURKEY = "turkey", "Turkey"
        OTHER = "other", "Other"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        UNKNOWN = "unknown", "Unknown"

    class ReproStatus(models.TextChoices):
        INTACT = "intact", "Intact"
        CASTRATED = "castrated", "Castrated"
        SPAYED = "spayed", "Spayed"
        PREGNANT = "pregnant", "Pregnant"
        NURSING = "nursing", "Nursing"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SOLD = "sold", "Sold"
        DECEASED = "deceased", "Deceased"
        TRANSFERRED = "transferred", "Transferred"

    ear_tag = models.CharField(max_length=50)
    name = models.CharField(max_length=100, blank=True)
    species = models.CharField(max_length=20, choices=Species.choices)
    breed = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.UNKNOWN)
    repro_status = models.CharField(
        max_length=20, choices=ReproStatus.choices, default=ReproStatus.INTACT,
        verbose_name="Reproductive status",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    date_of_birth = models.DateField(null=True, blank=True)
    date_acquired = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    current_field = models.ForeignKey(
        _LAND_FIELD, on_delete=models.SET_NULL, null=True, blank=True, related_name="animals",
    )
    sire = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="offspring_as_sire",
    )
    dam = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="offspring_as_dam",
    )
    photo = models.ImageField(upload_to="livestock/photos/", blank=True)

    class Meta:
        db_table = "animal"
        unique_together = [("farm", "ear_tag")]
        ordering = ["ear_tag"]

    def __str__(self):
        label = self.name or self.ear_tag
        return f"{label} ({self.get_species_display()})"

    @property
    def days_in_current_field(self):
        """Days since this animal was moved to its current field."""
        if not self.current_field:
            return None
        from django.utils import timezone

        last_movement = self.movements.filter(
            to_field=self.current_field,
        ).order_by("-date").first()
        if last_movement:
            return (timezone.now() - last_movement.date).days
        if self.date_acquired:
            return (timezone.now().date() - self.date_acquired).days
        return None


class VetRecord(FarmOwnedModel, NotesMixin, CostMixin):
    class RecordType(models.TextChoices):
        IMMUNIZATION = "immunization", "Immunization"
        EXAM = "exam", "Examination"
        TREATMENT = "treatment", "Treatment"
        SURGERY = "surgery", "Surgery"
        PREGNANCY_CHECK = "pregnancy_check", "Pregnancy Check"
        DEWORMING = "deworming", "Deworming"
        OTHER = "other", "Other"

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="vet_records")
    record_type = models.CharField(max_length=20, choices=RecordType.choices)
    date = models.DateField()
    description = models.TextField()
    veterinarian = models.CharField(max_length=200, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    attachment = models.FileField(upload_to="livestock/vet_attachments/", blank=True)

    class Meta:
        db_table = "vet_record"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.animal} — {self.get_record_type_display()} ({self.date})"


class FieldMovement(FarmOwnedModel, NotesMixin):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="movements")
    from_field = models.ForeignKey(
        _LAND_FIELD, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements_from",
    )
    to_field = models.ForeignKey(
        _LAND_FIELD, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements_to",
    )
    date = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "field_movement"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.animal} → {self.to_field} ({self.date:%Y-%m-%d})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update animal's current field
        if self.to_field:
            Animal.objects.filter(pk=self.animal_id).update(current_field=self.to_field)


class FeedType(models.Model):
    """Global catalog of livestock feed types."""

    class Category(models.TextChoices):
        HAY = "hay", "Hay"
        GRAIN = "grain", "Grain"
        SILAGE = "silage", "Silage"
        PELLET = "pellet", "Pellet / Concentrate"
        SUPPLEMENT = "supplement", "Supplement / Mineral"
        FRESH_FORAGE = "fresh_forage", "Fresh Forage"
        OTHER = "other", "Other"

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    default_unit = models.CharField(max_length=20, default="lbs")

    class Meta:
        db_table = "feed_type"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FeedStock(FarmOwnedModel, NotesMixin):
    """Tracks a specific feed supply on the farm."""

    class RestockSource(models.TextChoices):
        PURCHASED = "purchased", "Purchased"
        FARM_HAY = "farm_hay", "Farm Hay"
        FARM_GRAIN = "farm_grain", "Farm Grain"
        FARM_SILAGE = "farm_silage", "Farm Silage"
        PASTURE_FORAGE = "pasture_forage", "Pasture / Forage"
        OTHER = "other", "Other"

    feed_type = models.ForeignKey(FeedType, on_delete=models.CASCADE, related_name="stocks")
    name = models.CharField(max_length=200, help_text="Specific product or batch name")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, default="lbs")
    restock_source = models.CharField(
        max_length=20,
        choices=RestockSource.choices,
        default=RestockSource.PURCHASED,
        help_text="How this feed is restocked when low",
    )
    reorder_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Alert when quantity drops below this level",
    )
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    storage_location = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "feed_stock"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_threshold and self.reorder_threshold > 0


class FeedLog(FarmOwnedModel, NotesMixin):
    """Records a feeding event for a specific animal."""

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="feed_logs")
    feed_stock = models.ForeignKey(FeedStock, on_delete=models.CASCADE, related_name="feed_logs")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, default="lbs")
    date = models.DateTimeField()

    class Meta:
        db_table = "feeding_log"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.animal.ear_tag}: {self.quantity} {self.unit} of {self.feed_stock.name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.feed_stock.quantity = models.F("quantity") - self.quantity
            self.feed_stock.save(update_fields=["quantity"])
            self.feed_stock.refresh_from_db()
