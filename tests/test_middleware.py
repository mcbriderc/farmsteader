import pytest

from tests.factories import FarmFactory, FarmMembershipFactory, UserFactory


@pytest.mark.django_db
class TestCurrentFarmMiddleware:
    """Tests for CurrentFarmMiddleware — farm loading and access control."""

    def test_unauthenticated_request_redirects_to_login(self, client):
        resp = client.get("/equipment/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp["Location"]

    def test_authenticated_no_farm_redirects_to_farm_select(self, client, db):
        user = UserFactory()
        client.force_login(user)
        resp = client.get("/equipment/")
        assert resp.status_code == 302
        assert "/accounts/farm/select/" in resp["Location"]

    def test_authenticated_with_farm_in_session_allows_access(self, farm_client):
        resp = farm_client.get("/equipment/")
        assert resp.status_code == 200

    def test_exempt_path_not_redirected_without_farm(self, client, db):
        user = UserFactory()
        client.force_login(user)
        # /accounts/ is exempt — should reach the view, not be redirected to farm_select
        resp = client.get("/accounts/farm/select/")
        assert resp.status_code == 200

    def test_invalid_farm_id_cleared_from_session(self, client, db):
        user = UserFactory()
        client.force_login(user)
        session = client.session
        session["current_farm_id"] = 99999  # non-existent farm
        session.save()
        resp = client.get("/equipment/")
        # Session should be cleared and user redirected to farm_select
        assert resp.status_code == 302
        assert "/accounts/farm/select/" in resp["Location"]
        assert "current_farm_id" not in client.session

    def test_farm_must_belong_to_user(self, client, db):
        user = UserFactory()
        other_farm = FarmFactory()  # user is not a member
        client.force_login(user)
        session = client.session
        session["current_farm_id"] = other_farm.pk
        session.save()
        resp = client.get("/equipment/")
        assert resp.status_code == 302
        assert "/accounts/farm/select/" in resp["Location"]
