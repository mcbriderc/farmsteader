from django import forms

from .models import Building, BuildingMaintenanceRecord

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class BuildingForm(forms.ModelForm):
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Building
        fields = ["name", "building_type", "year_built", "square_feet",
                   "assessed_value", "insurance_policy", "insurance_annual",
                   "tax_annual", "photo", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.location:
            self.fields["latitude"].initial = self.instance.lat
            self.fields["longitude"].initial = self.instance.lon
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class") and not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs["class"] = INPUT_CLASS

    def save(self, commit=True):
        from django.contrib.gis.geos import Point

        instance = super().save(commit=False)
        lat = self.cleaned_data.get("latitude")
        lon = self.cleaned_data.get("longitude")
        if lat and lon:
            instance.location = Point(lon, lat, srid=4326)
        if commit:
            instance.save()
        return instance


class BuildingMaintenanceForm(forms.ModelForm):
    class Meta:
        model = BuildingMaintenanceRecord
        fields = ["maintenance_type", "date", "description", "contractor",
                   "cost", "next_due_date", "notes"]
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
