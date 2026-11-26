from decimal import Decimal

from django.db import models


class FarmOwnedModel(models.Model):
    """Abstract base for all models scoped to a farm."""

    farm = models.ForeignKey(
        "accounts.Farm",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class NotesMixin(models.Model):
    """Adds a notes field to any model."""

    notes = models.TextField(blank=True)

    class Meta:
        abstract = True


class CostMixin(models.Model):
    """Adds cost tracking to any model.

    Cost is optional: a blank one (an emptied form field, an empty CSV cell)
    is stored as 0, so a free vet visit needs nothing typed. The column stays
    NOT NULL -- totals and templates never have to cope with a missing cost.
    """

    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True)

    class Meta:
        abstract = True

    def _fill_blank_cost(self):
        if self.cost is None:
            self.cost = Decimal("0")

    def clean_fields(self, exclude=None):
        self._fill_blank_cost()
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self._fill_blank_cost()
        super().save(*args, **kwargs)
