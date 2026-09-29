from django.contrib import admin

from .models import ConsumableType, InventoryItem, InventoryTransaction


@admin.register(ConsumableType)
class ConsumableTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "default_unit"]


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ["name", "consumable_type", "quantity", "unit", "reorder_threshold", "farm"]
    list_filter = ["farm", "consumable_type"]


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ["item", "transaction_type", "quantity", "date"]
    list_filter = ["farm", "transaction_type"]
