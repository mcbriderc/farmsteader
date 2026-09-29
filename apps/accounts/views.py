from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from django.contrib import messages
from django.views.decorators.http import require_http_methods

from .forms import FarmSettingsForm, FarmUserRegistrationForm
from .models import Farm, FarmMembership, FarmSettings


@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "POST":
        form = FarmUserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            farm = user.farms.first()
            request.session["current_farm_id"] = farm.id
            return redirect("/")
    else:
        form = FarmUserRegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def farm_select(request):
    farms = Farm.objects.filter(memberships__user=request.user)

    if request.method == "POST":
        farm_id = request.POST.get("farm_id")
        if farms.filter(id=farm_id).exists():
            request.session["current_farm_id"] = int(farm_id)
            return redirect("/")

    return render(request, "accounts/farm_select.html", {"farms": farms})


@login_required
@require_http_methods(["GET", "POST"])
def farm_create(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            farm = Farm.objects.create(name=name)
            FarmMembership.objects.create(
                user=request.user, farm=farm, role=FarmMembership.Role.OWNER
            )
            request.session["current_farm_id"] = farm.id
            return redirect("/")

    return render(request, "accounts/farm_create.html")


@login_required
@require_http_methods(["GET", "POST"])
def farm_settings(request):
    farm = request.farm
    if not farm:
        return redirect("accounts:farm_select")

    # Check user is owner or manager
    membership = FarmMembership.objects.filter(user=request.user, farm=farm).first()
    if not membership or membership.role not in ("owner", "manager"):
        messages.error(request, "Only farm owners and managers can access settings.")
        return redirect("core:dashboard")

    settings_obj, _ = FarmSettings.objects.get_or_create(farm=farm)

    if request.method == "POST":
        form = FarmSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Farm settings updated.")
            return redirect("accounts:farm_settings")
    else:
        form = FarmSettingsForm(instance=settings_obj)

    return render(request, "accounts/farm_settings.html", {
        "form": form,
        "farm": farm,
    })
