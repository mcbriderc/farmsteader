from django import forms

from .models import Employee, Task, TimeEntry

INPUT_CLASS = "w-full rounded-lg border-gray-300 shadow-sm text-sm px-3 py-2 border"


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["first_name", "last_name", "email", "phone", "role", "status",
                   "hire_date", "hourly_rate", "emergency_contact", "notes"]
        widgets = {
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "emergency_contact": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "assigned_to", "priority", "status", "due_date", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["assigned_to"].queryset = Employee.objects.filter(farm=farm, status=Employee.Status.ACTIVE)
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ["employee", "task", "date", "hours", "description", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["employee"].queryset = Employee.objects.filter(farm=farm)
            self.fields["task"].queryset = Task.objects.filter(farm=farm)
            self.fields["task"].required = False
        for name, field in self.fields.items():
            if not field.widget.attrs.get("class"):
                field.widget.attrs["class"] = INPUT_CLASS
