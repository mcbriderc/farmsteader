import logging
from datetime import date as date_type

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _build_action_items(farm, today):
    from apps.livestock.models import VetRecord
    from apps.equipment.models import MaintenanceRecord
    from apps.buildings.models import BuildingMaintenanceRecord
    from apps.employment.models import Task

    items = []

    for r in (MaintenanceRecord.objects
              .filter(farm=farm, next_service_date__lte=today,
                      equipment__status__in=["active", "maintenance"])
              .select_related("equipment")
              .order_by("next_service_date")[:15]):
        items.append({
            "type": "equipment", "label": "Equipment",
            "title": r.equipment.name,
            "subtitle": r.get_maintenance_type_display(),
            "due": r.next_service_date,
            "url": reverse("equipment:equipment_detail", args=[r.equipment.pk]),
        })

    for r in (BuildingMaintenanceRecord.objects
              .filter(farm=farm, next_due_date__lte=today)
              .select_related("building")
              .order_by("next_due_date")[:15]):
        items.append({
            "type": "building", "label": "Building",
            "title": r.building.name,
            "subtitle": r.get_maintenance_type_display(),
            "due": r.next_due_date,
            "url": reverse("buildings:building_detail", args=[r.building.pk]),
        })

    for t in (Task.objects
              .filter(farm=farm, status__in=["todo", "in_progress"])
              .filter(Q(due_date__lte=today) | Q(priority="urgent"))
              .order_by("due_date", "-priority")[:15]):
        subtitle = t.get_priority_display()
        if t.due_date:
            subtitle += f" · due {t.due_date}"
        items.append({
            "type": "task", "label": "Task",
            "title": t.title,
            "subtitle": subtitle,
            "due": t.due_date,
            "url": reverse("employment:task_board"),
        })

    for r in (VetRecord.objects
              .filter(farm=farm, next_due_date__lte=today)
              .select_related("animal")
              .order_by("next_due_date")[:15]):
        items.append({
            "type": "vet", "label": "Vet",
            "title": r.animal.name,
            "subtitle": r.get_record_type_display(),
            "due": r.next_due_date,
            "url": reverse("livestock:animal_detail", args=[r.animal.pk]),
        })

    items.sort(key=lambda x: (x["due"] is None, x["due"] or date_type.max))
    return items


def _get_commodity_prices(farm):
    from apps.crops.models import CommodityPrice

    seen = set()
    prices = []
    for p in CommodityPrice.objects.order_by("commodity", "-date"):
        if p.ticker not in seen:
            seen.add(p.ticker)
            prices.append(p)

    try:
        visible = farm.settings.visible_tickers or []
    except Exception:
        visible = []

    if visible:
        prices = [p for p in prices if p.ticker in visible]
    return prices


@login_required
@require_GET
def dashboard(request):
    context = {}
    if request.farm:
        farm = request.farm
        context["farm"] = farm

        from apps.land.models import Field
        from apps.livestock.models import Animal, FeedStock
        from apps.equipment.models import Equipment
        from apps.buildings.models import Building
        from apps.consumables.models import InventoryItem
        from apps.employment.models import Task
        from apps.produce.models import ProduceItem

        context["field_count"] = Field.objects.filter(farm=farm).count()
        context["animal_count"] = Animal.objects.filter(farm=farm).count()
        context["equipment_count"] = Equipment.objects.filter(farm=farm).count()
        context["building_count"] = Building.objects.filter(farm=farm).count()

        context["open_task_count"] = Task.objects.filter(
            farm=farm, status__in=["todo", "in_progress"]
        ).count()

        context["low_stock_count"] = InventoryItem.objects.filter(
            farm=farm,
            reorder_threshold__gt=0,
            quantity__lte=F("reorder_threshold"),
        ).count()

        today = timezone.now().date()
        context["today"] = today
        context["expired_produce_count"] = ProduceItem.objects.filter(
            farm=farm, expiry_date__lt=today
        ).count()
        context["produce_count"] = ProduceItem.objects.filter(farm=farm).count()

        context["low_feed_count"] = FeedStock.objects.filter(
            farm=farm,
            reorder_threshold__gt=0,
            quantity__lte=F("reorder_threshold"),
        ).count()

        context["action_items"] = _build_action_items(farm, today)
        context["commodity_prices"] = _get_commodity_prices(farm)

    return render(request, "core/dashboard.html", context)


# --- Health probes ---------------------------------------------------------
#
# Both are wired into config/urls.py at project level *without* a trailing
# slash, and both are listed in CurrentFarmMiddleware.EXEMPT_PATHS. Miss that
# second part and the probe 302s to the login page -- which most health checkers
# follow or count as success, so the endpoint reports healthy no matter what.


@require_GET
@never_cache
def healthz(request):
    """Liveness: is this process up and serving?

    Deliberately touches no external service. A liveness probe that fails when
    Postgres blips gets the web process restarted, which does not fix Postgres
    and does drop every in-flight request. Readiness is `readyz`.
    """
    return JsonResponse({"status": "ok", "version": settings.APP_VERSION})


@require_GET
@never_cache
def readyz(request):
    """Readiness: can this process actually serve a request end to end?

    Returns 503 with a per-check breakdown when anything is down, so the
    installer's post-install poll and any external monitor can say *what* is
    broken rather than just that something is.
    """
    checks = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("readyz: database check failed: %s", exc)
        checks["database"] = "error"

    try:
        import redis

        client = redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            client.ping()
            checks["redis"] = "ok"
        finally:
            client.close()
    except Exception as exc:
        logger.warning("readyz: redis check failed: %s", exc)
        checks["redis"] = "error"

    healthy = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {
            "status": "ok" if healthy else "degraded",
            "version": settings.APP_VERSION,
            "checks": checks,
        },
        status=200 if healthy else 503,
    )
