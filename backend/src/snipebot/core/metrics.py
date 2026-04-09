from __future__ import annotations

from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = defaultdict(int)

    def inc(self, key: str, value: int = 1) -> None:
        if value <= 0:
            return
        with self._lock:
            self._counters[key] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))


metrics = MetricsRegistry()
