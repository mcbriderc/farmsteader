import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Let a harvest name the planting it came from, and stop catalog deletes cascading.

    crop_type moves from CASCADE to PROTECT: CropType is shared by every farm,
    so CASCADE meant deleting a catalog entry silently deleted every farm's
    harvests of that crop.
    """

    dependencies = [
        ("crops", "0003_add_commodity_price"),
        ("land", "0005_link_planting_crop_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="harvestrecord",
            name="planting",
            field=models.ForeignKey(
                blank=True,
                help_text="The planting this harvest came from, if any",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="harvests",
                to="land.croprecord",
            ),
        ),
        migrations.AlterField(
            model_name="harvestrecord",
            name="crop_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="harvests",
                to="crops.croptype",
            ),
        ),
    ]
