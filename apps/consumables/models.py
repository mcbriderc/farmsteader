from django.db import models

from apps.core.models import CostMixin, FarmOwnedModel, NotesMixin


class ConsumableType(models.Model):
    """Global catalog of consumable types."""
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, blank=True, help_text="e.g. Feed, Seed, Chemical, Fuel, Medical")
    default_unit = models.CharField(max_length=20, default="units")

    class Meta:
        db_table = "consumable_type"
        ordering = ["name"]

    def __str__(self):
        return self.name


class InventoryItem(FarmOwnedModel, NotesMixin):
    consumable_type = models.ForeignKey(ConsumableType, on_delete=models.CASCADE, related_name="inventory_items")
    name = models.CharField(max_length=200, help_text="Specific product name")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, default="units")
    reorder_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Alert when quantity drops below this level",
    )
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    storage_location = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "inventory_item"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_threshold and self.reorder_threshold > 0


class InventoryTransaction(FarmOwnedModel, NotesMixin):
    class TransactionType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        USE = "use", "Use"
        ADJUSTMENT = "adjustment", "Adjustment"
        TRANSFER = "transfer", "Transfer"
        WASTE = "waste", "Waste"

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Positive for additions, negative for removals")
    date = models.DateTimeField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=200, blank=True, help_text="Invoice number, PO, etc.")

    class Meta:
        db_table = "inventory_transaction"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.item.name}: {self.quantity:+} ({self.get_transaction_type_display()})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            # Update item quantity
            self.item.quantity = models.F("quantity") + self.quantity
            self.item.save(update_fields=["quantity"])
            self.item.refresh_from_db()
