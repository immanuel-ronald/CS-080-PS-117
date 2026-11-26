"""Category, priority and pool selection.  (Module 3)  Implements BR-05 .. BR-08, BR-19."""
from datetime import date
from typing import List, Tuple

from .calendar_utils import age_on
from .models import Application

RANK = {"TATKAL": 1, "SENIOR_CITIZEN": 2, "MINOR": 3, "DIFFERENTLY_ABLED": 4, "NORMAL": 5}
POOL_LABEL = {"TATKAL": "TATKAL", "SM": "SENIOR_MINOR", "PCC": "PCC", "NORMAL": "NORMAL", "OB": "NORMAL(OVERBOOK)", "WALKIN": "WALKIN"}


def effective_category(app: Application, on_date: date) -> Tuple[str, str]:
    """Return (category, human reason) evaluated on a given appointment date (BR-08)."""
    age = age_on(app.dob, on_date)
    if app.service == "TATKAL":
        return "TATKAL", "TATKAL service with VERIFIED Aadhaar"
    if age >= 60:
        return "SENIOR_CITIZEN", f"age {age} on {on_date}"
    if age < 18:
        return "MINOR", f"age {age} on {on_date}"
    if app.differently_abled:
        return "DIFFERENTLY_ABLED", "differently-abled flag"
    return "NORMAL", f"age {age} on {on_date}"


def priority_key(app: Application, on_date: date):
    cat, _ = effective_category(app, on_date)
    return (RANK[cat], app.queue_time, app.app_id)


def pool_order(app: Application, category: str, released: bool = True) -> List[str]:
    """BR-19: own quota first, then the NORMAL pool.  A PCC applicant may use the NORMAL pool only
    once the 17:00 release has happened for that day (then it is "the released NORMAL pool");
    before that PCC never eats into ordinary NORMAL seats.  TATKAL never falls back."""
    if app.service == "TATKAL":
        return ["TATKAL"]
    if app.service == "PCC":
        return ["PCC", "NORMAL"] if released else ["PCC"]
    if category in ("SENIOR_CITIZEN", "MINOR"):
        return ["SM", "NORMAL"]
    return ["NORMAL"]
