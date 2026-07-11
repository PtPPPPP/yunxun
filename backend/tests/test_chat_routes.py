import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_current_user
from backend.app.api.routes.chat import router


class ChatRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {"id": "user-1"}
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()

    def test_delete_session_returns_boolean_success_payload(self) -> None:
        with patch("backend.app.api.routes.chat.delete_user_session") as delete:
            response = self.client.delete("/api/chat/sessions/session-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "message": "会话已删除。"})
        delete.assert_called_once_with("session-1", "user-1")


if __name__ == "__main__":
    unittest.main()
