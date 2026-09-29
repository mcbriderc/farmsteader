from django.urls import path

from . import views

app_name = "land"

urlpatterns = [
    path("fields/", views.field_list, name="field_list"),
    path("fields/map/", views.field_map, name="field_map"),
    path("fields/geojson/", views.field_geojson, name="field_geojson"),
    path("fields/create/", views.field_create, name="field_create"),
    path("fields/<int:pk>/", views.field_detail, name="field_detail"),
    path("fields/<int:pk>/edit/", views.field_edit, name="field_edit"),
    path("fields/<int:pk>/delete/", views.field_delete, name="field_delete"),
    path("fields/<int:field_pk>/crops/add/", views.crop_record_create, name="crop_record_create"),
    path("fields/<int:field_pk>/crops/<int:pk>/edit/", views.crop_record_edit, name="crop_record_edit"),
    path("fields/<int:field_pk>/soil/add/", views.soil_sample_create, name="soil_sample_create"),
    path("fields/<int:pk>/sync-weather/", views.field_sync_weather, name="field_sync_weather"),
    path("fields/<int:pk>/sync-soil/", views.field_sync_soil, name="field_sync_soil"),
    path("fields/sync-all/", views.sync_all_fields, name="sync_all_fields"),
]
