from django import forms

from .models import Equipment, MaintenanceRecord

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ["name", "brand", "model_name", "year", "serial_number", "status",
                   "hours", "purchase_price", "purchase_date", "photo", "notes"]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class MaintenanceRecordForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = ["maintenance_type", "date", "description", "performed_by",
                   "hours_at_service", "cost", "next_service_date", "next_service_hours", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "next_service_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
