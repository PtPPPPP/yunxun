import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.farm import router
from backend.app.core.database import init_db
from backend.app.core.errors import AppError, ErrorCode
from backend.app.core.exceptions import http_exception_handler
from backend.app.repositories import create_plot, create_user, list_plots
from backend.app.services.farm import (
    create_user_farm_task,
    delete_user_farm_task,
    list_user_farm_tasks,
    update_user_farm_task,
)
from backend.tests.helpers import make_settings


def make_plot(user_id: str, name: str = "东坡三亩地") -> dict:
    return create_plot(
        user_id=user_id,
        name=name,
        area_mu=3.5,
        soil_type="壤土",
        irrigation="井灌",
        crop="玉米",
        planted_on="2026-05-12",
        notes="",
    )


class FarmTaskServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "task-service.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.plot = make_plot(self.user_id)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_task(self, title: str, due_on: str, plot_id: str | None = None, notes: str = "") -> dict:
        return create_user_farm_task(
            user_id=self.user_id,
            client_host="127.0.0.1",
            plot_id=plot_id,
            title=title,
            due_on=due_on,
            notes=notes,
        )

    def test_task_can_be_created_with_or_without_plot(self) -> None:
        with_plot = self.add_task("  复查长势  ", "2026-09-20", plot_id=self.plot["id"], notes=" 看叶色 ")
        without_plot = self.add_task("去镇上买地膜", "2026-09-18")

        self.assertEqual(with_plot["title"], "复查长势")
        self.assertEqual(with_plot["notes"], "看叶色")
        self.assertEqual(with_plot["plot_name"], "东坡三亩地")
        self.assertFalse(with_plot["done"])
        self.assertIsNone(without_plot["plot_id"])
        self.assertEqual(without_plot["plot_name"], "")

    def test_open_tasks_are_ordered_by_due_date(self) -> None:
        self.add_task("第三", "2026-09-25")
        self.add_task("第一", "2026-09-18")
        self.add_task("第二", "2026-09-20")

        tasks = list_user_farm_tasks(self.user_id)["tasks"]
        self.assertEqual([task["title"] for task in tasks], ["第一", "第二", "第三"])

    def test_completing_and_reopening_moves_between_lists(self) -> None:
        task = self.add_task("复查长势", "2026-09-20")

        done = update_user_farm_task(
            task["id"], self.user_id, "127.0.0.1",
            plot_id=task["plot_id"], title=task["title"], due_on=task["due_on"], notes=task["notes"], done=True,
        )
        self.assertTrue(done["done"])
        self.assertIsNotNone(done["done_at"])

        payload = list_user_farm_tasks(self.user_id)
        self.assertEqual(payload["tasks"], [])
        self.assertEqual([item["title"] for item in payload["recent_done"]], ["复查长势"])

        reopened = update_user_farm_task(
            task["id"], self.user_id, "127.0.0.1",
            plot_id=task["plot_id"], title=task["title"], due_on=task["due_on"], notes=task["notes"], done=False,
        )
        self.assertFalse(reopened["done"])
        self.assertIsNone(reopened["done_at"])
        self.assertEqual(len(list_user_farm_tasks(self.user_id)["tasks"]), 1)

    def test_editing_without_changing_done_keeps_done_at(self) -> None:
        task = self.add_task("复查长势", "2026-09-20")
        finished = update_user_farm_task(
            task["id"], self.user_id, "127.0.0.1",
            plot_id=task["plot_id"], title=task["title"], due_on=task["due_on"], notes="", done=True,
        )

        edited = update_user_farm_task(
            task["id"], self.user_id, "127.0.0.1",
            plot_id=task["plot_id"], title="复查长势并拍照", due_on="2026-09-22", notes="", done=True,
        )
        self.assertEqual(edited["title"], "复查长势并拍照")
        self.assertEqual(edited["due_on"], "2026-09-22")
        self.assertEqual(edited["done_at"], finished["done_at"])

    def test_plot_without_tasks_reports_zero(self) -> None:
        self.assertEqual(list_plots(self.user_id)[0]["open_task_count"], 0)
        self.add_task("复查长势", "2026-09-20", plot_id=self.plot["id"])
        self.assertEqual(list_plots(self.user_id)[0]["open_task_count"], 1)

    def test_tasks_are_isolated_by_user(self) -> None:
        self.add_task("复查长势", "2026-09-20")
        self.assertEqual(list_user_farm_tasks("user-other"), {"tasks": [], "recent_done": []})

    def test_foreign_task_and_plot_are_rejected(self) -> None:
        task = self.add_task("复查长势", "2026-09-20")

        with self.assertRaises(AppError) as foreign_task:
            update_user_farm_task(
                task["id"], "user-other", "127.0.0.1",
                plot_id=None, title="改一下", due_on="2026-09-20", notes="", done=False,
            )
        self.assertEqual(foreign_task.exception.code, ErrorCode.NOT_FOUND)

        with self.assertRaises(AppError):
            delete_user_farm_task(task["id"], "user-other", "127.0.0.1")

        # 挂到别人的地块上也要拒绝
        with self.assertRaises(AppError):
            create_user_farm_task(
                user_id="user-other",
                client_host="127.0.0.1",
                plot_id=self.plot["id"],
                title="越权",
                due_on="2026-09-20",
                notes="",
            )

    def test_delete_task(self) -> None:
        task = self.add_task("复查长势", "2026-09-20")
        delete_user_farm_task(task["id"], self.user_id, "127.0.0.1")
        self.assertEqual(list_user_farm_tasks(self.user_id)["tasks"], [])

        with self.assertRaises(AppError):
            delete_user_farm_task(task["id"], self.user_id, "127.0.0.1")

    def test_plot_delete_removes_its_tasks_and_reports_count(self) -> None:
        self.add_task("复查长势", "2026-09-20", plot_id=self.plot["id"])
        self.add_task("再查一次", "2026-09-27", plot_id=self.plot["id"])
        self.add_task("不挂地块的杂事", "2026-09-21")

        from backend.app.repositories import delete_plot_with_records

        removed_records, removed_tasks = delete_plot_with_records(self.plot["id"])
        self.assertEqual(removed_records, 0)
        self.assertEqual(removed_tasks, 2)
        remaining = list_user_farm_tasks(self.user_id)["tasks"]
        self.assertEqual([task["title"] for task in remaining], ["不挂地块的杂事"])


class FarmTaskRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "task-routes.db"
        patcher = patch("backend.app.core.database.get_settings", return_value=make_settings(self.db_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        init_db()
        self.app = FastAPI()
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.include_router(router)
        self.user_id = create_user("farmer", "hash", "农户")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.plot = make_plot(self.user_id)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def payload(self, **overrides: object) -> dict:
        base = {"plot_id": self.plot["id"], "title": "复查追肥后长势", "due_on": "2026-09-20", "notes": ""}
        base.update(overrides)
        return base

    def test_create_list_and_toggle(self) -> None:
        created = self.client.post("/api/farm-tasks", json=self.payload())
        self.assertEqual(created.status_code, 200)
        task = created.json()["task"]
        self.assertEqual(task["plot_name"], "东坡三亩地")
        self.assertFalse(task["done"])

        listed = self.client.get("/api/farm-tasks").json()
        self.assertEqual(len(listed["tasks"]), 1)
        self.assertEqual(listed["recent_done"], [])

        toggled = self.client.patch(
            f"/api/farm-tasks/{task['id']}",
            json=self.payload(done=True),
        ).json()["task"]
        self.assertTrue(toggled["done"])

        after = self.client.get("/api/farm-tasks").json()
        self.assertEqual(after["tasks"], [])
        self.assertEqual(len(after["recent_done"]), 1)

    def test_create_validates_payload(self) -> None:
        self.assertEqual(self.client.post("/api/farm-tasks", json=self.payload(title="")).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-tasks", json=self.payload(due_on="2026/09/20")).status_code, 422)
        self.assertEqual(self.client.post("/api/farm-tasks", json=self.payload(plot_id="missing")).status_code, 404)
        self.assertEqual(
            self.client.post("/api/farm-tasks", json=self.payload(title="x" * 61)).status_code, 422
        )

    def test_task_can_skip_plot(self) -> None:
        created = self.client.post("/api/farm-tasks", json=self.payload(plot_id=None))
        self.assertEqual(created.status_code, 200)
        self.assertIsNone(created.json()["task"]["plot_id"])

    def test_open_task_count_shows_on_plot_list(self) -> None:
        self.client.post("/api/farm-tasks", json=self.payload())
        self.assertEqual(self.client.get("/api/plots").json()["plots"][0]["open_task_count"], 1)

    def test_delete_task(self) -> None:
        task_id = self.client.post("/api/farm-tasks", json=self.payload()).json()["task"]["id"]
        self.assertEqual(self.client.delete(f"/api/farm-tasks/{task_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/farm-tasks/{task_id}").status_code, 404)

    def test_other_users_cannot_read_or_touch_tasks(self) -> None:
        task_id = self.client.post("/api/farm-tasks", json=self.payload()).json()["task"]["id"]
        other_id = create_user("intruder", "hash", "陌生人")["id"]
        self.app.dependency_overrides[get_current_user] = lambda: {"id": other_id}

        self.assertEqual(self.client.get("/api/farm-tasks").json(), {"success": True, "tasks": [], "recent_done": []})
        self.assertEqual(self.client.patch(f"/api/farm-tasks/{task_id}", json=self.payload()).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/farm-tasks/{task_id}").status_code, 404)
        self.assertEqual(self.client.post("/api/farm-tasks", json=self.payload(plot_id=None)).status_code, 200)


if __name__ == "__main__":
    unittest.main()
