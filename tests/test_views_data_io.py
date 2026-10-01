import io

import pytest

from apps.land.models import Field
from tests.factories import (
    CropRecordFactory,
    EmployeeFactory,
    FieldFactory,
    InventoryItemFactory,
)


@pytest.mark.django_db
class TestDataIOIndex:
    def test_requires_login(self, client):
        resp = client.get("/data/")
        assert resp.status_code == 302

    def test_renders(self, farm_client, farm):
        resp = farm_client.get("/data/")
        assert resp.status_code == 200
        assert "grouped" in resp.context


@pytest.mark.django_db
class TestDataExport:
    def test_export_csv(self, farm_client, farm):
        FieldFactory(farm=farm)
        resp = farm_client.get("/data/export/fields/?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp["Content-Type"]

    def test_export_xlsx(self, farm_client, farm):
        FieldFactory(farm=farm)
        resp = farm_client.get("/data/export/fields/?format=xlsx")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp["Content-Type"]

    def test_export_unknown_resource_redirects(self, farm_client):
        resp = farm_client.get("/data/export/bogus/")
        assert resp.status_code == 302

    def test_export_default_format_is_csv(self, farm_client, farm):
        resp = farm_client.get("/data/export/fields/")
        assert resp.status_code == 200
        assert "text/csv" in resp["Content-Type"]


@pytest.mark.django_db
class TestDataImport:
    def _csv_file(self, content, name="import.csv"):
        f = io.BytesIO(content.encode())
        f.name = name
        return f

    def test_import_get(self, farm_client):
        resp = farm_client.get("/data/import/fields/")
        assert resp.status_code == 200

    def test_import_unknown_resource_redirects(self, farm_client):
        resp = farm_client.get("/data/import/bogus/")
        assert resp.status_code == 302

    def test_import_no_file_redirects(self, farm_client):
        resp = farm_client.post("/data/import/inventory_items/")
        assert resp.status_code == 302

    def test_import_unsupported_format_redirects(self, farm_client):
        f = io.BytesIO(b"data")
        f.name = "import.txt"
        resp = farm_client.post("/data/import/inventory_items/", {"file": f})
        assert resp.status_code == 302

    def test_import_preview(self, farm_client, farm):
        item = InventoryItemFactory(farm=farm)
        csv_content = (
            "name,consumable_type,quantity,unit,reorder_threshold\n"
            f"Test Diesel,{item.consumable_type.pk},100,gallons,20\n"
        )
        f = self._csv_file(csv_content)
        resp = farm_client.post("/data/import/inventory_items/", {"file": f})
        assert resp.status_code == 200
        assert resp.context.get("show_confirm") or resp.context.get("errors") is not None


def csv_file(content, name="import.csv"):
    f = io.BytesIO(content.encode())
    f.name = name
    return f


@pytest.mark.django_db
class TestIndexGroups:
    """The registry keys and the page's groups have to agree, or a group renders empty."""

    def test_every_group_lists_data_types(self, farm_client):
        grouped = farm_client.get("/data/").context["grouped"]
        for group_name, items in grouped.items():
            assert items, f"{group_name} group is empty — its keys do not match the registry"

    def test_produce_and_feed_are_present(self, farm_client):
        grouped = farm_client.get("/data/").context["grouped"]
        assert [i["key"] for i in grouped["Produce"]] == ["produce_items", "produce_transactions"]
        assert [i["key"] for i in grouped["Feed"]] == ["feed_types", "feed_stocks", "feed_logs"]


@pytest.mark.django_db
class TestFieldGeometryRoundTrip:
    def test_export_includes_boundary(self, farm_client, farm):
        FieldFactory(farm=farm, name="Mapped")
        body = farm_client.get("/data/export/fields/?format=csv").content.decode()

        header, *rows = body.strip().splitlines()
        assert "boundary" in header.split(",")
        assert "POLYGON" in body

    def test_reimport_preserves_geometry_and_acreage(self, farm_client, farm):
        original = FieldFactory(farm=farm, name="Mapped")
        original.refresh_from_db()
        body = farm_client.get("/data/export/fields/?format=csv").content.decode()

        Field.objects.filter(pk=original.pk).delete()
        farm_client.post("/data/import/fields/", {"file": csv_file(body), "confirm": "1"})

        restored = Field.objects.get(farm=farm, name="Mapped")
        assert restored.boundary is not None
        assert restored.boundary.equals(original.boundary)
        assert restored.acreage == original.acreage


@pytest.mark.django_db
class TestCrossFarmIsolation:
    """A file exported by one farm must never reach into another farm's rows."""

    def test_import_cannot_overwrite_another_farms_row(self, farm_client, farm, other_farm):
        victim = FieldFactory(farm=other_farm, name="Their Field")
        csv_content = (
            "id,name,boundary,soil_type,color,timezone,notes\n"
            f'{victim.pk},Stolen,"{victim.boundary.wkt}",,#22c55e,,\n'
        )
        farm_client.post("/data/import/fields/", {"file": csv_file(csv_content), "confirm": "1"})

        victim.refresh_from_db()
        assert victim.name == "Their Field"
        assert victim.farm_id == other_farm.pk
        assert Field.objects.filter(farm=farm, name="Stolen").exists()

    def test_animal_import_cannot_hijack_another_farms_ear_tag(
        self, farm_client, farm, other_farm
    ):
        from tests.factories import AnimalFactory

        victim = AnimalFactory(farm=other_farm, ear_tag="SHARED", name="Theirs")
        csv_content = "ear_tag,name,species,gender,status\nSHARED,Mine,cattle,female,active\n"
        farm_client.post("/data/import/animals/", {"file": csv_file(csv_content), "confirm": "1"})

        victim.refresh_from_db()
        assert victim.name == "Theirs"
        assert victim.farm_id == other_farm.pk

    def test_foreign_key_lookup_does_not_cross_farms(self, farm_client, farm, other_farm):
        FieldFactory(farm=other_farm, name="North Pasture")
        # A real catalog crop, so the only thing wrong with the row is the field.
        # (The legacy crop_name header, as written by 0.5.0 exports, still reads.)
        csv_content = (
            "field_name,crop_name,season,status\nNorth Pasture,Soybeans,2026-Spring,planned\n"
        )
        resp = farm_client.post(
            "/data/import/crop_records/", {"file": csv_file(csv_content), "confirm": "1"}
        )

        # The only "North Pasture" belongs to someone else, so the row must not link to it.
        assert not CropRecordFactory._meta.model.objects.filter(farm=farm).exists()
        assert resp.context.get("errors")


@pytest.mark.django_db
class TestEmployeeLookup:
    def test_employee_matched_by_full_name(self, farm_client, farm):
        keeper = EmployeeFactory(farm=farm, first_name="Ada", last_name="Shepherd")
        EmployeeFactory(farm=farm, first_name="Grace", last_name="Shepherd")

        csv_content = "title,assigned_to,priority,status\nFix fence,Ada Shepherd,medium,todo\n"
        farm_client.post("/data/import/tasks/", {"file": csv_file(csv_content), "confirm": "1"})

        from apps.employment.models import Task

        assert Task.objects.get(farm=farm, title="Fix fence").assigned_to_id == keeper.pk

    def test_export_renders_full_name(self, farm_client, farm):
        EmployeeFactory(farm=farm, first_name="Ada", last_name="Shepherd")
        from tests.factories import TaskFactory

        TaskFactory(farm=farm, assigned_to=EmployeeFactory(
            farm=farm, first_name="Grace", last_name="Hopper"))

        body = farm_client.get("/data/export/tasks/?format=csv").content.decode()
        assert "Grace Hopper" in body


@pytest.mark.django_db
class TestBackupViews:
    def test_backup_page_requires_login(self, client):
        assert client.get("/data/backup/").status_code == 302

    def test_backup_page_lists_counts(self, farm_client, farm):
        FieldFactory(farm=farm)
        resp = farm_client.get("/data/backup/")
        assert resp.status_code == 200
        assert dict(resp.context["counts"])["Fields"] == 1

    def test_download_returns_a_zip(self, farm_client, farm):
        import zipfile

        FieldFactory(farm=farm)
        resp = farm_client.get("/data/backup/download/")
        assert resp.status_code == 200
        assert resp["Content-Disposition"].startswith("attachment;")

        payload = b"".join(resp.streaming_content)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            assert {"manifest.json", "data.json"} <= set(zf.namelist())

    def test_download_only_covers_the_current_farm(self, farm_client, farm, other_farm):
        import json
        import zipfile

        FieldFactory(farm=farm, name="Mine")
        FieldFactory(farm=other_farm, name="Theirs")

        payload = b"".join(farm_client.get("/data/backup/download/").streaming_content)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            data = json.loads(zf.read("data.json"))

        names = [row["name"] for row in data["land.Field"]]
        assert names == ["Mine"]

    def test_restore_creates_a_new_farm_and_switches_to_it(self, farm_client, farm):
        from apps.accounts.models import Farm

        FieldFactory(farm=farm, name="Round Trip")
        payload = b"".join(farm_client.get("/data/backup/download/").streaming_content)

        archive = io.BytesIO(payload)
        archive.name = "backup.zip"
        resp = farm_client.post(
            "/data/backup/restore/", {"archive": archive, "confirm": "1", "farm_name": "Restored"}
        )

        assert resp.status_code == 302
        new_farm = Farm.objects.get(name="Restored")
        assert new_farm.pk != farm.pk
        assert Field.objects.filter(farm=new_farm, name="Round Trip").exists()
        assert farm_client.session["current_farm_id"] == new_farm.pk

    def test_restore_requires_confirmation(self, farm_client, farm):
        from apps.accounts.models import Farm

        FieldFactory(farm=farm)
        payload = b"".join(farm_client.get("/data/backup/download/").streaming_content)
        archive = io.BytesIO(payload)
        archive.name = "backup.zip"

        before = Farm.objects.count()
        resp = farm_client.post("/data/backup/restore/", {"archive": archive})

        assert resp.status_code == 302
        assert Farm.objects.count() == before

    def test_restore_reports_errors_without_creating_a_farm(self, farm_client):
        from apps.accounts.models import Farm

        archive = io.BytesIO(b"not a zip at all")
        archive.name = "backup.zip"

        before = Farm.objects.count()
        resp = farm_client.post("/data/backup/restore/", {"archive": archive, "confirm": "1"})

        assert resp.status_code == 200
        assert resp.context["errors"]
        assert Farm.objects.count() == before
