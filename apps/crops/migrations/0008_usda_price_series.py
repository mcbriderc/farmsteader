"""Point the seeded crops at the USDA price series that actually describes them.

The price sync used to query USDA by the crop's display name ("CORN (GRAIN)",
"WINTER WHEAT", "ALFALFA HAY"), which USDA does not recognise, so 9 of the 19
seeded crops never got a price. It now queries by ``usda_code``, which holds the
series name. The seeded codes were bare commodities, several shared ("CORN" for
grain, silage and sweet corn; "HAY" for both hays; "WHEAT" for both wheats).

Only a crop that still has its seeded name *and* its seeded code is changed, so
a catalog entry someone has edited is left alone. Corn silage gets no code:
USDA publishes no price received for it.

Prices already synced are a cache. National rows were stored as state "US TOTAL";
they become "US", the code the sync now writes. The next sync replaces each
crop's rows outright, which also drops anything stored from the wrong series.
"""

from django.db import migrations

#: name -> (seeded code, series)
SERIES = {
    "Alfalfa Hay": ("HAY", "HAY, ALFALFA"),
    "Corn (Grain)": ("CORN", "CORN, GRAIN"),
    "Corn (Silage)": ("CORN", ""),
    # All-cotton is national only; states report upland (~97% of US cotton) and pima.
    "Cotton": ("COTTON", "COTTON, UPLAND"),
    "Dry Beans": ("BEANS", "BEANS, DRY EDIBLE, (EXCL CHICKPEAS)"),
    "Grass Hay": ("HAY", "HAY, (EXCL ALFALFA)"),
    "Sorghum (Grain)": ("SORGHUM", "SORGHUM, GRAIN"),
    "Spring Wheat": ("WHEAT", "WHEAT, SPRING, (EXCL DURUM)"),
    "Sweet Corn": ("CORN", "SWEET CORN"),
    "Winter Wheat": ("WHEAT", "WHEAT, WINTER"),
}


def forwards(apps, schema_editor):
    CropType = apps.get_model("crops", "CropType")
    MarketPrice = apps.get_model("crops", "MarketPrice")
    for name, (seeded, series) in SERIES.items():
        CropType.objects.filter(name=name, usda_code=seeded).update(usda_code=series)
    for price in MarketPrice.objects.filter(state="US TOTAL"):
        if MarketPrice.objects.filter(crop_type_id=price.crop_type_id, year=price.year, state="US").exists():
            price.delete()
        else:
            price.state = "US"
            price.save(update_fields=["state"])


def backwards(apps, schema_editor):
    CropType = apps.get_model("crops", "CropType")
    MarketPrice = apps.get_model("crops", "MarketPrice")
    for name, (seeded, series) in SERIES.items():
        CropType.objects.filter(name=name, usda_code=series).update(usda_code=seeded)
    # State rows did not exist before; national rows go back to their old label.
    MarketPrice.objects.exclude(state="US").delete()
    MarketPrice.objects.filter(state="US").update(state="US TOTAL")


class Migration(migrations.Migration):
    dependencies = [
        ("crops", "0007_longer_usda_code"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
