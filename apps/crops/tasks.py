import logging

from celery import shared_task
from django.conf import settings

from .constants import COMMODITY_TICKERS

logger = logging.getLogger(__name__)


@shared_task
def sync_commodity_prices():
    """Sync CME futures prices via yfinance. Run daily after market open."""
    from datetime import date

    try:
        import yfinance as yf
    except ImportError:
        # yfinance is in requirements/base.txt, but it is also by far the
        # heaviest dependency (pandas + numpy) and the first thing anyone trims
        # from a slim install. Degrade to a logged skip rather than a daily
        # traceback in the celery journal that nobody is watching.
        logger.warning(
            "yfinance is not installed; skipping commodity price sync. "
            "Install requirements/base.txt to enable it."
        )
        return

    from .models import CommodityPrice

    today = date.today()
    synced = 0
    for cfg in COMMODITY_TICKERS:
        try:
            info = yf.Ticker(cfg["ticker"]).fast_info
            raw = info.last_price
            prev = info.previous_close
            if raw is None:
                logger.warning("No price data for %s", cfg["ticker"])
                continue
            price = round(raw / cfg["divisor"], 2)
            change = round((raw - prev) / cfg["divisor"], 2) if prev else None
            change_pct = round(((raw - prev) / prev) * 100, 2) if prev else None
            CommodityPrice.objects.update_or_create(
                ticker=cfg["ticker"],
                date=today,
                defaults={
                    "commodity": cfg["name"],
                    "price": price,
                    "unit": cfg["unit"],
                    "change": change,
                    "change_pct": change_pct,
                },
            )
            synced += 1
        except Exception as e:
            logger.error("Commodity price sync failed for %s: %s", cfg["ticker"], e)

    logger.info("Synced %d commodity prices", synced)


@shared_task
def sync_crop_prices():
    """Sync crop prices from USDA NASS QuickStats API."""
    import httpx

    from apps.crops.models import CropType, MarketPrice

    api_key = getattr(settings, "USDA_NASS_API_KEY", "") or ""
    if not api_key:
        logger.warning("USDA_NASS_API_KEY not configured, skipping price sync")
        return

    base_url = "https://quickstats.nass.usda.gov/api/api_GET/"
    crop_types = CropType.objects.exclude(usda_code="")

    synced = 0
    for crop_type in crop_types:
        params = {
            "key": api_key,
            "commodity_desc": crop_type.name.upper(),
            "statisticcat_desc": "PRICE RECEIVED",
            "agg_level_desc": "NATIONAL",
            "freq_desc": "ANNUAL",
            "format": "JSON",
            "year__GE": "2020",
        }

        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(base_url, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            logger.error("USDA NASS fetch failed for %s: %s", crop_type.name, e)
            continue

        for item in data.get("data", []):
            value = item.get("Value", "").replace(",", "")
            try:
                price = float(value)
            except (ValueError, TypeError):
                continue

            MarketPrice.objects.update_or_create(
                crop_type=crop_type,
                year=int(item["year"]),
                state=item.get("state_name", "US"),
                defaults={
                    "price_per_unit": price,
                    "unit": f"$/{crop_type.default_unit}",
                },
            )
            synced += 1

    logger.info("USDA NASS: synced %d price records", synced)
