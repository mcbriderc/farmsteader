from django.contrib import admin

from .models import CropType, HarvestRecord, MarketPrice


@admin.register(CropType)
class CropTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "usda_code", "category", "default_unit"]
    search_fields = ["name"]


@admin.register(MarketPrice)
class MarketPriceAdmin(admin.ModelAdmin):
    list_display = ["crop_type", "year", "state", "price_per_unit"]
    list_filter = ["year", "crop_type"]


@admin.register(HarvestRecord)
class HarvestRecordAdmin(admin.ModelAdmin):
    list_display = ["crop_type", "field", "harvest_date", "yield_amount", "revenue"]
    list_filter = ["farm", "crop_type"]
