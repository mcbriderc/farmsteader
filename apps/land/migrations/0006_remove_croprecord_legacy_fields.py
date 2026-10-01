import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Last step: every planting now has a crop_type (0005) and its yield lives on
    harvests (crops 0005), so the free-text name and the planting-level yield
    fields go, and crop_type becomes required.
    """

    dependencies = [
        ("crops", "0005_move_planting_yields_and_link_harvests"),
        ("land", "0005_link_planting_crop_names"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="croprecord",
            options={"ordering": ["-season", "crop_type__name"]},
        ),
        # A default first, purely for the reverse: undoing the RemoveField
        # re-adds crop_name as NOT NULL, which existing rows could not satisfy
        # without one. Reversing 0005 then fills in the real names.
        migrations.AlterField(
            model_name="croprecord",
            name="crop_name",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.RemoveField(model_name="croprecord", name="crop_name"),
        migrations.RemoveField(model_name="croprecord", name="harvest_date"),
        migrations.RemoveField(model_name="croprecord", name="yield_amount"),
        migrations.RemoveField(model_name="croprecord", name="yield_unit"),
        migrations.AlterField(
            model_name="croprecord",
            name="crop_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plantings",
                to="crops.croptype",
            ),
        ),
    ]
