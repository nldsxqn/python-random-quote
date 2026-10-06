"""Clocks for the time bank. Tests advance ManualClock and never sleep."""

import time
from dataclasses import dataclass


class SystemClock:
    def now(self) -> float:
        return time.monotonic()


@dataclass
class ManualClock:
    instant: float = 0.0

    def now(self) -> float:
        return self.instant

    def advance(self, seconds: float) -> None:
        self.instant += seconds
