from django.db import migrations


CROP_TYPES = [
    {"name": "Corn (Grain)", "usda_code": "CORN", "category": "Grain", "default_unit": "bushels"},
    {"name": "Corn (Silage)", "usda_code": "CORN", "category": "Grain", "default_unit": "tons"},
    {"name": "Soybeans", "usda_code": "SOYBEANS", "category": "Oilseed", "default_unit": "bushels"},
    {"name": "Winter Wheat", "usda_code": "WHEAT", "category": "Grain", "default_unit": "bushels"},
    {"name": "Spring Wheat", "usda_code": "WHEAT", "category": "Grain", "default_unit": "bushels"},
    {"name": "Oats", "usda_code": "OATS", "category": "Grain", "default_unit": "bushels"},
    {"name": "Barley", "usda_code": "BARLEY", "category": "Grain", "default_unit": "bushels"},
    {"name": "Sorghum (Grain)", "usda_code": "SORGHUM", "category": "Grain", "default_unit": "bushels"},
    {"name": "Alfalfa Hay", "usda_code": "HAY", "category": "Forage", "default_unit": "tons"},
    {"name": "Grass Hay", "usda_code": "HAY", "category": "Forage", "default_unit": "tons"},
    {"name": "Cotton", "usda_code": "COTTON", "category": "Fiber", "default_unit": "bales"},
    {"name": "Rice", "usda_code": "RICE", "category": "Grain", "default_unit": "cwt"},
    {"name": "Sunflowers", "usda_code": "SUNFLOWER", "category": "Oilseed", "default_unit": "pounds"},
    {"name": "Canola", "usda_code": "CANOLA", "category": "Oilseed", "default_unit": "pounds"},
    {"name": "Dry Beans", "usda_code": "BEANS", "category": "Pulse", "default_unit": "cwt"},
    {"name": "Potatoes", "usda_code": "POTATOES", "category": "Vegetable", "default_unit": "cwt"},
    {"name": "Sweet Corn", "usda_code": "CORN", "category": "Vegetable", "default_unit": "tons"},
    {"name": "Tomatoes", "usda_code": "TOMATOES", "category": "Vegetable", "default_unit": "tons"},
    {"name": "Peanuts", "usda_code": "PEANUTS", "category": "Oilseed", "default_unit": "pounds"},
]


def seed_crop_types(apps, schema_editor):
    CropType = apps.get_model("crops", "CropType")
    for ct in CROP_TYPES:
        CropType.objects.get_or_create(name=ct["name"], defaults=ct)


def remove_crop_types(apps, schema_editor):
    CropType = apps.get_model("crops", "CropType")
    names = [ct["name"] for ct in CROP_TYPES]
    CropType.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crops", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_crop_types, remove_crop_types),
    ]
