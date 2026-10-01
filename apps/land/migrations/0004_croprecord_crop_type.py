import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 1 of linking plantings to the crop catalog: add the link, nullable.

    It becomes required in 0006, once 0005 has filled it for every existing
    planting.
    """

    dependencies = [
        ("crops", "0003_add_commodity_price"),
        ("land", "0003_parcel"),
    ]

    operations = [
        migrations.AddField(
            model_name="croprecord",
            name="crop_type",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plantings",
                to="crops.croptype",
            ),
        ),
    ]
