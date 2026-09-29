from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.data_io.backup import RestoreError, restore_farm


class Command(BaseCommand):
    help = "Restore a farm backup archive into a new farm. Never modifies an existing farm."

    def add_arguments(self, parser):
        parser.add_argument("archive", help="Path to the backup zip.")
        parser.add_argument("--owner", required=True, help="Username to own the restored farm.")
        parser.add_argument("--farm-name", help="Name for the new farm (defaults to the archive's).")
        parser.add_argument(
            "--allow-dropped-fields",
            action="store_true",
            help="Restore even if the archive holds fields this version does not have, "
                 "discarding them.",
        )

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["owner"]).first()
        if user is None:
            raise CommandError(f"No user named {options['owner']!r}.")

        try:
            report = restore_farm(
                options["archive"],
                user,
                farm_name=options.get("farm_name"),
                allow_dropped_fields=options["allow_dropped_fields"],
            )
        except RestoreError as exc:
            for error in exc.errors:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError("Restore aborted; nothing was written.") from exc

        for warning in report.warnings:
            self.stdout.write(self.style.WARNING(warning))
        for label, count in sorted(report.counts.items()):
            if count:
                self.stdout.write(f"  {label}: {count}")

        self.stdout.write(self.style.SUCCESS(
            f"Restored {sum(report.counts.values())} records and {report.media_restored} media "
            f"files into new farm “{report.farm.name}” (id {report.farm.pk}), owned by {user}."
        ))
