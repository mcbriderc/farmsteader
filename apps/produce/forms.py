from django import forms

from apps.land.models import CropRecord
from apps.livestock.models import Animal

from .models import ProduceItem, ProduceTransaction

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class ProduceItemForm(forms.ModelForm):
    class Meta:
        model = ProduceItem
        fields = ["name", "source", "storage_type", "quantity", "unit",
                   "expiry_date", "storage_location", "source_animal",
                   "source_crop_record", "notes"]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["source_animal"].queryset = Animal.objects.filter(farm=farm)
            self.fields["source_crop_record"].queryset = CropRecord.objects.filter(farm=farm)
        self.fields["source_animal"].required = False
        self.fields["source_crop_record"].required = False
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class ProduceTransactionForm(forms.ModelForm):
    class Meta:
        model = ProduceTransaction
        fields = ["transaction_type", "quantity", "date", "cost", "notes"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
