import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sync_all_weather():
    """Fan-out weather sync for every field."""
    from apps.land.models import Field

    field_ids = list(Field.objects.values_list("id", flat=True))
    for field_id in field_ids:
        sync_weather_for_field.delay(field_id)
    logger.info("Queued weather sync for %d fields", len(field_ids))


@shared_task
def sync_weather_for_field(field_id: int):
    """Sync weather data for a single field."""
    from apps.land.models import Field
    from apps.land.services.weather import fetch_weather_for_field

    try:
        field = Field.objects.get(id=field_id)
    except Field.DoesNotExist:
        logger.warning("Field %d not found, skipping weather sync", field_id)
        return

    fetch_weather_for_field(field)


@shared_task(rate_limit="5/m")
def sync_soil_data_for_field(field_id: int):
    """Sync soil data for a single field. Rate-limited to 5/min per SoilGrids limits."""
    from apps.land.models import Field
    from apps.land.services.soil import fetch_soil_for_field

    try:
        field = Field.objects.get(id=field_id)
    except Field.DoesNotExist:
        logger.warning("Field %d not found, skipping soil sync", field_id)
        return

    fetch_soil_for_field(field)
