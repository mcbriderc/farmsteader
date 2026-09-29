from unittest.mock import MagicMock, patch

import pytest

from apps.land.models import CropRecord, SoilSample
from tests.factories import CropRecordFactory, FieldFactory, SoilSampleFactory


@pytest.mark.django_db
class TestFieldEditAndMap:
    def test_field_edit_get(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.get(f"/land/fields/{field.pk}/edit/")
        assert resp.status_code == 200

    def test_field_map(self, farm_client, farm):
        FieldFactory(farm=farm)
        resp = farm_client.get("/land/fields/map/")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestCropRecordViews:
    def test_create_get(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.get(f"/land/fields/{field.pk}/crops/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.post(f"/land/fields/{field.pk}/crops/add/", {
            "crop_name": "Corn",
            "season": "2026-Spring",
            "status": "planned",
            "cost": "0.00",
        })
        assert resp.status_code == 302
        assert CropRecord.objects.filter(farm=farm, field=field, crop_name="Corn").exists()

    def test_edit_get(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        record = CropRecordFactory(farm=farm, field=field)
        resp = farm_client.get(f"/land/fields/{field.pk}/crops/{record.pk}/edit/")
        assert resp.status_code == 200

    def test_edit_post(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        record = CropRecordFactory(farm=farm, field=field, status="planned")
        resp = farm_client.post(f"/land/fields/{field.pk}/crops/{record.pk}/edit/", {
            "crop_name": record.crop_name,
            "season": record.season,
            "status": "seeded",
            "cost": "0.00",
        })
        assert resp.status_code == 302
        record.refresh_from_db()
        assert record.status == "seeded"

    def test_other_farm_crop_record_returns_404(self, farm_client, farm):
        other_field = FieldFactory()
        record = CropRecordFactory(field=other_field)
        resp = farm_client.get(f"/land/fields/{other_field.pk}/crops/{record.pk}/edit/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestSoilSampleViews:
    def test_create_get(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.get(f"/land/fields/{field.pk}/soil/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.post(f"/land/fields/{field.pk}/soil/add/", {
            "source": "manual",
            "depth_cm": "30",
            "ph": "6.8",
        })
        assert resp.status_code == 302
        assert SoilSample.objects.filter(farm=farm, field=field).exists()

    def test_other_farm_field_returns_404(self, farm_client):
        other_field = FieldFactory()
        resp = farm_client.get(f"/land/fields/{other_field.pk}/soil/add/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestFieldSyncSoil:
    def test_sync_soil_success(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        mock_sample = MagicMock()
        with patch("apps.land.services.soil.fetch_soil_for_field", return_value=mock_sample) as mock_fetch:
            resp = farm_client.post(f"/land/fields/{field.pk}/sync-soil/")
        assert resp.status_code == 302
        mock_fetch.assert_called_once_with(field)

    def test_sync_soil_no_data_returns_warning(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        with patch("apps.land.services.soil.fetch_soil_for_field", return_value=None):
            resp = farm_client.post(f"/land/fields/{field.pk}/sync-soil/")
        assert resp.status_code == 302
        messages = list(resp.wsgi_request._messages)
        assert any("No soil data" in str(m) for m in messages)

    def test_sync_soil_other_farm_returns_404(self, farm_client):
        other_field = FieldFactory()
        resp = farm_client.post(f"/land/fields/{other_field.pk}/sync-soil/")
        assert resp.status_code == 404

    def test_sync_soil_requires_post(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.get(f"/land/fields/{field.pk}/sync-soil/")
        assert resp.status_code == 405


@pytest.mark.django_db
class TestSyncAllFields:
    def test_syncs_weather_and_soil_for_each_field(self, farm_client, farm):
        fields = [FieldFactory(farm=farm), FieldFactory(farm=farm)]
        with (
            patch("apps.land.services.weather.fetch_weather_for_field") as mock_weather,
            patch("apps.land.services.soil.fetch_soil_for_field") as mock_soil,
        ):
            resp = farm_client.post("/land/fields/sync-all/")
        assert resp.status_code == 302
        assert mock_weather.call_count == 2
        assert mock_soil.call_count == 2
        synced_fields = {call.args[0] for call in mock_weather.call_args_list}
        assert synced_fields == set(fields)

    def test_does_not_sync_other_farm_fields(self, farm_client, farm):
        FieldFactory(farm=farm)
        FieldFactory()  # other farm
        with (
            patch("apps.land.services.weather.fetch_weather_for_field") as mock_weather,
            patch("apps.land.services.soil.fetch_soil_for_field") as mock_soil,
        ):
            farm_client.post("/land/fields/sync-all/")
        assert mock_weather.call_count == 1
        assert mock_soil.call_count == 1

    def test_sync_all_no_fields_redirects(self, farm_client):
        with (
            patch("apps.land.services.weather.fetch_weather_for_field") as mock_weather,
            patch("apps.land.services.soil.fetch_soil_for_field") as mock_soil,
        ):
            resp = farm_client.post("/land/fields/sync-all/")
        assert resp.status_code == 302
        mock_weather.assert_not_called()
        mock_soil.assert_not_called()

    def test_sync_all_partial_failure_shows_warning(self, farm_client, farm):
        FieldFactory(farm=farm)
        with (
            patch("apps.land.services.weather.fetch_weather_for_field", side_effect=Exception("boom")),
            patch("apps.land.services.soil.fetch_soil_for_field"),
        ):
            resp = farm_client.post("/land/fields/sync-all/")
        assert resp.status_code == 302
        msgs = [str(m) for m in resp.wsgi_request._messages]
        assert any("failed" in m for m in msgs)

    def test_sync_all_requires_post(self, farm_client):
        resp = farm_client.get("/land/fields/sync-all/")
        assert resp.status_code == 405
