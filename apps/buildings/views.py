import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import BuildingForm, BuildingMaintenanceForm
from .models import Building, BuildingMaintenanceRecord

BUILDING_DETAIL = "buildings:building_detail"


@require_GET
def building_list(request):
    buildings = Building.objects.filter(farm=request.farm)
    return render(request, "buildings/building_list.html", {"buildings": buildings})


@require_GET
def building_geojson(request):
    buildings = Building.objects.filter(farm=request.farm, location__isnull=False)
    features = []
    for b in buildings:
        features.append({
            "type": "Feature",
            "geometry": json.loads(b.location.json),
            "properties": {
                "id": b.id,
                "name": b.name,
                "type": b.get_building_type_display(),
                "url": f"/buildings/{b.id}/",
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_http_methods(["GET", "POST"])
def building_create(request):
    if request.method == "POST":
        form = BuildingForm(request.POST, request.FILES)
        if form.is_valid():
            building = form.save(commit=False)
            building.farm = request.farm
            building.save()
            messages.success(request, f'Building "{building.name}" added.')
            return redirect(BUILDING_DETAIL, pk=building.pk)
    else:
        form = BuildingForm()
    return render(request, "buildings/building_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def building_edit(request, pk):
    building = get_object_or_404(Building, pk=pk, farm=request.farm)
    if request.method == "POST":
        form = BuildingForm(request.POST, request.FILES, instance=building)
        if form.is_valid():
            form.save()
            messages.success(request, f'Building "{building.name}" updated.')
            return redirect(BUILDING_DETAIL, pk=building.pk)
    else:
        form = BuildingForm(instance=building)
    return render(request, "buildings/building_form.html", {"form": form, "building": building, "editing": True})


@require_GET
def building_detail(request, pk):
    building = get_object_or_404(Building, pk=pk, farm=request.farm)
    maintenance = building.maintenance_records.all()
    return render(request, "buildings/building_detail.html", {
        "building": building,
        "maintenance": maintenance,
    })


@require_http_methods(["GET", "POST"])
def building_delete(request, pk):
    building = get_object_or_404(Building, pk=pk, farm=request.farm)
    if request.method == "POST":
        name = building.name
        building.delete()
        messages.success(request, f'Building "{name}" deleted.')
        return redirect("buildings:building_list")
    return render(request, "buildings/building_confirm_delete.html", {"building": building})


@require_http_methods(["GET", "POST"])
def building_maintenance_create(request, building_pk):
    building = get_object_or_404(Building, pk=building_pk, farm=request.farm)
    if request.method == "POST":
        form = BuildingMaintenanceForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.farm = request.farm
            record.building = building
            record.save()
            messages.success(request, "Maintenance record added.")
            return redirect(BUILDING_DETAIL, pk=building.pk)
    else:
        form = BuildingMaintenanceForm()
    return render(request, "buildings/maintenance_form.html", {"form": form, "building": building})


@require_http_methods(["GET", "POST"])
def building_maintenance_edit(request, building_pk, pk):
    building = get_object_or_404(Building, pk=building_pk, farm=request.farm)
    record = get_object_or_404(BuildingMaintenanceRecord, pk=pk, building=building, farm=request.farm)
    if request.method == "POST":
        form = BuildingMaintenanceForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "Maintenance record updated.")
            return redirect(BUILDING_DETAIL, pk=building.pk)
    else:
        form = BuildingMaintenanceForm(instance=record)
    return render(request, "buildings/maintenance_form.html", {"form": form, "building": building, "editing": True})
