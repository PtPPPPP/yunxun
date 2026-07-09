import time
from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Deque

from fastapi import HTTPException


TimeProvider = Callable[[], float]


@dataclass(frozen=True)
class RateLimitResult:
    key: str
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: float


@dataclass
class RateLimitBucket:
    attempts: Deque[float]
    window_seconds: float

    def prune(self, now: float) -> int:
        removed = 0
        while self.attempts and now - self.attempts[0] >= self.window_seconds:
            self.attempts.popleft()
            removed += 1
        return removed

    def reset_after(self, now: float) -> float:
        if not self.attempts:
            return 0.0
        return max(0.0, self.window_seconds - (now - self.attempts[0]))


class InMemoryRateLimiter:
    def __init__(self, time_provider: TimeProvider | None = None) -> None:
        self._time_provider = time_provider or time.monotonic
        self._buckets: dict[str, RateLimitBucket] = {}
        self._lock = RLock()

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> RateLimitResult:
        self._validate_request(key, limit, window_seconds)

        with self._lock:
            now = self._time_provider()
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = RateLimitBucket(attempts=deque(), window_seconds=window_seconds)
                self._buckets[key] = bucket
            else:
                bucket.window_seconds = window_seconds

            bucket.prune(now)
            if len(bucket.attempts) >= limit:
                reset_after = bucket.reset_after(now)
                raise HTTPException(
                    status_code=429,
                    detail=f"请求太频繁了，请 {max(1, int(reset_after))} 秒后再试。",
                    headers={"Retry-After": str(max(1, int(reset_after)))},
                )

            bucket.attempts.append(now)
            remaining = max(0, limit - len(bucket.attempts))
            return RateLimitResult(
                key=key,
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_after_seconds=bucket.reset_after(now),
            )

    def cleanup(self, window_seconds: float | None = None) -> int:
        with self._lock:
            now = self._time_provider()
            removed_keys: list[str] = []

            for key, bucket in self._buckets.items():
                if window_seconds is not None and not bucket.attempts:
                    bucket.window_seconds = window_seconds
                bucket.prune(now)
                if not bucket.attempts:
                    removed_keys.append(key)

            for key in removed_keys:
                self._buckets.pop(key, None)

            return len(removed_keys)

    def reset(self, key: str | None = None) -> bool:
        with self._lock:
            if key is None:
                had_entries = bool(self._buckets)
                self._buckets.clear()
                return had_entries
            return self._buckets.pop(key, None) is not None

    def snapshot(self) -> dict[str, list[float]]:
        with self._lock:
            return {key: list(bucket.attempts) for key, bucket in self._buckets.items()}

    @staticmethod
    def _validate_request(key: str, limit: int, window_seconds: float) -> None:
        if not key or not key.strip():
            raise ValueError("rate limit key 不能为空。")
        if limit <= 0:
            raise ValueError("rate limit limit 必须大于 0。")
        if window_seconds <= 0:
            raise ValueError("rate limit window_seconds 必须大于 0。")
