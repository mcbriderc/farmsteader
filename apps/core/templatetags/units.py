"""Render a stored measurement in the farm's units: ``{{ w.temp_max_c|temperature:units }}``.

``units`` comes from the context processor. Every filter includes the unit label
and renders a missing value as a dash. Only a missing value: ``|default`` would
also blank a real 0, which is how dry days used to show no rainfall.
"""

from django import template

register = template.Library()


def _measurement_filter(name):
    def render(stored, units):
        return units.format(name, stored)

    register.filter(name, render)


for _name in ("temperature", "rainfall", "wind_speed", "weight", "soil_depth", "land_area", "floor_area"):
    _measurement_filter(_name)
