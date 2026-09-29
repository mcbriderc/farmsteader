import pytest

from tests.factories import FarmFactory, FarmMembershipFactory, UserFactory


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def farm(db):
    return FarmFactory()


@pytest.fixture
def membership(user, farm):
    return FarmMembershipFactory(user=user, farm=farm)


@pytest.fixture
def farm_client(client, user, farm, membership):
    """Authenticated client with a farm set in the session."""
    client.force_login(user)
    session = client.session
    session["current_farm_id"] = farm.pk
    session.save()
    return client


@pytest.fixture
def other_farm(db):
    return FarmFactory()


@pytest.fixture
def other_farm_client(client, other_farm):
    """Authenticated client belonging to a different farm."""
    other_user = UserFactory()
    FarmMembershipFactory(user=other_user, farm=other_farm)
    client.force_login(other_user)
    session = client.session
    session["current_farm_id"] = other_farm.pk
    session.save()
    return client
