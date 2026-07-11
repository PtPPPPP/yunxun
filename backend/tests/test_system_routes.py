import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.system import router


class SystemRoutesTestCase(unittest.TestCase):
    def test_root_reports_backend_is_running(self) -> None:
        app = FastAPI()
        app.include_router(router)

        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "message": "云寻智慧农业AI工作台软件后端已启动。",
            },
        )


if __name__ == "__main__":
    unittest.main()
