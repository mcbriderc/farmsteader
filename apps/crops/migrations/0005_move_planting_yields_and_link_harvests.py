from django.db import migrations

#: Marks harvests this migration created, so reversing it can find exactly
#: those and fold them back into their plantings.
MOVED_NOTE = "Moved from the planting record when plantings and harvests were linked."


def move_yields_and_link(apps, schema_editor):
    CropRecord = apps.get_model("land", "CropRecord")
    HarvestRecord = apps.get_model("crops", "HarvestRecord")

    # 1. A planting's own yield becomes a harvest of that planting, so the
    #    planting fields can be dropped without losing anything. A missing
    #    harvest date falls back to the day the planting was last edited --
    #    the closest thing on record -- and the note says so.
    for p in CropRecord.objects.exclude(yield_amount=None).select_related("crop_type"):
        note = MOVED_NOTE
        harvest_date = p.harvest_date
        if harvest_date is None:
            harvest_date = p.updated_at.date()
            note += " It had no harvest date, so the date it was last edited was used."
        HarvestRecord.objects.create(
            farm_id=p.farm_id,
            field_id=p.field_id,
            crop_type_id=p.crop_type_id,
            planting=p,
            harvest_date=harvest_date,
            yield_amount=p.yield_amount,
            yield_unit=p.yield_unit or p.crop_type.default_unit or "bushels",
            notes=note,
        )

    # 2. Link existing harvests to a planting only when exactly one fits:
    #    same farm, same field, same crop, planted on or before the harvest
    #    (or with no planted date). Two candidates -- e.g. corn on the same
    #    field two years running with no planted dates -- is left for a person.
    for h in HarvestRecord.objects.filter(planting=None):
        candidates = [
            p for p in CropRecord.objects.filter(
                farm_id=h.farm_id, field_id=h.field_id, crop_type_id=h.crop_type_id,
            )
            if p.planted_date is None or p.planted_date <= h.harvest_date
        ]
        if len(candidates) == 1:
            h.planting = candidates[0]
            h.save(update_fields=["planting"])


def fold_yields_back(apps, schema_editor):
    """Reverse of step 1. Step 2 needs no reverse: 0004 drops the column."""
    HarvestRecord = apps.get_model("crops", "HarvestRecord")
    for h in HarvestRecord.objects.filter(notes__startswith=MOVED_NOTE).select_related("planting"):
        p = h.planting
        if p is not None:
            p.harvest_date = h.harvest_date
            p.yield_amount = h.yield_amount
            p.yield_unit = h.yield_unit
            p.save(update_fields=["harvest_date", "yield_amount", "yield_unit"])
        h.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crops", "0004_harvestrecord_planting"),
    ]

    operations = [
        migrations.RunPython(move_yields_and_link, fold_yields_back),
    ]
