from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .forms import EmployeeForm, TaskForm, TimeEntryForm
from .models import Employee, Task, TimeEntry

TASK_BOARD = "employment:task_board"


# --- Employees ---

@require_GET
def employee_list(request):
    employees = Employee.objects.filter(farm=request.farm)
    return render(request, "employment/employee_list.html", {"employees": employees})


@require_http_methods(["GET", "POST"])
def employee_create(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            emp = form.save(commit=False)
            emp.farm = request.farm
            emp.save()
            messages.success(request, f"{emp} added.")
            return redirect("employment:employee_detail", pk=emp.pk)
    else:
        form = EmployeeForm()
    return render(request, "employment/employee_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def employee_edit(request, pk):
    emp = get_object_or_404(Employee, pk=pk, farm=request.farm)
    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=emp)
        if form.is_valid():
            form.save()
            messages.success(request, f"{emp} updated.")
            return redirect("employment:employee_detail", pk=emp.pk)
    else:
        form = EmployeeForm(instance=emp)
    return render(request, "employment/employee_form.html", {"form": form, "employee": emp, "editing": True})


@require_GET
def employee_detail(request, pk):
    emp = get_object_or_404(Employee, pk=pk, farm=request.farm)
    tasks = emp.tasks.all()[:10]
    time_entries = emp.time_entries.all()[:20]
    return render(request, "employment/employee_detail.html", {
        "employee": emp,
        "tasks": tasks,
        "time_entries": time_entries,
    })


# --- Tasks / Kanban ---

@require_GET
def task_board(request):
    tasks = Task.objects.filter(farm=request.farm).select_related("assigned_to")
    todo = tasks.filter(status=Task.Status.TODO)
    in_progress = tasks.filter(status=Task.Status.IN_PROGRESS)
    done = tasks.filter(status=Task.Status.DONE)[:20]
    return render(request, "employment/task_board.html", {
        "todo": todo,
        "in_progress": in_progress,
        "done": done,
    })


@require_http_methods(["GET", "POST"])
def task_create(request):
    if request.method == "POST":
        form = TaskForm(request.POST, farm=request.farm)
        if form.is_valid():
            task = form.save(commit=False)
            task.farm = request.farm
            task.save()
            messages.success(request, f'Task "{task.title}" created.')
            return redirect(TASK_BOARD)
    else:
        form = TaskForm(farm=request.farm)
    return render(request, "employment/task_form.html", {"form": form})


@require_http_methods(["GET", "POST"])
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk, farm=request.farm)
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, farm=request.farm)
        if form.is_valid():
            task = form.save(commit=False)
            if task.status == Task.Status.DONE and not task.completed_at:
                task.completed_at = timezone.now()
            elif task.status != Task.Status.DONE:
                task.completed_at = None
            task.save()
            messages.success(request, "Task updated.")
            return redirect(TASK_BOARD)
    else:
        form = TaskForm(instance=task, farm=request.farm)
    return render(request, "employment/task_form.html", {"form": form, "task": task, "editing": True})


@require_POST
def task_update_status(request, pk):
    """HTMX endpoint to update task status from kanban board."""
    task = get_object_or_404(Task, pk=pk, farm=request.farm)
    new_status = request.POST.get("status")
    if new_status in dict(Task.Status.choices):
        task.status = new_status
        if new_status == Task.Status.DONE and not task.completed_at:
            task.completed_at = timezone.now()
        elif new_status != Task.Status.DONE:
            task.completed_at = None
        task.save()
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "POST"])
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, farm=request.farm)
    if request.method == "POST":
        task.delete()
        messages.success(request, "Task deleted.")
        return redirect(TASK_BOARD)
    return render(request, "employment/task_confirm_delete.html", {"task": task})


# --- Time entries ---

@require_GET
def timesheet(request):
    entries = TimeEntry.objects.filter(farm=request.farm).select_related("employee", "task")[:50]
    return render(request, "employment/timesheet.html", {"entries": entries})


@require_http_methods(["GET", "POST"])
def time_entry_create(request):
    if request.method == "POST":
        form = TimeEntryForm(request.POST, farm=request.farm)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.farm = request.farm
            entry.save()
            messages.success(request, "Time entry recorded.")
            return redirect("employment:timesheet")
    else:
        form = TimeEntryForm(farm=request.farm)
    return render(request, "employment/time_entry_form.html", {"form": form})
