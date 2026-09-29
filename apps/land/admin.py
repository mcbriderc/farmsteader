from django.contrib.gis import admin

from .models import CropRecord, Field, SoilSample, WeatherCache


@admin.register(Field)
class FieldAdmin(admin.GISModelAdmin):
    list_display = ["name", "farm", "acreage", "soil_type"]
    list_filter = ["farm"]
    readonly_fields = ["acreage", "centroid_lat", "centroid_lon"]


@admin.register(WeatherCache)
class WeatherCacheAdmin(admin.ModelAdmin):
    list_display = ["field", "date", "temp_max_c", "temp_min_c", "precipitation_mm"]
    list_filter = ["field__farm", "date"]


@admin.register(SoilSample)
class SoilSampleAdmin(admin.ModelAdmin):
    list_display = ["field", "source", "sample_date", "ph", "texture_class"]
    list_filter = ["farm", "source"]


@admin.register(CropRecord)
class CropRecordAdmin(admin.ModelAdmin):
    list_display = ["field", "crop_name", "season", "status", "cost"]
    list_filter = ["farm", "status", "season"]
