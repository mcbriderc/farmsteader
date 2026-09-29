import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.accounts.mixins import FarmAccessMixin

from .forms import CropRecordForm, FieldForm, SoilSampleForm
from .models import CropRecord, Field, SoilSample
from .tasks import sync_soil_data_for_field, sync_weather_for_field

FIELD_DETAIL = "land:field_detail"


@require_GET
def field_list(request):
    fields = Field.objects.filter(farm=request.farm)
    return render(request, "land/field_list.html", {"fields": fields})


@require_GET
def field_map(request):
    """Full-screen map view for drawing/viewing fields."""
    fields = Field.objects.filter(farm=request.farm)
    return render(request, "land/field_map.html", {"fields": fields})


@require_GET
def field_geojson(request):
    """GeoJSON FeatureCollection of all farm fields."""
    fields = Field.objects.filter(farm=request.farm)
    features = []
    for field in fields:
        features.append({
            "type": "Feature",
            "geometry": json.loads(field.boundary.json),
            "properties": {
                "id": field.id,
                "name": field.name,
                "acreage": float(field.acreage),
                "color": field.color,
                "url": f"/land/fields/{field.id}/",
            },
        })

    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })


@require_http_methods(["GET", "POST"])
def field_create(request):
    if request.method == "POST":
        form = FieldForm(request.POST)
        if form.is_valid():
            field = form.save(commit=False)
            field.farm = request.farm
            field.save()
            # Trigger background data fetches
            sync_weather_for_field.delay(field.id)
            sync_soil_data_for_field.delay(field.id)
            messages.success(request, f'Field "{field.name}" created ({field.acreage} acres).')
            return redirect(FIELD_DETAIL, pk=field.pk)
    else:
        form = FieldForm()

    return render(request, "land/field_form.html", {"form": form, "editing": False})


@require_http_methods(["GET", "POST"])
def field_edit(request, pk):
    field = get_object_or_404(Field, pk=pk, farm=request.farm)

    if request.method == "POST":
        form = FieldForm(request.POST, instance=field)
        if form.is_valid():
            field = form.save()
            sync_weather_for_field.delay(field.id)
            sync_soil_data_for_field.delay(field.id)
            messages.success(request, f'Field "{field.name}" updated.')
            return redirect(FIELD_DETAIL, pk=field.pk)
    else:
        form = FieldForm(instance=field)

    return render(request, "land/field_form.html", {
        "form": form,
        "field": field,
        "editing": True,
        "boundary_geojson": field.boundary.json,
    })


@require_GET
def field_detail(request, pk):
    field = get_object_or_404(Field, pk=pk, farm=request.farm)
    tz = ZoneInfo(field.timezone) if field.timezone else ZoneInfo("UTC")
    today = datetime.now(tz=tz).date()
    weather_all = list(field.weather_records.all()[:14])
    weather_forecast = [w for w in weather_all if w.date > today]
    weather_history = [w for w in weather_all if w.date <= today]
    soil_samples = field.soil_samples.all()
    crop_records = field.crop_records.all()

    return render(request, "land/field_detail.html", {
        "field": field,
        "weather_forecast": weather_forecast,
        "weather_history": weather_history,
        "weather_count": len(weather_all),
        "soil_samples": soil_samples,
        "crop_records": crop_records,
    })


@require_POST
def field_sync_weather(request, pk):
    field = get_object_or_404(Field, pk=pk, farm=request.farm)
    from .services.weather import fetch_weather_for_field
    fetch_weather_for_field(field)
    messages.success(request, "Weather synced.")
    return redirect(FIELD_DETAIL, pk=field.pk)


@require_POST
def field_sync_soil(request, pk):
    field = get_object_or_404(Field, pk=pk, farm=request.farm)
    from .services.soil import fetch_soil_for_field
    try:
        sample = fetch_soil_for_field(field)
    except httpx.TimeoutException:
        messages.error(request, "SoilGrids did not respond in time — try again in a moment.")
        return redirect(FIELD_DETAIL, pk=field.pk)
    if sample:
        messages.success(request, "Soil data synced from SoilGrids.")
    else:
        messages.warning(request, "No soil data returned for this field.")
    return redirect(FIELD_DETAIL, pk=field.pk)


@require_POST
def sync_all_fields(request):
    from .services.soil import fetch_soil_for_field
    from .services.weather import fetch_weather_for_field

    fields = list(Field.objects.filter(farm=request.farm))
    synced, failed = 0, 0
    for field in fields:
        try:
            fetch_weather_for_field(field)
            fetch_soil_for_field(field)
            synced += 1
        except Exception:
            failed += 1

    if failed:
        messages.warning(request, f"Synced {synced} field(s); {failed} failed (check logs).")
    else:
        messages.success(request, f"Synced weather & soil for {synced} field(s).")
    return redirect("land:field_list")


@require_http_methods(["GET", "POST"])
def field_delete(request, pk):
    field = get_object_or_404(Field, pk=pk, farm=request.farm)
    if request.method == "POST":
        name = field.name
        field.delete()
        messages.success(request, f'Field "{name}" deleted.')
        return redirect("land:field_list")
    return render(request, "land/field_confirm_delete.html", {"field": field})


@require_http_methods(["GET", "POST"])
def crop_record_create(request, field_pk):
    field = get_object_or_404(Field, pk=field_pk, farm=request.farm)

    if request.method == "POST":
        form = CropRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.farm = request.farm
            record.field = field
            record.save()
            messages.success(request, f"Crop record added for {field.name}.")
            return redirect(FIELD_DETAIL, pk=field.pk)
    else:
        form = CropRecordForm()

    return render(request, "land/crop_record_form.html", {"form": form, "field": field})


@require_http_methods(["GET", "POST"])
def crop_record_edit(request, field_pk, pk):
    field = get_object_or_404(Field, pk=field_pk, farm=request.farm)
    record = get_object_or_404(CropRecord, pk=pk, field=field, farm=request.farm)

    if request.method == "POST":
        form = CropRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "Crop record updated.")
            return redirect(FIELD_DETAIL, pk=field.pk)
    else:
        form = CropRecordForm(instance=record)

    return render(request, "land/crop_record_form.html", {"form": form, "field": field, "editing": True})


@require_http_methods(["GET", "POST"])
def soil_sample_create(request, field_pk):
    field = get_object_or_404(Field, pk=field_pk, farm=request.farm)

    if request.method == "POST":
        form = SoilSampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.farm = request.farm
            sample.field = field
            sample.save()
            messages.success(request, f"Soil sample added for {field.name}.")
            return redirect(FIELD_DETAIL, pk=field.pk)
    else:
        form = SoilSampleForm()

    return render(request, "land/soil_sample_form.html", {"form": form, "field": field})
