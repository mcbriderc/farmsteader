from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import AnimalForm, FeedLogForm, FeedStockForm, FeedTypeForm, FieldMovementForm, VetRecordForm
from .models import Animal, FeedStock, FeedType, VetRecord

ANIMAL_DETAIL = "livestock:animal_detail"


@require_GET
def animal_list(request):
    animals = Animal.objects.filter(farm=request.farm).select_related("current_field")

    # Filters
    species = request.GET.get("species")
    status = request.GET.get("status")
    search = request.GET.get("q")

    if species:
        animals = animals.filter(species=species)
    if status:
        animals = animals.filter(status=status)
    if search:
        animals = animals.filter(
            models.Q(ear_tag__icontains=search) |
            models.Q(name__icontains=search) |
            models.Q(breed__icontains=search)
        )

    return render(request, "livestock/animal_list.html", {
        "animals": animals,
        "species_choices": Animal.Species.choices,
        "status_choices": Animal.Status.choices,
        "current_species": species,
        "current_status": status,
        "search_query": search or "",
    })


@require_http_methods(["GET", "POST"])
def animal_create(request):
    if request.method == "POST":
        form = AnimalForm(request.POST, request.FILES, farm=request.farm)
        if form.is_valid():
            animal = form.save(commit=False)
            animal.farm = request.farm
            animal.save()
            messages.success(request, f'Animal "{animal}" added.')
            return redirect(ANIMAL_DETAIL, pk=animal.pk)
    else:
        form = AnimalForm(farm=request.farm)

    return render(request, "livestock/animal_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def animal_edit(request, pk):
    animal = get_object_or_404(Animal, pk=pk, farm=request.farm)

    if request.method == "POST":
        form = AnimalForm(request.POST, request.FILES, instance=animal, farm=request.farm)
        if form.is_valid():
            form.save()
            messages.success(request, f'Animal "{animal}" updated.')
            return redirect(ANIMAL_DETAIL, pk=animal.pk)
    else:
        form = AnimalForm(instance=animal, farm=request.farm)

    return render(request, "livestock/animal_form.html", {"form": form, "animal": animal, "editing": True})


@require_GET
def animal_detail(request, pk):
    animal = get_object_or_404(
        Animal.objects.select_related("current_field", "sire", "dam"),
        pk=pk, farm=request.farm,
    )
    vet_records = animal.vet_records.all()
    movements = animal.movements.select_related("from_field", "to_field").all()[:20]
    offspring = Animal.objects.filter(
        farm=request.farm,
    ).filter(
        models.Q(sire=animal) | models.Q(dam=animal)
    )

    feed_logs = animal.feed_logs.select_related("feed_stock").all()[:20]

    return render(request, "livestock/animal_detail.html", {
        "animal": animal,
        "vet_records": vet_records,
        "movements": movements,
        "offspring": offspring,
        "feed_logs": feed_logs,
    })


@require_http_methods(["GET", "POST"])
def animal_delete(request, pk):
    animal = get_object_or_404(Animal, pk=pk, farm=request.farm)
    if request.method == "POST":
        label = str(animal)
        animal.delete()
        messages.success(request, f'Animal "{label}" deleted.')
        return redirect("livestock:animal_list")
    return render(request, "livestock/animal_confirm_delete.html", {"animal": animal})


@require_http_methods(["GET", "POST"])
def vet_record_create(request, animal_pk):
    animal = get_object_or_404(Animal, pk=animal_pk, farm=request.farm)

    if request.method == "POST":
        form = VetRecordForm(request.POST, request.FILES)
        if form.is_valid():
            record = form.save(commit=False)
            record.farm = request.farm
            record.animal = animal
            record.save()
            messages.success(request, "Vet record added.")
            return redirect(ANIMAL_DETAIL, pk=animal.pk)
    else:
        form = VetRecordForm()

    return render(request, "livestock/vet_record_form.html", {"form": form, "animal": animal})


@require_http_methods(["GET", "POST"])
def vet_record_edit(request, animal_pk, pk):
    animal = get_object_or_404(Animal, pk=animal_pk, farm=request.farm)
    record = get_object_or_404(VetRecord, pk=pk, animal=animal, farm=request.farm)

    if request.method == "POST":
        form = VetRecordForm(request.POST, request.FILES, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "Vet record updated.")
            return redirect(ANIMAL_DETAIL, pk=animal.pk)
    else:
        form = VetRecordForm(instance=record)

    return render(request, "livestock/vet_record_form.html", {"form": form, "animal": animal, "editing": True})


@require_http_methods(["GET", "POST"])
def movement_create(request, animal_pk):
    animal = get_object_or_404(Animal, pk=animal_pk, farm=request.farm)

    if request.method == "POST":
        form = FieldMovementForm(request.POST, farm=request.farm)
        if form.is_valid():
            movement = form.save(commit=False)
            movement.farm = request.farm
            movement.animal = animal
            movement.from_field = animal.current_field
            movement.save()
            messages.success(request, f"Moved {animal} to {movement.to_field}.")
            return redirect(ANIMAL_DETAIL, pk=animal.pk)
    else:
        form = FieldMovementForm(farm=request.farm)

    return render(request, "livestock/movement_form.html", {"form": form, "animal": animal})


# -- Feed type views --


@require_GET
def feed_type_list(request):
    feed_types = FeedType.objects.all()
    return render(request, "livestock/feed_type_list.html", {"feed_types": feed_types})


@require_GET
def feed_type_detail(request, pk):
    feed_type = get_object_or_404(FeedType, pk=pk)
    stocks = FeedStock.objects.filter(farm=request.farm, feed_type=feed_type)
    return render(request, "livestock/feed_type_detail.html", {
        "feed_type": feed_type,
        "stocks": stocks,
    })


@require_http_methods(["GET", "POST"])
def feed_type_create(request):
    if request.method == "POST":
        form = FeedTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Feed type added.")
            return redirect("livestock:feed_type_list")
    else:
        form = FeedTypeForm()
    return render(request, "livestock/feed_type_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def feed_type_edit(request, pk):
    feed_type = get_object_or_404(FeedType, pk=pk)
    if request.method == "POST":
        form = FeedTypeForm(request.POST, instance=feed_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Feed type updated.")
            return redirect("livestock:feed_type_detail", pk=feed_type.pk)
    else:
        form = FeedTypeForm(instance=feed_type)
    return render(request, "livestock/feed_type_form.html", {"form": form, "editing": True, "feed_type": feed_type})


@require_http_methods(["GET", "POST"])
def feed_type_delete(request, pk):
    feed_type = get_object_or_404(FeedType, pk=pk)
    if request.method == "POST":
        feed_type.delete()
        messages.success(request, "Feed type deleted.")
        return redirect("livestock:feed_type_list")
    return render(request, "livestock/feed_type_confirm_delete.html", {"feed_type": feed_type})


# -- Feed management views --


@require_GET
def feed_list(request):
    stocks = FeedStock.objects.filter(farm=request.farm).select_related("feed_type")

    source = request.GET.get("source")
    if source:
        stocks = stocks.filter(restock_source=source)

    low_stock = [s for s in stocks if s.is_low_stock]

    return render(request, "livestock/feed_list.html", {
        "stocks": stocks,
        "low_stock": low_stock,
        "source_choices": FeedStock.RestockSource.choices,
        "current_source": source,
    })


@require_http_methods(["GET", "POST"])
def feed_create(request):
    if request.method == "POST":
        form = FeedStockForm(request.POST)
        if form.is_valid():
            stock = form.save(commit=False)
            stock.farm = request.farm
            stock.save()
            messages.success(request, f'Feed stock "{stock.name}" added.')
            return redirect("livestock:feed_detail", pk=stock.pk)
    else:
        form = FeedStockForm()

    return render(request, "livestock/feed_form.html", {"form": form})


@require_GET
def feed_detail(request, pk):
    stock = get_object_or_404(
        FeedStock.objects.select_related("feed_type"),
        pk=pk, farm=request.farm,
    )
    feed_logs = stock.feed_logs.select_related("animal").all()[:30]

    return render(request, "livestock/feed_detail.html", {
        "stock": stock,
        "feed_logs": feed_logs,
    })


@require_http_methods(["GET", "POST"])
def feed_edit(request, pk):
    stock = get_object_or_404(FeedStock, pk=pk, farm=request.farm)

    if request.method == "POST":
        form = FeedStockForm(request.POST, instance=stock)
        if form.is_valid():
            form.save()
            messages.success(request, f'Feed stock "{stock.name}" updated.')
            return redirect("livestock:feed_detail", pk=stock.pk)
    else:
        form = FeedStockForm(instance=stock)

    return render(request, "livestock/feed_form.html", {"form": form, "stock": stock, "editing": True})


@require_http_methods(["GET", "POST"])
def feeding_log_create(request, animal_pk):
    animal = get_object_or_404(Animal, pk=animal_pk, farm=request.farm)

    if request.method == "POST":
        form = FeedLogForm(request.POST, farm=request.farm)
        if form.is_valid():
            log = form.save(commit=False)
            log.farm = request.farm
            log.animal = animal
            log.save()
            messages.success(request, f"Feeding logged for {animal}.")
            return redirect(ANIMAL_DETAIL, pk=animal.pk)
    else:
        form = FeedLogForm(farm=request.farm)

    return render(request, "livestock/feeding_log_form.html", {"form": form, "animal": animal})


# Need this import for Q objects in views
from django.db import models  # noqa: E402
