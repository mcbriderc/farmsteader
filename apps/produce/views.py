from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ProduceItemForm, ProduceTransactionForm
from .models import ProduceItem

PRODUCE_DETAIL = "produce:produce_detail"


@require_GET
def produce_list(request):
    items = ProduceItem.objects.filter(farm=request.farm)
    expired = [i for i in items if i.is_expired]
    return render(request, "produce/produce_list.html", {"items": items, "expired": expired})


@require_http_methods(["GET", "POST"])
def produce_create(request):
    if request.method == "POST":
        form = ProduceItemForm(request.POST, farm=request.farm)
        if form.is_valid():
            item = form.save(commit=False)
            item.farm = request.farm
            item.save()
            messages.success(request, f'"{item.name}" added.')
            return redirect(PRODUCE_DETAIL, pk=item.pk)
    else:
        form = ProduceItemForm(farm=request.farm)
    return render(request, "produce/produce_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def produce_edit(request, pk):
    item = get_object_or_404(ProduceItem, pk=pk, farm=request.farm)
    if request.method == "POST":
        form = ProduceItemForm(request.POST, instance=item, farm=request.farm)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{item.name}" updated.')
            return redirect(PRODUCE_DETAIL, pk=item.pk)
    else:
        form = ProduceItemForm(instance=item, farm=request.farm)
    return render(request, "produce/produce_form.html", {"form": form, "item": item, "editing": True})


@require_GET
def produce_detail(request, pk):
    item = get_object_or_404(ProduceItem, pk=pk, farm=request.farm)
    transactions = item.transactions.all()[:30]
    return render(request, "produce/produce_detail.html", {"item": item, "transactions": transactions})


@require_http_methods(["GET", "POST"])
def produce_delete(request, pk):
    item = get_object_or_404(ProduceItem, pk=pk, farm=request.farm)
    if request.method == "POST":
        name = item.name
        item.delete()
        messages.success(request, f'"{name}" deleted.')
        return redirect("produce:produce_list")
    return render(request, "produce/produce_confirm_delete.html", {"item": item})


@require_http_methods(["GET", "POST"])
def produce_transaction_create(request, item_pk):
    item = get_object_or_404(ProduceItem, pk=item_pk, farm=request.farm)
    if request.method == "POST":
        form = ProduceTransactionForm(request.POST)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.farm = request.farm
            txn.item = item
            txn.save()
            messages.success(request, f"Transaction recorded. Stock: {item.quantity} {item.unit}.")
            return redirect(PRODUCE_DETAIL, pk=item.pk)
    else:
        form = ProduceTransactionForm()
    return render(request, "produce/transaction_form.html", {"form": form, "item": item})
