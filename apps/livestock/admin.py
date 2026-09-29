from django.contrib import admin

from .models import Animal, FeedLog, FeedStock, FeedType, FieldMovement, VetRecord


class VetRecordInline(admin.TabularInline):
    model = VetRecord
    extra = 0


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ["ear_tag", "name", "species", "gender", "status", "farm"]
    list_filter = ["farm", "species", "status", "gender"]
    search_fields = ["ear_tag", "name", "breed"]
    inlines = [VetRecordInline]


@admin.register(VetRecord)
class VetRecordAdmin(admin.ModelAdmin):
    list_display = ["animal", "record_type", "date", "cost"]
    list_filter = ["farm", "record_type"]


@admin.register(FieldMovement)
class FieldMovementAdmin(admin.ModelAdmin):
    list_display = ["animal", "from_field", "to_field", "date"]
    list_filter = ["farm"]


@admin.register(FeedType)
class FeedTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "default_unit"]
    list_filter = ["category"]


@admin.register(FeedStock)
class FeedStockAdmin(admin.ModelAdmin):
    list_display = ["name", "feed_type", "quantity", "unit", "restock_source", "farm"]
    list_filter = ["farm", "restock_source", "feed_type__category"]


@admin.register(FeedLog)
class FeedLogAdmin(admin.ModelAdmin):
    list_display = ["animal", "feed_stock", "quantity", "unit", "date"]
    list_filter = ["farm"]
