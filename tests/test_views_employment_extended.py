import pytest

from apps.employment.models import Employee, TimeEntry
from tests.factories import EmployeeFactory, TaskFactory, TimeEntryFactory


@pytest.mark.django_db
class TestEmployeeViews:
    def test_list_requires_login(self, client):
        resp = client.get("/employment/employees/")
        assert resp.status_code == 302

    def test_list(self, farm_client, farm):
        EmployeeFactory(farm=farm)
        resp = farm_client.get("/employment/employees/")
        assert resp.status_code == 200

    def test_create_get(self, farm_client):
        resp = farm_client.get("/employment/employees/add/")
        assert resp.status_code == 200

    def test_create_post(self, farm_client, farm):
        resp = farm_client.post("/employment/employees/add/", {
            "first_name": "Jane",
            "last_name": "Smith",
            "status": "active",
        })
        assert resp.status_code == 302
        assert Employee.objects.filter(farm=farm, first_name="Jane").exists()

    def test_detail(self, farm_client, farm):
        emp = EmployeeFactory(farm=farm)
        resp = farm_client.get(f"/employment/employees/{emp.pk}/")
        assert resp.status_code == 200

    def test_edit(self, farm_client, farm):
        emp = EmployeeFactory(farm=farm, first_name="Old")
        resp = farm_client.post(f"/employment/employees/{emp.pk}/edit/", {
            "first_name": "New",
            "last_name": emp.last_name,
            "status": emp.status,
        })
        assert resp.status_code == 302
        emp.refresh_from_db()
        assert emp.first_name == "New"

    def test_detail_other_farm_returns_404(self, farm_client):
        other = EmployeeFactory()
        resp = farm_client.get(f"/employment/employees/{other.pk}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestTaskEditViews:
    def test_edit_get(self, farm_client, farm):
        task = TaskFactory(farm=farm)
        resp = farm_client.get(f"/employment/tasks/{task.pk}/edit/")
        assert resp.status_code == 200

    def test_edit_post(self, farm_client, farm):
        task = TaskFactory(farm=farm, title="Old Title")
        resp = farm_client.post(f"/employment/tasks/{task.pk}/edit/", {
            "title": "New Title",
            "status": "todo",
            "priority": "high",
        })
        assert resp.status_code == 302
        task.refresh_from_db()
        assert task.title == "New Title"


@pytest.mark.django_db
class TestTimesheetViews:
    def test_timesheet(self, farm_client, farm):
        emp = EmployeeFactory(farm=farm)
        TimeEntryFactory(farm=farm, employee=emp)
        resp = farm_client.get("/employment/timesheet/")
        assert resp.status_code == 200

    def test_time_entry_create_get(self, farm_client):
        resp = farm_client.get("/employment/timesheet/add/")
        assert resp.status_code == 200

    def test_time_entry_create_post(self, farm_client, farm):
        emp = EmployeeFactory(farm=farm)
        resp = farm_client.post("/employment/timesheet/add/", {
            "employee": emp.pk,
            "date": "2026-01-15",
            "hours": "8.0",
        })
        assert resp.status_code == 302
        assert TimeEntry.objects.filter(farm=farm, employee=emp).exists()
