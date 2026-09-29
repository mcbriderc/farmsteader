from django import forms

from .models import ConsumableType, InventoryItem, InventoryTransaction

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class ConsumableTypeForm(forms.ModelForm):
    class Meta:
        model = ConsumableType
        fields = ["name", "category", "default_unit"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ["consumable_type", "name", "quantity", "unit", "reorder_threshold",
                   "unit_cost", "storage_location", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class InventoryTransactionForm(forms.ModelForm):
    class Meta:
        model = InventoryTransaction
        fields = ["transaction_type", "quantity", "date", "unit_cost", "reference", "notes"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
