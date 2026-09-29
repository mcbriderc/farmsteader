from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin


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
            # Transform to EPSG:5070 (NAD83 Conus Albers) for accurate area in sq meters
            boundary_projected = self.boundary.transform(5070, clone=True)
            sq_meters = boundary_projected.area
            self.acreage = round(sq_meters / 4046.8564224, 2)

            centroid = self.boundary.centroid
            self.centroid_lat = centroid.y
            self.centroid_lon = centroid.x
        super().save(*args, **kwargs)


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
