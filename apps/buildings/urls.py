from django.urls import path

from . import views

app_name = "buildings"

urlpatterns = [
    path("", views.building_list, name="building_list"),
    path("geojson/", views.building_geojson, name="building_geojson"),
    path("add/", views.building_create, name="building_create"),
    path("<int:pk>/", views.building_detail, name="building_detail"),
    path("<int:pk>/edit/", views.building_edit, name="building_edit"),
    path("<int:pk>/delete/", views.building_delete, name="building_delete"),
    path("<int:building_pk>/maintenance/add/", views.building_maintenance_create, name="maintenance_create"),
    path("<int:building_pk>/maintenance/<int:pk>/edit/", views.building_maintenance_edit, name="maintenance_edit"),
]
