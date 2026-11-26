"""Cost is optional on every CostMixin record: blank means 0, never an error.

The vet form used to reject an emptied cost box, so a free visit needed a typed 0.
The column itself stays NOT NULL, so every path that can leave it blank -- a form,
a CSV cell, code calling save() -- has to land on 0 rather than on an IntegrityError.
"""

import csv
import io
from decimal import Decimal

import pytest

from apps.buildings.forms import BuildingMaintenanceForm
from apps.core.models import CostMixin
from apps.crops.forms import HarvestRecordForm
from apps.equipment.forms import MaintenanceRecordForm
from apps.land.forms import CropRecordForm
from apps.livestock.forms import VetRecordForm
from apps.livestock.models import VetRecord
from tests.factories import (
    AnimalFactory,
    BuildingMaintenanceRecordFactory,
    CropRecordFactory,
    HarvestRecordFactory,
    MaintenanceRecordFactory,
    VetRecordFactory,
)

COST_FORMS = [VetRecordForm, CropRecordForm, MaintenanceRecordForm, BuildingMaintenanceForm, HarvestRecordForm]
COST_FACTORIES = [
    VetRecordFactory,
    CropRecordFactory,
    MaintenanceRecordFactory,
    BuildingMaintenanceRecordFactory,
    HarvestRecordFactory,
]


@pytest.mark.parametrize("form_class", COST_FORMS, ids=lambda f: f.__name__)
def test_cost_is_not_required_on_any_form(form_class):
    assert issubclass(form_class._meta.model, CostMixin)
    assert form_class.base_fields["cost"].required is False


@pytest.mark.django_db
@pytest.mark.parametrize("factory", COST_FACTORIES, ids=lambda f: f._meta.model.__name__)
def test_blank_cost_is_stored_as_zero(factory):
    record = factory(cost=Decimal("12.50"))
    record.cost = None
    record.full_clean()
    assert record.cost == Decimal("0")

    record.cost = None
    record.save()
    record.refresh_from_db()
    assert record.cost == Decimal("0")


@pytest.mark.django_db
class TestVetRecordViews:
    def _post(self, animal, cost=""):
        return {"record_type": "exam", "date": "2026-11-20", "description": "Free recheck", "cost": cost}

    def test_create_with_blank_cost(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        resp = farm_client.post(f"/livestock/{animal.pk}/vet/add/", self._post(animal))
        assert resp.status_code == 302
        assert VetRecord.objects.get(animal=animal).cost == Decimal("0")

    def test_edit_clearing_cost(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        record = VetRecordFactory(farm=farm, animal=animal, cost=Decimal("80.00"))
        resp = farm_client.post(f"/livestock/{animal.pk}/vet/{record.pk}/edit/", self._post(animal))
        assert resp.status_code == 302
        record.refresh_from_db()
        assert record.cost == Decimal("0")

    def test_typed_cost_still_saved(self, farm_client, farm):
        animal = AnimalFactory(farm=farm)
        farm_client.post(f"/livestock/{animal.pk}/vet/add/", self._post(animal, cost="45.25"))
        assert VetRecord.objects.get(animal=animal).cost == Decimal("45.25")


@pytest.mark.django_db
def test_csv_import_with_empty_cost_cell(farm_client, farm):
    animal = AnimalFactory(farm=farm)
    VetRecordFactory(farm=farm, animal=animal, cost=Decimal("30.00"))
    exported = farm_client.get("/data/export/vet_records/?format=csv").content.decode()

    rows = list(csv.DictReader(io.StringIO(exported)))
    assert len(rows) == 1
    rows[0]["cost"] = ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    VetRecord.objects.all().delete()
    f = io.BytesIO(out.getvalue().encode())
    f.name = "vet.csv"
    farm_client.post("/data/import/vet_records/", {"file": f, "confirm": "1"})

    assert VetRecord.objects.get(animal=animal).cost == Decimal("0")
