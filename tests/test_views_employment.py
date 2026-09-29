import pytest

from apps.employment.models import Task
from tests.factories import TaskFactory


@pytest.mark.django_db
class TestTaskViews:
    def test_board_requires_login(self, client):
        resp = client.get("/employment/tasks/")
        assert resp.status_code == 302

    def test_board_renders(self, farm_client):
        resp = farm_client.get("/employment/tasks/")
        assert resp.status_code == 200
        assert "todo" in resp.context
        assert "in_progress" in resp.context
        assert "done" in resp.context

    def test_board_excludes_other_farm_tasks(self, farm_client, farm):
        own_task = TaskFactory(farm=farm)
        other_task = TaskFactory()
        resp = farm_client.get("/employment/tasks/")
        todo_pks = [t.pk for t in resp.context["todo"]]
        assert own_task.pk in todo_pks
        assert other_task.pk not in todo_pks

    def test_create_task(self, farm_client, farm):
        resp = farm_client.post("/employment/tasks/add/", {
            "title": "Fix the fence",
            "status": "todo",
            "priority": "high",
        })
        assert resp.status_code == 302
        assert Task.objects.filter(farm=farm, title="Fix the fence").exists()

    def test_update_status_htmx(self, farm_client, farm):
        task = TaskFactory(farm=farm, status=Task.Status.TODO)
        resp = farm_client.post(
            f"/employment/tasks/{task.pk}/status/",
            {"status": "in_progress"},
        )
        assert resp.status_code == 200
        task.refresh_from_db()
        assert task.status == Task.Status.IN_PROGRESS

    def test_delete_task(self, farm_client, farm):
        task = TaskFactory(farm=farm)
        resp = farm_client.post(f"/employment/tasks/{task.pk}/delete/")
        assert resp.status_code == 302
        assert not Task.objects.filter(pk=task.pk).exists()
