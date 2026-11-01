"""Who can fetch an upload, and how it reaches them."""

import pathlib

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.livestock.models import VetRecord
from tests.factories import AnimalFactory, EquipmentFactory, VetRecordFactory

PHOTO = "livestock/photos/cow.png"
ATTACHMENT = "livestock/vet_attachments/lab.pdf"


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    for name in (PHOTO, ATTACHMENT, "livestock/vet_attachments/old.html", "stray.png"):
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"file bytes")
    return tmp_path


@pytest.fixture
def nginx(settings):
    settings.FARMSTEADER_SERVE_MEDIA = False


@pytest.mark.django_db
class TestWhoCanFetch:
    def test_a_member_of_the_farm_can(self, farm_client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        response = farm_client.get(f"/media/{PHOTO}")
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"file bytes"

    def test_a_visitor_is_sent_to_log_in(self, client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        response = client.get(f"/media/{PHOTO}")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_a_member_of_another_farm_cannot(self, other_farm_client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        assert other_farm_client.get(f"/media/{PHOTO}").status_code == 404

    def test_a_file_no_record_holds_is_not_served(self, farm_client, media):
        assert farm_client.get("/media/stray.png").status_code == 404

    def test_a_blank_path_does_not_match_records_without_a_file(self, farm_client, farm, media):
        AnimalFactory(farm=farm)
        assert farm_client.get("/media/").status_code == 404

    def test_cannot_escape_the_media_directory(self, farm_client, media):
        assert farm_client.get("/media/../../etc/passwd").status_code == 404

    def test_a_missing_file_is_a_404(self, farm_client, farm, media):
        AnimalFactory(farm=farm, photo="livestock/photos/gone.png")
        assert farm_client.get("/media/livestock/photos/gone.png").status_code == 404

    def test_only_reading_is_allowed(self, farm_client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        assert farm_client.post(f"/media/{PHOTO}").status_code == 405

    def test_finds_every_upload_field(self, farm_client, farm, media):
        EquipmentFactory(farm=farm, photo="stray.png")
        assert farm_client.get("/media/stray.png").status_code == 200


@pytest.mark.django_db
class TestHowItIsSent:
    def test_a_photo_opens_in_the_browser(self, farm_client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        response = farm_client.get(f"/media/{PHOTO}")
        assert response["Content-Type"] == "image/png"
        assert response["Content-Disposition"].startswith("inline")

    def test_an_attachment_always_downloads(self, farm_client, farm, media):
        VetRecordFactory(animal__farm=farm, farm=farm, attachment=ATTACHMENT)
        response = farm_client.get(f"/media/{ATTACHMENT}")
        assert response["Content-Disposition"].startswith("attachment")

    def test_an_html_attachment_from_before_the_type_limit_still_downloads(self, farm_client, farm, media):
        name = "livestock/vet_attachments/old.html"
        VetRecordFactory(animal__farm=farm, farm=farm, attachment=name)
        assert farm_client.get(f"/media/{name}")["Content-Disposition"].startswith("attachment")

    def test_browsers_are_told_not_to_guess_the_type(self, farm_client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        assert farm_client.get(f"/media/{PHOTO}")["X-Content-Type-Options"] == "nosniff"

    def test_shared_caches_may_not_keep_it(self, farm_client, farm, media):
        AnimalFactory(farm=farm, photo=PHOTO)
        assert "private" in farm_client.get(f"/media/{PHOTO}")["Cache-Control"]


@pytest.mark.django_db
class TestBehindNginx:
    def test_hands_the_file_to_nginx(self, farm_client, farm, media, nginx):
        AnimalFactory(farm=farm, photo=PHOTO)
        response = farm_client.get(f"/media/{PHOTO}")
        assert response.status_code == 200
        assert response["X-Accel-Redirect"] == f"/protected-media/{PHOTO}"
        assert response.content == b""

    def test_sets_what_nginx_keeps_from_the_response(self, farm_client, farm, media, nginx):
        VetRecordFactory(animal__farm=farm, farm=farm, attachment=ATTACHMENT)
        response = farm_client.get(f"/media/{ATTACHMENT}")
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("attachment")
        assert "private" in response["Cache-Control"]

    def test_encodes_the_path_for_nginx(self, farm_client, farm, media, nginx):
        AnimalFactory(farm=farm, photo="livestock/photos/vache é.png")
        response = farm_client.get("/media/livestock/photos/vache%20%C3%A9.png")
        assert response["X-Accel-Redirect"] == "/protected-media/livestock/photos/vache%20%C3%A9.png"

    def test_still_refuses_another_farm(self, other_farm_client, farm, media, nginx):
        AnimalFactory(farm=farm, photo=PHOTO)
        response = other_farm_client.get(f"/media/{PHOTO}")
        assert response.status_code == 404
        assert "X-Accel-Redirect" not in response

    def test_nginx_has_no_public_route_to_the_files(self):
        conf = pathlib.Path("deploy/nginx/farmsteader.conf").read_text()
        assert "location /media/" not in conf
        internal_location = conf.split("location /protected-media/ {")[1].split("}")[0]
        assert "internal;" in internal_location
        assert "nosniff" in internal_location


@pytest.mark.django_db
class TestAttachmentTypes:
    @pytest.mark.parametrize("name", ["evil.html", "evil.htm", "evil.svg", "evil.js", "evil.xml", "evil.PDF.html"])
    def test_web_formats_are_refused(self, farm, name):
        record = VetRecordFactory.build(animal=AnimalFactory(farm=farm), farm=farm)
        record.attachment = SimpleUploadedFile(name, b"<script>alert(1)</script>")
        with pytest.raises(ValidationError) as error:
            record.full_clean()
        assert "attachment" in error.value.message_dict

    @pytest.mark.parametrize("name", ["lab.pdf", "lab.PDF", "xray.jpg", "bill.xlsx", "note.txt"])
    def test_common_documents_are_accepted(self, farm, name):
        record = VetRecordFactory.build(animal=AnimalFactory(farm=farm), farm=farm)
        record.attachment = SimpleUploadedFile(name, b"file bytes")
        record.full_clean()

    def test_the_form_refuses_an_html_upload(self, farm_client, farm, media):
        animal = AnimalFactory(farm=farm)
        response = farm_client.post(
            reverse("livestock:vet_record_create", args=[animal.pk]),
            {
                "record_type": "exam",
                "date": "2026-01-01",
                "description": "x",
                "cost": "0",
                "attachment": SimpleUploadedFile("evil.html", b"<script>alert(1)</script>"),
            },
        )
        assert "attachment" in response.context["form"].errors
        assert not VetRecord.objects.exists()
