"""Daily arming schedule utilities.

Parses strings like "22:00-06:00,12:30-13:30" into daily time windows and
provides helpers to check if the current time is within any window.
"""

from __future__ import annotations

from dataclasses import dataclass  # Lightweight window representation
from datetime import datetime, time  # Time handling
from typing import List  # Type hints


def _parse_hhmm(s: str) -> time:
    """Parse an "HH:MM" string into a time object.

    Args:
      s: Time string in 24-hour format (e.g., "22:30").

    Returns:
      A `datetime.time` instance for the given hours and minutes.
    """
    h, m = s.split(":", 1)  # Split into hours and minutes
    return time(int(h), int(m))  # Construct `time` value


@dataclass
class DailyWindow:
    """Represents a daily time window.

    If `end <= start`, the window wraps past midnight (e.g., 22:00-06:00).
    """

    start: time  # Inclusive start time
    end: time  # Exclusive end time

    def contains(self, t: time) -> bool:
        """Check if a given time is within this window.

        Args:
          t: The time to check.

        Returns:
          True if `t` lies inside the window; False otherwise.
        """
        if self.end > self.start:  # Normal (non-wrapping) window
            return self.start <= t < self.end  # Inclusive start, exclusive end
        # Wrap-around window (spans midnight)
        return t >= self.start or t < self.end


class DailySchedule:
    """Parses a schedule spec and evaluates if it's active now.

    The spec is a comma-separated list of windows in "HH:MM-HH:MM" format.
    Empty spec means always active.
    """

    def __init__(self, spec: str) -> None:
        """Create a schedule.

        Args:
          spec: Comma-separated windows or empty for always-on.
        """
        self.windows: List[DailyWindow] = []  # Parsed windows list
        spec = (spec or "").strip()  # Normalize input
        if not spec:  # No windows => always active
            self.windows = []
            return
        for part in spec.split(","):  # Iterate comma-separated windows
            part = part.strip()
            if not part:
                continue
            try:
                a, b = part.split("-", 1)  # Parse start-end
                self.windows.append(DailyWindow(_parse_hhmm(a), _parse_hhmm(b)))
            except Exception:
                # Ignore invalid fragments to keep behavior forgiving
                continue

    def is_active_now(self) -> bool:
        """Return True if the current local time is within any window.

        Returns:
          True if currently active, False otherwise.
        """
        if not self.windows:  # No windows configured => active
            return True
        now_t = datetime.now().time()  # Current local time-of-day
        return any(w.contains(now_t) for w in self.windows)  # Check windows
