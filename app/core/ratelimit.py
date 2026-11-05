"""Pembatas laju sederhana di memori (1 worker). Melindungi endpoint login dari tebakan password berulang.

Supabase punya batas sendiri; ini lapisan tambahan yang menolak lebih awal dan per kombinasi IP + email.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events, self.window = max_events, window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and q[0] <= now - self.window:
            q.popleft()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._events.get(key)
            if q is None:
                return False
            self._prune(q, now)
            if not q:
                del self._events[key]
                return False
            return len(q) >= self.max_events

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._events[key]
            self._prune(q, now)
            q.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)

    def check(self, key: str, detail: str = "Terlalu banyak percobaan, coba lagi beberapa menit lagi") -> None:
        if self.blocked(key):
            raise HTTPException(429, detail, headers={"Retry-After": str(int(self.window))})


def client_ip(request: Request) -> str:
    """IP klien; di belakang proxy Railway diambil dari X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
