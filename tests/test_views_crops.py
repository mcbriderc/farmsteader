import pytest

from apps.crops.models import CropType, HarvestRecord
from apps.land.models import CropRecord
from tests.factories import (
    CropRecordFactory,
    CropTypeFactory,
    FieldFactory,
    HarvestRecordFactory,
)


@pytest.mark.django_db
class TestCropTypeViews:
    def test_list(self, farm_client):
        CropTypeFactory()
        resp = farm_client.get("/crops/types/")
        assert resp.status_code == 200

    def test_detail(self, farm_client, farm):
        ct = CropTypeFactory()
        resp = farm_client.get(f"/crops/types/{ct.pk}/")
        assert resp.status_code == 200

    def test_create_get(self, farm_client):
        resp = farm_client.get("/crops/types/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client):
        resp = farm_client.post("/crops/types/add/", {
            "name": "Buckwheat",
            "category": "Grain",
            "default_unit": "bushels",
        })
        assert resp.status_code == 302
        assert CropType.objects.filter(name="Buckwheat").exists()

    def test_edit(self, farm_client):
        ct = CropTypeFactory(name="Old Crop")
        resp = farm_client.post(f"/crops/types/{ct.pk}/edit/", {
            "name": "New Crop",
            "category": "Grain",
            "default_unit": "bushels",
        })
        assert resp.status_code == 302
        ct.refresh_from_db()
        assert ct.name == "New Crop"

    def test_delete(self, farm_client):
        ct = CropTypeFactory()
        resp = farm_client.post(f"/crops/types/{ct.pk}/delete/")
        assert resp.status_code == 302
        assert not CropType.objects.filter(pk=ct.pk).exists()


@pytest.mark.django_db
class TestCropRecordListView:
    """The cross-field view of plantings.

    CropRecord is a land model reachable only from its field, so before this
    view existed a crop seeded on a field was invisible from the Crops section.
    Read-only by design: the record hangs off a Field, so it is still created
    and edited there.
    """

    def test_list_requires_login(self, client):
        resp = client.get("/crops/records/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        CropRecordFactory(farm=farm, field=FieldFactory(farm=farm))
        resp = farm_client.get("/crops/records/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        own = CropRecordFactory(farm=farm, field=FieldFactory(farm=farm))
        other = CropRecordFactory()
        resp = farm_client.get("/crops/records/")
        pks = [r.pk for r in resp.context["records"]]
        assert own.pk in pks
        assert other.pk not in pks

    def test_filter_by_status(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        seeded = CropRecordFactory(farm=farm, field=field, status=CropRecord.Status.SEEDED)
        planned = CropRecordFactory(farm=farm, field=field, status=CropRecord.Status.PLANNED)
        resp = farm_client.get("/crops/records/?status=seeded")
        pks = [r.pk for r in resp.context["records"]]
        assert pks == [seeded.pk]
        assert planned.pk not in pks

    def test_filter_by_season(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        spring = CropRecordFactory(farm=farm, field=field, season="2026-Spring")
        fall = CropRecordFactory(farm=farm, field=field, season="2026-Fall")
        resp = farm_client.get("/crops/records/?season=2026-Fall")
        pks = [r.pk for r in resp.context["records"]]
        assert pks == [fall.pk]
        assert spring.pk not in pks

    def test_search_matches_crop_and_variety(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        beans = CropRecordFactory(farm=farm, field=field, crop_type=CropTypeFactory(name="Test Soybeans"))
        variety = CropRecordFactory(farm=farm, field=field, crop_type=CropTypeFactory(name="Test Corn"),
                                    variety="Soybean Mix")
        CropRecordFactory(farm=farm, field=field, crop_type=CropTypeFactory(name="Test Oats"), variety="")
        pks = [r.pk for r in farm_client.get("/crops/records/?q=soybean").context["records"]]
        assert set(pks) == {beans.pk, variety.pk}

    def test_season_choices_survive_a_season_filter(self, farm_client, farm):
        """The dropdown is built from the unfiltered queryset.

        Built from the filtered one, picking a season would leave that season as
        the only option and there would be no way back to another.
        """
        field = FieldFactory(farm=farm)
        CropRecordFactory(farm=farm, field=field, season="2026-Spring")
        CropRecordFactory(farm=farm, field=field, season="2026-Fall")
        resp = farm_client.get("/crops/records/?season=2026-Fall")
        assert set(resp.context["seasons"]) == {"2026-Spring", "2026-Fall"}

    def test_other_farm_seasons_are_not_offered(self, farm_client, farm):
        CropRecordFactory(farm=farm, field=FieldFactory(farm=farm), season="2026-Spring")
        CropRecordFactory(season="1999-Winter")
        resp = farm_client.get("/crops/records/")
        assert set(resp.context["seasons"]) == {"2026-Spring"}


@pytest.mark.django_db
class TestHarvestRecordViews:
    def test_list_requires_login(self, client):
        resp = client.get("/crops/harvests/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        HarvestRecordFactory(farm=farm)
        resp = farm_client.get("/crops/harvests/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        own = HarvestRecordFactory(farm=farm)
        other = HarvestRecordFactory()
        resp = farm_client.get("/crops/harvests/")
        pks = [h.pk for h in resp.context["harvests"]]
        assert own.pk in pks
        assert other.pk not in pks

    def test_create_get(self, farm_client):
        resp = farm_client.get("/crops/harvests/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        ct = CropTypeFactory()
        resp = farm_client.post("/crops/harvests/add/", {
            "field": field.pk,
            "crop_type": ct.pk,
            "harvest_date": "2026-09-01",
            "yield_amount": "300",
            "yield_unit": "bushels",
            "cost": "500.00",
        })
        assert resp.status_code == 302
        assert HarvestRecord.objects.filter(farm=farm, yield_amount=300).exists()

    def test_edit(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        record = HarvestRecordFactory(farm=farm, field=field, yield_amount=200)
        resp = farm_client.post(f"/crops/harvests/{record.pk}/edit/", {
            "field": field.pk,
            "crop_type": record.crop_type.pk,
            "harvest_date": record.harvest_date,
            "yield_amount": "350",
            "yield_unit": record.yield_unit,
            "cost": "600.00",
        })
        assert resp.status_code == 302
        record.refresh_from_db()
        assert record.yield_amount == 350

    def test_delete(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        record = HarvestRecordFactory(farm=farm, field=field)
        resp = farm_client.post(f"/crops/harvests/{record.pk}/delete/")
        assert resp.status_code == 302
        assert not HarvestRecord.objects.filter(pk=record.pk).exists()

    def test_detail_other_farm_returns_404(self, farm_client):
        other = HarvestRecordFactory()
        resp = farm_client.post(f"/crops/harvests/{other.pk}/delete/")
        assert resp.status_code == 404
