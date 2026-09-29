"""Guards for the CSS-variable dark/light theme.

Dark mode works by redefining Tailwind's colour custom properties inside a
``html.dark { }`` block in ``static/css/input.css``. Tailwind v4 compiles every
colour utility to a variable reference (``.bg-white{background-color:var(--color-white)}``),
so that one block re-themes ~1,200 existing utility classes without touching a
single template.

That is cheap, but it rests on a few invariants that nothing else would catch if
they broke. These tests pin them down.
"""

import os
import re
from pathlib import Path

import pytest
from django.urls import reverse

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted(ROOT.glob("apps/*/templates/**/*.html"))
INPUT_CSS = ROOT / "assets/css/input.css"
DIST_CSS = ROOT / "static/css/dist/styles.css"

# Classes whose meaning is ambiguous between the two themes, and the semantic
# token that replaced each. `bg-white` is a card surface but `text-white` is text
# on a coloured fill; `bg-farm-600` is a button fill but `text-farm-600` is link
# text. Splitting them is what frees the dark block to remap the stock scales.
BANNED = {
    "bg-white": "bg-surface",
    "bg-farm-600": "bg-accent",
    "bg-farm-700": "bg-accent-hover",
    "bg-red-600": "bg-danger",
    "bg-red-700": "bg-danger-hover",
}

# Tokens the dark block must define. Not exhaustive -- these are the ones whose
# absence would leave large parts of the UI unreadable.
REQUIRED_DARK_TOKENS = [
    "--color-canvas",
    "--color-surface",
    "--color-gray-50",
    "--color-gray-500",
    "--color-gray-900",
    "--color-farm-600",
    "--color-red-700",
]


def _dark_block() -> str:
    """The body of the `html.dark { ... }` rule in input.css."""
    css = INPUT_CSS.read_text()
    match = re.search(r"html\.dark\s*\{(.*?)\n\}", css, re.DOTALL)
    assert match, "input.css has no `html.dark { ... }` block"
    return match.group(1)


@pytest.mark.parametrize("banned,replacement", sorted(BANNED.items()))
def test_templates_use_semantic_tokens(banned, replacement):
    """No template may reintroduce a class that only works in light mode.

    Matches variant prefixes too, so `hover:bg-white` is caught alongside
    `bg-white`.
    """
    pattern = re.compile(r"(?<![-\w])(?:[a-z-]+:)*" + re.escape(banned) + r"(?![-\w])")
    offenders = [
        f"{path.relative_to(ROOT)}:{n}"
        for path in TEMPLATES
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert not offenders, (
        f"`{banned}` does not re-theme; use `{replacement}` instead. Found in: "
        + ", ".join(offenders)
    )


def test_input_css_enables_class_based_dark_variant():
    """Tailwind v4 defaults `dark:` to prefers-color-scheme; we drive it by class."""
    assert "@custom-variant dark" in INPUT_CSS.read_text()


@pytest.mark.parametrize("token", REQUIRED_DARK_TOKENS)
def test_dark_block_defines_token(token):
    assert f"{token}:" in _dark_block(), f"{token} is not remapped for dark mode"


def test_dark_block_does_not_override_white():
    """`text-white` is text on a coloured fill (buttons, sidebar) in both themes.

    Remapping --color-white would flip those to dark text on green.
    """
    assert "--color-white:" not in _dark_block()


def test_theme_bootstrap_precedes_stylesheet():
    """The FOUC guard.

    Alpine and HTMX load deferred at the end of <body>, so the class on <html>
    has to be set by a blocking script above the stylesheet link. If a refactor
    moves it, dark mode still "works" but flashes white on every page load --
    which no other test would notice.
    """
    base = (ROOT / "apps/core/templates/base.html").read_text()
    bootstrap = base.index("localStorage.getItem('theme')")
    stylesheet = base.index("css/dist/styles.css")
    assert bootstrap < stylesheet


def test_built_stylesheet_contains_dark_theme():
    """The compiled CSS must actually carry the dark block.

    static/css/dist/ is gitignored, so this depends on a Tailwind build. CI runs
    one (see .forgejo/workflows/ci.yml) and sets CI=true, so a missing or stale
    build fails the pipeline instead of quietly skipping.
    """
    if not DIST_CSS.exists():
        if os.environ.get("CI"):
            pytest.fail(
                "static/css/dist/styles.css is missing -- the CI job must run "
                "`manage.py tailwind build` before pytest."
            )
        pytest.skip("stylesheet not built; run `make tailwind`")

    css = DIST_CSS.read_text()
    assert "html.dark" in css, "stylesheet is stale; rebuild with `make tailwind`"
    assert ".bg-surface" in css


def test_body_has_explicit_text_colour():
    """Untinted text must follow the theme.

    Remapping the colour variables only re-themes elements carrying a `text-*`
    utility. Most table cells carry none, so without this rule they inherit the
    browser default of black and vanish against a dark surface.
    """
    css = INPUT_CSS.read_text()
    assert re.search(
        r"body\s*\{[^}]*color:\s*var\(--color-gray-900\)", css, re.DOTALL
    ), "input.css must anchor `body` colour to a themed variable"


def test_form_controls_have_explicit_surface():
    """Selects and text inputs must not be left on Tailwind's transparent reset.

    Preflight resets every control to `background-color: transparent; color:
    inherit`. This is the one case `color-scheme: dark` cannot fix -- an
    author-set background beats the UA field colour -- so a <select> renders its
    option popup on the browser's white default with near-white inherited text.
    `option`/`optgroup` must be listed in their own right: the popup is a
    separate box that does not inherit the select's background.
    """
    css = INPUT_CSS.read_text()
    match = re.search(
        r"@layer base\s*\{[^{]*?\bselect\b(.*?)\n\}", css, re.DOTALL
    )
    assert match, "input.css must give form controls an explicit themed surface"
    rule = match.group(0)
    for selector in ("option", "optgroup", "textarea"):
        assert re.search(rf"\b{selector}\b", rule), (
            f"`{selector}` must share the form-control surface rule"
        )
    assert "var(--color-surface)" in rule and "var(--color-gray-900)" in rule
    for excluded in ("checkbox", "radio"):
        assert excluded in rule, (
            f"[type={excluded}] must stay excluded -- it is painted by the "
            "browser and handled by `color-scheme`"
        )


def test_dark_block_sets_color_scheme():
    """Checkboxes, radios, scrollbars and date pickers are painted by the browser.

    They ignore the custom properties entirely; `color-scheme` is the only thing
    that darkens them. Without it, unchecked checkboxes are white slabs.
    """
    assert "color-scheme: dark" in _dark_block()


def test_theme_toggle_advertises_target_theme():
    """The toggle sits among actions, so it must name the theme it switches TO.

    Light mode shows the moon and "Dark Mode"; dark mode shows the sun and
    "Light Mode". Swapping these is silent -- the toggle still works, it just
    describes the state you are already in.
    """
    css = INPUT_CSS.read_text()
    assert re.search(r"\.icon-sun\s*\{\s*display:\s*none", css)
    assert re.search(r"html\.dark\s+\.icon-sun\s*\{\s*display:\s*block", css)
    assert re.search(r"html\.dark\s+\.icon-moon\s*\{\s*display:\s*none", css)

    base = (ROOT / "apps/core/templates/base.html").read_text()
    assert '<span class="icon-sun">Light Mode</span>' in base
    assert '<span class="icon-moon">Dark Mode</span>' in base


def test_leaflet_draw_toolbar_excluded_from_bar_rules():
    """leaflet-draw's container carries `leaflet-bar` too.

    It is themed by inverting the whole button (its icons are dark-on-light
    sprites). Letting the `.leaflet-bar a` rule paint it dark first means the
    invert flips it straight back to light.
    """
    assert ".leaflet-bar:not(.leaflet-draw-toolbar) a" in INPUT_CSS.read_text()


def test_no_multiline_template_comments():
    """`{# ... #}` is single-line only in Django.

    A `{#` whose `#}` lands on a later line is not a comment at all -- the text
    renders into the page. Multi-line comments need `{% comment %}`.
    """
    offenders = []
    for path in TEMPLATES:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for match in re.finditer(r"\{#", line):
                if "#}" not in line[match.end() :]:
                    offenders.append(f"{path.relative_to(ROOT)}:{n}")
    assert not offenders, (
        "`{# #}` does not span lines -- the text renders into the page. Use "
        "`{% comment %}`. Found at: " + ", ".join(offenders)
    )


def test_stylesheet_url_is_cache_busted(farm_client):
    """A rebuilt stylesheet must not be invisible to an already-open tab.

    `runserver` sends only `Last-Modified` for static files, so Chromium applies
    heuristic freshness -- 10% of the file's age -- and a plain reload does not
    revalidate a still-fresh subresource. Since `styles.css` is git-ignored and
    usually weeks old before anyone edits the theme, that is days of staleness,
    and it presents as a theme fix that "did not work".
    """
    html = farm_client.get(reverse("core:dashboard")).content.decode()
    assert re.search(r'href="[^"]*css/dist/styles\.css\?v=\d+"', html), (
        "the stylesheet link must carry a `?v=<mtime>` stamp; see "
        "apps/core/templatetags/assets.py"
    )


def test_sidebar_renders_theme_toggle(farm_client):
    response = farm_client.get(reverse("core:dashboard"))
    assert response.status_code == 200
    assert "toggleTheme()" in response.content.decode()


def test_login_page_has_theme_bootstrap(client):
    """The auth pages are CurrentFarmMiddleware-exempt and render no sidebar.

    They still need the bootstrap script and a toggle of their own.
    """
    body = client.get(reverse("accounts:login")).content.decode()
    assert "localStorage.getItem('theme')" in body
    assert "toggleTheme()" in body
