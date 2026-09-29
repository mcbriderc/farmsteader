from django.contrib.auth.models import AbstractUser
from django.db import models


class FarmUser(AbstractUser):
    """Custom user model for FarmSteader."""

    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "farm_user"

    def __str__(self):
        return self.get_full_name() or self.username


class Farm(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    members = models.ManyToManyField(
        FarmUser, through="FarmMembership", related_name="farms"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "farm"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FarmMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        WORKER = "worker", "Worker"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        FarmUser, on_delete=models.CASCADE, related_name="memberships"
    )
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WORKER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "farm_membership"
        unique_together = [("user", "farm")]

    def __str__(self):
        return f"{self.user} – {self.farm} ({self.get_role_display()})"


class FarmSettings(models.Model):
    """Per-farm configuration for API keys and data source preferences."""

    farm = models.OneToOneField(Farm, on_delete=models.CASCADE, related_name="settings")

    # API keys
    usda_nass_api_key = models.CharField(
        max_length=200, blank=True, verbose_name="USDA NASS API Key",
        help_text="Get a free key at https://quickstats.nass.usda.gov/api/",
    )

    # Data source toggles
    weather_enabled = models.BooleanField(default=True, verbose_name="Weather sync",
        help_text="Fetch weather data from Open-Meteo (free, no key required)")
    soil_enabled = models.BooleanField(default=True, verbose_name="Soil data sync",
        help_text="Fetch soil data from SoilGrids (free, no key required)")
    crop_prices_enabled = models.BooleanField(default=False, verbose_name="Crop price sync",
        help_text="Fetch crop prices from USDA NASS (requires API key above)")

    # Dashboard display preferences
    visible_tickers = models.JSONField(
        default=list, blank=True,
        verbose_name="Visible commodity prices",
        help_text="Leave empty to show all. Select only the markets relevant to your farm.",
    )

    class Meta:
        db_table = "farm_settings"
        verbose_name_plural = "farm settings"

    def __str__(self):
        return f"Settings for {self.farm.name}"
