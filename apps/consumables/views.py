from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ConsumableTypeForm, InventoryItemForm, InventoryTransactionForm
from .models import ConsumableType, InventoryItem

INVENTORY_DETAIL = "consumables:inventory_detail"


@require_GET
def inventory_list(request):
    items = InventoryItem.objects.filter(farm=request.farm).select_related("consumable_type")
    low_stock = [i for i in items if i.is_low_stock]
    return render(request, "consumables/inventory_list.html", {
        "items": items,
        "low_stock": low_stock,
    })


@require_http_methods(["GET", "POST"])
def inventory_create(request):
    if request.method == "POST":
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.farm = request.farm
            item.save()
            messages.success(request, f'"{item.name}" added to inventory.')
            return redirect(INVENTORY_DETAIL, pk=item.pk)
    else:
        form = InventoryItemForm()
    return render(request, "consumables/inventory_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def inventory_edit(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, farm=request.farm)
    if request.method == "POST":
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{item.name}" updated.')
            return redirect(INVENTORY_DETAIL, pk=item.pk)
    else:
        form = InventoryItemForm(instance=item)
    return render(request, "consumables/inventory_form.html", {"form": form, "item": item, "editing": True})


@require_GET
def inventory_detail(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, farm=request.farm)
    transactions = item.transactions.all()[:30]
    return render(request, "consumables/inventory_detail.html", {
        "item": item,
        "transactions": transactions,
    })


@require_http_methods(["GET", "POST"])
def inventory_delete(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, farm=request.farm)
    if request.method == "POST":
        name = item.name
        item.delete()
        messages.success(request, f'"{name}" removed from inventory.')
        return redirect("consumables:inventory_list")
    return render(request, "consumables/inventory_confirm_delete.html", {"item": item})


@require_GET
def consumable_type_list(request):
    types = ConsumableType.objects.all()
    return render(request, "consumables/consumable_type_list.html", {"types": types})


@require_GET
def consumable_type_detail(request, pk):
    ct = get_object_or_404(ConsumableType, pk=pk)
    items = InventoryItem.objects.filter(farm=request.farm, consumable_type=ct)
    return render(request, "consumables/consumable_type_detail.html", {"ct": ct, "items": items})


@require_http_methods(["GET", "POST"])
def consumable_type_create(request):
    if request.method == "POST":
        form = ConsumableTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Consumable type added.")
            return redirect("consumables:consumable_type_list")
    else:
        form = ConsumableTypeForm()
    return render(request, "consumables/consumable_type_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def consumable_type_edit(request, pk):
    ct = get_object_or_404(ConsumableType, pk=pk)
    if request.method == "POST":
        form = ConsumableTypeForm(request.POST, instance=ct)
        if form.is_valid():
            form.save()
            messages.success(request, "Consumable type updated.")
            return redirect("consumables:consumable_type_detail", pk=ct.pk)
    else:
        form = ConsumableTypeForm(instance=ct)
    return render(request, "consumables/consumable_type_form.html", {"form": form, "editing": True, "ct": ct})


@require_http_methods(["GET", "POST"])
def consumable_type_delete(request, pk):
    ct = get_object_or_404(ConsumableType, pk=pk)
    if request.method == "POST":
        ct.delete()
        messages.success(request, "Consumable type deleted.")
        return redirect("consumables:consumable_type_list")
    return render(request, "consumables/consumable_type_confirm_delete.html", {"ct": ct})


@require_http_methods(["GET", "POST"])
def transaction_create(request, item_pk):
    item = get_object_or_404(InventoryItem, pk=item_pk, farm=request.farm)
    if request.method == "POST":
        form = InventoryTransactionForm(request.POST)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.farm = request.farm
            txn.item = item
            txn.save()
            messages.success(request, f"Transaction recorded. Current stock: {item.quantity} {item.unit}.")
            return redirect(INVENTORY_DETAIL, pk=item.pk)
    else:
        form = InventoryTransactionForm()
    return render(request, "consumables/transaction_form.html", {"form": form, "item": item})
