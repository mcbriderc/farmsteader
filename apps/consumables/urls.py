from django.urls import path

from . import views

app_name = "consumables"

urlpatterns = [
    path("", views.inventory_list, name="inventory_list"),
    path("add/", views.inventory_create, name="inventory_create"),
    path("<int:pk>/", views.inventory_detail, name="inventory_detail"),
    path("<int:pk>/edit/", views.inventory_edit, name="inventory_edit"),
    path("<int:pk>/delete/", views.inventory_delete, name="inventory_delete"),
    path("<int:item_pk>/transaction/add/", views.transaction_create, name="transaction_create"),
    # Consumable types
    path("types/", views.consumable_type_list, name="consumable_type_list"),
    path("types/add/", views.consumable_type_create, name="consumable_type_create"),
    path("types/<int:pk>/", views.consumable_type_detail, name="consumable_type_detail"),
    path("types/<int:pk>/edit/", views.consumable_type_edit, name="consumable_type_edit"),
    path("types/<int:pk>/delete/", views.consumable_type_delete, name="consumable_type_delete"),
]
