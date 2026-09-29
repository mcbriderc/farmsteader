from django.db import migrations


FEED_TYPES = [
    # Hay
    {"name": "Alfalfa Hay", "category": "hay", "default_unit": "lbs"},
    {"name": "Timothy Hay", "category": "hay", "default_unit": "lbs"},
    {"name": "Orchard Grass Hay", "category": "hay", "default_unit": "lbs"},
    {"name": "Bermuda Grass Hay", "category": "hay", "default_unit": "lbs"},
    {"name": "Mixed Grass Hay", "category": "hay", "default_unit": "lbs"},
    {"name": "Clover Hay", "category": "hay", "default_unit": "lbs"},
    # Grain
    {"name": "Whole Corn", "category": "grain", "default_unit": "lbs"},
    {"name": "Cracked Corn", "category": "grain", "default_unit": "lbs"},
    {"name": "Oats", "category": "grain", "default_unit": "lbs"},
    {"name": "Barley", "category": "grain", "default_unit": "lbs"},
    {"name": "Wheat", "category": "grain", "default_unit": "lbs"},
    {"name": "Soybean Meal", "category": "grain", "default_unit": "lbs"},
    # Silage
    {"name": "Corn Silage", "category": "silage", "default_unit": "lbs"},
    {"name": "Grass Silage (Haylage)", "category": "silage", "default_unit": "lbs"},
    {"name": "Sorghum Silage", "category": "silage", "default_unit": "lbs"},
    # Pellet / Concentrate
    {"name": "Layer Feed (Poultry)", "category": "pellet", "default_unit": "lbs"},
    {"name": "Broiler Feed (Poultry)", "category": "pellet", "default_unit": "lbs"},
    {"name": "Cattle Finishing Pellets", "category": "pellet", "default_unit": "lbs"},
    {"name": "Goat/Sheep Pellets", "category": "pellet", "default_unit": "lbs"},
    {"name": "Horse Sweet Feed", "category": "pellet", "default_unit": "lbs"},
    {"name": "Pig Grower Feed", "category": "pellet", "default_unit": "lbs"},
    # Supplement / Mineral
    {"name": "Mineral Block (Cattle)", "category": "supplement", "default_unit": "lbs"},
    {"name": "Salt Lick", "category": "supplement", "default_unit": "lbs"},
    {"name": "Loose Mineral Mix", "category": "supplement", "default_unit": "lbs"},
    {"name": "Baking Soda (Rumen Buffer)", "category": "supplement", "default_unit": "lbs"},
    {"name": "Kelp Meal", "category": "supplement", "default_unit": "lbs"},
    # Fresh Forage
    {"name": "Fresh Pasture", "category": "fresh_forage", "default_unit": "lbs"},
    {"name": "Fodder (Sprouted Grain)", "category": "fresh_forage", "default_unit": "lbs"},
    {"name": "Browse / Brush", "category": "fresh_forage", "default_unit": "lbs"},
]


def seed_feed_types(apps, schema_editor):
    FeedType = apps.get_model("livestock", "FeedType")
    for ft in FEED_TYPES:
        FeedType.objects.get_or_create(name=ft["name"], defaults=ft)


def remove_feed_types(apps, schema_editor):
    FeedType = apps.get_model("livestock", "FeedType")
    names = [ft["name"] for ft in FEED_TYPES]
    FeedType.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("livestock", "0002_feedtype_feedstock_feedlog"),
    ]

    operations = [
        migrations.RunPython(seed_feed_types, remove_feed_types),
    ]
