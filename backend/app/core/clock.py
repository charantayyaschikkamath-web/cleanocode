from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable

UTC = timezone.utc


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


class VirtualClock:
    """Injectable clock that keeps wall time and accelerated scenario time separate.

    The multiplier advances virtual timestamps faster than wall time. It must not be
    applied a second time to an already-specified virtual duration such as 600 seconds.
    """

    def __init__(
        self,
        multiplier: float = 1.0,
        *,
        wall_now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        virtual_origin: datetime | None = None,
    ) -> None:
        if multiplier <= 0:
            raise ValueError("multiplier must be greater than zero")
        self.multiplier = float(multiplier)
        self._wall_now = wall_now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._monotonic_origin = self._monotonic()
        origin = virtual_origin or self._wall_now()
        self._virtual_origin = as_utc(origin)

    def wall_now(self) -> datetime:
        return as_utc(self._wall_now())

    def virtual_now(self) -> datetime:
        elapsed_wall = max(0.0, self._monotonic() - self._monotonic_origin)
        return self._virtual_origin + timedelta(seconds=elapsed_wall * self.multiplier)

    def elapsed_virtual_seconds(self, start: datetime, end: datetime | None = None) -> float:
        start_utc = as_utc(start)
        end_utc = as_utc(end) if end is not None else self.virtual_now()
        return max(0.0, (end_utc - start_utc).total_seconds())

    def description(self) -> dict[str, object]:
        return {
            "multiplier": self.multiplier,
            "virtual_now": self.virtual_now().isoformat().replace("+00:00", "Z"),
            "wall_now": self.wall_now().isoformat().replace("+00:00", "Z"),
            "duration_unit": "virtual_seconds",
        }
