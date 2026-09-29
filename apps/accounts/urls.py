from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("farm/select/", views.farm_select, name="farm_select"),
    path("farm/create/", views.farm_create, name="farm_create"),
    path("farm/settings/", views.farm_settings, name="farm_settings"),
]
