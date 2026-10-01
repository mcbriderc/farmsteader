from django import forms

from apps.land.models import CropRecord, Field

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
    """A harvest, optionally from a planting.

    With a planting chosen, field and crop come from it (and are checked
    against it if also given); without one, both are required as before.
    """

    class Meta:
        model = HarvestRecord
        fields = ["planting", "field", "crop_type", "harvest_date", "yield_amount", "yield_unit",
                   "moisture_pct", "quality_grade", "cost", "revenue", "notes"]
        labels = {"planting": "From planting", "crop_type": "Crop"}
        help_texts = {
            "planting": "Optional. Choosing one fills in the field and crop for you.",
            "field": "Required unless a planting is chosen.",
            "crop_type": "Required unless a planting is chosen.",
        }
        widgets = {
            "harvest_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Never offer another farm's fields or plantings; with no farm, offer none.
        self.fields["field"].queryset = Field.objects.filter(farm=farm) if farm else Field.objects.none()
        self.fields["planting"].queryset = (
            CropRecord.objects.filter(farm=farm).select_related("crop_type", "field")
            if farm else CropRecord.objects.none()
        )
        self.fields["planting"].empty_label = "None (e.g. perennial hay or pasture)"
        self.fields["field"].required = False
        self.fields["crop_type"].required = False
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS

    def clean(self):
        cleaned = super().clean()
        planting = cleaned.get("planting")
        if planting is not None:
            # Fill from the planting; HarvestRecord.clean() then rejects any
            # field or crop that was given and disagrees with it.
            cleaned["field"] = cleaned.get("field") or planting.field
            cleaned["crop_type"] = cleaned.get("crop_type") or planting.crop_type
        else:
            if not cleaned.get("field"):
                self.add_error("field", "Choose a field, or the planting this harvest came from.")
            if not cleaned.get("crop_type"):
                self.add_error("crop_type", "Choose a crop, or the planting this harvest came from.")
        return cleaned
