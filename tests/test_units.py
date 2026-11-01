"""The per-farm unit setting: what is shown and typed changes, what is stored never does."""

import json
import pathlib
import zipfile
from decimal import Decimal

import pytest

from apps.accounts.models import FarmSettings
from apps.buildings.forms import BuildingForm
from apps.core.units import Units, UnitSystem, units_for
from apps.data_io.backup import export_farm, restore_farm
from apps.land.forms import SoilSampleForm
from apps.land.models import WeatherCache
from apps.livestock.forms import AnimalForm
from apps.livestock.models import Animal
from tests.factories import AnimalFactory, FieldFactory

US, METRIC = Units(UnitSystem.US), Units(UnitSystem.METRIC)


@pytest.fixture
def metric_farm(farm):
    FarmSettings.objects.create(farm=farm, unit_system=UnitSystem.METRIC)
    return farm


class TestFormatting:
    @pytest.mark.parametrize("name,stored,us,metric", [
        ("temperature", 20, "68.0°F", "20.0°C"),
        ("temperature", -17.78, "0.0°F", "-17.8°C"),
        ("rainfall", 25.4, "1.00 in", "25.4 mm"),
        ("wind_speed", 100, "62.1 mph", "100.0 km/h"),
        ("weight", Decimal("100"), "220.5 lb", "100.00 kg"),
        ("soil_depth", 30, "12 in", "30 cm"),
        ("land_area", Decimal("100.00"), "100.00 ac", "40.47 ha"),
        ("floor_area", 1000, "1000 sq ft", "93 m²"),
    ])
    def test_each_measure_in_both_systems(self, name, stored, us, metric):
        assert US.format(name, stored) == us
        assert METRIC.format(name, stored) == metric

    def test_only_a_missing_value_is_a_dash(self):
        assert US.format("rainfall", None) == "—"
        assert US.format("rainfall", 0) == "0.00 in"

    def test_a_small_negative_never_shows_as_minus_zero(self):
        assert METRIC.format("temperature", -0.01) == "0.0°C"


@pytest.mark.django_db
class TestFarmSetting:
    def test_defaults_to_us_with_or_without_a_settings_row(self, farm):
        assert units_for(farm).system == UnitSystem.US
        FarmSettings.objects.create(farm=farm)
        farm.refresh_from_db()
        assert units_for(farm).system == UnitSystem.US

    def test_no_farm_reads_as_us(self):
        assert units_for(None).system == UnitSystem.US

    def test_settings_page_saves_the_choice(self, farm_client, farm):
        resp = farm_client.post("/accounts/farm/settings/", {"unit_system": "metric"})
        assert resp.status_code == 302
        assert FarmSettings.objects.get(farm=farm).unit_system == "metric"
        assert b"Measurement Units" in farm_client.get("/accounts/farm/settings/").content


@pytest.mark.django_db
class TestPages:
    def test_field_page_follows_the_farm_setting(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        WeatherCache.objects.create(
            field=field, date="2026-06-01", temp_max_c=20, temp_min_c=10,
            precipitation_mm=0, wind_speed_max_kmh=100,
        )
        url = f"/land/fields/{field.pk}/"

        page = farm_client.get(url).content.decode()
        assert "68.0°F" in page and "62.1 mph" in page
        # A dry day is a real 0, not missing data.
        assert "0.00 in" in page

        FarmSettings.objects.create(farm=farm, unit_system=UnitSystem.METRIC)
        page = farm_client.get(url).content.decode()
        assert "20.0°C" in page and "100.0 km/h" in page and "0.0 mm" in page
        assert "°F" not in page and "mph" not in page
        assert f"{float(field.acreage) * 0.40468564224:.2f} ha" in page

    def test_map_data_carries_the_formatted_area(self, farm_client, metric_farm):
        FieldFactory(farm=metric_farm)
        feature = farm_client.get("/land/fields/geojson/").json()["features"][0]
        assert feature["properties"]["area"].endswith(" ha")

    def test_animal_weight_is_shown_in_the_farm_unit(self, farm_client, farm):
        animal = AnimalFactory(farm=farm, weight_kg=Decimal("100.00"))
        assert "220.5 lb" in farm_client.get(f"/livestock/{animal.pk}/").content.decode()

    def test_boundary_editor_preview_uses_the_farm_unit(self, farm_client, metric_farm):
        page = farm_client.get("/land/fields/create/").content.decode()
        assert "areaSqM / 10000" in page
        assert '<span id="acreage-value"></span> ha' in page


class TestNoHardcodedUnits:
    def test_templates_show_measurements_through_the_filters(self):
        """A literal unit in a template would ignore the setting. Free-text units
        (bushels, lbs) are user data and arrive through variables, so never match.
        """
        banned = ("°F", "°C", " mph", "km/h", " acres", "}} ac<", "}} kg", "Sq ft", "Square Feet")
        hits = [
            f"{path}: {word}"
            for path in pathlib.Path("apps").glob("*/templates/**/*.html")
            for word in banned
            if word in path.read_text()
        ]
        assert not hits


@pytest.mark.django_db
class TestForms:
    def _animal_data(self, **overrides):
        return {"ear_tag": "A1", "species": "cattle", "gender": "female", "repro_status": "intact", "status": "active", **overrides}

    def test_pounds_are_stored_as_kilograms(self, farm):
        form = AnimalForm(self._animal_data(weight_kg="1200"), farm=farm, units=US)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["weight_kg"] == Decimal("544.31")

    def test_kilograms_pass_through(self, farm):
        form = AnimalForm(self._animal_data(weight_kg="544.31"), farm=farm, units=METRIC)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["weight_kg"] == Decimal("544.31")

    def test_form_labels_and_prefills_in_the_farm_unit(self, farm):
        animal = AnimalFactory(farm=farm, weight_kg=Decimal("100.00"))
        form = AnimalForm(instance=animal, farm=farm, units=US)
        assert form.fields["weight_kg"].label == "Weight (lb)"
        assert 'value="220.5"' in str(form["weight_kg"])

    def test_saving_without_touching_the_weight_keeps_the_stored_number(self, farm):
        """100.03 kg shows as 220.5 lb, which converts back to 100.02 kg."""
        animal = AnimalFactory(farm=farm, weight_kg=Decimal("100.03"))
        form = AnimalForm(instance=animal, farm=farm, units=US)
        data = {name: form[name].value() for name in form.fields if form[name].value() is not None}
        data = {**data, "ear_tag": "RENAMED"}
        bound = AnimalForm(data, instance=animal, farm=farm, units=US)
        assert bound.is_valid(), bound.errors
        bound.save()
        animal = Animal.objects.get(pk=animal.pk)
        assert animal.ear_tag == "RENAMED"
        assert animal.weight_kg == Decimal("100.03")

    def test_clearing_a_weight_clears_it(self, farm):
        animal = AnimalFactory(farm=farm, weight_kg=Decimal("100.00"))
        form = AnimalForm(self._animal_data(weight_kg=""), instance=animal, farm=farm, units=US)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["weight_kg"] is None

    @pytest.mark.parametrize("inches", range(1, 80))
    def test_any_whole_inch_depth_reads_back_the_same(self, inches):
        form = SoilSampleForm({"depth_cm": str(inches)}, units=US)
        assert form.is_valid(), form.errors
        assert US.measure("soil_depth").to_display(form.cleaned_data["depth_cm"]) == inches

    def test_the_default_depth_stays_30_cm_on_a_us_farm(self):
        form = SoilSampleForm(units=US)
        assert 'value="12"' in str(form["depth_cm"])
        bound = SoilSampleForm({"depth_cm": "12"}, units=US)
        assert bound.is_valid(), bound.errors
        assert bound.cleaned_data["depth_cm"] == 30

    def test_floor_area_is_stored_in_square_feet(self):
        form = BuildingForm({"name": "Barn", "building_type": "barn", "square_feet": "100"}, units=METRIC)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["square_feet"] == 1076


@pytest.mark.django_db
class TestBackup:
    def _rewrite_as_format_2(self, source, target):
        with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
            for item in old.namelist():
                content = old.read(item)
                if item == "data.json":
                    data = json.loads(content)
                    for row in data["accounts.FarmSettings"]:
                        del row["unit_system"]
                    content = json.dumps(data).encode()
                if item == "manifest.json":
                    manifest = json.loads(content)
                    manifest["format_version"] = 2
                    manifest["schema"]["accounts.FarmSettings"].remove("unit_system")
                    manifest.pop("data_sha256", None)
                    content = json.dumps(manifest).encode()
                new.writestr(item, content)

    def test_the_setting_survives_a_round_trip(self, metric_farm, user, tmp_path):
        export_farm(metric_farm, tmp_path / "b.zip")
        report = restore_farm(tmp_path / "b.zip", user, farm_name="Restored")
        assert FarmSettings.objects.get(farm=report.farm).unit_system == "metric"

    def test_an_older_backup_restores_as_us_without_a_warning(self, farm, user, tmp_path):
        FarmSettings.objects.create(farm=farm)
        export_farm(farm, tmp_path / "new.zip")
        self._rewrite_as_format_2(tmp_path / "new.zip", tmp_path / "old.zip")
        report = restore_farm(tmp_path / "old.zip", user, farm_name="Restored")
        assert FarmSettings.objects.get(farm=report.farm).unit_system == "us"
        assert not [w for w in report.warnings if "unit_system" in w]
