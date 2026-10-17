"""Unit tests for availability, overlap detection, and slot suggestions."""

from datetime import datetime, time, timedelta, timezone
import unittest
from unittest.mock import Mock

from backend.integrations.google.availability import (
    AvailabilityReport,
    AvailabilityValidationError,
    Conflict,
    GoogleAvailabilityService,
    TimeSlot,
    detect_conflicts,
    extract_busy_slots,
    find_free_gaps,
    merge_busy_slots,
    parse_google_event_timeslot,
    suggest_available_slots,
)

EDT = timezone(timedelta(hours=-4))


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.base_date = datetime(2026, 10, 18, 12, 0, tzinfo=EDT)
        self.slot_1pm_2pm = TimeSlot(
            start_time=datetime(2026, 10, 18, 13, 0, tzinfo=EDT),
            end_time=datetime(2026, 10, 18, 14, 0, tzinfo=EDT),
        )
        self.slot_2pm_3pm = TimeSlot(
            start_time=datetime(2026, 10, 18, 14, 0, tzinfo=EDT),
            end_time=datetime(2026, 10, 18, 15, 0, tzinfo=EDT),
        )
        self.slot_130_230 = TimeSlot(
            start_time=datetime(2026, 10, 18, 13, 30, tzinfo=EDT),
            end_time=datetime(2026, 10, 18, 14, 30, tzinfo=EDT),
        )

    def test_timeslot_validation(self):
        # Timezone naive rejected
        naive = datetime(2026, 10, 18, 10, 0)
        with self.assertRaises(AvailabilityValidationError):
            TimeSlot(naive, naive + timedelta(hours=1))

        # End before or equal to start rejected
        aware = datetime(2026, 10, 18, 10, 0, tzinfo=EDT)
        with self.assertRaises(AvailabilityValidationError):
            TimeSlot(aware, aware)
        with self.assertRaises(AvailabilityValidationError):
            TimeSlot(aware, aware - timedelta(hours=1))

        # Valid properties
        s = TimeSlot(aware, aware + timedelta(hours=2, minutes=15))
        self.assertEqual(s.duration_minutes, 135)
        self.assertEqual(s.duration, timedelta(hours=2, minutes=15))

    def test_timeslot_overlaps_and_contains(self):
        # 1-2 PM and 2-3 PM touch at endpoint but do NOT overlap
        self.assertFalse(self.slot_1pm_2pm.overlaps(self.slot_2pm_3pm))

        # 1-2 PM and 1:30-2:30 PM DO overlap
        self.assertTrue(self.slot_1pm_2pm.overlaps(self.slot_130_230))
        self.assertTrue(self.slot_2pm_3pm.overlaps(self.slot_130_230))

        # Contains
        encompassing = TimeSlot(
            datetime(2026, 10, 18, 12, 0, tzinfo=EDT),
            datetime(2026, 10, 18, 16, 0, tzinfo=EDT),
        )
        self.assertTrue(encompassing.contains(self.slot_1pm_2pm))
        self.assertFalse(self.slot_1pm_2pm.contains(encompassing))

    def test_parse_google_event_timed(self):
        event = {
            "id": "e1",
            "summary": "Team Sync",
            "start": {"dateTime": "2026-10-18T14:00:00-04:00"},
            "end": {"dateTime": "2026-10-18T15:00:00-04:00"},
        }
        slot = parse_google_event_timeslot(event, default_tz=EDT)
        self.assertIsNotNone(slot)
        self.assertEqual(slot.start_time, datetime(2026, 10, 18, 14, 0, tzinfo=EDT))
        self.assertEqual(slot.end_time, datetime(2026, 10, 18, 15, 0, tzinfo=EDT))

    def test_parse_google_event_cancelled_and_transparent(self):
        cancelled = {
            "status": "cancelled",
            "start": {"dateTime": "2026-10-18T14:00:00-04:00"},
            "end": {"dateTime": "2026-10-18T15:00:00-04:00"},
        }
        self.assertIsNone(parse_google_event_timeslot(cancelled, default_tz=EDT))

        transparent = {
            "transparency": "transparent",
            "start": {"dateTime": "2026-10-18T14:00:00-04:00"},
            "end": {"dateTime": "2026-10-18T15:00:00-04:00"},
        }
        self.assertIsNone(parse_google_event_timeslot(transparent, default_tz=EDT))

    def test_parse_google_event_all_day(self):
        event = {
            "id": "all-day",
            "summary": "Hackathon Day",
            "start": {"date": "2026-10-18"},
            "end": {"date": "2026-10-19"},
        }
        slot = parse_google_event_timeslot(event, default_tz=EDT)
        self.assertIsNotNone(slot)
        self.assertEqual(slot.start_time, datetime(2026, 10, 18, 0, 0, tzinfo=EDT))
        self.assertEqual(slot.end_time, datetime(2026, 10, 19, 0, 0, tzinfo=EDT))

    def test_merge_busy_slots(self):
        slots = [
            TimeSlot(datetime(2026, 10, 18, 10, 0, tzinfo=EDT), datetime(2026, 10, 18, 11, 0, tzinfo=EDT)),
            TimeSlot(datetime(2026, 10, 18, 10, 30, tzinfo=EDT), datetime(2026, 10, 18, 12, 0, tzinfo=EDT)),
            TimeSlot(datetime(2026, 10, 18, 14, 0, tzinfo=EDT), datetime(2026, 10, 18, 15, 0, tzinfo=EDT)),
            TimeSlot(datetime(2026, 10, 18, 15, 0, tzinfo=EDT), datetime(2026, 10, 18, 16, 0, tzinfo=EDT)),
        ]
        merged = merge_busy_slots(slots)
        self.assertEqual(len(merged), 2)
        # First merged: 10:00 - 12:00
        self.assertEqual(merged[0].start_time, datetime(2026, 10, 18, 10, 0, tzinfo=EDT))
        self.assertEqual(merged[0].end_time, datetime(2026, 10, 18, 12, 0, tzinfo=EDT))
        # Second merged (contiguous): 14:00 - 16:00
        self.assertEqual(merged[1].start_time, datetime(2026, 10, 18, 14, 0, tzinfo=EDT))
        self.assertEqual(merged[1].end_time, datetime(2026, 10, 18, 16, 0, tzinfo=EDT))

    def test_detect_conflicts(self):
        events = [
            {
                "id": "e1",
                "summary": "CS 1331 Lecture",
                "start": {"dateTime": "2026-10-18T10:00:00-04:00"},
                "end": {"dateTime": "2026-10-18T11:00:00-04:00"},
            },
            {
                "id": "e2",
                "summary": "Lunch with Friends",
                "transparency": "transparent",  # free time, should not conflict
                "start": {"dateTime": "2026-10-18T12:00:00-04:00"},
                "end": {"dateTime": "2026-10-18T13:00:00-04:00"},
            },
        ]

        # Target: 10:30 - 11:30 overlaps with e1
        target = TimeSlot(datetime(2026, 10, 18, 10, 30, tzinfo=EDT), datetime(2026, 10, 18, 11, 30, tzinfo=EDT))
        conflicts = detect_conflicts(target, events, default_tz=EDT)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].title, "CS 1331 Lecture")
        self.assertEqual(conflicts[0].event_id, "e1")

        # Target during transparent event: no conflict
        target_lunch = TimeSlot(datetime(2026, 10, 18, 12, 15, tzinfo=EDT), datetime(2026, 10, 18, 12, 45, tzinfo=EDT))
        self.assertEqual(len(detect_conflicts(target_lunch, events, default_tz=EDT)), 0)

    def test_find_free_gaps(self):
        window = TimeSlot(datetime(2026, 10, 18, 9, 0, tzinfo=EDT), datetime(2026, 10, 18, 17, 0, tzinfo=EDT))
        busy = [
            TimeSlot(datetime(2026, 10, 18, 10, 0, tzinfo=EDT), datetime(2026, 10, 18, 12, 0, tzinfo=EDT)),
            TimeSlot(datetime(2026, 10, 18, 14, 0, tzinfo=EDT), datetime(2026, 10, 18, 15, 30, tzinfo=EDT)),
        ]
        gaps = find_free_gaps(window, busy)
        self.assertEqual(len(gaps), 3)
        # Gap 1: 9:00 - 10:00
        self.assertEqual(gaps[0].start_time, datetime(2026, 10, 18, 9, 0, tzinfo=EDT))
        self.assertEqual(gaps[0].end_time, datetime(2026, 10, 18, 10, 0, tzinfo=EDT))
        # Gap 2: 12:00 - 14:00
        self.assertEqual(gaps[1].start_time, datetime(2026, 10, 18, 12, 0, tzinfo=EDT))
        self.assertEqual(gaps[1].end_time, datetime(2026, 10, 18, 14, 0, tzinfo=EDT))
        # Gap 3: 15:30 - 17:00
        self.assertEqual(gaps[2].start_time, datetime(2026, 10, 18, 15, 30, tzinfo=EDT))
        self.assertEqual(gaps[2].end_time, datetime(2026, 10, 18, 17, 0, tzinfo=EDT))

    def test_suggest_available_slots(self):
        window = TimeSlot(datetime(2026, 10, 18, 9, 0, tzinfo=EDT), datetime(2026, 10, 18, 13, 0, tzinfo=EDT))
        busy = [
            TimeSlot(datetime(2026, 10, 18, 10, 0, tzinfo=EDT), datetime(2026, 10, 18, 11, 0, tzinfo=EDT))
        ]
        # Request 1-hour slots on 30-min step
        suggestions = suggest_available_slots(
            duration=timedelta(hours=1),
            search_window=window,
            busy_slots=busy,
            step=timedelta(minutes=30),
            limit=4,
        )
        # In 9-10 (1 hr free): 9:00-10:00
        # In 11-13 (2 hr free): 11:00-12:00, 11:30-12:30, 12:00-13:00
        self.assertEqual(len(suggestions), 4)
        self.assertEqual(suggestions[0].start_time, datetime(2026, 10, 18, 9, 0, tzinfo=EDT))
        self.assertEqual(suggestions[1].start_time, datetime(2026, 10, 18, 11, 0, tzinfo=EDT))
        self.assertEqual(suggestions[2].start_time, datetime(2026, 10, 18, 11, 30, tzinfo=EDT))
        self.assertEqual(suggestions[3].start_time, datetime(2026, 10, 18, 12, 0, tzinfo=EDT))

    def test_google_availability_service_mocked(self):
        cal_mock = Mock()
        cal_mock.list_events.return_value = [
            {
                "id": "event-101",
                "summary": "Existing Meeting",
                "start": {"dateTime": "2026-10-18T10:00:00-04:00"},
                "end": {"dateTime": "2026-10-18T11:00:00-04:00"},
            }
        ]
        svc = GoogleAvailabilityService(cal_mock)

        target = TimeSlot(
            datetime(2026, 10, 18, 10, 30, tzinfo=EDT),
            datetime(2026, 10, 18, 11, 30, tzinfo=EDT),
        )
        report = svc.check_availability(target, suggest_alternatives=True, limit=2)

        self.assertFalse(report.is_available)
        self.assertEqual(len(report.conflicts), 1)
        self.assertEqual(report.conflicts[0].title, "Existing Meeting")
        self.assertTrue(len(report.suggested_slots) > 0)


if __name__ == "__main__":
    unittest.main()
