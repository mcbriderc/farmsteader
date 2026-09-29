from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Farm
from apps.data_io.backup import export_farm


class Command(BaseCommand):
    help = "Write a complete backup of one farm to a zip archive."

    def add_arguments(self, parser):
        parser.add_argument("--farm", required=True, help="Farm id or exact name.")
        parser.add_argument("--output", required=True, help="Path to write the archive to.")

    def handle(self, *args, **options):
        farm = _resolve_farm(options["farm"])
        manifest = export_farm(farm, options["output"])

        total = sum(manifest["counts"].values())
        self.stdout.write(self.style.SUCCESS(
            f"Backed up {total} records and {manifest['media_files']} media files "
            f"from “{farm.name}” to {options['output']}"
        ))
        for name in manifest["missing_media"]:
            self.stdout.write(self.style.WARNING(f"Missing media file, skipped: {name}"))


def _resolve_farm(value):
    if value.isdigit():
        farm = Farm.objects.filter(pk=int(value)).first()
        if farm:
            return farm
    matches = list(Farm.objects.filter(name=value)[:2])
    if not matches:
        raise CommandError(f"No farm matching {value!r}.")
    if len(matches) > 1:
        raise CommandError(f"More than one farm is named {value!r}; use the id instead.")
    return matches[0]
