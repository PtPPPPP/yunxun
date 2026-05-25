import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = time.monotonic()
        bucket = self._buckets[key]

        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="请求太频繁了，请稍后再试。")

        bucket.append(now)
