from django.db import models

from apps.core.models import FarmOwnedModel, NotesMixin


class ProduceItem(FarmOwnedModel, NotesMixin):
    class Source(models.TextChoices):
        FARM_ANIMAL = "farm_animal", "Farm Animal"
        FARM_CROP = "farm_crop", "Farm Crop"
        PURCHASED = "purchased", "Purchased"
        DONATED = "donated", "Donated"

    class StorageType(models.TextChoices):
        FRESH = "fresh", "Fresh"
        FROZEN = "frozen", "Frozen"
        CANNED = "canned", "Canned"
        DRIED = "dried", "Dried"
        PRESERVED = "preserved", "Preserved"

    name = models.CharField(max_length=200)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.PURCHASED)
    storage_type = models.CharField(max_length=20, choices=StorageType.choices, default=StorageType.FRESH)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, default="lbs")
    expiry_date = models.DateField(null=True, blank=True)
    storage_location = models.CharField(max_length=200, blank=True)

    # Optional linkage to source
    source_animal = models.ForeignKey(
        "livestock.Animal", on_delete=models.SET_NULL, null=True, blank=True, related_name="produce_items",
    )
    source_crop_record = models.ForeignKey(
        "land.CropRecord", on_delete=models.SET_NULL, null=True, blank=True, related_name="produce_items",
    )

    class Meta:
        db_table = "food_item"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.expiry_date:
            return self.expiry_date < timezone.now().date()
        return False


class ProduceTransaction(FarmOwnedModel, NotesMixin):
    class TransactionType(models.TextChoices):
        HARVEST = "harvest", "Harvest"
        BUTCHER = "butcher", "Butcher"
        PURCHASE = "purchase", "Purchase"
        CONSUME = "consume", "Consume"
        SELL = "sell", "Sell"
        DONATE = "donate", "Donate"
        WASTE = "waste", "Waste"

    item = models.ForeignKey(ProduceItem, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Positive to add, negative to remove")
    date = models.DateTimeField()
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "food_transaction"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.item.name}: {self.quantity:+} ({self.get_transaction_type_display()})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.item.quantity = models.F("quantity") + self.quantity
            self.item.save(update_fields=["quantity"])
            self.item.refresh_from_db()
