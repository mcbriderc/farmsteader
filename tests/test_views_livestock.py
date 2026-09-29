import pytest

from apps.livestock.models import Animal
from tests.factories import AnimalFactory, FieldFactory


@pytest.mark.django_db
class TestAnimalViews:
    def test_list_requires_login(self, client):
        resp = client.get("/livestock/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        AnimalFactory(farm=farm)
        resp = farm_client.get("/livestock/")
        assert resp.status_code == 200

    def test_list_excludes_other_farm(self, farm_client, farm):
        own = AnimalFactory(farm=farm)
        other = AnimalFactory()
        resp = farm_client.get("/livestock/")
        pks = [a.pk for a in resp.context["animals"]]
        assert own.pk in pks
        assert other.pk not in pks

    def test_create_get(self, farm_client):
        resp = farm_client.get("/livestock/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        resp = farm_client.post("/livestock/add/", {
            "ear_tag": "NEW001",
            "name": "Daisy",
            "species": "cattle",
            "gender": "female",
            "repro_status": "intact",
            "status": "active",
        })
        assert resp.status_code == 302
        assert Animal.objects.filter(farm=farm, ear_tag="NEW001").exists()

    def test_detail(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        resp = farm_client.get(f"/livestock/{animal.pk}/")
        assert resp.status_code == 200

    def test_detail_other_farm_returns_404(self, farm_client):
        other = AnimalFactory()
        resp = farm_client.get(f"/livestock/{other.pk}/")
        assert resp.status_code == 404

    def test_edit(self, farm_client, farm):
        animal = AnimalFactory(farm=farm, name="Old Name")
        resp = farm_client.post(f"/livestock/{animal.pk}/edit/", {
            "ear_tag": animal.ear_tag,
            "name": "New Name",
            "species": animal.species,
            "gender": animal.gender,
            "repro_status": animal.repro_status,
            "status": animal.status,
        })
        assert resp.status_code == 302
        animal.refresh_from_db()
        assert animal.name == "New Name"

    def test_delete(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        resp = farm_client.post(f"/livestock/{animal.pk}/delete/")
        assert resp.status_code == 302
        assert not Animal.objects.filter(pk=animal.pk).exists()

    def test_list_filter_by_species(self, farm_client, farm):
        cattle = AnimalFactory(farm=farm, species=Animal.Species.CATTLE)
        sheep = AnimalFactory(farm=farm, species=Animal.Species.SHEEP)
        resp = farm_client.get("/livestock/?species=cattle")
        pks = [a.pk for a in resp.context["animals"]]
        assert cattle.pk in pks
        assert sheep.pk not in pks
