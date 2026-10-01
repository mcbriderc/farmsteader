import os
import tempfile
from datetime import datetime, timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_http_methods
from tablib import Dataset

from .backup import RestoreError, export_farm, farm_counts, restore_farm
from .resources import FARM_SCOPED_KEYS, RESOURCE_REGISTRY

URL_INDEX = "data_io:index"
URL_IMPORT = "data_io:import"
URL_BACKUP = "data_io:backup"
IMPORT_TEMPLATE = "data_io/import.html"
BACKUP_TEMPLATE = "data_io/backup.html"


def _load_dataset(file):
    """Load a tablib Dataset from an uploaded file. Returns (dataset, error_msg)."""
    fmt = file.name.rsplit(".", 1)[-1].lower()
    if fmt not in ("csv", "xlsx"):
        return None, "Only CSV and XLSX files are supported."
    dataset = Dataset()
    try:
        if fmt == "csv":
            dataset.load(file.read().decode("utf-8"), format="csv")
        else:
            dataset.load(file.read(), format="xlsx")
    except Exception as e:
        return None, f"Could not read file: {e}"
    return dataset, None


def _inject_farm_column(dataset, farm_pk):
    """Ensure every row in dataset has the correct farm_pk."""
    if "farm" not in dataset.headers:
        dataset.append_col([farm_pk] * len(dataset), header="farm")
    else:
        farm_idx = dataset.headers.index("farm")
        for i in range(len(dataset)):
            row = list(dataset[i])
            row[farm_idx] = farm_pk
            dataset[i] = tuple(row)


def _build_resource(resource_class, resource_key, farm):
    """Farm-scoped resources need the farm so their lookups cannot reach across tenants."""
    if resource_key in FARM_SCOPED_KEYS:
        return resource_class(farm=farm)
    return resource_class()


def _collect_error_messages(result):
    """Row errors *and* validation failures, as one list for the page.

    import-export keeps them apart: an exception (a failed lookup) is a row
    error, while a widget or model rejecting a value is an invalid row. Only
    the first used to be shown, so a row with, say, a malformed boundary was
    skipped in silence and the success message counted around it.
    """
    msgs = []
    for row_num, errors in result.row_errors():
        for error in errors:
            msgs.append(f"Row {row_num}: {error.error}")
    for invalid in result.invalid_rows:
        for field, field_errors in invalid.field_specific_errors.items():
            for message in field_errors:
                msgs.append(f"Row {invalid.number}: {field}: {message}")
        for message in invalid.non_field_specific_errors:
            msgs.append(f"Row {invalid.number}: {message}")
    return msgs[:20]


@login_required
@require_GET
def data_io_index(request):
    groups = {
        "Land": ["fields", "parcels", "soil_samples", "crop_records"],
        "Livestock": ["animals", "vet_records", "field_movements"],
        "Crops": ["crop_types", "market_prices", "harvest_records"],
        "Equipment": ["equipment", "maintenance_records"],
        "Buildings": ["buildings", "building_maintenance"],
        "Consumables": ["consumable_types", "inventory_items", "inventory_transactions"],
        "Employment": ["employees", "tasks", "time_entries"],
        "Feed": ["feed_types", "feed_stocks", "feed_logs"],
        "Produce": ["produce_items", "produce_transactions"],
    }
    grouped = {}
    for group_name, keys in groups.items():
        items = []
        for key in keys:
            if key in RESOURCE_REGISTRY:
                label, _, model = RESOURCE_REGISTRY[key]
                qs = model.objects.all()
                if key in FARM_SCOPED_KEYS:
                    qs = qs.filter(farm=request.farm)
                items.append({"key": key, "label": label, "count": qs.count()})
        grouped[group_name] = items
    return render(request, "data_io/index.html", {"grouped": grouped})


@login_required
@require_GET
def data_export(request, resource_key):
    if resource_key not in RESOURCE_REGISTRY:
        messages.error(request, "Unknown data type.")
        return redirect(URL_INDEX)

    _, resource_class, model = RESOURCE_REGISTRY[resource_key]
    fmt = request.GET.get("format", "csv")
    if fmt not in ("csv", "xlsx"):
        fmt = "csv"

    resource = _build_resource(resource_class, resource_key, request.farm)
    qs = model.objects.all()
    if resource_key in FARM_SCOPED_KEYS:
        qs = qs.filter(farm=request.farm)

    dataset = resource.export(queryset=qs)

    if fmt == "xlsx":
        response = HttpResponse(
            dataset.xlsx,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{resource_key}.xlsx"'
    else:
        response = HttpResponse(dataset.csv, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{resource_key}.csv"'

    return response


@login_required
@require_http_methods(["GET", "POST"])
def data_import(request, resource_key):
    if resource_key not in RESOURCE_REGISTRY:
        messages.error(request, "Unknown data type.")
        return redirect(URL_INDEX)

    label, resource_class, _ = RESOURCE_REGISTRY[resource_key]

    if request.method != "POST":
        return render(request, IMPORT_TEMPLATE, {"label": label, "resource_key": resource_key})

    file = request.FILES.get("file")
    if not file:
        messages.error(request, "Please select a file to import.")
        return redirect(URL_IMPORT, resource_key=resource_key)

    dataset, err = _load_dataset(file)
    if err:
        messages.error(request, err)
        return redirect(URL_IMPORT, resource_key=resource_key)

    if resource_key in FARM_SCOPED_KEYS:
        _inject_farm_column(dataset, request.farm.pk)

    resource = _build_resource(resource_class, resource_key, request.farm)
    result = resource.import_data(dataset, dry_run=True)

    if result.has_errors() or result.has_validation_errors():
        return render(request, IMPORT_TEMPLATE, {
            "label": label,
            "resource_key": resource_key,
            "errors": _collect_error_messages(result),
            "preview": None,
        })

    if "confirm" in request.POST:
        result = resource.import_data(dataset, dry_run=False)
        count = result.totals.get("new", 0) + result.totals.get("update", 0)
        messages.success(request, f"Imported {count} {label.lower()} records.")
        return redirect(URL_INDEX)

    return render(request, IMPORT_TEMPLATE, {
        "label": label,
        "resource_key": resource_key,
        "result": result,
        "headers": dataset.headers,
        "preview_rows": list(dataset)[:20],
        "total_rows": len(dataset),
        "show_confirm": True,
    })


# ---------------------------------------------------------------------------
# Whole-farm backup / restore
# ---------------------------------------------------------------------------

@login_required
@require_GET
def backup_index(request):
    return render(request, BACKUP_TEMPLATE, {"counts": farm_counts(request.farm)})


@login_required
@require_GET
def backup_download(request):
    """Stream a complete backup of the current farm."""
    fd, path = tempfile.mkstemp(suffix=".zip", prefix="farmsteader-backup-")
    os.close(fd)
    try:
        export_farm(request.farm, path)
    except Exception:
        os.unlink(path)
        raise

    stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"farmsteader-backup-{slugify(request.farm.name) or 'farm'}-{stamp}.zip"

    response = FileResponse(open(path, "rb"), as_attachment=True, filename=filename)
    # The archive only needs to survive long enough to be streamed.
    response._resource_closers.append(lambda: os.unlink(path))
    return response


@login_required
@require_http_methods(["GET", "POST"])
def backup_restore(request):
    """Restore an uploaded archive into a brand new farm. Never touches the current one."""
    if request.method != "POST":
        return redirect(URL_BACKUP)

    upload = request.FILES.get("archive")
    if not upload:
        messages.error(request, "Please choose a backup archive to restore.")
        return redirect(URL_BACKUP)
    if not request.POST.get("confirm"):
        messages.error(request, "Please confirm you understand a new farm will be created.")
        return redirect(URL_BACKUP)

    fd, path = tempfile.mkstemp(suffix=".zip", prefix="farmsteader-restore-")
    with os.fdopen(fd, "wb") as fh:
        for chunk in upload.chunks():
            fh.write(chunk)

    try:
        report = restore_farm(
            path,
            request.user,
            farm_name=(request.POST.get("farm_name") or "").strip() or None,
            allow_dropped_fields=bool(request.POST.get("allow_dropped_fields")),
        )
    except RestoreError as exc:
        return render(request, BACKUP_TEMPLATE, {
            "counts": farm_counts(request.farm),
            "errors": exc.errors,
            "dropped_fields": exc.dropped_fields,
        })
    finally:
        os.unlink(path)

    # Drop the user into what they just restored.
    request.session["current_farm_id"] = report.farm.pk
    total = sum(report.counts.values())
    messages.success(
        request,
        f"Restored {total} records into a new farm, “{report.farm.name}”. "
        f"Your previous farm was not modified.",
    )
    for warning in report.warnings[:10]:
        messages.warning(request, warning)
    return redirect("core:dashboard")
