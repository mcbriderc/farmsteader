"""Guards for the shared field/property boundary editor.

The editor is client-side Leaflet + leaflet-draw, so its usability fixes live in
``land/_boundary_editor_js.html`` and ``assets/css/input.css`` and nothing in the
Python suite would notice them being undone. They were verified by driving the
real editor in a headless browser; these pin the configuration that made them
work.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITOR_JS = ROOT / "apps/land/templates/land/_boundary_editor_js.html"
INPUT_CSS = ROOT / "assets/css/input.css"


def test_corners_use_the_small_ring_not_leaflet_draws_touch_squares():
    """Leaflet 1.9 reports every pointer-events browser as touch.

    leaflet-draw then swaps its 8px corner icon for a 20px opaque square even
    under a mouse, hiding the exact point being placed. Both icons must be
    overridden, for drawing and for editing.
    """
    js = EDITOR_JS.read_text()

    assert "icon: vertexIcon, touchIcon: vertexIcon" in js
    assert "L.Edit.PolyVerticesEdit.mergeOptions({ icon: vertexIcon, touchIcon: vertexIcon })" in js
    assert ".boundary-vertex {" in INPUT_CSS.read_text()


def test_map_zooms_past_the_tile_limit():
    """Both tile sets stop at 19; without maxNativeZoom the map stops there too."""
    js = EDITOR_JS.read_text()

    assert "L.map('map', { maxZoom: 22 })" in js
    assert js.count("maxNativeZoom: 19, maxZoom: 22") == 2


def test_a_plain_click_never_deletes_a_corner():
    """leaflet-draw removes a vertex on click, with no undo; it is right-click here."""
    js = EDITOR_JS.read_text()

    assert "_onMarkerClick: function() {}" in js
    assert "removeVertex.call(this, e)" in js


def test_the_finished_shape_is_editable_without_an_edit_mode():
    js = EDITOR_JS.read_text()

    assert "poly.editing.enable()" in js
    assert "edit: { featureGroup: drawnItems, edit: false }" in js
