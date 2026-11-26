"""Booking windows (BR-14..16), priority (BR-05, BR-06, BR-07), pool order (BR-19), BR-17, BR-20."""
from datetime import date, datetime, time, timedelta

import pytest

from passport_engine import calendar_utils
from passport_engine.engine import Engine, booking_window
from passport_engine.events import process_event
from passport_engine.models import Document, Event
from passport_engine.priority import RANK, effective_category, pool_order, priority_key
from passport_engine.slots import DayPlan

from .helpers import TODAY, good_docs, make_app, make_engine

FRI, SAT, SUN, MON = date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 9)
TUE, WED, THU = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)


def one_day_engine(day, slot_cap=10):
    return Engine({("C01", day): DayPlan("C01", day, slot_cap)})


class TestNormalAndReissueWindow:
    """BR-14: earliest = 2 working days after booking date, latest = +45 calendar days."""

    @pytest.mark.parametrize("service", ["NORMAL", "RE-ISSUE"])
    def test_friday_anchor(self, service):
        assert booking_window(service, FRI) == (TUE, FRI + timedelta(days=45))

    @pytest.mark.parametrize("today", [SAT, SUN])
    def test_weekend_anchor_same_as_friday(self, today):
        assert booking_window("NORMAL", today)[0] == TUE

    def test_thursday_anchor_skips_weekend(self):
        assert booking_window("NORMAL", date(2026, 11, 5))[0] == MON

    def test_monday_anchor(self):
        assert booking_window("NORMAL", MON)[0] == WED

    def test_holiday_pushes_earliest_day(self):
        calendar_utils.HOLIDAYS.add(MON)
        assert booking_window("NORMAL", FRI)[0] == WED

    def test_latest_day_is_45_calendar_days(self):
        assert booking_window("NORMAL", MON)[1] == date(2026, 12, 24)

    def test_engine_gives_tuesday_not_monday_to_friday_applicant(self):
        e = make_engine()
        a = make_app()
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.booking.day == TUE

    def test_engine_waitlists_when_only_day_is_past_the_45_day_limit(self):
        e = one_day_engine(date(2026, 12, 22))
        a = make_app()
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.status == "WAITLISTED" and a.note == "NO_PUBLISHED_SLOTS_IN_WINDOW"

    def test_engine_books_on_the_45th_day(self):
        e = one_day_engine(date(2026, 12, 21))
        a = make_app()
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.status == "BOOKED"


class TestTatkalWindow:
    """BR-15: next working day up to the 3rd working day after the booking date."""

    def test_friday_anchor(self):
        assert booking_window("TATKAL", FRI) == (MON, WED)

    def test_weekend_anchor(self):
        assert booking_window("TATKAL", SUN) == (MON, WED)

    def test_thursday_anchor(self):
        assert booking_window("TATKAL", THU) == (date(2026, 11, 13), date(2026, 11, 17))   # Fri, Mon, Tue

    def test_holiday_shifts_both_ends(self):
        calendar_utils.HOLIDAYS.add(MON)
        assert booking_window("TATKAL", FRI) == (TUE, THU)

    def test_engine_books_tatkal_next_working_day(self):
        e = make_engine()
        a = make_app(service="TATKAL")
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.booking.day == MON

    def test_engine_waitlists_tatkal_beyond_third_working_day(self):
        e = one_day_engine(THU)
        a = make_app(service="TATKAL")
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.status == "WAITLISTED"


class TestPccWindow:
    """BR-16: next working day up to 30 calendar days after the booking date."""

    def test_friday_anchor(self):
        assert booking_window("PCC", FRI) == (MON, date(2026, 12, 6))

    def test_holiday_pushes_start_only(self):
        calendar_utils.HOLIDAYS.add(MON)
        assert booking_window("PCC", FRI) == (TUE, date(2026, 12, 6))

    def test_engine_pcc_books_on_day_30_not_31(self):
        pcc_docs = [Document("PASSPORT", "V"), Document("AADHAAR", "V")]
        for day, ok in ((date(2026, 12, 9), True), (date(2026, 12, 10), False)):
            e = one_day_engine(day)
            a = make_app(service="PCC", applied="2026-11-09 10:00", docs=list(pcc_docs))
            e.add_application(a)
            e.allocate_batch(datetime(2026, 11, 9, 12, 0))
            assert (a.status == "BOOKED") is ok


class TestCategoryRanking:
    """BR-05: TATKAL > SENIOR > MINOR > DIFFERENTLY_ABLED > NORMAL (age on the appointment date)."""

    def cat(self, **kw):
        on = kw.pop("on", TUE)
        return effective_category(make_app(**kw), on)[0]

    def test_rank_table(self):
        order = sorted(RANK, key=RANK.get)
        assert order == ["TATKAL", "SENIOR_CITIZEN", "MINOR", "DIFFERENTLY_ABLED", "NORMAL"]

    def test_tatkal_service(self):
        assert self.cat(service="TATKAL") == "TATKAL"

    def test_tatkal_beats_senior_and_minor(self):
        assert self.cat(service="TATKAL", dob="1950-01-01") == "TATKAL"
        assert self.cat(service="TATKAL", dob="2015-01-01") == "TATKAL"

    def test_senior_at_60_exactly(self):
        assert self.cat(dob="1966-11-10") == "SENIOR_CITIZEN"

    def test_59_is_not_senior(self):
        assert self.cat(dob="1966-11-11") == "NORMAL"

    def test_senior_beats_differently_abled(self):
        assert self.cat(dob="1950-01-01", differently_abled=True) == "SENIOR_CITIZEN"

    def test_minor_at_17_and_not_at_18(self):
        assert self.cat(dob="2009-11-11") == "MINOR"
        assert self.cat(dob="2008-11-10") == "NORMAL"

    def test_minor_beats_differently_abled(self):
        assert self.cat(dob="2015-01-01", differently_abled=True) == "MINOR"

    def test_differently_abled_adult(self):
        assert self.cat(differently_abled=True) == "DIFFERENTLY_ABLED"

    def test_category_follows_the_date_argument(self):
        app = make_app(dob="1966-11-10")
        assert effective_category(app, MON)[0] == "NORMAL" and effective_category(app, TUE)[0] == "SENIOR_CITIZEN"

    def test_batch_order_follows_the_priority_ladder(self):
        e = make_engine()
        specs = [("NRM", {}), ("DA", {"differently_abled": True}), ("MIN", {"dob": "2015-01-01",
                 "docs": good_docs() + [Document("ANNEXURE_D", "V")]}), ("SEN", {"dob": "1950-01-01"}),
                 ("TAT", {"service": "TATKAL"})]
        for i, (aid, kw) in enumerate(specs):                      # best category applied LAST
            e.add_application(make_app(aid, applied=f"2026-11-0{i + 1} 10:00", **kw))
        order = [a.app_id for a in e.allocate_batch(TODAY)]
        assert order == ["TAT", "SEN", "MIN", "DA", "NRM"]


class TestQueueTieBreak:
    """BR-06: within a category earlier queue time first, ties by application id."""

    def keys(self, *apps):
        return [a.app_id for a in sorted(apps, key=lambda a: priority_key(a, TUE))]

    def test_earlier_queue_time_first(self):
        late, early = make_app("A1", applied="2026-11-05 10:00"), make_app("A2", applied="2026-11-04 10:00")
        for a in (late, early):
            a.queue_time = a.applied_at                            # add_application() does this at intake
        assert self.keys(late, early) == ["A2", "A1"]

    def test_same_minute_ties_by_id(self):
        b, a = make_app("B", applied="2026-11-05 10:00"), make_app("A", applied="2026-11-05 10:00")
        for x in (a, b):
            x.queue_time = x.applied_at
        assert self.keys(b, a) == ["A", "B"]

    def test_queue_time_not_application_time_is_used(self):
        a, b = make_app("A", applied="2026-11-01 10:00"), make_app("B", applied="2026-11-02 10:00")
        a.queue_time, b.queue_time = datetime(2026, 11, 5, 9, 0), datetime(2026, 11, 2, 10, 0)
        assert self.keys(a, b) == ["B", "A"]

    def test_category_beats_queue_time(self):
        senior = make_app("S", dob="1950-01-01", applied="2026-11-06 10:00")
        normal = make_app("N", applied="2026-11-01 10:00")
        for a in (senior, normal):
            a.queue_time = a.applied_at
        assert self.keys(normal, senior) == ["S", "N"]

    def test_engine_gives_scarce_seat_to_earlier_applicant(self):
        e = one_day_engine(TUE, slot_cap=1)                        # NORMAL quota 17 only
        for i in range(18):
            e.add_application(make_app(f"N{i:02d}", applied=f"2026-11-0{1 + i // 10} 1{i % 10}:00"))
        e.allocate_batch(TODAY)
        assert e.apps["N17"].status == "WAITLISTED" and e.apps["N00"].status == "BOOKED"


class TestTatkalAadhaar:
    """BR-07: TATKAL needs VERIFIED Aadhaar, otherwise REJECTED (never downgraded)."""

    def test_unverified_is_rejected(self):
        e = make_engine()
        a = make_app(service="TATKAL", aadhaar_verified=False)
        e.add_application(a)
        assert a.status == "REJECTED" and a.reject_reason == "TATKAL_AADHAAR_NOT_VERIFIED"

    def test_not_downgraded_to_normal_by_batch(self):
        e = make_engine()
        a = make_app(service="TATKAL", aadhaar_verified=False)
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.status == "REJECTED" and a.booking is None and a.fee is None

    def test_verified_is_accepted(self):
        e = make_engine()
        a = make_app(service="TATKAL")
        e.add_application(a)
        assert a.status == "PENDING"

    def test_unverified_aadhaar_irrelevant_for_normal(self):
        e = make_engine()
        a = make_app(aadhaar_verified=False)
        e.add_application(a)
        assert a.status == "PENDING"


class TestPoolOrder:
    """BR-19: own quota first then NORMAL; TATKAL applicants use only the TATKAL pool."""

    def order(self, category, **kw):
        return pool_order(make_app(**kw), category)

    def test_tatkal_only_tatkal(self):
        assert self.order("TATKAL", service="TATKAL") == ["TATKAL"]

    def test_pcc_then_normal(self):
        assert self.order("NORMAL", service="PCC") == ["PCC", "NORMAL"]

    @pytest.mark.parametrize("cat", ["SENIOR_CITIZEN", "MINOR"])
    def test_senior_and_minor_use_sm_then_normal(self, cat):
        assert self.order(cat) == ["SM", "NORMAL"]

    def test_reissue_senior_uses_sm_then_normal(self):
        assert self.order("SENIOR_CITIZEN", service="RE-ISSUE") == ["SM", "NORMAL"]

    @pytest.mark.parametrize("cat", ["DIFFERENTLY_ABLED", "NORMAL"])
    def test_da_and_normal_use_normal(self, cat):
        assert self.order(cat) == ["NORMAL"]

    def test_senior_overflows_to_normal_when_sm_full(self):
        e = one_day_engine(TUE, slot_cap=1)                        # SM quota 4
        for i in range(5):
            e.add_application(make_app(f"S{i}", dob="1950-01-01", applied=f"2026-11-02 10:0{i}"))
        e.allocate_batch(TODAY)
        assert [e.apps[f"S{i}"].booking.pool for i in range(5)] == ["SM"] * 4 + ["NORMAL"]


class TestOneActiveAppointment:
    """BR-17: an application holds at most one active appointment."""

    def test_duplicate_application_id_refused(self):
        e = make_engine()
        e.add_application(make_app("A1"))
        with pytest.raises(ValueError):
            e.add_application(make_app("A1"))

    def test_second_batch_does_not_rebook(self):
        e = make_engine()
        a = make_app()
        e.add_application(a)
        e.allocate_batch(TODAY)
        first = a.booking
        e.allocate_batch(TODAY + timedelta(hours=1))
        assert a.booking is first and sum(a.app_id in s.booked for p in e.cal.values() for s in p.slots) == 1

    def test_reschedule_leaves_exactly_one_seat(self):
        e = make_engine()
        a = make_app(applied="2026-11-01 10:00")
        e.add_application(a)
        e.allocate_batch(TODAY)
        process_event(e, Event(datetime(2026, 11, 6, 19, 0), "RESCHEDULE", "A1", "2026-11-20", order=1))
        seats = [(k, s.idx) for k, p in e.cal.items() for s in p.slots if "A1" in s.booked]
        assert len(seats) == 1 and seats[0][0] == ("C01", date(2026, 11, 20))

    def test_rebook_refused_while_booked(self):
        e = make_engine()
        a = make_app()
        e.add_application(a)
        e.allocate_batch(TODAY)
        out = process_event(e, Event(datetime(2026, 11, 7, 9, 0), "REBOOK", "A1", order=1))
        assert "REBOOK_NOT_ALLOWED" in out[0]

    def test_walkin_refused_while_booked(self):
        e = make_engine()
        a = make_app(dob="1950-01-01")
        e.add_application(a)
        e.allocate_batch(TODAY)
        out = process_event(e, Event(TUE.__class__(2026, 11, 10).isoformat() and datetime(2026, 11, 10, 10, 0),
                                     "WALKIN", "A1", "C01", "2026-11-10", order=1))
        assert "ACTIVE_APPOINTMENT_EXISTS" in out[0]


class TestTimePreference:
    """BR-20: earliest slot at/after the preferred time else earliest; earlier dates beat better times."""

    def plan(self):
        return DayPlan("C01", TUE, 10)

    def test_no_preference_gives_first_slot(self):
        assert self.plan().find_slot("NORMAL", None) == 0

    def test_exact_grid_time(self):
        assert self.plan().slots[self.plan().find_slot("NORMAL", time(11, 30))].start == time(11, 30)

    def test_off_grid_time_rounds_up_to_next_slot(self):
        p = self.plan()
        assert p.slots[p.find_slot("NORMAL", time(11, 20))].start == time(11, 30)

    def test_preference_at_last_slot(self):
        assert self.plan().find_slot("NORMAL", time(15, 45)) == 27

    def test_preference_after_close_falls_back_to_earliest(self):
        assert self.plan().find_slot("NORMAL", time(16, 30)) == 0

    def test_full_preferred_slot_takes_next_one_after(self):
        p = self.plan()
        for i in range(10):
            p.assign(f"X{i}", 10, "NORMAL")                         # 11:30 slot at capacity
        assert p.slots[p.find_slot("NORMAL", time(11, 30), allow_overbook=False)].start == time(11, 45)

    def test_nothing_after_preference_takes_earliest_on_same_day(self):
        p = self.plan()
        for i in range(10):
            p.assign(f"X{i}", 27, "NORMAL")
        assert p.find_slot("NORMAL", time(15, 45), allow_overbook=False) == 0

    def test_engine_honours_preference(self):
        e = make_engine()
        a = make_app(pref_time=time(11, 30))
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert (a.booking.day, a.booking.start) == (TUE, time(11, 30))

    def test_earlier_date_wins_over_better_time(self):
        e = make_engine(slot_cap=1)
        plan = e.cal[("C01", TUE)]
        for i in range(17):                                         # NORMAL pool of Tuesday full
            plan.assign(f"X{i}", i, "NORMAL")
        a = make_app(pref_time=time(9, 0))
        e.add_application(a)
        e.allocate_batch(TODAY)
        assert a.booking.day == WED and a.booking.start == time(9, 0)
