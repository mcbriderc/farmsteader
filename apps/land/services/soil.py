import logging

import httpx

from apps.land.models import Field, SoilSample

logger = logging.getLogger(__name__)

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Conversion factors: (divisor, multiplier) applied as raw_value / divisor * multiplier
# Keys match SoilGrids property names; values map to SoilSample field names and scale factors.
_PROPERTY_MAP = {
    "phh2o":    ("ph",                 10,   1),   # pH * 10 → pH
    "soc":      ("organic_carbon_pct", 100,  1),   # dg/kg → %
    "nitrogen": ("nitrogen_ppm",       1,    10),  # cg/kg → ppm (approx)
    "sand":     ("sand_pct",           10,   1),   # g/kg → %
    "silt":     ("silt_pct",           10,   1),
    "clay":     ("clay_pct",           10,   1),
    "cec":      ("cec",                10,   1),   # mmol(c)/kg → cmol/kg
}

# SoilGrids only accepts these exact depth strings.
_DEPTH_RANGES = [
    (5,   "0-5cm"),
    (15,  "5-15cm"),
    (30,  "15-30cm"),
    (60,  "30-60cm"),
    (100, "60-100cm"),
    (200, "100-200cm"),
]


def _depth_to_range(depth_cm: int) -> tuple[str, int]:
    """Return the SoilGrids depth string and canonical bottom-depth for a target depth."""
    for bottom, label in _DEPTH_RANGES:
        if depth_cm <= bottom:
            return label, bottom
    return "100-200cm", 200


def _parse_soil_layers(data):
    """Extract mean values from a SoilGrids API response into a flat dict."""
    properties = {}
    for layer in data.get("properties", {}).get("layers", []):
        depths = layer.get("depths", [])
        if depths:
            mean_val = depths[0].get("values", {}).get("mean")
            if mean_val is not None:
                properties[layer["name"]] = mean_val
    return properties


def _classify_texture(sand, silt, clay):
    """USDA soil texture triangle classification from percentages."""
    if None in (sand, silt, clay):
        return ""
    rules = [
        (clay >= 40 and silt >= 40, "Silty Clay"),
        (clay >= 40 and sand >= 45, "Sandy Clay"),
        (clay >= 40, "Clay"),
        (clay >= 27 and sand < 20, "Silty Clay Loam"),
        (clay >= 27 and silt >= 40, "Silty Clay Loam"),
        (clay >= 27, "Clay Loam"),
        (clay >= 20 and sand >= 45, "Sandy Clay Loam"),
        (silt >= 80, "Silt"),
        (silt >= 50, "Silt Loam"),
        (sand >= 85, "Sand"),
        (sand >= 70, "Loamy Sand"),
        (sand >= 43 and clay < 20, "Sandy Loam"),
    ]
    return next((label for cond, label in rules if cond), "Loam")


def _build_soil_defaults(properties):
    defaults = {}
    for prop, (field_name, divisor, multiplier) in _PROPERTY_MAP.items():
        raw = properties.get(prop)
        defaults[field_name] = (raw / divisor * multiplier) if raw else None
    defaults["texture_class"] = _classify_texture(
        defaults.get("sand_pct"), defaults.get("silt_pct"), defaults.get("clay_pct")
    )
    return defaults


def fetch_soil_for_field(field: Field, depth: int = 30):
    """Fetch soil properties from SoilGrids API for a field's centroid."""
    depth_range, canonical_depth = _depth_to_range(depth)
    params = {
        "lon": field.centroid_lon,
        "lat": field.centroid_lat,
        "property": list(_PROPERTY_MAP.keys()),
        "depth": depth_range,
        "value": "mean",
    }

    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(SOILGRIDS_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.error("Soil fetch timed out for field %s", field.name)
        raise
    except httpx.HTTPError as e:
        logger.error("Soil fetch failed for field %s: %s", field.name, e)
        return None

    properties = _parse_soil_layers(data)
    if not properties:
        logger.warning("No soil data returned for field %s", field.name)
        return None

    defaults = _build_soil_defaults(properties)
    sample, created = SoilSample.objects.update_or_create(
        farm=field.farm,
        field=field,
        source=SoilSample.Source.SOILGRIDS,
        depth_cm=canonical_depth,
        defaults=defaults,
    )

    if defaults.get("texture_class"):
        Field.objects.filter(pk=field.pk).update(soil_type=defaults["texture_class"])

    action = "created" if created else "updated"
    logger.info("Soil sample %s for %s (depth %dcm, texture: %s)", action, field.name, depth, defaults.get("texture_class"))
    return sample
