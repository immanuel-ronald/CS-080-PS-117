"""Regression tests for defects found in the independent review (walk-in slot, centre id case,
PCC pool fallback before release, leap-day convention)."""
from datetime import date, datetime, timedelta

from passport_engine.calendar_utils import add_years, age_on
from passport_engine.events import process_event
from passport_engine.models import Document, Event
from passport_engine.priority import effective_category, pool_order
from passport_engine.slots import DayPlan

from .helpers import TODAY, make_app, make_engine

DAY = date(2026, 11, 10)


def _two_noshows():
    """Two scheduled applicants (09:00 and 09:15 slots, capacity 1) who both no-show."""
    e = make_engine(slot_cap=1, days=[DAY])
    ids = []
    for i in range(2):
        a = make_app(f"N{i}", applied=f"2026-11-02 10:0{i}")
        e.add_application(a)
        ids.append(a)
    e.allocate_batch(TODAY)
    for a in ids:
        process_event(e, Event(a.booking.start_dt + timedelta(minutes=5), "NOSHOW", a.app_id, order=1))
    return e


class TestWalkInSlotChoice:
    def test_late_walkin_gets_most_recent_vacated_slot_not_the_first_of_the_day(self):
        e = _two_noshows()
        w = make_app("W", dob="1950-01-01", channel="WALKIN")
        e.add_application(w)
        out = process_event(e, Event(datetime(2026, 11, 10, 15, 50), "WALKIN", "W", "C01", "2026-11-10", order=1))
        assert "-> OK" in out[0] and w.booking.start.strftime("%H:%M") == "09:15"

    def test_walkin_during_the_day_takes_the_current_vacated_slot(self):
        e = _two_noshows()
        w = make_app("W", dob="1950-01-01", channel="WALKIN")
        e.add_application(w)
        process_event(e, Event(datetime(2026, 11, 10, 9, 8), "WALKIN", "W", "C01", "2026-11-10", order=1))
        assert w.booking.start.strftime("%H:%M") == "09:00"          # slot 09:00-09:15 still running

    def test_walkin_centre_id_is_case_insensitive(self):
        e = _two_noshows()
        w = make_app("W", dob="1950-01-01", channel="WALKIN")
        e.add_application(w)
        out = process_event(e, Event(datetime(2026, 11, 10, 16, 30), "WALKIN", "W", " c01 ", "2026-11-10", order=1))
        assert "-> OK" in out[0]


class TestPccFallback:
    def test_pcc_never_uses_normal_seats_before_the_release(self):
        assert pool_order(make_app(service="PCC"), "NORMAL", released=False) == ["PCC"]
        assert pool_order(make_app(service="PCC"), "NORMAL", released=True) == ["PCC", "NORMAL"]

    def test_pcc_overflow_goes_to_next_day_instead_of_eating_normal_seats(self):
        e = make_engine(slot_cap=1, days=[date(2026, 11, 9), DAY])   # PCC quota 2 per day, capacity 28
        apps = []
        for i in range(3):
            a = make_app(f"P{i}", service="PCC", applied=f"2026-11-06 10:0{i}",
                         docs=[Document("PASSPORT", "V"), Document("AADHAAR", "V")])
            e.add_application(a)
            apps.append(a)
        e.allocate_batch(TODAY)
        days = [a.booking.day for a in apps]
        assert days == [date(2026, 11, 9), date(2026, 11, 9), DAY]    # 3rd PCC waits for the next day's PCC quota
        assert all(a.booking.pool == "PCC" for a in apps)


class TestLeapDay:
    def test_feb_29_birthday_and_expiry_use_the_same_convention(self):
        assert age_on(date(2000, 2, 29), date(2026, 2, 28)) == 25
        assert age_on(date(2000, 2, 29), date(2026, 3, 1)) == 26
        assert add_years(date(2024, 2, 29), 3) == date(2027, 3, 1)
        assert add_years(date(2026, 5, 4), 3) == date(2029, 5, 4)
