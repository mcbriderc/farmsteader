from django import forms

from .models import CropRecord, Field, Parcel, SoilSample

_INPUT_CLASSES = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"
_COLOR_WIDGET = forms.TextInput(attrs={"type": "color", "class": "h-10 w-16 rounded border-gray-300"})


class BoundaryFormMixin:
    """A polygon drawn on the map arrives as GeoJSON in a hidden input.

    Shared by every form that stores a `boundary`, so fields and parcels accept
    exactly the same shapes.
    """

    def clean_boundary_geojson(self):
        from django.contrib.gis.geos import GEOSException, GEOSGeometry

        geojson = self.cleaned_data["boundary_geojson"]
        try:
            geom = GEOSGeometry(geojson)
        except (GEOSException, ValueError, TypeError) as e:
            raise forms.ValidationError(f"Invalid GeoJSON: {e}") from e
        if geom.geom_type != "Polygon":
            raise forms.ValidationError("Boundary must be a polygon.")
        # A self-crossing outline has no meaningful area, and GEOS refuses to
        # intersect it with anything -- which a parcel's field coverage needs.
        if not geom.valid:
            raise forms.ValidationError(
                f"The boundary crosses itself ({geom.valid_reason}). Redraw it without overlapping edges."
            )
        return geom

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.boundary = self.cleaned_data["boundary_geojson"]
        if commit:
            instance.save()
        return instance


class FieldForm(BoundaryFormMixin, forms.ModelForm):
    boundary_geojson = forms.CharField(widget=forms.HiddenInput, required=True)

    class Meta:
        model = Field
        fields = ["name", "soil_type", "color", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT_CLASSES}),
            "soil_type": forms.TextInput(attrs={"class": _INPUT_CLASSES}),
            "color": _COLOR_WIDGET,
            "notes": forms.Textarea(attrs={"rows": 3, "class": _INPUT_CLASSES}),
        }


class ParcelForm(BoundaryFormMixin, forms.ModelForm):
    boundary_geojson = forms.CharField(widget=forms.HiddenInput, required=True)

    class Meta:
        model = Parcel
        fields = ["name", "parcel_number", "color", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT_CLASSES}),
            "parcel_number": forms.TextInput(attrs={"class": _INPUT_CLASSES}),
            "color": _COLOR_WIDGET,
            "notes": forms.Textarea(attrs={"rows": 3, "class": _INPUT_CLASSES}),
        }


class CropRecordForm(forms.ModelForm):
    class Meta:
        model = CropRecord
        fields = ["crop_name", "variety", "season", "status", "planted_date", "harvest_date",
                   "yield_amount", "yield_unit", "cost", "notes"]
        widgets = {
            "planted_date": forms.DateInput(attrs={"type": "date", "class": _INPUT_CLASSES}),
            "harvest_date": forms.DateInput(attrs={"type": "date", "class": _INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = _INPUT_CLASSES


class SoilSampleForm(forms.ModelForm):
    class Meta:
        model = SoilSample
        fields = ["sample_date", "depth_cm", "ph", "organic_carbon_pct", "nitrogen_ppm",
                   "sand_pct", "silt_pct", "clay_pct", "texture_class", "cec", "notes"]
        widgets = {
            "sample_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.source = SoilSample.Source.MANUAL
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = _INPUT_CLASSES
