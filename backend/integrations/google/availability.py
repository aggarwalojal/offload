"""Calendar availability and conflict detection for TimeSlice.

Analyzes Google Calendar events to detect scheduling overlaps,
evaluate busy vs free time, and suggest available time slots for activities.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from .calendar import GoogleCalendarService


class AvailabilityValidationError(ValueError):
    """Raised when parameters, windows, or time ranges are invalid."""


def _validate_timezone_aware(dt: datetime, name: str) -> None:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise AvailabilityValidationError(f"{name} must be a timezone-aware datetime.")


def _validate_window(start: datetime, end: datetime) -> None:
    _validate_timezone_aware(start, "start_time")
    _validate_timezone_aware(end, "end_time")
    if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        raise AvailabilityValidationError("end_time must be later than start_time.")


@dataclass(frozen=True)
class TimeSlot:
    """A discrete timezone-aware time window [start_time, end_time)."""

    start_time: datetime
    end_time: datetime

    def __post_init__(self):
        _validate_window(self.start_time, self.end_time)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() // 60)

    @property
    def duration(self) -> timedelta:
        return self.end_time - self.start_time

    def start_utc(self) -> datetime:
        return self.start_time.astimezone(timezone.utc)

    def end_utc(self) -> datetime:
        return self.end_time.astimezone(timezone.utc)

    def overlaps(self, other: "TimeSlot") -> bool:
        """Two half-open intervals [s1, e1) and [s2, e2) overlap if max(s1, s2) < min(e1, e2)."""
        return max(self.start_utc(), other.start_utc()) < min(self.end_utc(), other.end_utc())

    def contains(self, other: "TimeSlot") -> bool:
        """Returns True if self completely encompasses other."""
        return self.start_utc() <= other.start_utc() and other.end_utc() <= self.end_utc()


@dataclass(frozen=True)
class Conflict:
    """Details of a scheduled event that conflicts with a requested time slot."""

    event_id: str | None
    title: str
    slot: TimeSlot


@dataclass(frozen=True)
class AvailabilityReport:
    """Result of an availability check for a proposed time slot."""

    requested_slot: TimeSlot
    is_available: bool
    conflicts: list[Conflict] = field(default_factory=list)
    suggested_slots: list[TimeSlot] = field(default_factory=list)


def parse_google_event_timeslot(
    event: dict[str, Any], default_tz: timezone | ZoneInfo = timezone.utc
) -> TimeSlot | None:
    """Extracts a normalized TimeSlot from a Google Calendar event dictionary.

    Returns None if the event is cancelled, transparent (free), or missing time information.
    Handles both timed events ('dateTime') and all-day events ('date').
    """
    if event.get("status") == "cancelled":
        return None
    if event.get("transparency") == "transparent":
        # Google Calendar treats 'transparent' events as free time (show me as available)
        return None

    start_info = event.get("start", {})
    end_info = event.get("end", {})

    # Timed event
    start_dt_str = start_info.get("dateTime")
    end_dt_str = end_info.get("dateTime")

    if start_dt_str and end_dt_str:
        try:
            start_dt = datetime.fromisoformat(start_dt_str)
            end_dt = datetime.fromisoformat(end_dt_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=default_tz)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=default_tz)
            return TimeSlot(start_time=start_dt, end_time=end_dt)
        except (ValueError, TypeError):
            return None

    # All-day event
    start_date_str = start_info.get("date")
    end_date_str = end_info.get("date")

    if start_date_str and end_date_str:
        try:
            # All-day start: midnight at user's timezone on start date
            s_date = date.fromisoformat(start_date_str)
            e_date = date.fromisoformat(end_date_str)
            start_dt = datetime.combine(s_date, time.min, tzinfo=default_tz)
            end_dt = datetime.combine(e_date, time.min, tzinfo=default_tz)
            return TimeSlot(start_time=start_dt, end_time=end_dt)
        except (ValueError, TypeError):
            return None

    return None


def extract_busy_slots(
    events: Sequence[dict[str, Any]], default_tz: timezone | ZoneInfo = timezone.utc
) -> list[TimeSlot]:
    """Converts a sequence of Google event dictionaries into busy TimeSlots."""
    busy: list[TimeSlot] = []
    for ev in events:
        slot = parse_google_event_timeslot(ev, default_tz=default_tz)
        if slot is not None:
            busy.append(slot)
    return busy


def merge_busy_slots(slots: Sequence[TimeSlot]) -> list[TimeSlot]:
    """Merges overlapping or immediately adjoining TimeSlots into contiguous blocks."""
    if not slots:
        return []

    # Sort slots chronologically by UTC start time
    sorted_slots = sorted(slots, key=lambda s: (s.start_utc(), s.end_utc()))
    merged: list[TimeSlot] = [sorted_slots[0]]

    for current in sorted_slots[1:]:
        last = merged[-1]
        # Overlapping or contiguous in UTC
        if current.start_utc() <= last.end_utc():
            new_end = max(last.end_utc(), current.end_utc())
            # Retain original timezone formatting where possible
            tz = last.start_time.tzinfo
            merged[-1] = TimeSlot(
                start_time=last.start_time,
                end_time=new_end.astimezone(tz),
            )
        else:
            merged.append(current)

    return merged


def detect_conflicts(
    target_slot: TimeSlot,
    events: Sequence[dict[str, Any]],
    default_tz: timezone | ZoneInfo = timezone.utc,
) -> list[Conflict]:
    """Checks for overlaps between a target slot and a list of Google Calendar events."""
    conflicts: list[Conflict] = []
    for ev in events:
        slot = parse_google_event_timeslot(ev, default_tz=default_tz)
        if slot and target_slot.overlaps(slot):
            title = ev.get("summary") or "Untitled Event"
            event_id = ev.get("id")
            conflicts.append(Conflict(event_id=event_id, title=title, slot=slot))
    return conflicts


def find_free_gaps(
    search_window: TimeSlot,
    busy_slots: Sequence[TimeSlot],
) -> list[TimeSlot]:
    """Computes free intervals within search_window that are not occupied by busy_slots."""
    tz = search_window.start_time.tzinfo

    # Filter and clip busy slots to the search window
    clipped_busy: list[TimeSlot] = []
    window_start_utc = search_window.start_utc()
    window_end_utc = search_window.end_utc()

    for b in busy_slots:
        b_start_utc = b.start_utc()
        b_end_utc = b.end_utc()
        if b_end_utc <= window_start_utc or b_start_utc >= window_end_utc:
            continue
        clipped_start = max(window_start_utc, b_start_utc)
        clipped_end = min(window_end_utc, b_end_utc)
        clipped_busy.append(
            TimeSlot(
                start_time=clipped_start.astimezone(tz),
                end_time=clipped_end.astimezone(tz),
            )
        )

    merged = merge_busy_slots(clipped_busy)

    free_gaps: list[TimeSlot] = []
    current_time_utc = window_start_utc

    for b in merged:
        b_start_utc = b.start_utc()
        if current_time_utc < b_start_utc:
            free_gaps.append(
                TimeSlot(
                    start_time=current_time_utc.astimezone(tz),
                    end_time=b_start_utc.astimezone(tz),
                )
            )
        current_time_utc = max(current_time_utc, b.end_utc())

    if current_time_utc < window_end_utc:
        free_gaps.append(
            TimeSlot(
                start_time=current_time_utc.astimezone(tz),
                end_time=window_end_utc.astimezone(tz),
            )
        )

    return free_gaps


def suggest_available_slots(
    duration: timedelta,
    search_window: TimeSlot,
    busy_slots: Sequence[TimeSlot],
    step: timedelta = timedelta(minutes=30),
    limit: int = 5,
) -> list[TimeSlot]:
    """Suggests up to `limit` available time slots of `duration` within search_window.

    Slots are generated on regular `step` boundaries (default 30 mins) inside free gaps.
    """
    if duration <= timedelta(0):
        raise AvailabilityValidationError("duration must be greater than zero.")
    if step <= timedelta(0):
        raise AvailabilityValidationError("step must be greater than zero.")
    if limit < 1:
        return []

    gaps = find_free_gaps(search_window, busy_slots)
    suggestions: list[TimeSlot] = []

    for gap in gaps:
        gap_start = gap.start_time
        gap_end = gap.end_time

        candidate_start = gap_start
        while candidate_start + duration <= gap_end:
            suggestions.append(
                TimeSlot(
                    start_time=candidate_start,
                    end_time=candidate_start + duration,
                )
            )
            if len(suggestions) >= limit:
                return suggestions
            candidate_start += step

    return suggestions


class GoogleAvailabilityService:
    """Service to evaluate availability and suggest alternatives using GoogleCalendarService."""

    def __init__(self, calendar_service: GoogleCalendarService):
        if not hasattr(calendar_service, "list_events") or not callable(getattr(calendar_service, "list_events")):
            raise AvailabilityValidationError("calendar_service with list_events method is required.")
        self.calendar_service = calendar_service

    def check_availability(
        self,
        target_slot: TimeSlot,
        *,
        calendar_id: str = "primary",
        suggest_alternatives: bool = True,
        search_window: TimeSlot | None = None,
        limit: int = 3,
    ) -> AvailabilityReport:
        """Checks if target_slot is free on the user's Google Calendar.

        If conflicts exist and suggest_alternatives is True, queries the surrounding
        search_window (defaults to target day) and proposes non-conflicting slots.
        """
        # Determine query window
        if search_window is None:
            # Default search window: same day from 08:00 to 22:00 in user's timezone
            tz = target_slot.start_time.tzinfo or timezone.utc
            target_day = target_slot.start_time.date()
            window_start = datetime.combine(target_day, time(8, 0), tzinfo=tz)
            window_end = datetime.combine(target_day, time(22, 0), tzinfo=tz)
            # Ensure window encompasses the target slot
            if target_slot.start_time < window_start:
                window_start = target_slot.start_time
            if target_slot.end_time > window_end:
                window_end = target_slot.end_time
            query_window = TimeSlot(start_time=window_start, end_time=window_end)
        else:
            query_window = search_window

        # Fetch events overlapping the query window
        events = self.calendar_service.list_events(
            start_time=query_window.start_time,
            end_time=query_window.end_time,
            calendar_id=calendar_id,
        )

        default_tz = target_slot.start_time.tzinfo or timezone.utc
        conflicts = detect_conflicts(target_slot, events, default_tz=default_tz)
        is_available = len(conflicts) == 0

        suggested: list[TimeSlot] = []
        if not is_available and suggest_alternatives:
            busy = extract_busy_slots(events, default_tz=default_tz)
            suggested = suggest_available_slots(
                duration=target_slot.duration,
                search_window=query_window,
                busy_slots=busy,
                limit=limit,
            )

        return AvailabilityReport(
            requested_slot=target_slot,
            is_available=is_available,
            conflicts=conflicts,
            suggested_slots=suggested,
        )
