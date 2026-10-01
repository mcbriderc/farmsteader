"""Plantings (land.CropRecord) linked to the crop catalog, and harvests linked to plantings.

The database migration itself is covered in test_migration_link_plantings_harvests.
These cover everything around it: the forms that keep a harvest consistent with
its planting, yield totals, the catalog delete protection, and the two ways old
data comes back in -- a backup made by 0.5.0 and a CSV exported by 0.5.0.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.crops.models import CropType, HarvestRecord
from apps.data_io.backup import MOVED_YIELD_NOTE, export_farm, restore_farm
from apps.land.models import CropRecord

from .factories import (
    CropRecordFactory,
    CropTypeFactory,
    FieldFactory,
    HarvestRecordFactory,
    UserFactory,
)
from .test_backup import do_round_trip, read_archive, rewrite_archive
from .test_views_data_io import csv_file


@pytest.fixture
def corn(db):
    return CropTypeFactory(name="Test Corn", default_unit="bushels")


@pytest.fixture
def planting(farm, corn):
    return CropRecordFactory(farm=farm, field=FieldFactory(farm=farm, name="North"), crop_type=corn,
                             season="2026", variety="P1197")


def harvest_post(**overrides):
    data = {"harvest_date": "2026-10-01", "yield_amount": "100", "yield_unit": "bushels", "cost": "0"}
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


@pytest.mark.django_db
class TestHarvestForm:
    def test_choosing_a_planting_fills_field_and_crop(self, farm_client, farm, planting):
        resp = farm_client.post(reverse("crops:harvest_create"), harvest_post(planting=planting.pk))

        assert resp.status_code == 302
        h = HarvestRecord.objects.get(farm=farm)
        assert (h.planting, h.field, h.crop_type) == (planting, planting.field, planting.crop_type)

    def test_a_field_that_disagrees_with_the_planting_is_rejected(self, farm_client, farm, planting):
        elsewhere = FieldFactory(farm=farm, name="South")
        resp = farm_client.post(reverse("crops:harvest_create"),
                                harvest_post(planting=planting.pk, field=elsewhere.pk))

        assert resp.status_code == 200
        assert "The planting is on North" in resp.content.decode()
        assert not HarvestRecord.objects.exists()

    def test_a_crop_that_disagrees_with_the_planting_is_rejected(self, farm_client, planting):
        resp = farm_client.post(reverse("crops:harvest_create"),
                                harvest_post(planting=planting.pk, crop_type=CropTypeFactory().pk))

        assert resp.status_code == 200
        assert not HarvestRecord.objects.exists()

    def test_without_a_planting_field_and_crop_are_required(self, farm_client):
        resp = farm_client.post(reverse("crops:harvest_create"), harvest_post())

        body = resp.content.decode()
        assert "Choose a field, or the planting" in body
        assert "Choose a crop, or the planting" in body

    def test_unlinked_harvest_still_works(self, farm_client, farm, corn):
        field = FieldFactory(farm=farm)
        resp = farm_client.post(reverse("crops:harvest_create"),
                                harvest_post(field=field.pk, crop_type=corn.pk))

        assert resp.status_code == 302
        assert HarvestRecord.objects.get(farm=farm).planting is None

    def test_another_farms_planting_cannot_be_chosen(self, farm_client, other_farm, corn):
        theirs = CropRecordFactory(farm=other_farm, crop_type=corn)
        resp = farm_client.post(reverse("crops:harvest_create"), harvest_post(planting=theirs.pk))

        assert resp.status_code == 200
        assert not HarvestRecord.objects.exists()

    def test_record_harvest_link_prefills_from_the_planting(self, farm_client, planting):
        form = farm_client.get(reverse("crops:harvest_create"), {"planting": planting.pk}).context["form"]

        assert form.initial["planting"] == planting
        assert form.initial["field"] == planting.field
        assert form.initial["crop_type"] == planting.crop_type

    def test_record_harvest_link_ignores_another_farms_planting(self, farm_client, other_farm, corn):
        theirs = CropRecordFactory(farm=other_farm, crop_type=corn)
        form = farm_client.get(reverse("crops:harvest_create"), {"planting": theirs.pk}).context["form"]

        assert "planting" not in form.initial


@pytest.mark.django_db
class TestYield:
    def test_yield_is_summed_per_unit_from_harvests(self, farm, planting):
        for amount, unit in (("120.5", "bales"), ("80", "bales"), ("3", "tons")):
            HarvestRecordFactory(farm=farm, field=planting.field, crop_type=planting.crop_type,
                                 planting=planting, yield_amount=Decimal(amount), yield_unit=unit)

        assert planting.yield_totals() == [("bales", Decimal("200.50")), ("tons", Decimal("3"))]

    def test_crop_records_page_shows_yield_and_record_harvest(self, farm_client, farm, planting):
        HarvestRecordFactory(farm=farm, field=planting.field, crop_type=planting.crop_type,
                             planting=planting, yield_amount=Decimal("1500"), yield_unit="bushels")

        body = farm_client.get(reverse("crops:crop_record_list")).content.decode()

        assert "1500.00 bushels" in body
        assert f"?planting={planting.pk}" in body

    def test_deleting_a_harvest_never_deletes_its_planting(self, farm, planting):
        h = HarvestRecordFactory(farm=farm, field=planting.field, crop_type=planting.crop_type, planting=planting)
        h.delete()
        assert CropRecord.objects.filter(pk=planting.pk).exists()

    def test_deleting_a_planting_keeps_its_harvests_unlinked(self, farm, planting):
        h = HarvestRecordFactory(farm=farm, field=planting.field, crop_type=planting.crop_type, planting=planting)
        planting.delete()
        h.refresh_from_db()
        assert h.planting is None


@pytest.mark.django_db
class TestCatalogProtection:
    """The catalog is shared by every farm; deleting an entry used to CASCADE."""

    def test_crop_type_used_by_another_farm_cannot_be_deleted(self, farm_client, other_farm, corn):
        theirs = HarvestRecordFactory(farm=other_farm, crop_type=corn)

        resp = farm_client.post(reverse("crops:crop_type_delete", args=[corn.pk]), follow=True)

        assert CropType.objects.filter(pk=corn.pk).exists()
        assert HarvestRecord.objects.filter(pk=theirs.pk).exists()
        assert "cannot be deleted" in resp.content.decode()

    def test_unused_crop_type_still_deletes(self, farm_client):
        spare = CropTypeFactory(name="Spare")
        farm_client.post(reverse("crops:crop_type_delete", args=[spare.pk]))
        assert not CropType.objects.filter(pk=spare.pk).exists()


@pytest.mark.django_db
class TestBackups:
    def test_round_trip_keeps_the_planting_link(self, farm, planting, tmp_path):
        HarvestRecordFactory(farm=farm, field=planting.field, crop_type=planting.crop_type, planting=planting)

        report = do_round_trip(farm, tmp_path)

        restored = HarvestRecord.objects.get(farm=report.farm)
        assert restored.planting.farm == report.farm
        assert restored.planting.crop_type == planting.crop_type
        assert restored.planting.variety == "P1197"

    def test_a_backup_made_by_0_5_0_restores_and_is_upgraded(self, farm, tmp_path):
        """Rewrite a current archive into the format-1 shape 0.5.0 wrote, then restore it."""
        field = FieldFactory(farm=farm, name="North")
        soy = CropType.objects.get(name="Soybeans")
        p_match = CropRecordFactory(farm=farm, field=field, crop_type=soy, season="2025",
                                    planted_date=date(2025, 5, 1))
        p_yield = CropRecordFactory(farm=farm, field=field, crop_type=soy, season="2024",
                                    planted_date=date(2025, 6, 1))
        lone = HarvestRecordFactory(farm=farm, field=field, crop_type=soy, harvest_date=date(2025, 10, 1))
        src = tmp_path / "current.zip"
        export_farm(farm, src)
        manifest, data = read_archive(src)

        # Turn it into what 0.5.0 wrote: free-text names, yields on plantings, no link.
        manifest["format_version"] = 1
        manifest["schema"]["land.CropRecord"] = [
            n for n in manifest["schema"]["land.CropRecord"] if n != "crop_type"
        ] + ["crop_name", "harvest_date", "yield_amount", "yield_unit"]
        manifest["schema"]["crops.HarvestRecord"].remove("planting")
        for row in data["land.CropRecord"]:
            row["crop_name"] = " soybeans " if row["id"] == p_match.pk else "Purple Kale"
            del row["crop_type"]
            row.update(harvest_date=None, yield_amount=None, yield_unit="bushels")
            if row["id"] == p_yield.pk:
                row.update(harvest_date="2024-09-30", yield_amount="42.00", yield_unit="")
        for row in data["crops.HarvestRecord"]:
            del row["planting"]
        old = rewrite_archive(src, tmp_path / "from-0.5.0.zip", manifest=manifest, data=data)

        report = restore_farm(old, UserFactory())

        plantings = {p.season: p for p in CropRecord.objects.filter(farm=report.farm)}
        assert plantings["2025"].crop_type.name == "Soybeans"   # case/space-insensitive match
        assert plantings["2024"].crop_type.name == "Purple Kale"  # unmatched -> added to catalog
        moved = HarvestRecord.objects.get(farm=report.farm, planting=plantings["2024"])
        assert (moved.harvest_date, moved.yield_amount) == (date(2024, 9, 30), Decimal("42.00"))
        assert moved.notes.startswith(MOVED_YIELD_NOTE)
        # The pre-existing harvest is linked: one soybean planting on North planted before it.
        original = HarvestRecord.objects.get(farm=report.farm, harvest_date=lone.harvest_date)
        assert original.planting == plantings["2025"]
        assert any("older FarmSteader" in w for w in report.warnings)

    def test_a_new_backup_is_refused_by_an_older_format(self, farm, tmp_path):
        """Format 2 tells a 0.5.0 install (which reads format 1) to upgrade first."""
        manifest = export_farm(farm, tmp_path / "b.zip")
        assert manifest["format_version"] == 2


@pytest.mark.django_db
class TestCsv:
    def test_harvest_export_names_its_planting(self, farm_client, farm, planting):
        HarvestRecordFactory(farm=farm, field=planting.field, crop_type=planting.crop_type, planting=planting)

        body = farm_client.get("/data/export/harvest_records/?format=csv").content.decode()

        assert "North | Test Corn | 2026 | P1197" in body

    def test_harvest_import_resolves_the_planting(self, farm_client, farm, planting):
        csv = ("field_name,crop_type,planting,harvest_date,yield_amount,yield_unit\n"
               "North,test corn,North | Test Corn | 2026 | P1197,2026-10-01,77,bushels\n")
        farm_client.post("/data/import/harvest_records/", {"file": csv_file(csv), "confirm": "1"})

        assert HarvestRecord.objects.get(farm=farm).planting == planting

    def test_harvest_import_rejects_a_planting_that_does_not_match(self, farm_client, farm, planting):
        csv = ("field_name,crop_type,planting,harvest_date,yield_amount,yield_unit\n"
               "North,Test Corn,North | Test Corn | 1999,2026-10-01,77,bushels\n")
        resp = farm_client.post("/data/import/harvest_records/", {"file": csv_file(csv), "confirm": "1"})

        assert not HarvestRecord.objects.filter(farm=farm).exists()
        assert resp.context.get("errors")

    def test_planting_import_rejects_an_unknown_crop(self, farm_client, farm):
        FieldFactory(farm=farm, name="North")
        csv = "field_name,crop_type,season,status\nNorth,Dragonfruit,2026,planned\n"
        resp = farm_client.post("/data/import/crop_records/", {"file": csv_file(csv), "confirm": "1"})

        assert not CropRecord.objects.filter(farm=farm).exists()
        assert not CropType.objects.filter(name="Dragonfruit").exists()
        assert resp.context.get("errors")

    OLD_HEADER = "id,field_name,crop_name,variety,season,status,planted_date,harvest_date,yield_amount,yield_unit,cost,notes\n"

    def test_a_0_5_0_planting_csv_imports_and_its_yield_becomes_a_harvest(self, farm_client, farm):
        FieldFactory(farm=farm, name="North")
        old_csv = self.OLD_HEADER + ",North,soybeans,,2025,harvested,2025-05-01,2025-10-02,1500,bushels,0,\n"

        farm_client.post("/data/import/crop_records/", {"file": csv_file(old_csv), "confirm": "1"})

        planting = CropRecord.objects.get(farm=farm)
        assert planting.crop_type.name == "Soybeans"
        h = HarvestRecord.objects.get(farm=farm)
        assert (h.planting, h.harvest_date, h.yield_amount) == (planting, date(2025, 10, 2), Decimal("1500.00"))

    def test_reimporting_old_rows_for_existing_plantings_does_not_double_the_harvest(self, farm_client, farm):
        """0.5.0 exports carry ids, so re-importing updates the same plantings."""
        field = FieldFactory(farm=farm, name="North")
        p = CropRecordFactory(farm=farm, field=field, crop_type=CropType.objects.get(name="Soybeans"), season="2025")
        old_csv = self.OLD_HEADER + f"{p.pk},North,Soybeans,,2025,harvested,,2025-10-02,1500,bushels,0,\n"

        for _ in range(2):
            farm_client.post("/data/import/crop_records/", {"file": csv_file(old_csv), "confirm": "1"})

        assert CropRecord.objects.filter(farm=farm).count() == 1
        assert HarvestRecord.objects.filter(farm=farm, planting=p).count() == 1


def test_backup_format_comment_lists_this_version():
    """FORMAT_VERSION and its changelog comment must move together."""
    import inspect

    from apps.data_io import backup

    assert f"  {backup.FORMAT_VERSION} --" in inspect.getsource(backup)
