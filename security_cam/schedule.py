from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import List, Tuple


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":", 1)
    return time(int(h), int(m))


@dataclass
class DailyWindow:
    start: time
    end: time  # if end <= start, window wraps past midnight

    def contains(self, t: time) -> bool:
        if self.end > self.start:
            return self.start <= t < self.end
        # wrap-around window
        return t >= self.start or t < self.end


class DailySchedule:
    def __init__(self, spec: str) -> None:
        self.windows: List[DailyWindow] = []
        spec = (spec or "").strip()
        if not spec:
            self.windows = []  # empty => always active
            return
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                a, b = part.split("-", 1)
                self.windows.append(DailyWindow(_parse_hhmm(a), _parse_hhmm(b)))
            except Exception:
                # ignore invalid pieces silently to stay simple
                continue

    def is_active_now(self) -> bool:
        if not self.windows:
            return True
        now_t = datetime.now().time()
        return any(w.contains(now_t) for w in self.windows)

