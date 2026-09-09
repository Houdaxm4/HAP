"""In-process login throttle and session revocation. Single worker assumed."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from hap_auth import LOCKOUT_SECONDS, MAX_FAILED_ATTEMPTS


@dataclass
class LoginThrottle:
    failures: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    locked_until: dict[str, float] = field(default_factory=dict)

    def is_blocked(self, key: str, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        until = self.locked_until.get(key, 0.0)
        return current < until

    def register_failure(self, key: str, now: float | None = None) -> None:
        current = now if now is not None else time.time()
        window_start = current - LOCKOUT_SECONDS
        recent = [t for t in self.failures[key] if t >= window_start]
        recent.append(current)
        self.failures[key] = recent
        if len(recent) >= MAX_FAILED_ATTEMPTS:
            self.locked_until[key] = current + LOCKOUT_SECONDS

    def register_success(self, key: str) -> None:
        self.failures.pop(key, None)
        self.locked_until.pop(key, None)


throttle = LoginThrottle()
revoked_jtis: set[str] = set()
