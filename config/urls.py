from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    # Health probes live at project level with no trailing slash: APPEND_SLASH
    # would 301 a probe of "/healthz" to "/healthz/", and a checker that counts
    # any 2xx/3xx as success would then pass against a completely dead app.
    path("healthz", core_views.healthz, name="healthz"),
    path("readyz", core_views.readyz, name="readyz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("land/", include("apps.land.urls")),
    path("livestock/", include("apps.livestock.urls")),
    path("crops/", include("apps.crops.urls")),
    path("equipment/", include("apps.equipment.urls")),
    path("buildings/", include("apps.buildings.urls")),
    path("consumables/", include("apps.consumables.urls")),
    path("employment/", include("apps.employment.urls")),
    path("produce/", include("apps.produce.urls")),
    path("data/", include("apps.data_io.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
    except ImportError:
        pass
