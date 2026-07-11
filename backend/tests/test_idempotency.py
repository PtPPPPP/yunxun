import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.app.core.config import Settings
from backend.app.core.database import init_db
from backend.app.core.idempotency import DatabaseIdempotencyStore, build_fingerprint


def make_settings(db_path: Path) -> Settings:
    return Settings(
        app_name="yunxun-test",
        app_version="test",
        environment="test",
        debug=False,
        host="127.0.0.1",
        port=8001,
        backend_url="http://127.0.0.1:8001",
        jwt_secret="test-secret",
        api_key="",
        base_url="https://example.invalid",
        chat_endpoint="test-model",
        vision_endpoint="test-model",
        available_models_raw="test-model",
        database_url=f"sqlite:///{db_path}",
        db_path=str(db_path),
        allowed_origins_raw="http://127.0.0.1:5173",
        cors_methods_raw="GET,POST,PATCH,DELETE,OPTIONS",
        cors_headers_raw="Authorization,Content-Type,X-Idempotency-Key",
        max_message_length=3000,
        requests_per_minute=20,
        token_hours=168,
    )


class ManualClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 12, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class DatabaseIdempotencyStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "idempotency.db"
        self.settings = make_settings(self.db_path)
        self.database_patch = patch("backend.app.core.database.get_settings", return_value=self.settings)
        self.database_patch.start()
        init_db()

    def tearDown(self) -> None:
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_fingerprint_is_stable_and_order_sensitive(self) -> None:
        self.assertEqual(build_fingerprint("chat", "u1", "你好"), build_fingerprint("chat", "u1", "你好"))
        self.assertNotEqual(build_fingerprint("a", "b"), build_fingerprint("b", "a"))
        self.assertEqual(len(build_fingerprint("x")), 64)

    def test_first_claim_is_atomic_and_second_is_in_flight(self) -> None:
        store = DatabaseIdempotencyStore()
        first = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60)
        second = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60)

        self.assertEqual(first.state, "acquired")
        self.assertIsNotNone(first.lease_id)
        self.assertEqual(second.state, "in_flight")

    def test_completed_result_survives_store_reinitialization(self) -> None:
        first_store = DatabaseIdempotencyStore()
        claim = first_store.begin(
            owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60
        )
        self.assertTrue(
            first_store.complete(
                owner_id="u1",
                key_hash="key-1",
                lease_id=str(claim.lease_id),
                response_status=200,
                response_body={"reply": "ok"},
                ttl_seconds=60,
            )
        )

        replay = DatabaseIdempotencyStore().begin(
            owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60
        )
        self.assertEqual(replay.state, "completed")
        self.assertEqual(replay.response_status, 200)
        self.assertEqual(replay.response_body, {"reply": "ok"})

    def test_same_key_with_different_request_conflicts(self) -> None:
        store = DatabaseIdempotencyStore()
        store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-a", ttl_seconds=60)
        conflict = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-b", ttl_seconds=60)
        self.assertEqual(conflict.state, "conflict")

    def test_failed_request_can_be_claimed_again(self) -> None:
        store = DatabaseIdempotencyStore()
        claim = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60)
        self.assertTrue(store.fail(owner_id="u1", key_hash="key-1", lease_id=str(claim.lease_id)))
        retried = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60)
        self.assertEqual(retried.state, "acquired")
        self.assertNotEqual(retried.lease_id, claim.lease_id)

    def test_expired_record_is_reclaimed_and_cleanup_is_bounded(self) -> None:
        clock = ManualClock()
        store = DatabaseIdempotencyStore(now_provider=clock.now)
        store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=5)
        clock.advance(6)
        reclaimed = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=5)
        self.assertEqual(reclaimed.state, "acquired")

    def test_response_size_limit_prevents_unbounded_database_growth(self) -> None:
        store = DatabaseIdempotencyStore(max_response_bytes=16)
        claim = store.begin(owner_id="u1", key_hash="key-1", request_fingerprint="payload-1", ttl_seconds=60)
        with self.assertRaises(ValueError):
            store.complete(
                owner_id="u1",
                key_hash="key-1",
                lease_id=str(claim.lease_id),
                response_status=200,
                response_body={"reply": "x" * 100},
                ttl_seconds=60,
            )

    def test_two_store_instances_cannot_both_acquire_same_request(self) -> None:
        barrier = threading.Barrier(2)
        states: list[str] = []
        errors: list[Exception] = []

        def claim() -> None:
            try:
                barrier.wait()
                result = DatabaseIdempotencyStore().begin(
                    owner_id="u1",
                    key_hash="shared-key",
                    request_fingerprint="payload-1",
                    ttl_seconds=60,
                )
                states.append(result.state)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertCountEqual(states, ["acquired", "in_flight"])


if __name__ == "__main__":
    unittest.main()
