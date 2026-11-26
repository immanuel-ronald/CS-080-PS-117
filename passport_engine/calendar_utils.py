"""Date helpers: parsing, working-day arithmetic, age calculation.  (Module 3)"""
from datetime import date, datetime, time, timedelta

HOLIDAYS: set = set()          # optionally filled by the caller with datetime.date values


def parse_date(text: str) -> date:
    return datetime.strptime(text.strip(), "%Y-%m-%d").date()


def parse_datetime(text: str) -> datetime:
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"bad datetime '{text}' (expected YYYY-MM-DD HH:MM)")


def parse_time(text: str) -> time:
    return datetime.strptime(text.strip(), "%H:%M").time()


def age_on(dob: date, on: date) -> int:
    """Completed years on the given date; the birthday itself counts (turning 60 today => 60)."""
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def add_working_days(d: date, n: int) -> date:
    """The n-th working day strictly after d."""
    cur = d
    while n > 0:
        cur += timedelta(days=1)
        if is_working_day(cur):
            n -= 1
    return cur


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:               # 29 February -> 1 March, same convention as age_on()
        return date(d.year + years, 3, 1)
