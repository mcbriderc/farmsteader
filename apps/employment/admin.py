from django.contrib import admin

from .models import Employee, Task, TimeEntry


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "role", "status", "farm"]
    list_filter = ["farm", "status"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "assigned_to", "priority", "status", "due_date"]
    list_filter = ["farm", "status", "priority"]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ["employee", "date", "hours", "task"]
    list_filter = ["farm", "employee"]
