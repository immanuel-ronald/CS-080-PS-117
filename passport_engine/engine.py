"""Allocation engine: intake, booking windows, slot search, batch allocation, waitlist.  (Module 3)

Pipeline per application (BR-18):
    document validation -> category -> booking window -> quota -> time preference -> earliest slot
then the fee is computed from the final category/service on the appointment date.
"""
from collections import namedtuple
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from . import config as C
from .calendar_utils import add_working_days
from .documents import validate_documents
from .fees import compute_fee
from .models import Application, Booking
from .priority import RANK, POOL_LABEL, effective_category, pool_order, priority_key
from .slots import DayPlan

Candidate = namedtuple("Candidate", "day plan slot_idx pool category detail")


def booking_window(service: str, today: date) -> Tuple[date, date]:
    """BR-14 .. BR-16.  `today` is the date the booking is being made."""
    if service == "TATKAL":
        return add_working_days(today, 1), add_working_days(today, C.TATKAL_MAX_WORKING_DAYS)
    if service == "PCC":
        return add_working_days(today, 1), today + timedelta(days=C.PCC_MAX_DAYS)
    return (add_working_days(today, C.NORMAL_MIN_WORKING_DAYS),
            today + timedelta(days=C.NORMAL_MAX_DAYS))


class Engine:
    def __init__(self, calendar: Dict[Tuple[str, date], DayPlan]):
        self.cal = calendar
        self.centre_days: Dict[str, List[date]] = {}
        for (centre, day) in calendar:
            self.centre_days.setdefault(centre, []).append(day)
        for days in self.centre_days.values():
            days.sort()
        self.apps: Dict[str, Application] = {}
        self.log: List[str] = []           # event / waitlist log lines

    # ---- clock ------------------------------------------------------------------
    def advance_clock(self, now: datetime) -> List[str]:
        """BR-04: quota release happens at 17:00 two days before each day, whether or not
        anybody searched that day.  Called before every batch run and every event.

        Releases are applied in chronological order; after each release moment the waitlist is
        re-tried (BR-37) because released seats may now be available.  Returns log lines.
        """
        lines: List[str] = []
        due = sorted((p.release_time, key) for key, p in self.cal.items()
                     if not p.released and p.release_time <= now)
        i = 0
        while i < len(due):
            moment = due[i][0]
            while i < len(due) and due[i][0] == moment:
                plan = self.cal[due[i][1]]
                plan.release_if_due(moment)
                ra = plan.released_amount
                lines.append(f"[{moment:%Y-%m-%d %H:%M}] QUOTA-RELEASE {plan.centre_id} {plan.day} -> "
                             f"SM {ra['SM']} + PCC {ra['PCC']} moved to NORMAL | TATKAL untouched "
                             f"({plan.pools['TATKAL']['cap'] - plan.pools['TATKAL']['used']} free of "
                             f"{plan.pools['TATKAL']['cap']})")
                i += 1
            lines += self.drain_waitlist(moment)
        self.log += lines
        return lines

    # ---- intake -----------------------------------------------------------------
    def add_application(self, app: Application) -> None:
        if app.app_id in self.apps:
            raise ValueError(f"duplicate application id {app.app_id}")
        app.order = len(self.apps)
        app.queue_time = app.applied_at
        self.apps[app.app_id] = app
        v = validate_documents(app, app.applied_at.date())
        app.validation = v
        if app.dob > app.applied_at.date():                              # nobody is born in the future
            app.status = "REJECTED"
            app.reject_reason = "INVALID_DOB"
        elif app.centre_id not in self.centre_days:
            app.status = "REJECTED"
            app.reject_reason = "UNKNOWN_CENTRE"
        elif v.status == "DOC_BLOCK":
            app.status = "DOC_BLOCK"
        elif app.service == "TATKAL" and not app.aadhaar_verified:      # BR-07
            app.status = "REJECTED"
            app.reject_reason = "TATKAL_AADHAAR_NOT_VERIFIED"
        elif app.channel == "WALKIN":
            app.status = "WALKIN_PENDING"
        else:
            app.status = "PENDING"

    # ---- search -----------------------------------------------------------------
    def window_for(self, app: Application, now: datetime, anchor: Optional[date] = None) -> Tuple[date, date]:
        """BR-14..16 evaluated from the date the booking request was made: the application date
        for a first booking / waitlist retry, the event date for a reschedule or rebook.  A slot
        today or in the past can never be given (the engine decides at `now`)."""
        start, end = booking_window(app.service, anchor or app.applied_at.date())
        return max(start, now.date() + timedelta(days=1)), end

    def find_slot(self, app: Application, now: datetime, exclude: Optional[Tuple[str, date, int]] = None,
                  pref_date: Optional[date] = None, pref_time=None,
                  anchor: Optional[date] = None) -> Tuple[Optional[Candidate], str]:
        start, end = self.window_for(app, now, anchor)
        if pref_date and pref_date > start:
            start = pref_date
        pref_time = pref_time or app.pref_time
        tried = blocked = 0
        for day in self.centre_days.get(app.centre_id, []):
            if day < start or day > end:
                continue
            tried += 1
            if validate_documents(app, day).status != "VALID":          # BR-10 on the candidate date
                blocked += 1
                continue
            plan = self.cal[(app.centre_id, day)]
            category, detail = effective_category(app, day)
            for pool in pool_order(app, category, plan.released):
                ex = exclude[2] if exclude and exclude[0] == app.centre_id and exclude[1] == day else None
                idx = plan.find_slot(pool, pref_time, ex, allow_overbook=(pool == "NORMAL" and app.service == "NORMAL"))
                if idx is not None:
                    return Candidate(day, plan, idx, pool, category, detail), ""
        if tried == 0:
            return None, "NO_PUBLISHED_SLOTS_IN_WINDOW"
        if blocked == tried:
            return None, "DOC_EXPIRES_BEFORE_SLOT"
        return None, "NO_CAPACITY_IN_WINDOW"

    # ---- commit -----------------------------------------------------------------
    def commit(self, app: Application, cand: Candidate, extra_reason: str = "") -> Booking:
        counter = cand.plan.assign(app.app_id, cand.slot_idx, cand.pool)
        reason = (f"P{RANK[cand.category]} {cand.category} ({cand.detail}); "
                  f"queue_time={app.queue_time:%Y-%m-%d %H:%M}")
        if extra_reason:
            reason += "; " + extra_reason
        app.booking = Booking(app.centre_id, cand.day, cand.slot_idx, cand.plan.slots[cand.slot_idx].start,
                              counter, "SCHEDULED", cand.category, reason)
        app.status = "BOOKED"
        app.validation = validate_documents(app, cand.day)             # final mode on the appointment date
        if app.fee is None:                                            # fee is paid once (BR-18)
            app.fee = compute_fee(app, cand.day)
        return app.booking

    def release_booking(self, app: Application) -> Booking:
        b = app.booking
        self.cal[(b.centre_id, b.day)].release(app.app_id, b.slot_idx, b.pool)
        app.booking = None
        return b

    def restore_booking(self, app: Application, b: Booking) -> None:
        self.cal[(b.centre_id, b.day)].restore(app.app_id, b.slot_idx, b.pool)
        app.booking = b
        app.status = "BOOKED"

    # ---- batch allocation -----------------------------------------------------------
    def _rank_key(self, app: Application, now: datetime):
        start, _ = self.window_for(app, now)
        return priority_key(app, start)

    def allocate_batch(self, now: datetime) -> List[Application]:
        self.advance_clock(now)
        pending = [a for a in self.apps.values() if a.status == "PENDING"]
        pending.sort(key=lambda a: self._rank_key(a, now))
        for pos, app in enumerate(pending, start=1):
            cand, why = self.find_slot(app, now)
            if cand:
                self.commit(app, cand, f"batch_position={pos}/{len(pending)}")
            elif why == "DOC_EXPIRES_BEFORE_SLOT":
                app.status = "DOC_BLOCK"
                app.note = why
                start, _ = self.window_for(app, now)
                app.validation = validate_documents(app, start)
            else:
                app.status = "WAITLISTED"
                app.note = why
        return pending

    # ---- waitlist (BR-37) -------------------------------------------------------------
    def drain_waitlist(self, now: datetime, ahead_of=None) -> List[str]:
        """Promote waitlisted applications in priority order.  `ahead_of` limits the drain to
        applications whose priority key sorts before it (used for a third reschedule)."""
        lines = []
        waiting = [a for a in self.apps.values() if a.status == "WAITLISTED"]
        waiting.sort(key=lambda a: self._rank_key(a, now))
        for app in waiting:
            if ahead_of is not None and not self._rank_key(app, now) < ahead_of:
                break
            cand, _ = self.find_slot(app, now)
            if cand:
                b = self.commit(app, cand, "promoted from waitlist")
                lines.append(f"[{now:%Y-%m-%d %H:%M}] WAITLIST-PROMOTE {app.app_id} -> OK | "
                             f"{b.centre_id} {b.day} {b.start:%H:%M} | {b.category}")
        return lines
