from django.contrib.gis import admin

from .models import Building, BuildingMaintenanceRecord


class MaintenanceInline(admin.TabularInline):
    model = BuildingMaintenanceRecord
    extra = 0


@admin.register(Building)
class BuildingAdmin(admin.GISModelAdmin):
    list_display = ["name", "building_type", "year_built", "assessed_value", "farm"]
    list_filter = ["farm", "building_type"]
    inlines = [MaintenanceInline]


@admin.register(BuildingMaintenanceRecord)
class BuildingMaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ["building", "maintenance_type", "date", "cost"]
    list_filter = ["farm", "maintenance_type"]
