from django.db import migrations

#: Used when a planting's free-text name is blank after trimming.
UNNAMED = "Unnamed crop"


def link_crop_names(apps, schema_editor):
    """Point every planting at a catalog CropType, matched from its free-text name.

    Matching ignores case and surrounding whitespace, so "soybeans " finds
    "Soybeans". A name with no match is added to the catalog rather than
    dropped or left unlinked: nothing is lost, and it can be renamed or merged
    afterwards from Crops > Crop Types. Deliberately no fuzzy matching --
    guessing that "Corn" meant "Corn (Grain)" rather than "Sweet Corn" would
    silently mislabel a farm's records.

    Oldest planting first, so when the same unmatched name appears in several
    spellings ("Soybean", "soybean") the catalog keeps the first one entered.
    """
    CropRecord = apps.get_model("land", "CropRecord")
    CropType = apps.get_model("crops", "CropType")

    catalog = {ct.name.strip().lower(): ct for ct in CropType.objects.all()}
    for record in CropRecord.objects.filter(crop_type__isnull=True).order_by("pk"):
        name = " ".join((record.crop_name or "").split()) or UNNAMED
        crop_type = catalog.get(name.lower())
        if crop_type is None:
            crop_type = CropType.objects.create(name=name)
            catalog[name.lower()] = crop_type
        record.crop_type = crop_type
        record.save(update_fields=["crop_type"])


def restore_crop_names(apps, schema_editor):
    CropRecord = apps.get_model("land", "CropRecord")
    for record in CropRecord.objects.select_related("crop_type").exclude(crop_type=None):
        record.crop_name = record.crop_type.name
        record.save(update_fields=["crop_name"])


class Migration(migrations.Migration):
    dependencies = [
        ("land", "0004_croprecord_crop_type"),
    ]

    operations = [
        migrations.RunPython(link_crop_names, restore_crop_names),
    ]
