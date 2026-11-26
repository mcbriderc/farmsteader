from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import FarmSettings
from apps.core.us_states import STATE_NAMES
from apps.land.models import CropRecord

from .forms import CropTypeForm, HarvestRecordForm
from .models import CropType, HarvestRecord, MarketPrice
from .prices import NATIONAL

HARVEST_LIST = "crops:harvest_list"


@require_GET
def crop_type_list(request):
    crop_types = CropType.objects.all()
    return render(request, "crops/crop_type_list.html", {"crop_types": crop_types})


PRICE_YEARS = 10


def _price_table(crop_type, state):
    """Rows of (year, national price, state price) for the last PRICE_YEARS years with data.

    Either side may be None: USDA's state coverage has gaps, and a year can have a
    state figure before the national one is out. Returns (rows, whether any row has
    a state price).
    """
    states = [NATIONAL] + ([state] if state else [])
    by_year = {}
    for price in crop_type.prices.filter(state__in=states):
        by_year.setdefault(price.year, {})[price.state] = price
    years = sorted(by_year, reverse=True)[:PRICE_YEARS]
    rows = [(year, by_year[year].get(NATIONAL), by_year[year].get(state)) for year in years]
    return rows, any(row[2] for row in rows)


@require_GET
def crop_type_detail(request, pk):
    crop_type = get_object_or_404(CropType, pk=pk)
    state = FarmSettings.for_farm(request.farm).state
    price_rows, state_has_prices = _price_table(crop_type, state)
    harvests = HarvestRecord.objects.filter(farm=request.farm, crop_type=crop_type).select_related("field", "planting")
    plantings = (
        CropRecord.objects.filter(farm=request.farm, crop_type=crop_type)
        .select_related("field", "crop_type").prefetch_related("harvests")
    )

    return render(request, "crops/crop_type_detail.html", {
        "crop_type": crop_type,
        "price_rows": price_rows,
        "state": state,
        "state_name": STATE_NAMES.get(state, ""),
        "state_has_prices": state_has_prices,
        "harvests": harvests,
        "plantings": plantings,
    })


@require_http_methods(["GET", "POST"])
def crop_type_create(request):
    if request.method == "POST":
        form = CropTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Crop type added.")
            return redirect("crops:crop_type_list")
    else:
        form = CropTypeForm()

    return render(request, "crops/crop_type_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def crop_type_edit(request, pk):
    crop_type = get_object_or_404(CropType, pk=pk)

    if request.method == "POST":
        form = CropTypeForm(request.POST, instance=crop_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Crop type updated.")
            return redirect("crops:crop_type_detail", pk=crop_type.pk)
    else:
        form = CropTypeForm(instance=crop_type)

    return render(request, "crops/crop_type_form.html", {"form": form, "editing": True, "crop_type": crop_type})


@require_http_methods(["GET", "POST"])
def crop_type_delete(request, pk):
    crop_type = get_object_or_404(CropType, pk=pk)
    if request.method == "POST":
        # The catalog is shared by every farm on the install, so a crop type in
        # use anywhere is protected (on_delete=PROTECT) rather than taking other
        # farms' plantings and harvests with it.
        try:
            crop_type.delete()
        except ProtectedError:
            messages.error(
                request,
                f'"{crop_type.name}" cannot be deleted: it is used by '
                f"{crop_type.plantings.count()} planting(s) and {crop_type.harvests.count()} harvest(s).",
            )
            return redirect("crops:crop_type_detail", pk=crop_type.pk)
        messages.success(request, "Crop type deleted.")
        return redirect("crops:crop_type_list")
    return render(request, "crops/crop_type_confirm_delete.html", {"crop_type": crop_type})


@require_GET
def harvest_list(request):
    harvests = HarvestRecord.objects.filter(farm=request.farm).select_related("field", "crop_type", "planting")
    return render(request, "crops/harvest_list.html", {"harvests": harvests})


@require_GET
def crop_record_list(request):
    """Every planting on the farm, across all fields.

    CropRecord lives in the land app because it hangs off a Field, and until now
    it was only reachable from that field's detail page -- so a crop seeded on
    one field was invisible from the Crops section, which lists only harvests.
    This is the cross-field view of the same records; creating and editing still
    happen against the field (`land:crop_record_create` / `_edit`), which is what
    owns the FK.
    """
    records = (
        CropRecord.objects.filter(farm=request.farm)
        .select_related("field", "crop_type").prefetch_related("harvests")
    )

    season = request.GET.get("season")
    status = request.GET.get("status")
    search = request.GET.get("q")

    if season:
        records = records.filter(season=season)
    if status:
        records = records.filter(status=status)
    if search:
        records = records.filter(Q(crop_type__name__icontains=search) | Q(variety__icontains=search))

    # Seasons are free text ("2026-Spring"), so the filter offers what the farm
    # has actually recorded rather than a fixed list. Drawn from the unfiltered
    # queryset, or selecting a season would leave only itself to choose from.
    seasons = (
        CropRecord.objects.filter(farm=request.farm)
        .exclude(season="")
        .values_list("season", flat=True)
        .distinct()
        .order_by("-season")
    )

    return render(request, "crops/crop_record_list.html", {
        "records": records,
        "seasons": seasons,
        "status_choices": CropRecord.Status.choices,
        "current_season": season or "",
        "current_status": status or "",
        "search_query": search or "",
    })


@require_http_methods(["GET", "POST"])
def harvest_create(request):
    if request.method == "POST":
        form = HarvestRecordForm(request.POST, farm=request.farm)
        if form.is_valid():
            record = form.save(commit=False)
            record.farm = request.farm
            record.save()
            messages.success(request, "Harvest record added.")
            return redirect(HARVEST_LIST)
    else:
        # "Record harvest" on a planting arrives with ?planting=<id>; anything
        # not one of this farm's plantings is ignored.
        initial = {}
        planting = CropRecord.objects.filter(
            farm=request.farm, pk=request.GET.get("planting") or 0,
        ).select_related("field", "crop_type").first()
        if planting:
            initial = {
                "planting": planting, "field": planting.field, "crop_type": planting.crop_type,
                "yield_unit": planting.crop_type.default_unit,
            }
        form = HarvestRecordForm(farm=request.farm, initial=initial)

    return render(request, "crops/harvest_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def harvest_edit(request, pk):
    record = get_object_or_404(HarvestRecord, pk=pk, farm=request.farm)

    if request.method == "POST":
        form = HarvestRecordForm(request.POST, instance=record, farm=request.farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Harvest record updated.")
            return redirect(HARVEST_LIST)
    else:
        form = HarvestRecordForm(instance=record, farm=request.farm)

    return render(request, "crops/harvest_form.html", {"form": form, "editing": True, "record": record})


@require_http_methods(["GET", "POST"])
def harvest_delete(request, pk):
    record = get_object_or_404(HarvestRecord, pk=pk, farm=request.farm)
    if request.method == "POST":
        record.delete()
        messages.success(request, "Harvest record deleted.")
        return redirect(HARVEST_LIST)
    return render(request, "crops/harvest_confirm_delete.html", {"record": record})
