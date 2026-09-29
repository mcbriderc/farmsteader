from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import EquipmentForm, MaintenanceRecordForm
from .models import Equipment, MaintenanceRecord

EQUIPMENT_DETAIL = "equipment:equipment_detail"


@require_GET
def equipment_list(request):
    equipment = Equipment.objects.filter(farm=request.farm)
    return render(request, "equipment/equipment_list.html", {"equipment": equipment})


@require_http_methods(["GET", "POST"])
def equipment_create(request):
    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            eq = form.save(commit=False)
            eq.farm = request.farm
            eq.save()
            messages.success(request, f'Equipment "{eq.name}" added.')
            return redirect(EQUIPMENT_DETAIL, pk=eq.pk)
    else:
        form = EquipmentForm()
    return render(request, "equipment/equipment_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def equipment_edit(request, pk):
    eq = get_object_or_404(Equipment, pk=pk, farm=request.farm)
    if request.method == "POST":
        form = EquipmentForm(request.POST, request.FILES, instance=eq)
        if form.is_valid():
            form.save()
            messages.success(request, f'Equipment "{eq.name}" updated.')
            return redirect(EQUIPMENT_DETAIL, pk=eq.pk)
    else:
        form = EquipmentForm(instance=eq)
    return render(request, "equipment/equipment_form.html", {"form": form, "equipment": eq, "editing": True})


@require_GET
def equipment_detail(request, pk):
    eq = get_object_or_404(Equipment, pk=pk, farm=request.farm)
    maintenance = eq.maintenance_records.all()
    return render(request, "equipment/equipment_detail.html", {
        "equipment": eq,
        "maintenance": maintenance,
    })


@require_http_methods(["GET", "POST"])
def equipment_delete(request, pk):
    eq = get_object_or_404(Equipment, pk=pk, farm=request.farm)
    if request.method == "POST":
        name = eq.name
        eq.delete()
        messages.success(request, f'Equipment "{name}" deleted.')
        return redirect("equipment:equipment_list")
    return render(request, "equipment/equipment_confirm_delete.html", {"equipment": eq})


@require_http_methods(["GET", "POST"])
def maintenance_create(request, equipment_pk):
    eq = get_object_or_404(Equipment, pk=equipment_pk, farm=request.farm)
    if request.method == "POST":
        form = MaintenanceRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.farm = request.farm
            record.equipment = eq
            record.save()
            messages.success(request, "Maintenance record added.")
            return redirect(EQUIPMENT_DETAIL, pk=eq.pk)
    else:
        form = MaintenanceRecordForm()
    return render(request, "equipment/maintenance_form.html", {"form": form, "equipment": eq})


@require_http_methods(["GET", "POST"])
def maintenance_edit(request, equipment_pk, pk):
    eq = get_object_or_404(Equipment, pk=equipment_pk, farm=request.farm)
    record = get_object_or_404(MaintenanceRecord, pk=pk, equipment=eq, farm=request.farm)
    if request.method == "POST":
        form = MaintenanceRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "Maintenance record updated.")
            return redirect(EQUIPMENT_DETAIL, pk=eq.pk)
    else:
        form = MaintenanceRecordForm(instance=record)
    return render(request, "equipment/maintenance_form.html", {"form": form, "equipment": eq, "editing": True})
