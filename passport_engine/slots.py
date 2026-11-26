"""Slot grid, quota pools, release and overbooking.  (Module 3)  BR-01..BR-04, BR-31..BR-36."""
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from . import config as C


def slot_starts() -> List[time]:
    out, cur = [], datetime.combine(date(2000, 1, 1), C.DAY_START)
    for _ in range(C.NUM_SLOTS):
        out.append(cur.time())
        cur += timedelta(minutes=C.SLOT_MINUTES)
    return out


def day_capacity(slot_cap: int) -> int:
    return C.NUM_SLOTS * slot_cap


def quota_split(day_cap: int) -> Dict[str, int]:
    """BR-03: floor() on the reserved quotas, NORMAL takes the remainder."""
    tatkal = day_cap * C.QUOTA_PCT["TATKAL"] // 100
    sm = day_cap * C.QUOTA_PCT["SM"] // 100
    pcc = day_cap * C.QUOTA_PCT["PCC"] // 100
    return {"TATKAL": tatkal, "SM": sm, "PCC": pcc, "NORMAL": day_cap - tatkal - sm - pcc}


def overbook_per_slot(slot_cap: int) -> int:
    """BR-35: floor(10%), min 0.  Capacity 7 -> 0, capacity 10 -> 1."""
    return max(0, slot_cap * C.OVERBOOK_PCT // 100)


def walkin_cap(day_cap: int) -> int:
    """BR-32: floor(10% of the day's capacity).  Capacity 35 -> 3."""
    return day_cap * C.WALKIN_PCT // 100


class Slot:
    def __init__(self, idx: int, start: time, cap: int):
        self.idx = idx
        self.start = start
        self.cap = cap
        self.booked: List[str] = []      # active scheduled bookings (app ids)
        self.noshows: List[str] = []
        self.walkins: List[str] = []


def spread_capacity(day_cap: int) -> List[int]:
    """Spread a day total over the 28 slots as evenly as possible (earlier slots get the remainder)."""
    base, extra = divmod(day_cap, C.NUM_SLOTS)
    return [base + (1 if i < extra else 0) for i in range(C.NUM_SLOTS)]


class DayPlan:
    """One centre on one day: 28 slots plus the four quota pools.

    Capacity is given either as `slot_cap` (uniform, = number of counters) or as `day_cap`
    (a day total, e.g. 35, spread over the 28 slots).  Overbooking is computed per slot.
    """

    def __init__(self, centre_id: str, day: date, slot_cap: int = 0, day_cap: Optional[int] = None):
        self.centre_id = centre_id
        self.day = day
        caps = spread_capacity(day_cap) if day_cap is not None else [slot_cap] * C.NUM_SLOTS
        self.slot_cap = max(caps)                       # nominal / largest slot capacity (for display)
        self.uniform = len(set(caps)) == 1
        self.day_cap = sum(caps)
        self.ob = overbook_per_slot(self.slot_cap)
        self.ob_total = sum(overbook_per_slot(c) for c in caps)
        self.slots = [Slot(i, t, c) for i, (t, c) in enumerate(zip(slot_starts(), caps))]
        q = quota_split(self.day_cap)
        self.initial_quota = dict(q)
        self.pools = {
            "TATKAL": {"cap": q["TATKAL"], "used": 0},
            "SM": {"cap": q["SM"], "used": 0},
            "PCC": {"cap": q["PCC"], "used": 0},
            # overbooked seats are NORMAL-only, so they are part of the NORMAL pool
            # "used" counts every NORMAL-pool booking, real seats and overbooked seats alike
            "NORMAL": {"cap": q["NORMAL"], "used": 0},
        }
        self.released = False
        self.released_amount = {"SM": 0, "PCC": 0}
        self.walkin_count = 0

    # ---- release (BR-04) -----------------------------------------------------
    @property
    def release_time(self) -> datetime:
        return datetime.combine(self.day - timedelta(days=C.RELEASE_DAYS_BEFORE), C.RELEASE_TIME)

    def release_if_due(self, now: datetime) -> bool:
        if self.released or now < self.release_time:
            return False
        for name in ("SM", "PCC"):                       # TATKAL deliberately untouched
            pool = self.pools[name]
            unused = max(0, pool["cap"] - pool["used"])
            self.released_amount[name] = unused
            pool["cap"] -= unused
            self.pools["NORMAL"]["cap"] += unused
        self.released = True
        return True

    # ---- seat search ---------------------------------------------------------
    def ob_used(self) -> int:
        """Overbooked seats in use = bookings beyond capacity, summed over slots.  Derived from the
        slots themselves so it can never drift after cancels / reschedules / no-shows (BR-35)."""
        return sum(max(0, len(s.booked) - s.cap) for s in self.slots)

    def pool_free(self, pool: str) -> int:
        if pool == "OB":                               # free overbook seats (BR-35)
            return self.ob_total - self.ob_used()
        used = self.pools[pool]["used"]
        if pool == "NORMAL":                           # real NORMAL seats exclude the overbooked ones
            used -= self.ob_used()
        return self.pools[pool]["cap"] - used

    def slot_limit(self, pool: str) -> int:
        return self.slot_cap + (self.ob if pool == "NORMAL" else 0)

    def find_slot(self, pool: str, pref_time: Optional[time] = None,
                  exclude_idx: Optional[int] = None, allow_overbook: Optional[bool] = None) -> Optional[int]:
        """BR-20: earliest slot at/after the preferred time, else earliest slot.

        A NORMAL-pool booking may use a real seat (slot not yet at capacity, NORMAL quota left)
        or, when `allow_overbook`, an overbooked seat (slot at capacity but below
        capacity + floor(10%), overbook counter not exhausted).  `allow_overbook` defaults to
        "pool is NORMAL"; the engine passes True only for NORMAL-service applicants (BR-35).
        """
        if allow_overbook is None:
            allow_overbook = pool == "NORMAL"
        real_ok = self.pool_free(pool) > 0
        ob_ok = pool == "NORMAL" and allow_overbook and self.pool_free("OB") > 0
        if not real_ok and not ob_ok:
            return None
        real, over = [], []
        for s in self.slots:
            n = len(s.booked)
            if s.idx == exclude_idx:
                continue
            if real_ok and n < s.cap:
                real.append(s.idx)
            elif ob_ok and s.cap <= n < s.cap + overbook_per_slot(s.cap):
                over.append(s.idx)
        options = real or over          # BR-35: overbooked seats are a last resort, real seats first
        if not options:
            return None
        if pref_time is None:
            return options[0]
        after = [i for i in options if self.slots[i].start >= pref_time]
        return after[0] if after else options[0]

    def assign(self, app_id: str, slot_idx: int, pool: str) -> str:
        """Book a seat; returns the label stored on the booking ('OB' = booked into an overbooked
        seat; for display only, the NORMAL-pool counter is charged either way)."""
        slot = self.slots[slot_idx]
        label = "OB" if pool == "NORMAL" and len(slot.booked) >= slot.cap else pool
        slot.booked.append(app_id)
        self.pools[pool]["used"] += 1
        return label

    def release(self, app_id: str, slot_idx: int, counter: str) -> None:
        """Give a seat back.  After the 17:00 release moment a freed SM/PCC seat joins NORMAL (BR-04)."""
        self.slots[slot_idx].booked.remove(app_id)
        counter = "NORMAL" if counter == "OB" else counter
        pool = self.pools[counter]
        pool["used"] -= 1
        if self.released and counter in ("SM", "PCC"):
            pool["cap"] -= 1
            self.pools["NORMAL"]["cap"] += 1
            self.released_amount[counter] += 1

    def restore(self, app_id: str, slot_idx: int, counter: str) -> None:
        """Exact inverse of release(); used when a reschedule fails and the old seat is kept."""
        self.slots[slot_idx].booked.append(app_id)
        counter = "NORMAL" if counter == "OB" else counter
        pool = self.pools[counter]
        pool["used"] += 1
        if self.released and counter in ("SM", "PCC"):
            pool["cap"] += 1
            self.pools["NORMAL"]["cap"] -= 1
            self.released_amount[counter] -= 1

    def vacate_noshow(self, app_id: str, slot_idx: int, counter: str) -> None:
        """A no-show leaves the slot's arrival list; the (past) seat is not re-sold or released."""
        self.slots[slot_idx].booked.remove(app_id)
        self.pools["NORMAL" if counter == "OB" else counter]["used"] -= 1

    # ---- walk-ins (BR-31, BR-32) ----------------------------------------------
    def walkin_slot(self, now: Optional[datetime] = None) -> Optional[int]:
        """A slot with a vacancy created by a no-show.  Prefer the earliest vacated slot that is
        still running or ahead of `now`; if every vacated slot is already over (a late-day or
        after-close walk-in) use the MOST RECENT vacated slot, never the first slot of the day."""
        vacant = [s for s in self.slots
                  if min(len(s.noshows) - len(s.walkins), s.cap - len(s.booked) - len(s.walkins)) > 0]
        if not vacant:
            return None
        if now is not None:
            live = [s for s in vacant
                    if datetime.combine(self.day, s.start) + timedelta(minutes=C.SLOT_MINUTES) > now]
            if live:
                return live[0].idx
            return vacant[-1].idx
        return vacant[0].idx
