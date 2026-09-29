from django.urls import path

from . import views

app_name = "employment"

urlpatterns = [
    # Employees
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/add/", views.employee_create, name="employee_create"),
    path("employees/<int:pk>/", views.employee_detail, name="employee_detail"),
    path("employees/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    # Tasks
    path("tasks/", views.task_board, name="task_board"),
    path("tasks/add/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:pk>/status/", views.task_update_status, name="task_update_status"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    # Time entries
    path("timesheet/", views.timesheet, name="timesheet"),
    path("timesheet/add/", views.time_entry_create, name="time_entry_create"),
]
