"""Whole-farm backup and restore.

Produces a single self-contained zip archive holding every record belonging to one farm —
including PostGIS geometry, uploaded media, and exact timestamps — and restores it into a
brand new farm on any FarmSteader install.

This is deliberately separate from the per-model CSV/XLSX flow in ``resources.py``: CSV cannot
carry geometry, media, or a faithful foreign-key graph. See DOCS.md for the archive format.
"""

import hashlib
import json
import posixpath
import zipfile
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, time as dt_time, timezone as dt_timezone

import django
from django.conf import settings
from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction

from apps.accounts.models import Farm, FarmMembership, FarmSettings
from apps.buildings.models import Building, BuildingMaintenanceRecord
from apps.consumables.models import ConsumableType, InventoryItem, InventoryTransaction
from apps.crops.models import CropType, HarvestRecord
from apps.employment.models import Employee, Task, TimeEntry
from apps.equipment.models import Equipment, MaintenanceRecord
from apps.land.models import CropRecord, Field, SoilSample
from apps.livestock.models import Animal, FeedLog, FeedStock, FeedType, FieldMovement, VetRecord
from apps.produce.models import ProduceItem, ProduceTransaction

FORMAT = "farmsteader-backup"
FORMAT_VERSION = 1

MANIFEST_NAME = "manifest.json"
DATA_NAME = "data.json"
MEDIA_PREFIX = "media/"

#: Fields never carried in the archive: the pk is remapped on restore and ``farm`` is
#: reassigned to the newly created farm.
_SKIPPED_FIELDS = frozenset({"id", "farm"})

_TIMESTAMP_FIELDS = ("created_at", "updated_at")


class BackupError(Exception):
    """Base class for backup/restore failures."""


class RestoreError(BackupError):
    """Raised when an archive cannot be restored. Carries every problem found, not just the first."""

    def __init__(self, errors, dropped_fields=None):
        self.errors = list(errors)
        self.dropped_fields = dropped_fields or {}
        super().__init__("; ".join(self.errors))


# ---------------------------------------------------------------------------
# Model specs — ordered so every FK target is written before its dependents
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelSpec:
    model: type[models.Model]
    #: FK name -> global catalog model. Stored by ``name`` instead of pk, because these
    #: catalogs ship as seed-data migrations and have their own ids on every install.
    natural_fks: dict = dataclass_field(default_factory=dict)
    #: FK names written in a second pass, after this model's own ids exist (self-references).
    deferred: tuple = ()

    @property
    def label(self):
        return self.model._meta.label


MODEL_SPECS = (
    ModelSpec(FarmSettings),
    ModelSpec(Field),
    ModelSpec(Animal, deferred=("current_field", "sire", "dam")),
    ModelSpec(SoilSample),
    ModelSpec(CropRecord),
    ModelSpec(HarvestRecord, natural_fks={"crop_type": CropType}),
    ModelSpec(VetRecord),
    ModelSpec(FieldMovement),
    ModelSpec(FeedStock, natural_fks={"feed_type": FeedType}),
    ModelSpec(FeedLog),
    ModelSpec(Equipment),
    ModelSpec(MaintenanceRecord),
    ModelSpec(Building),
    ModelSpec(BuildingMaintenanceRecord),
    ModelSpec(InventoryItem, natural_fks={"consumable_type": ConsumableType}),
    ModelSpec(InventoryTransaction),
    ModelSpec(Employee),
    ModelSpec(Task),
    ModelSpec(TimeEntry),
    ModelSpec(ProduceItem),
    ModelSpec(ProduceTransaction),
)

SPECS_BY_LABEL = {spec.label: spec for spec in MODEL_SPECS}

#: Global catalogs referenced by ``natural_fks``. Their rows travel with the archive so a
#: restore still works if a later release renamed or dropped a seed entry.
CATALOG_MODELS = (CropType, FeedType, ConsumableType)
_CATALOG_FIELDS = {
    CropType._meta.label: ("name", "usda_code", "category", "default_unit"),
    FeedType._meta.label: ("name", "category", "default_unit"),
    ConsumableType._meta.label: ("name", "category", "default_unit"),
}


class ArchiveJSONEncoder(DjangoJSONEncoder):
    """DjangoJSONEncoder, but without its millisecond truncation.

    ``DjangoJSONEncoder`` clips datetimes to three decimal places for ECMA-262 compatibility,
    which would quietly drop sub-millisecond precision from every ``created_at`` in a backup.
    A backup has no such compatibility constraint, so emit the full ISO 8601 value.
    """

    def default(self, o):
        if isinstance(o, (datetime, dt_time)):
            return o.isoformat()
        return super().default(o)


def _exported_fields(model):
    """Concrete fields carried in the archive, in a stable order."""
    return [f for f in model._meta.concrete_fields if f.name not in _SKIPPED_FIELDS]


def _exported_field_names(model):
    return [f.name for f in _exported_fields(model)]


def app_version():
    try:
        from config.__version__ import __version__

        return __version__
    except ImportError:
        return "unknown"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _serialize_value(obj, f, spec, media_names):
    name = f.name
    if name in spec.natural_fks:
        related = getattr(obj, name)
        return getattr(related, "name") if related else None
    if f.many_to_one or f.one_to_one:
        return getattr(obj, f.attname)
    if isinstance(f, GeometryField):
        geom = getattr(obj, name)
        return {"srid": geom.srid, "geojson": json.loads(geom.geojson)} if geom else None
    if isinstance(f, models.FileField):
        stored = getattr(obj, name).name or ""
        if stored:
            media_names.add(stored)
        return stored
    return getattr(obj, name)


def _serialize_row(obj, spec, media_names):
    row = {"id": obj.pk}
    for f in _exported_fields(spec.model):
        row[f.name] = _serialize_value(obj, f, spec, media_names)
    return row


def _collect_catalog_rows(data):
    """Gather the full rows of every catalog entry referenced by the exported data."""
    catalogs = {}
    for spec in MODEL_SPECS:
        rows = data.get(spec.label) or []
        for fk_name, catalog_model in spec.natural_fks.items():
            label = catalog_model._meta.label
            used = {row[fk_name] for row in rows if row.get(fk_name)}
            if not used:
                continue
            fields = _CATALOG_FIELDS[label]
            existing = {entry["name"] for entry in catalogs.setdefault(label, [])}
            for entry in catalog_model.objects.filter(name__in=used).values(*fields):
                if entry["name"] not in existing:
                    catalogs[label].append(entry)
                    existing.add(entry["name"])
    return catalogs


def _write_media(zf, media_names):
    """Copy referenced media into the archive. A missing file warns, never aborts a backup."""
    written, total_bytes, missing = 0, 0, []
    for name in sorted(media_names):
        try:
            with default_storage.open(name, "rb") as fh:
                payload = fh.read()
        except (OSError, ValueError, SuspiciousFileOperation):
            missing.append(name)
            continue
        zf.writestr(MEDIA_PREFIX + name, payload)
        written += 1
        total_bytes += len(payload)
    return written, total_bytes, missing


def export_farm(farm, dest_path):
    """Write a complete backup of ``farm`` to ``dest_path``. Returns the manifest dict."""
    data = {}
    counts = {}
    media_names = set()

    for spec in MODEL_SPECS:
        rows = [
            _serialize_row(obj, spec, media_names)
            for obj in spec.model.objects.filter(farm=farm).order_by("pk").iterator(chunk_size=2000)
        ]
        data[spec.label] = rows
        counts[spec.label] = len(rows)

    data["catalogs"] = _collect_catalog_rows(data)

    payload = json.dumps(data, cls=ArchiveJSONEncoder, indent=1, sort_keys=True).encode()

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(DATA_NAME, payload)
        media_count, media_bytes, missing = _write_media(zf, media_names)
        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "app_version": app_version(),
            "django_version": django.get_version(),
            "exported_at": datetime.now(dt_timezone.utc).isoformat(),
            "farm": {"name": farm.name, "address": farm.address},
            "counts": counts,
            "schema": {spec.label: _exported_field_names(spec.model) for spec in MODEL_SPECS},
            "media_files": media_count,
            "media_bytes": media_bytes,
            "missing_media": missing,
            "data_sha256": hashlib.sha256(payload).hexdigest(),
        }
        # Written last so a truncated archive is missing its manifest and fails fast.
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=1))

    return manifest


# ---------------------------------------------------------------------------
# Restore — Phase A: validate without touching the database
# ---------------------------------------------------------------------------

def _max_restore_bytes():
    return getattr(settings, "FARMSTEADER_MAX_RESTORE_BYTES", 2 * 1024**3)


def _member_is_safe(name):
    """Reject absolute paths, traversal, and anything outside the known layout (zip slip)."""
    if not name or name.startswith("/") or "\\" in name or ":" in name:
        return False
    normalized = posixpath.normpath(name)
    if normalized.startswith("../") or normalized in ("..", "."):
        return False
    if normalized in (MANIFEST_NAME, DATA_NAME):
        return True
    return normalized.startswith(MEDIA_PREFIX) and len(normalized) > len(MEDIA_PREFIX)


def _validate_members(zf, errors):
    total = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        if not _member_is_safe(info.filename):
            errors.append(f"Unsafe path in archive: {info.filename!r}")
            continue
        total += info.file_size
    limit = _max_restore_bytes()
    if total > limit:
        errors.append(f"Archive expands to {total} bytes, over the {limit} byte limit.")


def _read_manifest(zf, errors):
    try:
        manifest = json.loads(zf.read(MANIFEST_NAME))
    except KeyError:
        errors.append("Archive has no manifest.json — this is not a FarmSteader backup.")
        return None
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError both derive from it
        errors.append(f"manifest.json is not valid JSON: {exc}")
        return None

    if manifest.get("format") != FORMAT:
        errors.append("Archive is not a FarmSteader backup.")
        return None
    version = manifest.get("format_version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        errors.append(
            f"Archive format version {version} is newer than this install supports "
            f"({FORMAT_VERSION}). Upgrade FarmSteader before restoring."
        )
        return None
    return manifest


def _read_data(zf, manifest, errors):
    try:
        raw = zf.read(DATA_NAME)
    except KeyError:
        errors.append("Archive has no data.json.")
        return None
    expected = manifest.get("data_sha256")
    if expected and hashlib.sha256(raw).hexdigest() != expected:
        errors.append("data.json checksum does not match the manifest — the archive is corrupt.")
        return None
    try:
        return json.loads(raw)
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError both derive from it
        errors.append(f"data.json is not valid JSON: {exc}")
        return None


def _reconcile_schema(schema, errors, warnings):
    """Diff the archive's field lists against the live models.

    Returns the fields present in the archive but not in this version's models. Dropping them
    silently is how a "successful" restore quietly loses data, so the caller must opt in.
    """
    dropped = {}
    for label, archived in sorted(schema.items()):
        spec = SPECS_BY_LABEL.get(label)
        if spec is None:
            errors.append(f"Archive contains unknown model {label!r} — it is from a newer release.")
            continue

        live = {f.name: f for f in _exported_fields(spec.model)}
        extra = sorted(set(archived) - set(live))
        if extra:
            dropped[label] = extra

        for name in sorted(set(live) - set(archived)):
            f = live[name]
            if f.has_default() or f.null or f.empty_strings_allowed:
                warnings.append(f"{label}.{name} is not in the archive; it will take its default.")
            else:
                errors.append(
                    f"{label}.{name} is required but missing from the archive, which predates it."
                )
    return dropped


def _remapped_fks(spec):
    """FK fields on this model whose target is remapped through the id map."""
    for f in _exported_fields(spec.model):
        if (f.many_to_one or f.one_to_one) and f.name not in spec.natural_fks:
            if f.related_model._meta.label in SPECS_BY_LABEL:
                yield f


def _check_field_references(spec, f, rows, known_ids, errors, warnings):
    target = f.related_model._meta.label
    for row in rows:
        value = row.get(f.name)
        if value is None or value in known_ids:
            continue
        where = f"{spec.label} id={row.get('id')} .{f.name} -> {target} id={value}"
        if f.null:
            warnings.append(f"{where} is outside this farm; it will be cleared.")
        else:
            errors.append(f"{where} is outside this farm and the field is required.")


def _validate_references(data, errors, warnings):
    """Check every foreign key points at something the archive actually carries.

    Nothing in the schema stops one farm's row from referencing another farm's row (e.g. a
    FeedLog whose animal belongs elsewhere), so an archive can legitimately contain a dangling
    reference. Catch it here and say which record is at fault, rather than letting Postgres
    raise a bare NOT NULL violation halfway through the restore.
    """
    known = {spec.label: {row.get("id") for row in (data.get(spec.label) or [])}
             for spec in MODEL_SPECS}

    for spec in MODEL_SPECS:
        rows = data.get(spec.label) or []
        for f in _remapped_fks(spec):
            target = f.related_model._meta.label
            _check_field_references(spec, f, rows, known[target], errors, warnings)


# ---------------------------------------------------------------------------
# Restore — Phase B: write
# ---------------------------------------------------------------------------

@dataclass
class RestoreReport:
    farm: Farm
    counts: dict
    warnings: list
    dropped_fields: dict
    media_restored: int


def _unique_farm_name(name):
    candidate = (name or "Restored Farm").strip() or "Restored Farm"
    if not Farm.objects.filter(name=candidate).exists():
        return candidate
    base = f"{candidate} (restored)"
    if not Farm.objects.filter(name=base).exists():
        return base
    n = 2
    while Farm.objects.filter(name=f"{base} {n}").exists():
        n += 1
    return f"{base} {n}"


def _restore_catalogs(catalogs):
    """Map catalog name -> live pk, creating any entry this install does not have."""
    resolved = {}
    for catalog_model in CATALOG_MODELS:
        label = catalog_model._meta.label
        by_name = dict(catalog_model.objects.values_list("name", "pk"))
        for entry in catalogs.get(label, []) or []:
            name = entry.get("name")
            if name and name not in by_name:
                defaults = {k: v for k, v in entry.items() if k != "name"}
                obj, _ = catalog_model.objects.get_or_create(name=name, defaults=defaults)
                by_name[name] = obj.pk
        resolved[label] = by_name
    return resolved


def _deserialize_value(f, value):
    if value is None:
        return None
    if isinstance(f, GeometryField):
        return GEOSGeometry(json.dumps(value["geojson"]), srid=value.get("srid", 4326))
    if isinstance(f, models.FileField):
        return value or ""
    if isinstance(f, models.JSONField):
        return value
    return f.to_python(value)


def _build_instance(spec, row, ctx):
    """Build (unsaved) one instance, remapping every foreign key through the id map."""
    model = spec.model
    kwargs = {"farm_id": ctx["farm_id"]}

    for f in _exported_fields(model):
        name = f.name
        if name not in row or name in spec.deferred:
            continue
        value = row[name]

        if name in spec.natural_fks:
            catalog_label = spec.natural_fks[name]._meta.label
            kwargs[f.attname] = ctx["catalogs"][catalog_label].get(value)
        elif f.many_to_one or f.one_to_one:
            kwargs[f.attname] = ctx["id_map"].get(f.related_model._meta.label, {}).get(value)
        else:
            kwargs[name] = _deserialize_value(f, value)

    return model(**kwargs)


def _apply_deferred(spec, objs, rows, ctx):
    if not spec.deferred:
        return
    for obj, row in zip(objs, rows):
        for name in spec.deferred:
            f = spec.model._meta.get_field(name)
            old = row.get(name)
            setattr(obj, f.attname, ctx["id_map"].get(f.related_model._meta.label, {}).get(old))
    spec.model.objects.bulk_update(objs, list(spec.deferred))


def _restore_timestamps(spec, objs, rows):
    """Re-apply the original created_at/updated_at.

    ``bulk_create`` runs ``pre_save``, so auto_now/auto_now_add stamp "now" over the archived
    values. ``bulk_update`` does not run ``pre_save``, so a second pass sticks.
    """
    names = [n for n in _TIMESTAMP_FIELDS if n in {f.name for f in _exported_fields(spec.model)}]
    if not names:
        return
    for obj, row in zip(objs, rows):
        for name in names:
            if row.get(name):
                setattr(obj, name, spec.model._meta.get_field(name).to_python(row[name]))
    spec.model.objects.bulk_update(objs, names)


def _restore_model(spec, rows, ctx):
    """Create every row for one model. Returns the created instances, in archive order.

    ``bulk_create`` is load-bearing: it bypasses ``Model.save()``, so the quantity side effects
    on InventoryTransaction/ProduceTransaction/FeedLog and the current_field rewrite in
    FieldMovement do not re-fire. Quantities restore to exactly their archived values.
    Field.save()'s acreage/centroid maths is skipped for the same reason, which is why those
    columns are archived and written verbatim.
    """
    if not rows:
        return []
    objs = [_build_instance(spec, row, ctx) for row in rows]
    created = spec.model.objects.bulk_create(objs)

    ctx["id_map"][spec.label] = {
        row["id"]: obj.pk for row, obj in zip(rows, created) if row.get("id") is not None
    }
    _apply_deferred(spec, created, rows, ctx)
    _restore_timestamps(spec, created, rows)
    return created


def _restore_one_file(zf, stored):
    """Save a single archived file, returning the name storage actually used.

    Storage appends a suffix when the name is taken, which happens whenever an archive is
    restored into an install that already holds that file. Returns ``None`` when the archive
    has no such member.
    """
    try:
        payload = zf.read(MEDIA_PREFIX + stored)
    except KeyError:
        return None
    return default_storage.save(stored, ContentFile(payload))


def _restore_object_files(zf, obj, row, file_fields):
    """Restore every file field on one object. Returns (files written, name was rewritten)."""
    written, touched = 0, False
    for name in file_fields:
        stored = row.get(name)
        if not stored:
            continue
        actual = _restore_one_file(zf, stored)
        if actual is None:
            continue
        written += 1
        if actual != stored:
            setattr(obj, name, actual)
            touched = True
    return written, touched


def _restore_media(zf, spec, objs, rows):
    """Write archived media back through default_storage, honouring the name it hands back."""
    file_fields = [f.name for f in _exported_fields(spec.model) if isinstance(f, models.FileField)]
    if not file_fields or not objs:
        return 0

    changed, restored = [], 0
    for obj, row in zip(objs, rows):
        written, touched = _restore_object_files(zf, obj, row, file_fields)
        restored += written
        if touched:
            changed.append(obj)

    if changed:
        spec.model.objects.bulk_update(changed, file_fields)
    return restored


def restore_farm(archive_path, user, farm_name=None, allow_dropped_fields=False):
    """Restore an archive into a brand new farm owned by ``user``.

    Never modifies an existing farm. Raises ``RestoreError`` with every problem found if the
    archive cannot be restored.
    """
    errors, warnings = [], []

    try:
        zf = zipfile.ZipFile(archive_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise RestoreError([f"Not a readable zip archive: {exc}"]) from exc

    with zf:
        _validate_members(zf, errors)
        manifest = _read_manifest(zf, errors) if not errors else None
        if manifest is None:
            raise RestoreError(errors or ["Archive could not be validated."])

        data = _read_data(zf, manifest, errors)
        if data is None:
            raise RestoreError(errors)

        dropped = _reconcile_schema(manifest.get("schema") or {}, errors, warnings)
        _validate_references(data, errors, warnings)
        if dropped and not allow_dropped_fields:
            names = ", ".join(f"{k}.{v}" for k, vals in dropped.items() for v in vals)
            errors.append(
                "The archive was made by a newer FarmSteader and holds fields this version "
                f"does not have ({names}). Restoring would discard them."
            )
        if errors:
            raise RestoreError(errors, dropped_fields=dropped)

        report = _do_restore(zf, manifest, data, user, farm_name, warnings, dropped)

    return report


@transaction.atomic
def _do_restore(zf, manifest, data, user, farm_name, warnings, dropped):
    archived_farm = manifest.get("farm") or {}
    farm = Farm.objects.create(
        name=_unique_farm_name(farm_name or archived_farm.get("name")),
        address=archived_farm.get("address", ""),
    )
    FarmMembership.objects.create(user=user, farm=farm, role=FarmMembership.Role.OWNER)

    ctx = {
        "farm_id": farm.pk,
        "id_map": {},
        "catalogs": _restore_catalogs(data.get("catalogs") or {}),
    }

    counts, media_restored = {}, 0
    for spec in MODEL_SPECS:
        rows = data.get(spec.label) or []
        created = _restore_model(spec, rows, ctx)
        counts[spec.label] = len(created)
        media_restored += _restore_media(zf, spec, created, rows)

    if not FarmSettings.objects.filter(farm=farm).exists():
        FarmSettings.objects.create(farm=farm)

    return RestoreReport(
        farm=farm,
        counts=counts,
        warnings=warnings,
        dropped_fields=dropped,
        media_restored=media_restored,
    )


def farm_counts(farm):
    """[(label, count), …] for every model in a backup — used by the backup page."""
    return [
        (spec.model._meta.verbose_name_plural.title(), spec.model.objects.filter(farm=farm).count())
        for spec in MODEL_SPECS
    ]
