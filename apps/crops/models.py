from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin


class CropType(models.Model):
    """Global crop catalog — not farm-scoped."""
    name = models.CharField(max_length=100, unique=True)
    usda_code = models.CharField(max_length=20, blank=True, help_text="USDA NASS commodity code")
    category = models.CharField(max_length=50, blank=True, help_text="e.g. Grain, Oilseed, Vegetable")
    default_unit = models.CharField(max_length=20, default="bushels")

    class Meta:
        db_table = "crop_type"
        ordering = ["name"]

    def __str__(self):
        return self.name


class MarketPrice(models.Model):
    """Cached crop prices from USDA NASS."""
    crop_type = models.ForeignKey(CropType, on_delete=models.CASCADE, related_name="prices")
    year = models.IntegerField()
    state = models.CharField(max_length=50, blank=True, help_text="US state or 'US' for national")
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, default="$/bushel")
    source = models.CharField(max_length=50, default="USDA NASS")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "market_price"
        unique_together = [("crop_type", "year", "state")]
        ordering = ["-year"]

    def __str__(self):
        return f"{self.crop_type.name} {self.year} ({self.state}): ${self.price_per_unit}/{self.unit}"


class CommodityPrice(models.Model):
    """CME futures prices synced daily via yfinance. Global — not farm-scoped."""
    ticker = models.CharField(max_length=20)
    commodity = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20)
    change = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    change_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    date = models.DateField()
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commodity_price"
        unique_together = [("ticker", "date")]
        ordering = ["commodity"]

    def __str__(self):
        return f"{self.commodity} ${self.price} {self.unit} ({self.date})"


class HarvestRecord(FarmOwnedModel, NotesMixin, CostMixin):
    """What came off a field.

    `planting` is optional: perennial crops (hay, pasture) often have no
    planting record. When it is set, `field` and `crop_type` must match it --
    they stay on the harvest so unlinked harvests still say where and what.
    """

    field = models.ForeignKey("land.Field", on_delete=models.CASCADE, related_name="harvests")
    # PROTECT, not CASCADE: CropType is a catalog shared by every farm, and
    # CASCADE let deleting a catalog entry silently delete every farm's harvests.
    crop_type = models.ForeignKey(CropType, on_delete=models.PROTECT, related_name="harvests")
    planting = models.ForeignKey(
        "land.CropRecord", on_delete=models.SET_NULL, null=True, blank=True, related_name="harvests",
        help_text="The planting this harvest came from, if any",
    )
    harvest_date = models.DateField()
    yield_amount = models.DecimalField(max_digits=10, decimal_places=2)
    yield_unit = models.CharField(max_length=20, default="bushels")
    moisture_pct = models.FloatField(null=True, blank=True, verbose_name="Moisture %")
    quality_grade = models.CharField(max_length=50, blank=True)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "harvest_record"
        ordering = ["-harvest_date"]

    def __str__(self):
        return f"{self.crop_type.name} — {self.field.name} ({self.harvest_date})"

    def clean(self):
        super().clean()
        p = self.planting
        if p is None:
            return
        from django.core.exceptions import ValidationError

        errors = {}
        if self.farm_id and p.farm_id != self.farm_id:
            errors["planting"] = "That planting belongs to another farm."
        if self.field_id and p.field_id != self.field_id:
            errors["field"] = f"The planting is on {p.field.name}; a harvest from it must be too."
        if self.crop_type_id and p.crop_type_id != self.crop_type_id:
            errors["crop_type"] = f"The planting is {p.crop_type.name}; a harvest from it must be too."
        if errors:
            raise ValidationError(errors)
