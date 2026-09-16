import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from backend.app.core.database import init_db
from backend.app.repositories import create_tool_record, create_user, list_tool_records_page
from backend.tests.helpers import make_settings


class SQLiteConcurrencyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.temp_dir.name) / "concurrency.db")
        self.patcher = patch("backend.app.core.database.get_settings", return_value=self.settings)
        self.patcher.start()
        init_db()
        self.user = create_user("concurrent", "hash", "Concurrent")

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_concurrent_tool_record_writes_lose_no_records(self) -> None:
        def write(index: int) -> str:
            return create_tool_record(
                user_id=self.user["id"],
                kind="decision",
                crop=f"作物{index}",
                payload={"index": index},
                result=f"建议 {index}",
                mode="local",
            )["id"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(write, range(20)))

        self.assertEqual(len(set(ids)), 20)
        records, has_more = list_tool_records_page(self.user["id"], kind=None, limit=100, cursor=None)
        self.assertEqual(len(records), 20)
        self.assertFalse(has_more)
