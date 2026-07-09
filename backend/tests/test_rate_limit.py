import threading
import unittest

from fastapi import HTTPException

from backend.app.core.rate_limit import InMemoryRateLimiter


class ManualClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RateLimitTestCase(unittest.TestCase):
    def test_rate_limiter_tracks_remaining_attempts_and_resets_after_window(self) -> None:
        clock = ManualClock()
        limiter = InMemoryRateLimiter(time_provider=clock.now)

        first = limiter.check("user:1", limit=2, window_seconds=10)
        second = limiter.check("user:1", limit=2, window_seconds=10)

        self.assertTrue(first.allowed)
        self.assertEqual(first.remaining, 1)
        self.assertTrue(second.allowed)
        self.assertEqual(second.remaining, 0)

        with self.assertRaises(HTTPException) as blocked:
            limiter.check("user:1", limit=2, window_seconds=10)
        self.assertEqual(blocked.exception.status_code, 429)

        clock.advance(11)
        recovered = limiter.check("user:1", limit=2, window_seconds=10)
        self.assertTrue(recovered.allowed)
        self.assertEqual(recovered.remaining, 1)

    def test_cleanup_removes_expired_and_empty_buckets(self) -> None:
        clock = ManualClock()
        limiter = InMemoryRateLimiter(time_provider=clock.now)
        limiter.check("old", limit=3, window_seconds=5)
        limiter.check("fresh", limit=3, window_seconds=20)

        clock.advance(6)
        removed = limiter.cleanup(window_seconds=5)

        self.assertEqual(removed, 1)
        self.assertNotIn("old", limiter.snapshot())
        self.assertIn("fresh", limiter.snapshot())

    def test_reset_can_clear_one_key_or_all_keys(self) -> None:
        clock = ManualClock()
        limiter = InMemoryRateLimiter(time_provider=clock.now)
        limiter.check("a", limit=3)
        limiter.check("b", limit=3)

        self.assertTrue(limiter.reset("a"))
        self.assertNotIn("a", limiter.snapshot())
        self.assertIn("b", limiter.snapshot())

        self.assertTrue(limiter.reset())
        self.assertEqual(limiter.snapshot(), {})

    def test_concurrent_checks_do_not_exceed_limit(self) -> None:
        clock = ManualClock()
        limiter = InMemoryRateLimiter(time_provider=clock.now)
        accepted = 0
        lock = threading.Lock()

        def attempt() -> None:
            nonlocal accepted
            try:
                limiter.check("shared", limit=5, window_seconds=60)
            except HTTPException:
                return
            with lock:
                accepted += 1

        threads = [threading.Thread(target=attempt) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(accepted, 5)


if __name__ == "__main__":
    unittest.main()
