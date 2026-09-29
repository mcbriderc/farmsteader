from django.urls import path

from . import views

app_name = "data_io"

urlpatterns = [
    path("", views.data_io_index, name="index"),
    path("export/<str:resource_key>/", views.data_export, name="export"),
    path("import/<str:resource_key>/", views.data_import, name="import"),
    path("backup/", views.backup_index, name="backup"),
    path("backup/download/", views.backup_download, name="backup_download"),
    path("backup/restore/", views.backup_restore, name="backup_restore"),
]
