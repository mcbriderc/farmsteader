from django.contrib.gis.db import models as gis_models
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin

from .geo import acreage_of

hex_color_validator = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Enter a colour like #f59e0b.")


class Field(FarmOwnedModel, NotesMixin):
    name = models.CharField(max_length=200)
    boundary = gis_models.PolygonField(srid=4326)
    acreage = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    centroid_lat = models.FloatField(editable=False, default=0)
    centroid_lon = models.FloatField(editable=False, default=0)
    soil_type = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=7, default="#22c55e", help_text="Hex color for map display")
    timezone = models.CharField(max_length=50, blank=True, default="", help_text="IANA timezone, auto-populated from Open-Meteo")

    class Meta:
        db_table = "field"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.acreage} ac)"

    def save(self, *args, **kwargs):
        if self.boundary:
            self.acreage = acreage_of(self.boundary)
            centroid = self.boundary.centroid
            self.centroid_lat = centroid.y
            self.centroid_lon = centroid.x
        super().save(*args, **kwargs)


class Parcel(FarmOwnedModel, NotesMixin):
    """A piece of property: the legal boundary a farm owns or leases.

    Distinct from Field, which is a *managed* area inside it (planted, grazed,
    soil-sampled). A parcel is usually larger than the fields on it and holds
    ground that is never farmed -- woodland, yard, buildings, waterways -- so
    total parcel acreage and total field acreage answer different questions.
    """

    name = models.CharField(max_length=200)
    boundary = gis_models.PolygonField(srid=4326)
    acreage = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    parcel_number = models.CharField(
        max_length=100, blank=True,
        help_text="County tax parcel ID / APN, if known",
    )
    color = models.CharField(
        max_length=7, default="#f59e0b", validators=[hex_color_validator],
        help_text="Hex colour for the property line on the map",
    )

    class Meta:
        db_table = "parcel"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.acreage} ac)"

    def save(self, *args, **kwargs):
        if self.boundary:
            self.acreage = acreage_of(self.boundary)
        super().save(*args, **kwargs)

    def fields_within(self):
        """This farm's fields that overlap the parcel at all, largest first."""
        return Field.objects.filter(
            farm_id=self.farm_id, boundary__intersects=self.boundary,
        ).order_by("-acreage", "name")

    def field_coverage(self):
        """How much of the parcel is taken up by fields.

        Returns ``(rows, covered_acres, covered_pct)`` where each row is
        ``(field, acres_inside)``. Measured on the *overlap*, not each field's
        own acreage: a field that straddles the property line only counts for
        the part inside it. The total is taken over the union of the overlaps,
        so fields drawn on top of each other are not counted twice.
        """
        rows, pieces = [], []
        for field in self.fields_within():
            overlap = field.boundary.intersection(self.boundary)
            if overlap.empty or overlap.area == 0:
                continue  # touches the line without sharing any ground
            rows.append((field, acreage_of(overlap)))
            pieces.append(overlap)
        if not pieces:
            return rows, 0, 0
        union = pieces[0]
        for piece in pieces[1:]:
            union = union.union(piece)
        covered = acreage_of(union)
        pct = round(100 * covered / float(self.acreage)) if self.acreage else 0
        return rows, covered, min(pct, 100)


class WeatherCache(models.Model):
    field = models.ForeignKey(Field, on_delete=models.CASCADE, related_name="weather_records")
    date = models.DateField()
    temp_max_c = models.FloatField(null=True, blank=True)
    temp_min_c = models.FloatField(null=True, blank=True)
    precipitation_mm = models.FloatField(null=True, blank=True)
    wind_speed_max_kmh = models.FloatField(null=True, blank=True)
    weather_code = models.IntegerField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "weather_cache"
        unique_together = [("field", "date")]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.field.name} — {self.date}"

    @property
    def temp_max_f(self):
        if self.temp_max_c is not None:
            return round(self.temp_max_c * 9 / 5 + 32, 1)
        return None

    @property
    def temp_min_f(self):
        if self.temp_min_c is not None:
            return round(self.temp_min_c * 9 / 5 + 32, 1)
        return None

    @property
    def precipitation_in(self):
        if self.precipitation_mm is not None:
            return round(self.precipitation_mm / 25.4, 2)
        return None

    @property
    def wind_speed_max_mph(self):
        if self.wind_speed_max_kmh is not None:
            return round(self.wind_speed_max_kmh / 1.60934, 1)
        return None


class SoilSample(FarmOwnedModel, NotesMixin):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual Entry"
        SOILGRIDS = "soilgrids", "SoilGrids API"
        USDA = "usda", "USDA Soil Data"

    field = models.ForeignKey(Field, on_delete=models.CASCADE, related_name="soil_samples")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    sample_date = models.DateField(null=True, blank=True)
    depth_cm = models.IntegerField(default=30, help_text="Sample depth in cm")

    # Soil properties
    ph = models.FloatField(null=True, blank=True)
    organic_carbon_pct = models.FloatField(null=True, blank=True, verbose_name="Organic carbon %")
    nitrogen_ppm = models.FloatField(null=True, blank=True, verbose_name="Nitrogen (ppm)")
    sand_pct = models.FloatField(null=True, blank=True)
    silt_pct = models.FloatField(null=True, blank=True)
    clay_pct = models.FloatField(null=True, blank=True)
    texture_class = models.CharField(max_length=50, blank=True)
    cec = models.FloatField(null=True, blank=True, verbose_name="CEC (cmol/kg)")

    class Meta:
        db_table = "soil_sample"
        ordering = ["-sample_date"]

    def __str__(self):
        return f"{self.field.name} — {self.get_source_display()} ({self.sample_date or 'no date'})"


class CropRecord(FarmOwnedModel, NotesMixin, CostMixin):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        SEEDED = "seeded", "Seeded"
        GROWING = "growing", "Growing"
        FERTILIZED = "fertilized", "Fertilized"
        HARVESTED = "harvested", "Harvested"
        FAILED = "failed", "Failed"

    field = models.ForeignKey(Field, on_delete=models.CASCADE, related_name="crop_records")
    crop_name = models.CharField(max_length=100)
    variety = models.CharField(max_length=100, blank=True)
    season = models.CharField(max_length=20, help_text="e.g. 2026-Spring")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)

    planted_date = models.DateField(null=True, blank=True)
    harvest_date = models.DateField(null=True, blank=True)
    yield_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    yield_unit = models.CharField(max_length=20, blank=True, default="bushels")

    class Meta:
        db_table = "crop_record"
        ordering = ["-season", "crop_name"]

    def __str__(self):
        return f"{self.crop_name} — {self.field.name} ({self.season})"
