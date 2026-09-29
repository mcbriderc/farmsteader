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
    """Adds cost tracking to any model."""

    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        abstract = True
