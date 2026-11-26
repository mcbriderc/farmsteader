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


def usda_api_key():
    """The key the price sync uses, or "" when there is none.

    Prices are public and shared by every farm on the install, so any farm that
    has crop price sync on can supply the key; the key only identifies the caller
    to USDA. The oldest such farm wins, so the choice is stable. A key in the
    server config (``USDA_NASS_API_KEY``) is the fallback, which keeps installs
    that set it at install time syncing without anyone opening Farm Settings.
    """
    from apps.accounts.models import FarmSettings

    farm_key = (
        FarmSettings.objects.filter(crop_prices_enabled=True)
        .exclude(usda_nass_api_key="")
        .order_by("farm_id")
        .values_list("usda_nass_api_key", flat=True)
        .first()
    )
    return (farm_key or getattr(settings, "USDA_NASS_API_KEY", "") or "").strip()


@shared_task
def sync_crop_prices():
    """Sync national and state crop prices from USDA NASS QuickStats (see crops.prices)."""
    from apps.crops.prices import sync_all

    api_key = usda_api_key()
    if not api_key:
        logger.info("No USDA NASS API key in any farm's settings or the server config, skipping price sync")
        return

    crops, stored = sync_all(api_key)
    logger.info("USDA NASS: stored %d prices for %d crops", stored, crops)
