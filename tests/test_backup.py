"""Whole-farm backup/restore round-trip, isolation, hostile-archive, and version-skew tests."""

import io
import json
import zipfile
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Farm, FarmMembership, FarmSettings
from apps.consumables.models import InventoryItem, InventoryTransaction
from apps.crops.models import HarvestRecord
from apps.employment.models import Employee, Task, TimeEntry
from apps.data_io.backup import (
    RestoreError,
    export_farm,
    restore_farm,
)
from apps.land.models import CropRecord, Field, SoilSample
from apps.livestock.models import Animal, FeedLog, FeedStock, FeedType, FieldMovement, VetRecord
from apps.produce.models import ProduceItem, ProduceTransaction
from tests.factories import (
    AnimalFactory,
    BuildingFactory,
    BuildingMaintenanceRecordFactory,
    ConsumableTypeFactory,
    CropRecordFactory,
    CropTypeFactory,
    EmployeeFactory,
    EquipmentFactory,
    FarmFactory,
    FarmMembershipFactory,
    FeedLogFactory,
    FeedStockFactory,
    FeedTypeFactory,
    FieldFactory,
    HarvestRecordFactory,
    InventoryItemFactory,
    InventoryTransactionFactory,
    MaintenanceRecordFactory,
    ProduceItemFactory,
    ProduceTransactionFactory,
    SoilSampleFactory,
    TaskFactory,
    TimeEntryFactory,
    UserFactory,
    VetRecordFactory,
)


def populate(farm):
    """Build a farm touching every model in a backup, including the awkward relationships."""
    field = FieldFactory(farm=farm, name="North Pasture", soil_type="loam")
    other_field = FieldFactory(farm=farm, name="South Paddock")

    sire = AnimalFactory(farm=farm, ear_tag="SIRE1", species=Animal.Species.CATTLE)
    dam = AnimalFactory(farm=farm, ear_tag="DAM1", species=Animal.Species.CATTLE)
    calf = AnimalFactory(farm=farm, ear_tag="CALF1", sire=sire, dam=dam, current_field=field)

    VetRecordFactory(farm=farm, animal=calf)
    FieldMovement.objects.create(
        farm=farm, animal=calf, from_field=other_field, to_field=field, date="2026-03-01T12:00:00Z"
    )

    SoilSampleFactory(farm=farm, field=field, ph=6.4)
    backup_corn = CropTypeFactory(name="Backup Corn")
    planting = CropRecordFactory(farm=farm, field=field, crop_type=backup_corn, season="2026-Spring")
    HarvestRecordFactory(farm=farm, field=field, crop_type=backup_corn, planting=planting)

    stock = FeedStockFactory(farm=farm, feed_type=FeedTypeFactory(name="Backup Alfalfa"))
    FeedLogFactory(farm=farm, animal=calf, feed_stock=stock, quantity=Decimal("25.00"))

    equipment = EquipmentFactory(farm=farm)
    MaintenanceRecordFactory(farm=farm, equipment=equipment)

    building = BuildingFactory(farm=farm)
    BuildingMaintenanceRecordFactory(farm=farm, building=building)

    item = InventoryItemFactory(farm=farm, consumable_type=ConsumableTypeFactory(name="Backup Fuel"))
    InventoryTransactionFactory(farm=farm, item=item, quantity=Decimal("50.00"))

    employee = EmployeeFactory(farm=farm)
    task = TaskFactory(farm=farm, assigned_to=employee)
    TimeEntryFactory(farm=farm, employee=employee, task=task)

    produce = ProduceItemFactory(farm=farm, source_animal=calf)
    ProduceTransactionFactory(farm=farm, item=produce, quantity=Decimal("12.00"))

    FarmSettings.objects.create(
        farm=farm, usda_nass_api_key="secret-key", crop_prices_enabled=True,
        visible_tickers=["ZC=F", "ZS=F"],
    )
    return field, calf, stock, item, produce


def do_round_trip(farm, tmp_path, name="backup.zip", **kwargs):
    archive = tmp_path / name
    export_farm(farm, archive)
    return restore_farm(archive, UserFactory(), **kwargs)


def read_archive(path):
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("manifest.json")), json.loads(zf.read("data.json"))


def rewrite_archive(src, dest, manifest=None, data=None):
    """Copy an archive, replacing manifest/data and refreshing the checksum."""
    with zipfile.ZipFile(src) as zf:
        old_manifest = json.loads(zf.read("manifest.json"))
        old_data = json.loads(zf.read("data.json"))
        media = [(i.filename, zf.read(i.filename)) for i in zf.infolist()
                 if i.filename.startswith("media/")]

    manifest = old_manifest if manifest is None else manifest
    payload = json.dumps(old_data if data is None else data).encode()
    manifest["data_sha256"] = __import__("hashlib").sha256(payload).hexdigest()

    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("data.json", payload)
        for name, blob in media:
            zf.writestr(name, blob)
        zf.writestr("manifest.json", json.dumps(manifest))
    return dest


@pytest.mark.django_db
class TestRoundTrip:
    def test_counts_and_relationships_survive(self, farm, tmp_path):
        populate(farm)
        report = do_round_trip(farm, tmp_path)
        new = report.farm

        assert new.pk != farm.pk
        assert FarmMembership.objects.filter(farm=new, role="owner").exists()

        for model in (Field, Animal, SoilSample, CropRecord, HarvestRecord, VetRecord,
                      FieldMovement, FeedStock, FeedLog, InventoryItem, InventoryTransaction,
                      Employee, Task, TimeEntry, ProduceItem, ProduceTransaction):
            assert model.objects.filter(farm=new).count() == model.objects.filter(farm=farm).count()

        calf = Animal.objects.get(farm=new, ear_tag="CALF1")
        assert calf.sire.ear_tag == "SIRE1"
        assert calf.dam.ear_tag == "DAM1"
        assert calf.current_field.name == "North Pasture"
        assert calf.current_field.farm_id == new.pk

    def test_geometry_and_derived_acreage_survive(self, farm, tmp_path):
        original = FieldFactory(farm=farm, name="Geo Field")
        original.refresh_from_db()
        assert original.acreage > 0

        report = do_round_trip(farm, tmp_path)
        restored = Field.objects.get(farm=report.farm, name="Geo Field")

        assert restored.boundary is not None
        assert restored.boundary.srid == 4326
        assert restored.boundary.equals(original.boundary)
        assert restored.acreage == original.acreage
        assert restored.centroid_lat == pytest.approx(original.centroid_lat)

    def test_point_geometry_survives(self, farm, tmp_path):
        BuildingFactory(farm=farm, name="Geo Barn")
        report = do_round_trip(farm, tmp_path)
        restored = report.farm.buildings_buildings.get(name="Geo Barn")
        assert restored.location is not None
        assert restored.location.x == pytest.approx(-93.6)

    def test_farm_settings_survive(self, farm, tmp_path):
        FarmSettings.objects.create(
            farm=farm, usda_nass_api_key="abc123", crop_prices_enabled=True,
            weather_enabled=False, visible_tickers=["ZC=F"],
        )
        report = do_round_trip(farm, tmp_path)
        settings = FarmSettings.objects.get(farm=report.farm)

        assert settings.usda_nass_api_key == "abc123"
        assert settings.crop_prices_enabled is True
        assert settings.weather_enabled is False
        assert settings.visible_tickers == ["ZC=F"]

    def test_farm_without_settings_gets_defaults(self, farm, tmp_path):
        FieldFactory(farm=farm)
        report = do_round_trip(farm, tmp_path)
        assert FarmSettings.objects.filter(farm=report.farm).exists()

    def test_timestamps_are_preserved(self, farm, tmp_path):
        original = FieldFactory(farm=farm, name="Old Field")
        report = do_round_trip(farm, tmp_path)
        restored = Field.objects.get(farm=report.farm, name="Old Field")

        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at


@pytest.mark.django_db
class TestQuantitiesNotDoubleCounted:
    """The regression that justifies bulk_create over save() in _restore_model."""

    def test_inventory_quantity(self, farm, tmp_path):
        item = InventoryItemFactory(farm=farm, name="Diesel", quantity=Decimal("0"))
        InventoryTransactionFactory(farm=farm, item=item, quantity=Decimal("120.00"))
        InventoryTransactionFactory(farm=farm, item=item, quantity=Decimal("-20.00"))
        item.refresh_from_db()
        assert item.quantity == Decimal("100.00")

        report = do_round_trip(farm, tmp_path)
        assert InventoryItem.objects.get(farm=report.farm).quantity == Decimal("100.00")

    def test_produce_quantity(self, farm, tmp_path):
        produce = ProduceItemFactory(farm=farm, quantity=Decimal("0"))
        ProduceTransactionFactory(farm=farm, item=produce, quantity=Decimal("36.00"))
        produce.refresh_from_db()

        report = do_round_trip(farm, tmp_path)
        assert ProduceItem.objects.get(farm=report.farm).quantity == produce.quantity

    def test_feed_stock_quantity(self, farm, tmp_path):
        stock = FeedStockFactory(farm=farm, quantity=Decimal("500.00"))
        FeedLogFactory(
            farm=farm, animal=AnimalFactory(farm=farm), feed_stock=stock, quantity=Decimal("75.00")
        )
        stock.refresh_from_db()
        assert stock.quantity == Decimal("425.00")

        report = do_round_trip(farm, tmp_path)
        assert FeedStock.objects.get(farm=report.farm).quantity == Decimal("425.00")

    def test_field_movement_does_not_rewrite_current_field(self, farm, tmp_path):
        home = FieldFactory(farm=farm, name="Home")
        away = FieldFactory(farm=farm, name="Away")
        animal = AnimalFactory(farm=farm, ear_tag="A1", current_field=home)
        # A historical move to Away, but the animal is back Home now.
        FieldMovement.objects.create(
            farm=farm, animal=animal, from_field=home, to_field=away, date="2026-01-01T00:00:00Z"
        )
        Animal.objects.filter(pk=animal.pk).update(current_field=home)

        report = do_round_trip(farm, tmp_path)
        assert Animal.objects.get(farm=report.farm, ear_tag="A1").current_field.name == "Home"


@pytest.mark.django_db
class TestMedia:
    def test_photo_round_trips(self, farm, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path / "media"
        animal = AnimalFactory(farm=farm, ear_tag="PHOTO1")
        animal.photo.save("steer.jpg", SimpleUploadedFile("steer.jpg", b"jpeg-bytes"), save=True)

        report = do_round_trip(farm, tmp_path)
        restored = Animal.objects.get(farm=report.farm, ear_tag="PHOTO1")

        assert restored.photo.name
        with restored.photo.open("rb") as fh:
            assert fh.read() == b"jpeg-bytes"
        # Restoring alongside the original must not clobber it.
        animal.refresh_from_db()
        assert restored.photo.name != animal.photo.name

    def test_missing_media_warns_instead_of_failing(self, farm, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path / "media"
        animal = AnimalFactory(farm=farm, ear_tag="GHOST")
        Animal.objects.filter(pk=animal.pk).update(photo="livestock/photos/vanished.jpg")

        archive = tmp_path / "backup.zip"
        manifest = export_farm(farm, archive)
        assert manifest["missing_media"] == ["livestock/photos/vanished.jpg"]

        report = restore_farm(archive, UserFactory())
        assert Animal.objects.filter(farm=report.farm, ear_tag="GHOST").exists()


@pytest.mark.django_db
class TestIsolation:
    def test_source_farm_is_untouched(self, farm, tmp_path):
        populate(farm)
        before = {m.__name__: m.objects.filter(farm=farm).count()
                  for m in (Field, Animal, InventoryItem, ProduceItem)}
        original_quantity = InventoryItem.objects.filter(farm=farm).first().quantity

        do_round_trip(farm, tmp_path)

        after = {m.__name__: m.objects.filter(farm=farm).count()
                 for m in (Field, Animal, InventoryItem, ProduceItem)}
        assert before == after
        assert InventoryItem.objects.filter(farm=farm).first().quantity == original_quantity

    def test_every_restored_row_belongs_to_the_new_farm(self, farm, tmp_path):
        populate(farm)
        report = do_round_trip(farm, tmp_path)
        for model in (Field, Animal, SoilSample, HarvestRecord, FeedLog, TimeEntry, ProduceItem):
            assert not model.objects.filter(farm=report.farm).exclude(farm=report.farm).exists()
            assert model.objects.filter(farm=report.farm).exists()

    def test_restoring_twice_creates_two_distinct_farms(self, farm, tmp_path):
        populate(farm)
        archive = tmp_path / "backup.zip"
        export_farm(farm, archive)

        first = restore_farm(archive, UserFactory())
        second = restore_farm(archive, UserFactory())

        assert first.farm.pk != second.farm.pk
        assert first.farm.name != second.farm.name


@pytest.mark.django_db
class TestSequenceIntegrity:
    def test_new_rows_can_be_created_after_a_restore(self, farm, tmp_path):
        populate(farm)
        report = do_round_trip(farm, tmp_path)
        # Guards against any future change that writes archived pks verbatim and leaves the
        # Postgres sequence behind.
        FieldFactory(farm=report.farm, name="Brand New Field")
        AnimalFactory(farm=report.farm, ear_tag="NEW1")


@pytest.mark.django_db
class TestHostileArchives:
    def _restore_should_fail(self, path, message_fragment=None):
        before = Farm.objects.count()
        with pytest.raises(RestoreError) as exc:
            restore_farm(path, UserFactory())
        assert Farm.objects.count() == before
        if message_fragment:
            assert any(message_fragment in e for e in exc.value.errors), exc.value.errors

    def test_not_a_zip(self, tmp_path):
        path = tmp_path / "junk.zip"
        path.write_bytes(b"definitely not a zip file")
        self._restore_should_fail(path, "zip")

    def test_path_traversal_member_is_rejected(self, farm, tmp_path):
        populate(farm)
        good = tmp_path / "good.zip"
        export_farm(farm, good)

        evil = tmp_path / "evil.zip"
        with zipfile.ZipFile(good) as src, zipfile.ZipFile(evil, "w") as dst:
            for info in src.infolist():
                dst.writestr(info.filename, src.read(info.filename))
            dst.writestr("media/../../../../tmp/pwned.txt", b"owned")

        self._restore_should_fail(evil, "Unsafe path")

    def test_absolute_path_member_is_rejected(self, farm, tmp_path):
        good = tmp_path / "good.zip"
        FieldFactory(farm=farm)
        export_farm(farm, good)

        evil = tmp_path / "abs.zip"
        with zipfile.ZipFile(good) as src, zipfile.ZipFile(evil, "w") as dst:
            for info in src.infolist():
                dst.writestr(info.filename, src.read(info.filename))
            dst.writestr("/etc/cron.d/pwned", b"owned")

        self._restore_should_fail(evil, "Unsafe path")

    def test_missing_manifest(self, tmp_path):
        path = tmp_path / "nomanifest.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("data.json", "{}")
        self._restore_should_fail(path, "no manifest.json")

    def test_foreign_archive_is_rejected(self, tmp_path):
        path = tmp_path / "foreign.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("data.json", "{}")
            zf.writestr("manifest.json", json.dumps({"format": "something-else"}))
        self._restore_should_fail(path, "not a FarmSteader backup")

    def test_future_format_version_is_rejected(self, farm, tmp_path):
        FieldFactory(farm=farm)
        good = tmp_path / "good.zip"
        export_farm(farm, good)
        manifest, _ = read_archive(good)
        manifest["format_version"] = 99

        self._restore_should_fail(
            rewrite_archive(good, tmp_path / "future.zip", manifest=manifest), "newer"
        )

    def test_tampered_data_fails_checksum(self, farm, tmp_path):
        FieldFactory(farm=farm)
        good = tmp_path / "good.zip"
        export_farm(farm, good)

        with zipfile.ZipFile(good) as src:
            manifest = json.loads(src.read("manifest.json"))
            members = [(i.filename, src.read(i.filename)) for i in src.infolist()]

        tampered = tmp_path / "tampered.zip"
        with zipfile.ZipFile(tampered, "w") as dst:
            for name, blob in members:
                dst.writestr(name, b'{"land.Field": []}' if name == "data.json" else blob)
        assert manifest["data_sha256"]

        self._restore_should_fail(tampered, "checksum")

    def test_oversized_archive_is_rejected(self, farm, tmp_path, settings):
        settings.FARMSTEADER_MAX_RESTORE_BYTES = 10
        FieldFactory(farm=farm)
        path = tmp_path / "big.zip"
        export_farm(farm, path)
        self._restore_should_fail(path, "over the")


@pytest.mark.django_db
class TestVersionSkew:
    def test_unknown_field_refused_then_allowed(self, farm, tmp_path):
        FieldFactory(farm=farm, name="Skew")
        good = tmp_path / "good.zip"
        export_farm(farm, good)
        manifest, data = read_archive(good)

        manifest["schema"]["land.Field"].append("drone_survey_url")
        for row in data["land.Field"]:
            row["drone_survey_url"] = "https://example.com/survey"
        newer = rewrite_archive(good, tmp_path / "newer.zip", manifest=manifest, data=data)

        with pytest.raises(RestoreError) as exc:
            restore_farm(newer, UserFactory())
        assert exc.value.dropped_fields == {"land.Field": ["drone_survey_url"]}

        report = restore_farm(newer, UserFactory(), allow_dropped_fields=True)
        assert Field.objects.filter(farm=report.farm, name="Skew").exists()
        assert report.dropped_fields == {"land.Field": ["drone_survey_url"]}

    def test_older_archive_missing_optional_field_restores_with_default(self, farm, tmp_path):
        FieldFactory(farm=farm, name="Old", timezone="America/Chicago")
        good = tmp_path / "good.zip"
        export_farm(farm, good)
        manifest, data = read_archive(good)

        manifest["schema"]["land.Field"].remove("timezone")
        for row in data["land.Field"]:
            del row["timezone"]
        older = rewrite_archive(good, tmp_path / "older.zip", manifest=manifest, data=data)

        report = restore_farm(older, UserFactory())
        assert Field.objects.get(farm=report.farm, name="Old").timezone == ""
        assert any("timezone" in w for w in report.warnings)

    def test_unknown_model_is_rejected(self, farm, tmp_path):
        FieldFactory(farm=farm)
        good = tmp_path / "good.zip"
        export_farm(farm, good)
        manifest, _ = read_archive(good)
        manifest["schema"]["land.DroneFlight"] = ["altitude"]

        with pytest.raises(RestoreError) as exc:
            restore_farm(rewrite_archive(good, tmp_path / "x.zip", manifest=manifest), UserFactory())
        assert any("unknown model" in e for e in exc.value.errors)

    def test_missing_catalog_entry_is_recreated(self, farm, tmp_path):
        stock = FeedStockFactory(farm=farm, feed_type=FeedTypeFactory(name="Rare Fodder"))
        archive = tmp_path / "backup.zip"
        export_farm(farm, archive)

        # Simulate a release that dropped the seed entry.
        FeedStock.objects.filter(pk=stock.pk).delete()
        FeedType.objects.filter(name="Rare Fodder").delete()
        assert not FeedType.objects.filter(name="Rare Fodder").exists()

        report = restore_farm(archive, UserFactory())
        restored = FeedStock.objects.get(farm=report.farm)
        assert restored.feed_type.name == "Rare Fodder"

    def test_existing_catalog_entry_is_reused_not_duplicated(self, farm, tmp_path):
        FeedStockFactory(farm=farm, feed_type=FeedTypeFactory(name="Shared Hay"))
        report = do_round_trip(farm, tmp_path)

        assert FeedType.objects.filter(name="Shared Hay").count() == 1
        assert FeedStock.objects.get(farm=report.farm).feed_type.name == "Shared Hay"


@pytest.mark.django_db
class TestDanglingReferences:
    def test_dangling_required_reference_is_reported_clearly(self, farm, tmp_path, other_farm):
        # Nothing in the schema stops a farm's row from pointing at another farm's row.
        stray = AnimalFactory(farm=other_farm, ear_tag="STRAY")
        FeedLogFactory(farm=farm, animal=stray, feed_stock=FeedStockFactory(farm=farm))

        archive = tmp_path / "backup.zip"
        export_farm(farm, archive)

        with pytest.raises(RestoreError) as exc:
            restore_farm(archive, UserFactory())
        assert any("outside this farm" in e for e in exc.value.errors), exc.value.errors

    def test_dangling_optional_reference_is_cleared_with_a_warning(self, farm, tmp_path, other_farm):
        stray = FieldFactory(farm=other_farm, name="Neighbour Field")
        AnimalFactory(farm=farm, ear_tag="WANDERER", current_field=stray)

        report = do_round_trip(farm, tmp_path)
        restored = Animal.objects.get(farm=report.farm, ear_tag="WANDERER")

        assert restored.current_field is None
        assert any("outside this farm" in w for w in report.warnings)


@pytest.mark.django_db
class TestManagementCommands:
    def _backup(self, farm_ref, path):
        out = io.StringIO()
        call_command("farm_backup", farm=str(farm_ref), output=str(path), stdout=out)
        return out.getvalue()

    def test_backup_and_restore_by_id(self, farm, tmp_path):
        populate(farm)
        user = UserFactory()
        archive = tmp_path / "cli.zip"

        assert "Backed up" in self._backup(farm.pk, archive)

        out = io.StringIO()
        call_command("farm_restore", str(archive), owner=user.username, stdout=out)
        assert "Restored" in out.getvalue()

        restored = Farm.objects.exclude(pk=farm.pk).get()
        assert Field.objects.filter(farm=restored).count() == 2

    def test_backup_by_name(self, farm, tmp_path):
        FieldFactory(farm=farm)
        assert "Backed up" in self._backup(farm.name, tmp_path / "byname.zip")

    def test_backup_unknown_farm(self, db, tmp_path):
        with pytest.raises(CommandError, match="No farm matching"):
            self._backup("Nowhere Farm", tmp_path / "x.zip")

    def test_backup_ambiguous_name(self, tmp_path):
        FarmFactory(name="Twin Oaks")
        FarmFactory(name="Twin Oaks")
        with pytest.raises(CommandError, match="More than one farm"):
            self._backup("Twin Oaks", tmp_path / "x.zip")

    def test_restore_unknown_owner(self, farm, tmp_path):
        FieldFactory(farm=farm)
        archive = tmp_path / "cli.zip"
        self._backup(farm.pk, archive)

        with pytest.raises(CommandError, match="No user named"):
            call_command("farm_restore", str(archive), owner="ghost")

    def test_restore_names_the_new_farm(self, farm, tmp_path):
        FieldFactory(farm=farm)
        archive = tmp_path / "cli.zip"
        self._backup(farm.pk, archive)

        call_command(
            "farm_restore", str(archive), owner=UserFactory().username, farm_name="Renamed",
            stdout=io.StringIO(),
        )
        assert Farm.objects.filter(name="Renamed").exists()

    def test_restore_aborts_and_writes_nothing_on_a_bad_archive(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip")
        before = Farm.objects.count()

        with pytest.raises(CommandError, match="nothing was written"):
            call_command("farm_restore", str(bad), owner=UserFactory().username,
                         stderr=io.StringIO())
        assert Farm.objects.count() == before


@pytest.mark.django_db
class TestManifest:
    def test_manifest_describes_the_archive(self, farm, tmp_path):
        populate(farm)
        archive = tmp_path / "backup.zip"
        manifest = export_farm(farm, archive)

        assert manifest["format"] == "farmsteader-backup"
        assert manifest["format_version"] == 2  # 2: plantings link to the crop catalog (0.6.0)
        assert manifest["farm"]["name"] == farm.name
        assert manifest["counts"]["land.Field"] == 2
        assert "boundary" in manifest["schema"]["land.Field"]
        assert manifest["data_sha256"]

        with zipfile.ZipFile(archive) as zf:
            assert set(zf.namelist()) >= {"manifest.json", "data.json"}
