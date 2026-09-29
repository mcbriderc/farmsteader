import json

import pytest

from apps.land.models import Field
from tests.factories import FieldFactory

_BOUNDARY_GEOJSON = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [-93.6, 41.6], [-93.61, 41.6], [-93.61, 41.61],
        [-93.6, 41.61], [-93.6, 41.6],
    ]],
})


@pytest.mark.django_db
class TestFieldViews:
    def test_list_requires_login(self, client):
        resp = client.get("/land/fields/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        FieldFactory(farm=farm)
        resp = farm_client.get("/land/fields/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        own = FieldFactory(farm=farm)
        other = FieldFactory()
        resp = farm_client.get("/land/fields/")
        pks = [f.pk for f in resp.context["fields"]]
        assert own.pk in pks
        assert other.pk not in pks

    def test_create_get(self, farm_client):
        resp = farm_client.get("/land/fields/create/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        resp = farm_client.post("/land/fields/create/", {
            "name": "South Field",
            "color": "#22c55e",
            "boundary_geojson": _BOUNDARY_GEOJSON,
        })
        assert resp.status_code == 302
        assert Field.objects.filter(farm=farm, name="South Field").exists()

    def test_detail(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.get(f"/land/fields/{field.pk}/")
        assert resp.status_code == 200

    def test_detail_other_farm_returns_404(self, farm_client):
        other = FieldFactory()
        resp = farm_client.get(f"/land/fields/{other.pk}/")
        assert resp.status_code == 404

    def test_geojson_endpoint(self, farm_client, farm):
        FieldFactory(farm=farm)
        resp = farm_client.get("/land/fields/geojson/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

    def test_delete(self, farm_client, farm):
        field = FieldFactory(farm=farm)
        resp = farm_client.post(f"/land/fields/{field.pk}/delete/")
        assert resp.status_code == 302
        assert not Field.objects.filter(pk=field.pk).exists()
