from django.contrib import admin

from .models import Equipment, MaintenanceRecord


class MaintenanceInline(admin.TabularInline):
    model = MaintenanceRecord
    extra = 0


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "model_name", "status", "hours", "farm"]
    list_filter = ["farm", "status"]
    search_fields = ["name", "brand", "serial_number"]
    inlines = [MaintenanceInline]


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ["equipment", "maintenance_type", "date", "cost", "next_service_date"]
    list_filter = ["farm", "maintenance_type"]
