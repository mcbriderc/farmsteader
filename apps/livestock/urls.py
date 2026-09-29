from django.urls import path

from . import views

app_name = "livestock"

urlpatterns = [
    path("", views.animal_list, name="animal_list"),
    path("add/", views.animal_create, name="animal_create"),
    path("<int:pk>/", views.animal_detail, name="animal_detail"),
    path("<int:pk>/edit/", views.animal_edit, name="animal_edit"),
    path("<int:pk>/delete/", views.animal_delete, name="animal_delete"),
    path("<int:animal_pk>/vet/add/", views.vet_record_create, name="vet_record_create"),
    path("<int:animal_pk>/vet/<int:pk>/edit/", views.vet_record_edit, name="vet_record_edit"),
    path("<int:animal_pk>/move/", views.movement_create, name="movement_create"),
    # Feed type catalog
    path("feed/types/", views.feed_type_list, name="feed_type_list"),
    path("feed/types/add/", views.feed_type_create, name="feed_type_create"),
    path("feed/types/<int:pk>/", views.feed_type_detail, name="feed_type_detail"),
    path("feed/types/<int:pk>/edit/", views.feed_type_edit, name="feed_type_edit"),
    path("feed/types/<int:pk>/delete/", views.feed_type_delete, name="feed_type_delete"),
    # Feed management
    path("feed/", views.feed_list, name="feed_list"),
    path("feed/add/", views.feed_create, name="feed_create"),
    path("feed/<int:pk>/", views.feed_detail, name="feed_detail"),
    path("feed/<int:pk>/edit/", views.feed_edit, name="feed_edit"),
    path("<int:animal_pk>/feed/add/", views.feeding_log_create, name="feeding_log_create"),
]
