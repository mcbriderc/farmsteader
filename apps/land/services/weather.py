import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from apps.land.models import Field, WeatherCache

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _field_today(field: Field):
    """Return today's date in the field's local timezone (falls back to UTC)."""
    tz = ZoneInfo(field.timezone) if field.timezone else ZoneInfo("UTC")
    return datetime.now(tz=tz).date()


def fetch_weather_for_field(field: Field, days_back: int = 7, days_forward: int = 7):
    """Fetch weather data from Open-Meteo for a field's centroid location."""
    today = _field_today(field)
    start_date = today - timedelta(days=days_back)
    end_date = today + timedelta(days=days_forward)

    params = {
        "latitude": field.centroid_lat,
        "longitude": field.centroid_lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "auto",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        logger.error("Weather fetch failed for field %s: %s", field.name, e)
        return 0

    # Persist the IANA timezone returned by Open-Meteo so views can use it
    tz_name = data.get("timezone", "")
    if tz_name and tz_name != field.timezone:
        Field.objects.filter(pk=field.pk).update(timezone=tz_name)
        field.timezone = tz_name

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    created_count = 0

    for i, day_str in enumerate(dates):
        day = date.fromisoformat(day_str)
        _, created = WeatherCache.objects.update_or_create(
            field=field,
            date=day,
            defaults={
                "temp_max_c": daily["temperature_2m_max"][i],
                "temp_min_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "wind_speed_max_kmh": daily["wind_speed_10m_max"][i],
                "weather_code": daily["weather_code"][i],
            },
        )
        if created:
            created_count += 1

    logger.info("Weather: %d days synced for %s (%d new)", len(dates), field.name, created_count)
    return len(dates)
