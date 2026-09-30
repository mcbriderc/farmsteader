"""Property boundaries (land.Parcel).

The interesting part is field_coverage(): it measures fields on the *overlap*
with the property, not their own acreage, and on the union of overlaps, so a
field straddling the line or two fields drawn on top of each other cannot
inflate the covered acreage past what is really there.
"""

import json
from decimal import Decimal

import pytest
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.urls import reverse

from apps.core.models import FarmOwnedModel
from apps.data_io.backup import MODEL_SPECS
from apps.land.geo import acreage_of
from apps.land.models import Field, Parcel

from .factories import FieldFactory, ParcelFactory
from .test_backup import do_round_trip
from .test_views_data_io import csv_file


def acres(geom):
    """acreage_of() as the Decimal a DecimalField reads back from the database."""
    return Decimal(str(acreage_of(geom)))


def square(x0, y0, x1, y1):
    """An axis-aligned lon/lat rectangle in SRID 4326."""
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


# A ~1.1 km square property in Iowa, and shapes positioned relative to it.
PROPERTY = square(-93.62, 41.60, -93.60, 41.62)
INSIDE = square(-93.619, 41.601, -93.611, 41.609)       # wholly inside
STRADDLING = square(-93.605, 41.605, -93.595, 41.615)   # half in, half out (east edge)
OUTSIDE = square(-93.58, 41.60, -93.57, 41.61)          # nowhere near
TOUCHING = square(-93.60, 41.60, -93.59, 41.61)         # shares only the east edge

GEOJSON_POLYGON = json.dumps({
    "type": "Polygon",
    "coordinates": [[[-93.62, 41.60], [-93.60, 41.60], [-93.60, 41.62], [-93.62, 41.62], [-93.62, 41.60]]],
})


@pytest.mark.django_db
class TestAcreage:
    def test_acreage_is_computed_on_save(self, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        assert parcel.acreage == acreage_of(PROPERTY)
        assert parcel.acreage > 0

    def test_parcel_and_field_measure_the_same_shape_identically(self, farm):
        """One helper for both, so the two can never drift apart."""
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        field = FieldFactory(farm=farm, boundary=PROPERTY)
        parcel.refresh_from_db()
        field.refresh_from_db()
        assert parcel.acreage == field.acreage

    def test_field_acreage_unchanged_by_the_refactor(self, farm):
        """Field.save() used to inline this maths; the stored value must not move."""
        field = FieldFactory(farm=farm, boundary=PROPERTY)
        field.refresh_from_db()
        legacy = round(PROPERTY.transform(5070, clone=True).area / 4046.8564224, 2)
        assert field.acreage == Decimal(str(legacy))


@pytest.mark.django_db
class TestFieldCoverage:
    def test_field_wholly_inside_counts_in_full(self, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        field = FieldFactory(farm=farm, boundary=INSIDE)

        rows, covered, pct = parcel.field_coverage()

        assert [f.pk for f, _ in rows] == [field.pk]
        assert covered == acreage_of(INSIDE)
        assert 0 < pct < 100

    def test_straddling_field_counts_only_the_part_inside(self, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        field = FieldFactory(farm=farm, boundary=STRADDLING)

        rows, covered, _ = parcel.field_coverage()

        (_, inside), = rows
        assert inside == acreage_of(STRADDLING.intersection(PROPERTY))
        assert inside < field.acreage
        # The straddler is split down the middle by the property line.
        assert abs(float(inside) - float(field.acreage) / 2) < 0.5

    def test_overlapping_fields_are_not_double_counted(self, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        FieldFactory(farm=farm, name="A", boundary=INSIDE)
        FieldFactory(farm=farm, name="A again", boundary=INSIDE)

        rows, covered, _ = parcel.field_coverage()

        assert len(rows) == 2                 # both listed...
        assert covered == acreage_of(INSIDE)  # ...but the ground counted once

    def test_touching_or_distant_fields_are_excluded(self, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        FieldFactory(farm=farm, boundary=OUTSIDE)
        FieldFactory(farm=farm, boundary=TOUCHING)

        rows, covered, pct = parcel.field_coverage()

        assert rows == []
        assert (covered, pct) == (0, 0)

    def test_other_farms_fields_are_never_counted(self, farm, other_farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        FieldFactory(farm=other_farm, boundary=INSIDE)

        rows, covered, _ = parcel.field_coverage()

        assert rows == [] and covered == 0

    def test_coverage_is_capped_at_100_percent(self, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        FieldFactory(farm=farm, boundary=PROPERTY)

        _, _, pct = parcel.field_coverage()

        assert pct == 100


@pytest.mark.django_db
class TestViews:
    def test_list_shows_only_this_farms_parcels(self, farm_client, farm, other_farm):
        ParcelFactory(farm=farm, name="Home Place")
        ParcelFactory(farm=other_farm, name="Their Place")

        body = farm_client.get(reverse("land:parcel_list")).content.decode()

        assert "Home Place" in body
        assert "Their Place" not in body

    def test_detail_of_another_farms_parcel_is_404(self, farm_client, other_farm):
        theirs = ParcelFactory(farm=other_farm)
        assert farm_client.get(reverse("land:parcel_detail", args=[theirs.pk])).status_code == 404

    def test_detail_lists_fields_inside(self, farm_client, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        FieldFactory(farm=farm, name="North Forty", boundary=INSIDE)

        resp = farm_client.get(reverse("land:parcel_detail", args=[parcel.pk]))

        assert resp.status_code == 200
        assert "North Forty" in resp.content.decode()

    def test_create_computes_acreage_and_assigns_the_farm(self, farm_client, farm):
        resp = farm_client.post(reverse("land:parcel_create"), {
            "name": "Home Place",
            "parcel_number": "12-34-567",
            "color": "#f59e0b",
            "notes": "",
            "boundary_geojson": GEOJSON_POLYGON,
        })

        parcel = Parcel.objects.get(name="Home Place")
        assert resp.status_code == 302
        assert parcel.farm == farm
        assert parcel.parcel_number == "12-34-567"
        assert parcel.acreage == acres(GEOSGeometry(GEOJSON_POLYGON))

    def test_self_crossing_boundary_is_rejected(self, farm_client):
        bowtie = json.dumps({
            "type": "Polygon",
            "coordinates": [[[-93.62, 41.60], [-93.60, 41.62], [-93.60, 41.60], [-93.62, 41.62], [-93.62, 41.60]]],
        })
        resp = farm_client.post(reverse("land:parcel_create"), {
            "name": "Bowtie", "color": "#f59e0b", "boundary_geojson": bowtie,
        })

        assert resp.status_code == 200
        assert "crosses itself" in resp.content.decode()
        assert not Parcel.objects.filter(name="Bowtie").exists()

    def test_non_polygon_error_is_readable(self, farm_client):
        """It used to be swallowed and re-wrapped as "Invalid GeoJSON: ['...']"."""
        point = json.dumps({"type": "Point", "coordinates": [-93.6, 41.6]})
        resp = farm_client.post(reverse("land:parcel_create"), {
            "name": "Dot", "color": "#f59e0b", "boundary_geojson": point,
        })

        body = resp.content.decode()
        assert "Boundary must be a polygon." in body
        assert "Invalid GeoJSON" not in body

    def test_bad_colour_is_rejected(self, farm_client):
        resp = farm_client.post(reverse("land:parcel_create"), {
            "name": "Loud", "color": "red'; alert(1)//", "boundary_geojson": GEOJSON_POLYGON,
        })
        assert resp.status_code == 200
        assert not Parcel.objects.filter(name="Loud").exists()

    def test_edit_redraws_and_recomputes(self, farm_client, farm):
        parcel = ParcelFactory(farm=farm, boundary=INSIDE)
        farm_client.post(reverse("land:parcel_edit", args=[parcel.pk]), {
            "name": parcel.name, "color": parcel.color, "boundary_geojson": GEOJSON_POLYGON,
        })
        parcel.refresh_from_db()
        assert parcel.acreage == acres(GEOSGeometry(GEOJSON_POLYGON))

    def test_delete_leaves_fields_alone(self, farm_client, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        field = FieldFactory(farm=farm, boundary=INSIDE)

        farm_client.post(reverse("land:parcel_delete", args=[parcel.pk]))

        assert not Parcel.objects.filter(pk=parcel.pk).exists()
        assert Field.objects.filter(pk=field.pk).exists()

    def test_geojson_is_farm_scoped_and_links_to_detail(self, farm_client, farm, other_farm):
        mine = ParcelFactory(farm=farm, name="Mine")
        ParcelFactory(farm=other_farm, name="Theirs")

        data = farm_client.get(reverse("land:parcel_geojson")).json()

        assert [f["properties"]["name"] for f in data["features"]] == ["Mine"]
        assert data["features"][0]["properties"]["url"] == reverse("land:parcel_detail", args=[mine.pk])


@pytest.mark.django_db
class TestMapDoesNotRenderNamesAsHtml:
    """Leaflet treats a string popup or tooltip as HTML. Names are user-entered."""

    def test_farm_map_builds_popups_from_dom_nodes(self, farm_client):
        body = farm_client.get(reverse("land:field_map")).content.decode()
        assert "'<strong>' + p.name" not in body
        assert "title.textContent = p.name" in body

    def test_detail_page_escapes_field_names_in_embedded_data(self, farm_client, farm):
        parcel = ParcelFactory(farm=farm, boundary=PROPERTY)
        FieldFactory(farm=farm, name="</script><script>alert(1)</script>", boundary=INSIDE)

        body = farm_client.get(reverse("land:parcel_detail", args=[parcel.pk])).content.decode()

        assert "</script><script>alert(1)" not in body


@pytest.mark.django_db
class TestDataPortability:
    def test_backup_round_trip_keeps_parcels(self, farm, tmp_path):
        ParcelFactory(farm=farm, name="Home Place", boundary=PROPERTY, parcel_number="12-34")

        report = do_round_trip(farm, tmp_path)

        restored = Parcel.objects.get(farm=report.farm)
        assert (restored.name, restored.parcel_number) == ("Home Place", "12-34")
        assert restored.boundary.equals(PROPERTY)
        assert restored.acreage == acres(PROPERTY)

    def test_csv_export_and_reimport(self, farm_client, farm):
        original = ParcelFactory(farm=farm, name="Home Place", boundary=PROPERTY)
        original.refresh_from_db()
        body = farm_client.get("/data/export/parcels/?format=csv").content.decode()
        assert "POLYGON" in body

        Parcel.objects.all().delete()
        farm_client.post("/data/import/parcels/", {"file": csv_file(body), "confirm": "1"})

        restored = Parcel.objects.get(farm=farm, name="Home Place")
        assert restored.boundary.equals(original.boundary)
        assert restored.acreage == original.acreage


def _concrete_subclasses(cls):
    for sub in cls.__subclasses__():
        if not sub._meta.abstract and not sub._meta.proxy:
            yield sub
        yield from _concrete_subclasses(sub)


def test_every_farm_scoped_model_is_in_the_whole_farm_backup():
    """A model missing from MODEL_SPECS is silently dropped from every backup.

    Nothing else would notice: the backup succeeds, the restore succeeds, and
    the data is simply gone. Add a ModelSpec for any new FarmOwnedModel.
    """
    backed_up = {spec.model for spec in MODEL_SPECS}
    missing = sorted(m._meta.label for m in _concrete_subclasses(FarmOwnedModel) if m not in backed_up)
    assert missing == []
