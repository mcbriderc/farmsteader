from django import forms

from apps.land.models import Field

from .models import Animal, FeedLog, FeedStock, FeedType, FieldMovement, VetRecord

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class AnimalForm(forms.ModelForm):
    class Meta:
        model = Animal
        fields = [
            "ear_tag", "name", "species", "breed", "gender", "repro_status", "status",
            "date_of_birth", "date_acquired", "purchase_price", "weight_kg",
            "current_field", "sire", "dam", "photo", "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "date_acquired": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["current_field"].queryset = Field.objects.filter(farm=farm)
            self.fields["sire"].queryset = Animal.objects.filter(farm=farm, gender=Animal.Gender.MALE)
            self.fields["dam"].queryset = Animal.objects.filter(farm=farm, gender=Animal.Gender.FEMALE)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class VetRecordForm(forms.ModelForm):
    class Meta:
        model = VetRecord
        fields = ["record_type", "date", "description", "veterinarian", "cost", "next_due_date", "attachment", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "next_due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class FieldMovementForm(forms.ModelForm):
    class Meta:
        model = FieldMovement
        fields = ["to_field", "date", "reason", "notes"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["to_field"].queryset = Field.objects.filter(farm=farm)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class FeedTypeForm(forms.ModelForm):
    class Meta:
        model = FeedType
        fields = ["name", "category", "default_unit"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class FeedStockForm(forms.ModelForm):
    class Meta:
        model = FeedStock
        fields = [
            "feed_type", "name", "quantity", "unit", "restock_source",
            "reorder_threshold", "unit_cost", "storage_location", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class FeedLogForm(forms.ModelForm):
    class Meta:
        model = FeedLog
        fields = ["feed_stock", "quantity", "unit", "date", "notes"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["feed_stock"].queryset = FeedStock.objects.filter(farm=farm)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
