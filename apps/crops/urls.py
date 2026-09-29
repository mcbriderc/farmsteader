from django.urls import path

from . import views

app_name = "crops"

urlpatterns = [
    path("types/", views.crop_type_list, name="crop_type_list"),
    path("types/add/", views.crop_type_create, name="crop_type_create"),
    path("types/<int:pk>/", views.crop_type_detail, name="crop_type_detail"),
    path("types/<int:pk>/edit/", views.crop_type_edit, name="crop_type_edit"),
    path("types/<int:pk>/delete/", views.crop_type_delete, name="crop_type_delete"),
    path("records/", views.crop_record_list, name="crop_record_list"),
    path("harvests/", views.harvest_list, name="harvest_list"),
    path("harvests/add/", views.harvest_create, name="harvest_create"),
    path("harvests/<int:pk>/edit/", views.harvest_edit, name="harvest_edit"),
    path("harvests/<int:pk>/delete/", views.harvest_delete, name="harvest_delete"),
]
