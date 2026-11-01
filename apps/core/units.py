"""Measurement units: what a farm sees and types, versus what is stored.

Stored values never change with the farm's preference. Each column keeps the one
unit its name says (temp_max_c, weight_kg, acreage, square_feet), and CSV and
backup files carry those same stored values, so flipping the setting cannot
alter data and a file means the same thing whichever farm reads it.

Yield, feed, inventory and produce quantities are not here on purpose: their
unit is a free-text label the user chose ("bushels", "bales"), and market prices
are quoted per bushel or hundredweight whatever the reader's system.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import models


class UnitSystem(models.TextChoices):
    US = "us", "US (acres, °F, inches, pounds)"
    METRIC = "metric", "Metric (hectares, °C, millimetres, kilograms)"


@dataclass(frozen=True)
class Measure:
    """How one quantity is shown: ``displayed = stored * factor + offset``."""

    label: str
    decimals: int
    factor: float = 1
    offset: float = 0

    def to_display(self, stored):
        # Adding 0.0 turns the -0.0 that round() can return into plain 0.0.
        return round(float(stored) * self.factor + self.offset, self.decimals) + 0.0

    def to_stored(self, displayed):
        return (float(displayed) - self.offset) / self.factor

    def format(self, stored):
        if stored is None:
            return "—"
        value = f"{self.to_display(stored):.{self.decimals}f}"
        return f"{value}{self.label}" if self.label.startswith("°") else f"{value} {self.label}"


_MEASURES = {
    UnitSystem.US: {
        "temperature": Measure("°F", 1, factor=9 / 5, offset=32),
        "rainfall": Measure("in", 2, factor=1 / 25.4),
        "wind_speed": Measure("mph", 1, factor=1 / 1.609344),
        "weight": Measure("lb", 1, factor=2.20462262185),
        "soil_depth": Measure("in", 0, factor=1 / 2.54),
        "land_area": Measure("ac", 2),
        "floor_area": Measure("sq ft", 0),
    },
    UnitSystem.METRIC: {
        "temperature": Measure("°C", 1),
        "rainfall": Measure("mm", 1),
        "wind_speed": Measure("km/h", 1),
        "weight": Measure("kg", 2),
        "soil_depth": Measure("cm", 0),
        "land_area": Measure("ha", 2, factor=0.40468564224),
        "floor_area": Measure("m²", 0, factor=0.09290304),
    },
}


class Units:
    """One farm's unit system. Templates get it as ``units``, for the filters in
    ``templatetags/units.py``; views use it directly: ``units.format("land_area", x)``.
    """

    def __init__(self, system=UnitSystem.US):
        self.system = UnitSystem(system)
        self.is_metric = self.system == UnitSystem.METRIC

    def measure(self, name):
        return _MEASURES[self.system][name]

    def format(self, name, stored):
        return self.measure(name).format(stored)

    @property
    def land_area_label(self):
        return self.measure("land_area").label

    @property
    def land_area_heading(self):
        return "Area" if self.is_metric else "Acreage"

    @property
    def sq_m_per_land_area(self):
        """For the boundary editor's client-side preview, which measures in m²."""
        return "10000" if self.is_metric else "4046.8564224"


def units_for(farm):
    """The farm's Units. A farm has no settings row until its settings page is
    first opened, and there is no farm at all on the account pages: both read as US.
    """
    settings = getattr(farm, "settings", None)
    return Units(settings.unit_system) if settings else Units()


class UnitFieldsMixin:
    """For a ModelForm whose fields are stored in one unit but typed in the farm's.

    ``unit_fields`` maps a field name to ``(measure name, label)``. The field keeps
    its model name, so ``weight_kg`` holds pounds while on a US farm's form; the
    value is converted back in ``clean()``, before the instance is built.

    An untouched value keeps its stored number rather than being converted back:
    display rounding loses precision (31 cm shows as 12 in, which is 30 cm), and
    editing an animal's name must not quietly change its weight.
    """

    unit_fields = {}

    def __init__(self, *args, units=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.units = units or Units()
        self._stored_values = {}
        for name, (measure_name, label) in self.unit_fields.items():
            field, measure = self.fields[name], self.units.measure(measure_name)
            field.label = f"{label} ({measure.label})"
            field.help_text = ""
            stored = self.get_initial_for_field(field, name)
            self._stored_values[name] = stored
            if stored is not None:
                self.initial[name] = self._displayed_initial(field, measure, stored)

    @staticmethod
    def _displayed_initial(field, measure, stored):
        displayed = measure.to_display(stored)
        return int(displayed) if measure.decimals == 0 else Decimal(f"{displayed:.{measure.decimals}f}")

    def clean(self):
        cleaned = super().clean()
        for name, (measure_name, _) in self.unit_fields.items():
            value = cleaned.get(name)
            if value is None:
                continue
            if name not in self.changed_data:
                cleaned[name] = self._stored_values[name]
                continue
            stored = self.units.measure(measure_name).to_stored(value)
            places = getattr(self.fields[name], "decimal_places", None)
            cleaned[name] = round(stored) if places is None else round(Decimal(str(stored)), places)
        return cleaned
