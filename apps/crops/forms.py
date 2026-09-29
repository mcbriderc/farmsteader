from django import forms

from apps.land.models import Field

from .models import CropType, HarvestRecord

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class CropTypeForm(forms.ModelForm):
    class Meta:
        model = CropType
        fields = ["name", "category", "default_unit", "usda_code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class HarvestRecordForm(forms.ModelForm):
    class Meta:
        model = HarvestRecord
        fields = ["field", "crop_type", "harvest_date", "yield_amount", "yield_unit",
                   "moisture_pct", "quality_grade", "cost", "revenue", "notes"]
        widgets = {
            "harvest_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["field"].queryset = Field.objects.filter(farm=farm)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
