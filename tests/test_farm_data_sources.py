"""Farm Settings' key and data-source switches actually govern the syncs.

All four used to be saved and then ignored: the price sync read only the server's
USDA_NASS_API_KEY, and weather and soil always ran. Saving the page for any other
reason also wiped the key, because the password box never sends it back.
"""

from unittest import mock

import pytest
from django.test import override_settings

from apps.accounts.forms import FarmSettingsForm
from apps.accounts.models import FarmSettings
from apps.crops.tasks import usda_api_key
from apps.land import tasks as land_tasks
from tests.factories import FarmFactory, FieldFactory

SETTINGS_URL = "/accounts/farm/settings/"


def settings_post(**overrides):
    data = {"unit_system": "us", "usda_nass_api_key": "", "weather_enabled": "on", "soil_enabled": "on"}
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


@pytest.fixture
def owner_client(farm_client, membership):
    membership.role = "owner"
    membership.save()
    return farm_client


# --- which key the price sync uses -----------------------------------------------------


@pytest.mark.django_db
class TestUsdaApiKey:
    @override_settings(USDA_NASS_API_KEY="")
    def test_no_key_anywhere(self):
        assert usda_api_key() == ""

    @override_settings(USDA_NASS_API_KEY="server-key")
    def test_server_key_is_the_fallback(self):
        assert usda_api_key() == "server-key"

    @override_settings(USDA_NASS_API_KEY="server-key")
    def test_a_farm_key_with_sync_on_is_used(self):
        FarmSettings.objects.create(farm=FarmFactory(), usda_nass_api_key="farm-key", crop_prices_enabled=True)
        assert usda_api_key() == "farm-key"

    @override_settings(USDA_NASS_API_KEY="")
    def test_a_farm_key_with_sync_off_is_not_used(self):
        FarmSettings.objects.create(farm=FarmFactory(), usda_nass_api_key="farm-key", crop_prices_enabled=False)
        assert usda_api_key() == ""

    @override_settings(USDA_NASS_API_KEY="")
    def test_the_oldest_farm_wins(self):
        first, second = FarmFactory(), FarmFactory()
        FarmSettings.objects.create(farm=second, usda_nass_api_key="second", crop_prices_enabled=True)
        FarmSettings.objects.create(farm=first, usda_nass_api_key="first", crop_prices_enabled=True)
        assert usda_api_key() == "first"

    @override_settings(USDA_NASS_API_KEY="")
    def test_sync_skips_without_a_key(self):
        from apps.crops.tasks import sync_crop_prices

        with mock.patch("httpx.Client") as client:
            sync_crop_prices()
        client.assert_not_called()


# --- the settings page keeps the key --------------------------------------------------


@pytest.mark.django_db
class TestSettingsPageKey:
    def _saved(self, farm, key="abc123", enabled=True):
        return FarmSettings.objects.create(farm=farm, usda_nass_api_key=key, crop_prices_enabled=enabled)

    def test_saving_with_a_blank_key_box_keeps_the_key(self, owner_client, farm):
        self._saved(farm)
        with mock.patch("apps.crops.tasks.sync_crop_prices.delay"):
            owner_client.post(SETTINGS_URL, settings_post(unit_system="metric", crop_prices_enabled="on"))
        farm.settings.refresh_from_db()
        assert farm.settings.unit_system == "metric"
        assert farm.settings.usda_nass_api_key == "abc123"

    def test_the_key_can_be_removed(self, owner_client, farm):
        self._saved(farm)
        owner_client.post(SETTINGS_URL, settings_post(clear_usda_nass_api_key="on"))
        farm.settings.refresh_from_db()
        assert farm.settings.usda_nass_api_key == ""

    def test_a_new_key_replaces_the_old_one(self, owner_client, farm):
        self._saved(farm)
        with mock.patch("apps.crops.tasks.sync_crop_prices.delay"):
            owner_client.post(SETTINGS_URL, settings_post(usda_nass_api_key="  newkey  ", crop_prices_enabled="on"))
        farm.settings.refresh_from_db()
        assert farm.settings.usda_nass_api_key == "newkey"

    def test_the_saved_key_is_never_sent_to_the_browser(self, owner_client, farm):
        self._saved(farm, key="secret-key-value")
        body = owner_client.get(SETTINGS_URL).content.decode()
        assert "secret-key-value" not in body
        assert "Remove the saved key" in body

    def test_form_without_a_saved_key_offers_no_remove_box(self, owner_client, farm):
        FarmSettings.objects.create(farm=farm)
        assert "Remove the saved key" not in owner_client.get(SETTINGS_URL).content.decode()

    def test_form_clean_unit(self, farm):
        settings_obj = self._saved(farm)
        form = FarmSettingsForm(settings_post(), instance=settings_obj)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["usda_nass_api_key"] == "abc123"


@pytest.mark.django_db
class TestSettingsPageStartsAPriceSync:
    def test_adding_a_key_with_sync_on_fetches_now(self, owner_client, farm):
        with mock.patch("apps.crops.tasks.sync_crop_prices.delay") as delay:
            owner_client.post(SETTINGS_URL, settings_post(usda_nass_api_key="k", crop_prices_enabled="on"))
        delay.assert_called_once()

    def test_turning_sync_on_with_a_saved_key_fetches_now(self, owner_client, farm):
        FarmSettings.objects.create(farm=farm, usda_nass_api_key="k", crop_prices_enabled=False)
        with mock.patch("apps.crops.tasks.sync_crop_prices.delay") as delay:
            owner_client.post(SETTINGS_URL, settings_post(crop_prices_enabled="on"))
        delay.assert_called_once()

    def test_an_unrelated_save_does_not_fetch(self, owner_client, farm):
        FarmSettings.objects.create(farm=farm, usda_nass_api_key="k", crop_prices_enabled=True)
        with mock.patch("apps.crops.tasks.sync_crop_prices.delay") as delay:
            owner_client.post(SETTINGS_URL, settings_post(unit_system="metric", crop_prices_enabled="on"))
        delay.assert_not_called()

    def test_a_key_with_sync_off_does_not_fetch(self, owner_client, farm):
        with mock.patch("apps.crops.tasks.sync_crop_prices.delay") as delay:
            owner_client.post(SETTINGS_URL, settings_post(usda_nass_api_key="k"))
        delay.assert_not_called()


# --- weather and soil switches ---------------------------------------------------------


@pytest.mark.django_db
class TestWeatherAndSoilSwitches:
    def test_defaults_without_a_settings_row(self, farm):
        sources = FarmSettings.for_farm(farm)
        assert sources.pk is None
        assert (sources.weather_enabled, sources.soil_enabled, sources.crop_prices_enabled) == (True, True, False)

    def test_fan_out_skips_farms_with_weather_off(self):
        on_field = FieldFactory()  # no settings row: weather defaults to on
        off_farm = FarmFactory()
        FarmSettings.objects.create(farm=off_farm, weather_enabled=False)
        FieldFactory(farm=off_farm)

        with mock.patch.object(land_tasks.sync_weather_for_field, "delay") as delay:
            land_tasks.sync_all_weather()
        delay.assert_called_once_with(on_field.id)

    @pytest.mark.parametrize(
        ("task", "flag", "fetcher"),
        [
            ("sync_weather_for_field", "weather_enabled", "apps.land.services.weather.fetch_weather_for_field"),
            ("sync_soil_data_for_field", "soil_enabled", "apps.land.services.soil.fetch_soil_for_field"),
        ],
    )
    def test_field_task_honours_the_switch(self, task, flag, fetcher):
        field = FieldFactory()
        settings_obj = FarmSettings.objects.create(farm=field.farm, **{flag: False})

        with mock.patch(fetcher) as fetch:
            getattr(land_tasks, task)(field.id)
            fetch.assert_not_called()

            setattr(settings_obj, flag, True)
            settings_obj.save()
            getattr(land_tasks, task)(field.id)
            fetch.assert_called_once()

    def test_sync_now_buttons_are_replaced_when_off(self, farm_client, farm):
        FarmSettings.objects.create(farm=farm, weather_enabled=False, soil_enabled=False)
        field = FieldFactory(farm=farm)
        body = farm_client.get(f"/land/fields/{field.pk}/").content.decode()
        assert "Weather sync is off in" in body
        assert "Soil data sync is off in" in body
        assert f"/land/fields/{field.pk}/sync-weather/" not in body
        assert f"/land/fields/{field.pk}/sync-soil/" not in body

    def test_sync_now_buttons_show_by_default(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        body = farm_client.get(f"/land/fields/{field.pk}/").content.decode()
        assert f"/land/fields/{field.pk}/sync-weather/" in body
        assert f"/land/fields/{field.pk}/sync-soil/" in body

    @pytest.mark.parametrize(
        ("path", "flag", "fetcher"),
        [
            ("sync-weather", "weather_enabled", "apps.land.services.weather.fetch_weather_for_field"),
            ("sync-soil", "soil_enabled", "apps.land.services.soil.fetch_soil_for_field"),
        ],
    )
    def test_manual_sync_refuses_when_off(self, farm_client, farm, path, flag, fetcher):
        FarmSettings.objects.create(farm=farm, **{flag: False})
        field = FieldFactory(farm=farm)
        with mock.patch(fetcher) as fetch:
            resp = farm_client.post(f"/land/fields/{field.pk}/{path}/", follow=True)
        fetch.assert_not_called()
        assert "sync is off in Farm Settings" in resp.content.decode()

    def test_sync_all_only_runs_the_sources_that_are_on(self, farm_client, farm):
        FarmSettings.objects.create(farm=farm, weather_enabled=False)
        FieldFactory(farm=farm)
        with (
            mock.patch("apps.land.services.weather.fetch_weather_for_field") as weather,
            mock.patch("apps.land.services.soil.fetch_soil_for_field") as soil,
        ):
            resp = farm_client.post("/land/fields/sync-all/", follow=True)
        weather.assert_not_called()
        soil.assert_called_once()
        assert "Synced soil for 1 field(s)." in resp.content.decode()

    def test_sync_all_button_hidden_when_both_off(self, farm_client, farm):
        FarmSettings.objects.create(farm=farm, weather_enabled=False, soil_enabled=False)
        FieldFactory(farm=farm)
        assert "Sync All Fields" not in farm_client.get("/land/fields/").content.decode()
