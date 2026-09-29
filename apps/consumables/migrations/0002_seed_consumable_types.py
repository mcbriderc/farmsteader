from django.db import migrations


CONSUMABLE_TYPES = [
    # Fuel
    {"name": "Diesel", "category": "Fuel", "default_unit": "gallons"},
    {"name": "Gasoline", "category": "Fuel", "default_unit": "gallons"},
    {"name": "Propane", "category": "Fuel", "default_unit": "gallons"},
    {"name": "Kerosene", "category": "Fuel", "default_unit": "gallons"},
    # Seed
    {"name": "Corn Seed", "category": "Seed", "default_unit": "lbs"},
    {"name": "Soybean Seed", "category": "Seed", "default_unit": "lbs"},
    {"name": "Wheat Seed", "category": "Seed", "default_unit": "lbs"},
    {"name": "Alfalfa Seed", "category": "Seed", "default_unit": "lbs"},
    {"name": "Grass Seed", "category": "Seed", "default_unit": "lbs"},
    {"name": "Cover Crop Seed", "category": "Seed", "default_unit": "lbs"},
    # Fertilizer
    {"name": "Urea (46-0-0)", "category": "Fertilizer", "default_unit": "lbs"},
    {"name": "DAP (18-46-0)", "category": "Fertilizer", "default_unit": "lbs"},
    {"name": "Potash (0-0-60)", "category": "Fertilizer", "default_unit": "lbs"},
    {"name": "Ammonium Nitrate (34-0-0)", "category": "Fertilizer", "default_unit": "lbs"},
    {"name": "Lime (Agricultural)", "category": "Fertilizer", "default_unit": "tons"},
    {"name": "Compost", "category": "Fertilizer", "default_unit": "yards"},
    # Chemical
    {"name": "Glyphosate", "category": "Chemical", "default_unit": "gallons"},
    {"name": "2,4-D Herbicide", "category": "Chemical", "default_unit": "gallons"},
    {"name": "Insecticide (General)", "category": "Chemical", "default_unit": "gallons"},
    {"name": "Fungicide (General)", "category": "Chemical", "default_unit": "gallons"},
    {"name": "Adjuvant / Surfactant", "category": "Chemical", "default_unit": "gallons"},
    # Medical / Veterinary
    {"name": "Dewormer (Oral)", "category": "Medical", "default_unit": "mL"},
    {"name": "Dewormer (Injectable)", "category": "Medical", "default_unit": "mL"},
    {"name": "Antibiotic (Injectable)", "category": "Medical", "default_unit": "mL"},
    {"name": "Iodine / Wound Spray", "category": "Medical", "default_unit": "oz"},
    {"name": "Fly Spray / Pour-On", "category": "Medical", "default_unit": "oz"},
    # Hardware / Supplies
    {"name": "Fencing Wire", "category": "Hardware", "default_unit": "rolls"},
    {"name": "T-Posts", "category": "Hardware", "default_unit": "units"},
    {"name": "Baling Twine", "category": "Hardware", "default_unit": "rolls"},
    {"name": "Ear Tags", "category": "Hardware", "default_unit": "units"},
    {"name": "Syringes", "category": "Hardware", "default_unit": "units"},
    # Bedding
    {"name": "Straw Bedding", "category": "Bedding", "default_unit": "bales"},
    {"name": "Wood Shavings", "category": "Bedding", "default_unit": "bags"},
    {"name": "Sand (Bedding)", "category": "Bedding", "default_unit": "tons"},
]


def seed_consumable_types(apps, schema_editor):
    ConsumableType = apps.get_model("consumables", "ConsumableType")
    for ct in CONSUMABLE_TYPES:
        ConsumableType.objects.get_or_create(name=ct["name"], defaults=ct)


def remove_consumable_types(apps, schema_editor):
    ConsumableType = apps.get_model("consumables", "ConsumableType")
    names = [ct["name"] for ct in CONSUMABLE_TYPES]
    ConsumableType.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("consumables", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_consumable_types, remove_consumable_types),
    ]
