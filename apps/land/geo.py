"""Geometry helpers shared by every polygon the land app stores."""

SQ_METERS_PER_ACRE = 4046.8564224

#: NAD83 / Conus Albers: an equal-area projection for the contiguous US, so an
#: area measured in it is true on the ground. Areas taken directly in SRID 4326
#: are in square *degrees*, which shrink toward the poles.
EQUAL_AREA_SRID = 5070


def acreage_of(polygon):
    """Acres enclosed by a polygon in SRID 4326, rounded to two places.

    Plain round() on purpose: it is what Field.save() has always stored, so
    re-saving an existing field can never shift its acreage by a cent.
    """
    sq_meters = polygon.transform(EQUAL_AREA_SRID, clone=True).area
    return round(sq_meters / SQ_METERS_PER_ACRE, 2)
