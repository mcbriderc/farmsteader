"""USDA NASS "price received" sync: national and state annual prices per crop.

Each crop's ``usda_code`` names a series -- the part of a QuickStats ``short_desc``
before " - PRICE RECEIVED", e.g. "CORN, GRAIN" or "HAY, ALFALFA". USDA answers a
commodity query ("HAY") with every series under it (all hay, alfalfa, other hay)
and, nationally, both a marketing-year and a calendar-year figure. They used to be
saved over one another under the same crop and year, so the stored price was
whichever arrived last; here exactly one row is kept per state and year.

Prices are public and the same for every farm, so the table is shared install-wide.
All states are stored, not only the ones farms have chosen: it is a few thousand
rows, and a farm that picks a state sees its prices without waiting for a sync.
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from django.db import transaction

logger = logging.getLogger(__name__)

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
NATIONAL = "US"
#: How far back to keep. The crop page shows the last ten years.
YEARS_BACK = 10
#: State data comes as marketing-year averages only; national data has both. Using
#: the same basis for both keeps a state price comparable with the national one.
PERIOD_PREFERENCE = ("MARKETING YEAR", "YEAR")
SERIES_SEPARATOR = " - PRICE RECEIVED"


class PriceFetchError(Exception):
    """USDA could not be asked (network, auth, server): keep what is stored."""


def commodity_of(series):
    """'HAY, ALFALFA' -> 'HAY'; the commodity is everything before the first comma."""
    return series.split(",", 1)[0].strip()


def unit_label(unit_desc):
    """'$ / BU' -> '$/bu'."""
    return unit_desc.replace(" ", "").lower() if unit_desc else ""


def fetch(api_key, commodity, level, client):
    """All price-received rows for a commodity at NATIONAL or STATE level.

    USDA answers a query that matches nothing with 400 rather than an empty list,
    which is the normal case for a crop with no state-level reporting.
    """
    params = {
        "key": api_key,
        "commodity_desc": commodity,
        "statisticcat_desc": "PRICE RECEIVED",
        "agg_level_desc": level,
        "freq_desc": "ANNUAL",
        "year__GE": str(date.today().year - YEARS_BACK),
        "format": "JSON",
    }
    try:
        response = client.get(API_URL, params=params)
    except httpx.HTTPError as e:
        raise PriceFetchError(str(e)) from e
    if response.status_code == 400:
        return []
    if response.status_code != 200:
        raise PriceFetchError(f"HTTP {response.status_code}")
    try:
        return response.json().get("data", [])
    except ValueError as e:
        raise PriceFetchError("response was not JSON") from e


def select_rows(rows, series):
    """One price per (state, year) for the series, as dicts ready for MarketPrice.

    Matches the series exactly. A bare commodity code ("SOYBEANS") also matches when
    USDA has a single series for it, which covers custom catalog entries written
    before codes named series.
    """
    def series_of(row):
        return row.get("short_desc", "").split(SERIES_SEPARATOR, 1)[0].strip()

    wanted = series.strip().upper()
    matching = [r for r in rows if series_of(r) == wanted]
    if not matching and "," not in wanted:
        found = {series_of(r) for r in rows}
        if len(found) == 1:
            matching = rows

    best = {}
    for row in matching:
        try:
            price = Decimal(row.get("Value", "").replace(",", "").strip())
            year = int(row["year"])
        except (InvalidOperation, KeyError, ValueError):
            continue  # "(D)" withheld, "(NA)" not available
        if price <= 0:
            continue  # some states report 0 where they have no figure
        state = NATIONAL if row.get("agg_level_desc") == "NATIONAL" else row.get("state_alpha", "")
        if not state:
            continue
        period = row.get("reference_period_desc", "")
        rank = PERIOD_PREFERENCE.index(period) if period in PERIOD_PREFERENCE else len(PERIOD_PREFERENCE)
        key = (state, year)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, {"state": state, "year": year, "price_per_unit": price,
                                "unit": unit_label(row.get("unit_desc", ""))})
    return [entry for _, entry in sorted(best.values(), key=lambda e: (e[1]["state"], e[1]["year"]))]


def sync_crop(crop_type, api_key, client):
    """Replace one crop's stored prices with USDA's current national and state figures.

    Replacing rather than updating drops rows from a series the crop no longer uses.
    On any fetch failure the stored prices are left as they were.
    """
    from apps.crops.models import MarketPrice

    commodity = commodity_of(crop_type.usda_code)
    rows = fetch(api_key, commodity, "NATIONAL", client) + fetch(api_key, commodity, "STATE", client)
    entries = select_rows(rows, crop_type.usda_code)
    with transaction.atomic():
        MarketPrice.objects.filter(crop_type=crop_type).delete()
        MarketPrice.objects.bulk_create(
            MarketPrice(crop_type=crop_type, source="USDA NASS", **entry) for entry in entries
        )
    return len(entries)


def sync_all(api_key):
    """Sync every catalog crop that names a series. Returns (crops synced, rows stored)."""
    from apps.crops.models import CropType

    crops, stored = 0, 0
    with httpx.Client(timeout=60) as client:
        for crop_type in CropType.objects.exclude(usda_code="").order_by("name"):
            try:
                stored += sync_crop(crop_type, api_key, client)
                crops += 1
            except PriceFetchError as e:
                logger.error("USDA NASS fetch failed for %s: %s", crop_type.name, e)
    return crops, stored
