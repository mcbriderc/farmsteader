from django.contrib import admin

from .models import ProduceItem, ProduceTransaction


@admin.register(ProduceItem)
class ProduceItemAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "storage_type", "quantity", "unit", "expiry_date", "farm"]
    list_filter = ["farm", "source", "storage_type"]


@admin.register(ProduceTransaction)
class ProduceTransactionAdmin(admin.ModelAdmin):
    list_display = ["item", "transaction_type", "quantity", "date"]
    list_filter = ["farm", "transaction_type"]
