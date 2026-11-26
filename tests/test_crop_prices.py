"""USDA price sync and the national-vs-state price table.

The sync used to query USDA by display name ("CORN (GRAIN)"), which matched nothing
for 9 of the 19 seeded crops, and saved every series USDA returned over one another
under the same crop and year. The rows below are shaped like real QuickStats data.
"""

import importlib
from decimal import Decimal
from unittest import mock

import httpx
import pytest
from django.apps import apps as django_apps

from apps.accounts.models import FarmSettings
from apps.crops import prices
from apps.crops.models import CropType, MarketPrice
from tests.factories import CropTypeFactory


def row(series, value, year=2025, state="US", period="MARKETING YEAR", unit="$ / BU"):
    national = state == "US"
    return {
        "short_desc": f"{series} - PRICE RECEIVED, MEASURED IN {unit}",
        "Value": value,
        "year": year,
        "state_alpha": state,
        "agg_level_desc": "NATIONAL" if national else "STATE",
        "reference_period_desc": period,
        "unit_desc": unit,
    }


HAY = [
    row("HAY", "160", unit="$ / TON"),
    row("HAY, ALFALFA", "172", unit="$ / TON"),
    row("HAY, (EXCL ALFALFA)", "137", unit="$ / TON"),
    row("HAY, ALFALFA", "180", state="MO", unit="$ / TON"),
    row("HAY, (EXCL ALFALFA)", "113", state="MO", unit="$ / TON"),
]


class TestSelectRows:
    def test_only_the_named_series_is_kept(self):
        entries = prices.select_rows(HAY, "HAY, (EXCL ALFALFA)")
        assert [(e["state"], e["price_per_unit"]) for e in entries] == [("MO", Decimal("113")), ("US", Decimal("137"))]

    def test_marketing_year_beats_calendar_year(self):
        rows = [row("CORN, GRAIN", "4.30", period="YEAR"), row("CORN, GRAIN", "4.16")]
        assert prices.select_rows(rows, "CORN, GRAIN")[0]["price_per_unit"] == Decimal("4.16")
        assert prices.select_rows(list(reversed(rows)), "CORN, GRAIN")[0]["price_per_unit"] == Decimal("4.16")

    def test_calendar_year_is_used_when_it_is_all_there_is(self):
        assert prices.select_rows([row("OATS", "3.20", period="YEAR")], "OATS")[0]["price_per_unit"] == Decimal("3.20")

    @pytest.mark.parametrize("value", ["(D)", "                 (D)", "(NA)", "", "0"])
    def test_withheld_and_zero_values_are_skipped(self, value):
        assert prices.select_rows([row("COTTON, UPLAND", value, state="TX")], "COTTON, UPLAND") == []

    def test_thousands_separators(self):
        assert prices.select_rows([row("RICE", "1,250.5")], "RICE")[0]["price_per_unit"] == Decimal("1250.5")

    def test_a_bare_commodity_matches_a_single_series(self):
        rows = [row("CORN, GRAIN", "4.16"), row("CORN, GRAIN", "4.10", state="IA")]
        assert len(prices.select_rows(rows, "CORN")) == 2

    def test_a_bare_commodity_never_guesses_between_series(self):
        assert prices.select_rows(HAY[1:], "HAY") == []

    def test_unit_comes_from_usda_not_the_catalog(self):
        assert prices.select_rows(HAY, "HAY, ALFALFA")[0]["unit"] == "$/ton"

    def test_series_match_ignores_case_and_padding(self):
        assert len(prices.select_rows(HAY, "  hay, alfalfa ")) == 2

    def test_commodity_of(self):
        assert prices.commodity_of("HAY, (EXCL ALFALFA)") == "HAY"
        assert prices.commodity_of("SWEET CORN") == "SWEET CORN"


class TestFetch:
    def _client(self, status, payload=None):
        response = mock.Mock(status_code=status)
        response.json.return_value = payload or {}
        client = mock.Mock()
        client.get.return_value = response
        return client

    def test_queries_by_commodity(self):
        client = self._client(200, {"data": [row("HAY", "160")]})
        assert prices.fetch("k", "HAY", "STATE", client) == [row("HAY", "160")]
        params = client.get.call_args.kwargs["params"]
        assert (params["commodity_desc"], params["agg_level_desc"], params["key"]) == ("HAY", "STATE", "k")

    def test_400_means_no_data(self):
        assert prices.fetch("k", "CANOLA", "STATE", self._client(400)) == []

    @pytest.mark.parametrize("status", [401, 403, 500, 503])
    def test_other_errors_raise(self, status):
        with pytest.raises(prices.PriceFetchError):
            prices.fetch("k", "HAY", "NATIONAL", self._client(status))

    def test_network_errors_raise(self):
        client = mock.Mock()
        client.get.side_effect = httpx.ConnectTimeout("slow")
        with pytest.raises(prices.PriceFetchError):
            prices.fetch("k", "HAY", "NATIONAL", client)


@pytest.mark.django_db
class TestSyncCrop:
    def _crop(self, code="HAY, ALFALFA"):
        return CropTypeFactory(name="Test Alfalfa", usda_code=code)

    def test_replaces_the_crops_rows(self):
        crop = self._crop()
        MarketPrice.objects.create(crop_type=crop, year=2019, state="US TOTAL", price_per_unit=1, unit="$/x")
        with mock.patch.object(prices, "fetch", side_effect=[HAY[:3], HAY[3:]]):
            assert prices.sync_crop(crop, "k", client=None) == 2

        stored = {(p.state, p.year): p.price_per_unit for p in MarketPrice.objects.filter(crop_type=crop)}
        assert stored == {("US", 2025): Decimal("172"), ("MO", 2025): Decimal("180")}

    def test_a_failed_fetch_keeps_what_was_stored(self):
        crop = self._crop()
        MarketPrice.objects.create(crop_type=crop, year=2024, state="US", price_per_unit=150, unit="$/ton")
        with (
            mock.patch.object(prices, "fetch", side_effect=prices.PriceFetchError("HTTP 503")),
            mock.patch("httpx.Client"),
        ):
            assert prices.sync_all("k") == (0, 0)
        assert MarketPrice.objects.filter(crop_type=crop).count() == 1

    def test_three_decimal_prices_are_kept(self):
        crop = self._crop(code="PEANUTS")
        with mock.patch.object(prices, "fetch", side_effect=[[row("PEANUTS", "0.235", unit="$ / LB")], []]):
            prices.sync_crop(crop, "k", client=None)
        price = MarketPrice.objects.get(crop_type=crop)
        assert price.price_per_unit == Decimal("0.235")
        assert price.price_label == "$0.235/lb"


class TestPriceLabel:
    @pytest.mark.parametrize(
        ("value", "unit", "label"),
        [
            ("4.16", "$/bu", "$4.16/bu"),
            ("4.100", "$/bu", "$4.10/bu"),
            ("0.235", "$/lb", "$0.235/lb"),
            ("157", "$/ton", "$157.00/ton"),
            ("12", "", "$12.00"),
        ],
    )
    def test_label(self, value, unit, label):
        assert MarketPrice(price_per_unit=Decimal(value), unit=unit).price_label == label


@pytest.mark.django_db
class TestSeriesMigration:
    """crops 0008: seeded crops get their series; edited entries are left alone."""

    def _forwards(self):
        module = importlib.import_module("apps.crops.migrations.0008_usda_price_series")
        module.forwards(django_apps, None)

    def test_seeded_crops_get_series(self):
        CropType.objects.filter(name__in=["Corn (Grain)", "Alfalfa Hay", "Cotton", "Corn (Silage)"]).delete()
        CropType.objects.create(name="Corn (Grain)", usda_code="CORN")
        CropType.objects.create(name="Alfalfa Hay", usda_code="HAY")
        CropType.objects.create(name="Cotton", usda_code="COTTON")
        CropType.objects.create(name="Corn (Silage)", usda_code="CORN")
        self._forwards()
        codes = dict(CropType.objects.values_list("name", "usda_code"))
        assert codes["Corn (Grain)"] == "CORN, GRAIN"
        assert codes["Alfalfa Hay"] == "HAY, ALFALFA"
        assert codes["Cotton"] == "COTTON, UPLAND"
        assert codes["Corn (Silage)"] == ""

    def test_an_edited_code_is_left_alone(self):
        CropType.objects.filter(name="Grass Hay").delete()
        CropType.objects.create(name="Grass Hay", usda_code="HAY, OTHER")
        self._forwards()
        assert CropType.objects.get(name="Grass Hay").usda_code == "HAY, OTHER"

    def test_national_rows_are_relabelled(self):
        crop = CropTypeFactory()
        MarketPrice.objects.create(crop_type=crop, year=2024, state="US TOTAL", price_per_unit=4, unit="$/bu")
        self._forwards()
        assert MarketPrice.objects.get(crop_type=crop).state == "US"


@pytest.mark.django_db
class TestCropPagePrices:
    def _crop_with_prices(self):
        crop = CropTypeFactory(name="Priced Hay", usda_code="HAY, ALFALFA")
        for year, us, mo in [(2025, "172", "180"), (2024, "190", None), (2023, "200", "205")]:
            MarketPrice.objects.create(crop_type=crop, year=year, state="US", price_per_unit=us, unit="$/ton")
            if mo:
                MarketPrice.objects.create(crop_type=crop, year=year, state="MO", price_per_unit=mo, unit="$/ton")
        MarketPrice.objects.create(crop_type=crop, year=2025, state="IA", price_per_unit="99", unit="$/ton")
        return crop

    def test_state_column_beside_national(self, farm_client, farm):
        FarmSettings.objects.create(farm=farm, state="MO")
        crop = self._crop_with_prices()
        resp = farm_client.get(f"/crops/types/{crop.pk}/")
        assert [(y, n.state, s.state if s else None) for y, n, s in resp.context["price_rows"]] == [
            (2025, "US", "MO"), (2024, "US", None), (2023, "US", "MO"),
        ]
        body = resp.content.decode()
        assert "Missouri" in body
        assert "$180.00/ton" in body
        assert "$99.00" not in body  # another state's price never shows

    def test_without_a_state_only_national_shows_with_a_hint(self, farm_client, farm):
        crop = self._crop_with_prices()
        resp = farm_client.get(f"/crops/types/{crop.pk}/")
        assert all(s is None for _, _, s in resp.context["price_rows"])
        assert "Choose your state in" in resp.content.decode()

    def test_a_state_with_no_usda_figure_says_so(self, farm_client, farm):
        FarmSettings.objects.create(farm=farm, state="AK")
        crop = self._crop_with_prices()
        assert "USDA publishes no Alaska price for this crop" in farm_client.get(f"/crops/types/{crop.pk}/").content.decode()

    def test_a_crop_with_no_series(self, farm_client):
        crop = CropTypeFactory(name="Silage", usda_code="")
        assert "has no USDA series" in farm_client.get(f"/crops/types/{crop.pk}/").content.decode()


@pytest.mark.django_db
class TestStateSetting:
    def test_saved_from_the_settings_page(self, farm_client, farm, membership):
        membership.role = "owner"
        membership.save()
        farm_client.post("/accounts/farm/settings/", {
            "unit_system": "us", "state": "MO", "usda_nass_api_key": "", "weather_enabled": "on", "soil_enabled": "on",
        })
        assert FarmSettings.objects.get(farm=farm).state == "MO"

    def test_survives_a_backup(self, farm, user, tmp_path):
        from apps.data_io.backup import export_farm, restore_farm

        FarmSettings.objects.create(farm=farm, state="MO")
        export_farm(farm, tmp_path / "b.zip")
        report = restore_farm(tmp_path / "b.zip", user, farm_name="Restored")
        assert FarmSettings.objects.get(farm=report.farm).state == "MO"

    def test_a_format_3_backup_restores_with_no_state(self, farm, user, tmp_path):
        import json
        import zipfile

        from apps.data_io.backup import export_farm, restore_farm

        FarmSettings.objects.create(farm=farm, state="MO")
        export_farm(farm, tmp_path / "new.zip")
        with zipfile.ZipFile(tmp_path / "new.zip") as old, zipfile.ZipFile(tmp_path / "old.zip", "w") as new:
            for item in old.namelist():
                content = old.read(item)
                if item == "data.json":
                    data = json.loads(content)
                    for settings_row in data["accounts.FarmSettings"]:
                        del settings_row["state"]
                    content = json.dumps(data).encode()
                elif item == "manifest.json":
                    manifest = json.loads(content)
                    manifest["format_version"] = 3
                    manifest["schema"]["accounts.FarmSettings"].remove("state")
                    manifest.pop("data_sha256", None)
                    content = json.dumps(manifest).encode()
                new.writestr(item, content)

        report = restore_farm(tmp_path / "old.zip", user, farm_name="Restored")
        assert FarmSettings.objects.get(farm=report.farm).state == ""
        assert not [w for w in report.warnings if "state" in w]
