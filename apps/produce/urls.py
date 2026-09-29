from django.urls import path

from . import views

app_name = "produce"

urlpatterns = [
    path("", views.produce_list, name="produce_list"),
    path("add/", views.produce_create, name="produce_create"),
    path("<int:pk>/", views.produce_detail, name="produce_detail"),
    path("<int:pk>/edit/", views.produce_edit, name="produce_edit"),
    path("<int:pk>/delete/", views.produce_delete, name="produce_delete"),
    path("<int:item_pk>/transaction/add/", views.produce_transaction_create, name="transaction_create"),
]
