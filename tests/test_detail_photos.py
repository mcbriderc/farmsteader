"""Uploaded photos and vet attachments appear on the detail pages."""

import pytest
from django.urls import reverse

from tests.factories import AnimalFactory, BuildingFactory, EquipmentFactory, VetRecordFactory

DETAIL_PAGES = [
    (AnimalFactory, "livestock:animal_detail", {"ear_tag": "<b>C1</b>"}),
    (EquipmentFactory, "equipment:equipment_detail", {"name": "<b>C1</b>"}),
    (BuildingFactory, "buildings:building_detail", {"name": "<b>C1</b>"}),
]


@pytest.mark.parametrize("factory,url_name,fields", DETAIL_PAGES)
class TestDetailPhoto:
    def test_shows_the_photo_and_links_to_the_full_size_file(self, farm_client, farm, factory, url_name, fields):
        obj = factory(farm=farm, photo="photos/cow.png", **fields)
        html = farm_client.get(reverse(url_name, args=[obj.pk])).content.decode()
        assert '<img src="/media/photos/cow.png"' in html
        assert '<a href="/media/photos/cow.png" target="_blank" rel="noopener"' in html

    def test_shows_nothing_without_a_photo(self, farm_client, farm, factory, url_name, fields):
        obj = factory(farm=farm, **fields)
        assert "<img" not in farm_client.get(reverse(url_name, args=[obj.pk])).content.decode()

    def test_alt_text_is_escaped(self, farm_client, farm, factory, url_name, fields):
        obj = factory(farm=farm, photo="photos/cow.png", **fields)
        html = farm_client.get(reverse(url_name, args=[obj.pk])).content.decode()
        assert 'alt="Photo of &lt;b&gt;C1&lt;/b&gt;"' in html


class TestVetAttachment:
    def test_links_to_the_file_as_a_download(self, farm_client, farm):
        record = VetRecordFactory(animal__farm=farm, farm=farm, attachment="livestock/vet_attachments/lab.pdf")
        html = farm_client.get(reverse("livestock:animal_detail", args=[record.animal.pk])).content.decode()
        assert '<a href="/media/livestock/vet_attachments/lab.pdf" download' in html

    def test_shows_nothing_without_an_attachment(self, farm_client, farm):
        record = VetRecordFactory(animal__farm=farm, farm=farm)
        html = farm_client.get(reverse("livestock:animal_detail", args=[record.animal.pk])).content.decode()
        assert ">Attachment</a>" not in html
