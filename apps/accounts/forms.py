from django import forms
from django.contrib.auth.forms import UserCreationForm

from apps.crops.constants import COMMODITY_TICKERS

from .models import Farm, FarmSettings, FarmUser

TICKER_CHOICES = [(c["ticker"], c["name"]) for c in COMMODITY_TICKERS]


class FarmUserRegistrationForm(UserCreationForm):
    farm_name = forms.CharField(
        max_length=200,
        help_text="Name of your farm. You can add more farms later.",
    )

    class Meta:
        model = FarmUser
        fields = ["username", "email", "first_name", "last_name"]

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            farm = Farm.objects.create(name=self.cleaned_data["farm_name"])
            farm.memberships.create(user=user, role="owner")
        return user


INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class FarmSettingsForm(forms.ModelForm):
    visible_tickers = forms.MultipleChoiceField(
        choices=TICKER_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Visible commodity prices",
        help_text="Select up to 6 markets to pin on the dashboard. Leave all unchecked to show all.",
    )

    class Meta:
        model = FarmSettings
        fields = [
            "unit_system",
            "state",
            "usda_nass_api_key",
            "weather_enabled",
            "soil_enabled",
            "crop_prices_enabled",
            "visible_tickers",
        ]
        widgets = {
            # The saved key is never sent back to the browser, so a blank box means
            # "keep it", not "delete it" -- see clean(). It used to be wiped every
            # time the page was saved for any other reason, such as a units change.
            "usda_nass_api_key": forms.PasswordInput(attrs={"autocomplete": "off"}),
        }

    clear_usda_nass_api_key = forms.BooleanField(required=False, label="Remove the saved key")

    def clean(self):
        cleaned = super().clean()
        key = (cleaned.get("usda_nass_api_key") or "").strip()
        if cleaned.get("clear_usda_nass_api_key"):
            key = ""
        elif not key:
            key = self.saved_usda_key
        cleaned["usda_nass_api_key"] = key
        return cleaned

    def clean_visible_tickers(self):
        tickers = self.cleaned_data.get("visible_tickers", [])
        if len(tickers) > 6:
            raise forms.ValidationError("Select at most 6 commodities.")
        return tickers

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Read before validation copies the submitted values onto the instance.
        self.saved_usda_key = self.instance.usda_nass_api_key
        if self.saved_usda_key:
            self.fields["usda_nass_api_key"].widget.attrs["placeholder"] = "Saved -- leave blank to keep it"
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs["class"] = "rounded border-gray-300 text-farm-600 focus:ring-farm-500 h-5 w-5"
            elif not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
