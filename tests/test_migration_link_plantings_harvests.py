"""The planting <-> harvest migrations, run forwards and backwards over old-shape data.

These migrate a real (test) database to the state just before the change,
create records the way 0.5.0 stored them, then run the migrations. They are the
only check that matters for an upgrade on a farm with years of records: the
model code after the change cannot even express the old shape.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Polygon
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("land", "0003_parcel"), ("crops", "0003_add_commodity_price")]
AFTER = [("land", "0006_remove_croprecord_legacy_fields"), ("crops", "0005_move_planting_yields_and_link_harvests")]

SQUARE = Polygon(((-93.62, 41.60), (-93.60, 41.60), (-93.60, 41.62), (-93.62, 41.62), (-93.62, 41.60)), srid=4326)


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


# Real migrations need a transactional database, which is emptied afterwards --
# including rows seeded by migrations, such as the crop catalog other tests use.
# serialized_rollback puts them back.
pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@pytest.fixture
def old_world():
    """Old-shape data, migrated back to the latest schema afterwards whatever happens."""
    apps = migrate(BEFORE)
    try:
        Farm = apps.get_model("accounts", "Farm")
        Field = apps.get_model("land", "Field")
        CropRecord = apps.get_model("land", "CropRecord")
        CropType = apps.get_model("crops", "CropType")
        HarvestRecord = apps.get_model("crops", "HarvestRecord")

        farm = Farm.objects.create(name="Old Farm")
        north = Field.objects.create(farm=farm, name="North", boundary=SQUARE)
        south = Field.objects.create(farm=farm, name="South", boundary=SQUARE)
        soy, _ = CropType.objects.get_or_create(name="Soybeans")
        hay, _ = CropType.objects.get_or_create(name="Grass Hay")
        corn, _ = CropType.objects.get_or_create(name="Corn (Grain)")

        def planting(**kw):
            kw.setdefault("farm", farm)
            kw.setdefault("field", north)
            kw.setdefault("season", "2025")
            return CropRecord.objects.create(**kw)

        rec = {
            "exact": planting(crop_name="Soybeans", planted_date=date(2025, 5, 1)),
            "messy": planting(crop_name="  grass   HAY ", field=south),
            "typo": planting(crop_name="Soybean"),
            "typo2": planting(crop_name="soybean"),
            "blank": planting(crop_name="   "),
            "yield_dated": planting(crop_name="Soybeans", field=south, season="2024",
                                    harvest_date=date(2024, 10, 2), yield_amount=Decimal("1500.00"),
                                    yield_unit="bushels"),
            "yield_undated": planting(crop_name="Corn (Grain)", field=south, season="2023",
                                      yield_amount=Decimal("90.50"), yield_unit=""),
            "corn_a": planting(crop_name="Corn (Grain)", season="2022"),
            "corn_b": planting(crop_name="Corn (Grain)", season="2021"),
        }
        harvests = {
            # One soybean planting on North planted before this -> links.
            "fits": HarvestRecord.objects.create(farm=farm, field=north, crop_type=soy,
                                                 harvest_date=date(2025, 10, 1), yield_amount=50),
            # Two undated corn plantings on North -> ambiguous, stays unlinked.
            "ambiguous": HarvestRecord.objects.create(farm=farm, field=north, crop_type=corn,
                                                      harvest_date=date(2022, 10, 1), yield_amount=60),
            # Hay on North: the only hay planting is on South -> no candidate.
            "orphan": HarvestRecord.objects.create(farm=farm, field=north, crop_type=hay,
                                                   harvest_date=date(2025, 6, 1), yield_amount=3),
        }
        yield apps, farm, rec, harvests
    finally:
        migrate(AFTER)


def test_forward_migration(old_world):
    _, farm, rec, harvests = old_world
    apps = migrate(AFTER)
    CropRecord = apps.get_model("land", "CropRecord")
    CropType = apps.get_model("crops", "CropType")
    HarvestRecord = apps.get_model("crops", "HarvestRecord")

    def crop_of(key):
        return CropRecord.objects.get(pk=rec[key].pk).crop_type.name

    # Exact and case/space-insensitive matches use the existing catalog rows.
    assert crop_of("exact") == "Soybeans"
    assert crop_of("messy") == "Grass Hay"
    # A typo is NOT guessed into "Soybeans": it becomes its own catalog entry,
    # created once and shared by every planting with that name in any case.
    assert crop_of("typo") == "Soybean"
    assert crop_of("typo2") == "Soybean"
    assert CropType.objects.filter(name__iexact="soybean").count() == 1
    assert crop_of("blank") == "Unnamed crop"

    # A planting's own yield became a harvest of that planting.
    moved = HarvestRecord.objects.get(planting_id=rec["yield_dated"].pk)
    assert (moved.harvest_date, moved.yield_amount, moved.yield_unit) == (date(2024, 10, 2), Decimal("1500.00"), "bushels")
    assert moved.field_id == rec["yield_dated"].field_id
    assert moved.crop_type.name == "Soybeans"

    # No harvest date: the planting's last-edited day stands in, and the note says so.
    undated = HarvestRecord.objects.get(planting_id=rec["yield_undated"].pk)
    assert undated.harvest_date == rec["yield_undated"].updated_at.date()
    assert "last edited" in undated.notes
    assert undated.yield_unit == "bushels"  # blank unit fell back to the crop's default

    # Auto-linking only when exactly one planting fits.
    assert HarvestRecord.objects.get(pk=harvests["fits"].pk).planting_id == rec["exact"].pk
    assert HarvestRecord.objects.get(pk=harvests["ambiguous"].pk).planting_id is None
    assert HarvestRecord.objects.get(pk=harvests["orphan"].pk).planting_id is None

    # Nothing lost: every planting survived, and only the two yields were added.
    assert CropRecord.objects.filter(farm_id=farm.pk).count() == len(rec)
    assert HarvestRecord.objects.filter(farm_id=farm.pk).count() == len(harvests) + 2


def test_backward_migration_restores_the_old_shape(old_world):
    _, farm, rec, harvests = old_world
    migrate(AFTER)
    apps = migrate(BEFORE)
    CropRecord = apps.get_model("land", "CropRecord")
    HarvestRecord = apps.get_model("crops", "HarvestRecord")

    p = CropRecord.objects.get(pk=rec["yield_dated"].pk)
    assert (p.harvest_date, p.yield_amount, p.yield_unit) == (date(2024, 10, 2), Decimal("1500.00"), "bushels")
    assert CropRecord.objects.get(pk=rec["messy"].pk).crop_name == "Grass Hay"
    # The harvests the forward migration created are gone again; the originals remain.
    assert HarvestRecord.objects.filter(farm_id=farm.pk).count() == len(harvests)
