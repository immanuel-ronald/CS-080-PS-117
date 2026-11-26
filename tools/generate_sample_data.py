"""Generate reproducible sample data (the official Week-2 files are not out yet).

    python tools/generate_sample_data.py            # writes data/*.csv

* 3 centres x 10 working days (2026-11-09 .. 2026-11-20)
* 120 applications (+ documents.csv), batch allocation time 2026-11-06 18:00
* 80 events (reschedule / cancel / no-show / rebook / walk-in)
* a handful of hand-planted applications (IDs APP101..APP120) reproduce the
  edge cases listed in the brief.
"""
import csv
import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from passport_engine.cli import run_pipeline          # noqa: E402

AS_OF = datetime(2026, 11, 6, 18, 0)
DATA = os.path.join(os.path.dirname(__file__), "..", "data")
CENTRES = {"C01": ("Bengaluru Central", 1), "C02": ("Bengaluru East", 7), "C03": ("Bengaluru South", 10)}
DAYS = [date(2026, 11, 9) + timedelta(days=i) for i in range(12) if (date(2026, 11, 9) + timedelta(days=i)).weekday() < 5]
ADDR = ["AADHAAR", "ELECTION_ID", "RATION_CARD", "UTILITY_BILL", "BANK_PASSBOOK", "RENT_AGREEMENT", "GAS_CONNECTION", "EMPLOYER_LETTER"]
DOBP = ["BIRTH_CERTIFICATE", "SCHOOL_LEAVING_CERT", "PAN_CARD", "MATRICULATION_CERT", "INSURANCE_POLICY"]
FIRST = ["Aarav", "Diya", "Kiran", "Meera", "Rohan", "Sneha", "Vikram", "Anjali", "Arjun", "Divya", "Farhan", "Geeta",
         "Harish", "Ishita", "Joseph", "Kavya", "Lakshmi", "Manoj", "Nisha", "Omkar", "Priya", "Rahul", "Sana", "Tarun"]
LAST = ["Sharma", "Rao", "Nair", "Iyer", "Khan", "D'Souza", "Reddy", "Menon", "Patil", "Gowda", "Singh", "Joseph"]


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def docs_for(rng, service, minor, addr_changed, defect, v_prob=0.7):
    st = lambda: "V" if rng.random() < v_prob else "S"
    far = lambda: str(d("2029-01-01") + timedelta(days=rng.randint(0, 900)))
    out = []
    if service in ("NORMAL", "TATKAL"):
        if defect != "no_address":
            out.append((rng.choice(ADDR), st(), ""))
        if defect == "expired_dob":
            out.append((rng.choice(DOBP), st(), "2026-10-01"))
        elif defect != "no_dob":
            out.append((rng.choice(DOBP), st(), ""))
        if defect != "no_photo":
            out.append(("PHOTO", st(), ""))
    elif service == "RE-ISSUE":
        out.append(("OLD_PASSPORT", "V", ""))
        if addr_changed:
            out.append((rng.choice(ADDR), "S" if defect == "low_score" else st(), ""))
    elif service == "PCC":
        out.append(("PASSPORT", st(), far()))
        if defect != "no_address":
            out.append((rng.choice(ADDR), st(), ""))
    if minor and service != "PCC" and defect != "no_parent":
        out.append((rng.choice(["PARENT_PASSPORT", "ANNEXURE_D"]), st(), far()))
    if defect == "all_self":
        out = [(t, "S", v) for t, s, v in out]
    return out


def build(rng):
    apps, docs = [], []

    def add(app_id, name, dob, service, booklet, centre, when, da="N", aad="VERIFIED", pref="", addr_changed="N",
            lost="N", expiry="", channel="ONLINE", doc_list=None):
        apps.append([app_id, name, dob, service, booklet, centre, when, da, aad, pref, addr_changed, lost, expiry, channel, ""])
        for t, s, v in doc_list or []:
            docs.append([app_id, t, s, v])

    # ---- 100 random applications --------------------------------------------------------------------
    defects = ["no_address", "expired_dob", "no_photo", "no_parent", "all_self", "low_score", "no_dob"]
    for n in range(1, 101):
        app_id = f"APP{n:03d}"
        centre = rng.choices(list(CENTRES), [48, 14, 38])[0]
        # the small centre C01 (1 counter) is tatkal-heavy so the tatkal quota overflows into the waitlist
        service = rng.choices(["NORMAL", "TATKAL", "PCC", "RE-ISSUE"], [30, 48, 5, 17] if centre == "C01" else [62, 12, 8, 18])[0]
        kind = rng.choices(["adult", "senior", "minor"], [68, 17, 15])[0]
        dob = {"adult": d("1965-01-01") + timedelta(days=rng.randint(0, 17000)),
               "senior": d("1945-01-01") + timedelta(days=rng.randint(0, 5000)),
               "minor": d("2009-01-01") + timedelta(days=rng.randint(0, 6000))}[kind]
        # TATKAL windows are only 3 working days long, so TATKAL applications are recent (4-6 Nov);
        # nobody applies after the 18:00 batch run on 6 Nov
        day_off = rng.randint(2, 4) if service == "TATKAL" else rng.randint(0, 4)
        when = datetime(2026, 11, 2) + timedelta(days=day_off, hours=rng.randint(8, 21 if day_off < 4 else 17),
                                                 minutes=rng.randint(0, 59))
        da = "Y" if rng.random() < 0.09 else "N"
        aad = "VERIFIED" if (service != "TATKAL" or rng.random() > 0.08) else "PENDING"
        pref = rng.choice(["", "", "10:00", "11:30", "14:00", "09:15"])
        addr_changed = "Y" if service == "RE-ISSUE" and rng.random() < 0.5 else "N"
        lost = "Y" if service == "RE-ISSUE" and rng.random() < 0.15 else "N"
        expiry = str(d("2020-01-01") + timedelta(days=rng.randint(0, 2300))) if service == "RE-ISSUE" else ""
        booklet = rng.choice([36, 36, 60])
        channel = "ONLINE"
        if kind == "senior" and service == "NORMAL" and rng.random() < 0.35 or (da == "Y" and service == "NORMAL" and rng.random() < 0.4):
            channel = "WALKIN"
        defect = rng.choice(defects) if rng.random() < 0.13 else None
        add(app_id, f"{rng.choice(FIRST)} {rng.choice(LAST)}", str(dob), service, booklet, centre, when.strftime("%Y-%m-%d %H:%M"),
            da, aad, pref, addr_changed, lost, expiry, channel,
            docs_for(rng, service, kind == "minor", addr_changed == "Y", defect))

    # ---- 20 hand-planted edge cases ---------------------------------------------------------------------
    G = lambda s=None: [("AADHAAR", "V", ""), ("BIRTH_CERTIFICATE", "V", ""), ("PHOTO", "V", "")]
    t = "2026-11-03 10:00"
    tt = "2026-11-05 10:00"                      # TATKAL edge cases need a recent application date
    # 101 turns 60 on the first possible NORMAL appointment day (2026-11-10)
    add("APP101", "Edge Turning Sixty", "1966-11-10", "NORMAL", 36, "C03", t, doc_list=G())
    # 102 minor turns 15 on 2026-11-10 -> NORMAL fee, not the Rs 1,000 minor fee
    add("APP102", "Edge Turns Fifteen", "2011-11-10", "NORMAL", 60, "C03", t, doc_list=G() + [("PARENT_PASSPORT", "V", "2031-01-01")])
    # 103 minor still 14 on 2026-11-10 -> Rs 1,000, 60-page request downgraded
    add("APP103", "Edge Still Fourteen", "2011-11-11", "NORMAL", 60, "C03", t, doc_list=G() + [("ANNEXURE_D", "V", "")])
    # 104 document expires exactly on the appointment date -> still valid
    add("APP104", "Edge Doc Expires On Day", "1990-05-05", "NORMAL", 36, "C03", t,
        doc_list=[("UTILITY_BILL", "V", "2026-11-10"), ("PAN_CARD", "V", ""), ("PHOTO", "V", "")])
    # 105 document expires the day before the first possible slot -> DOC_BLOCK at allocation
    add("APP105", "Edge Doc Expired Before Slot", "1990-05-05", "NORMAL", 36, "C03", t,
        doc_list=[("UTILITY_BILL", "V", "2026-11-09"), ("PAN_CARD", "V", ""), ("PHOTO", "V", "")])
    # 106..108 third-reschedule scenario (see events): applied 2026-11-02
    add("APP106", "Edge Third Resched Day7", "1988-03-03", "NORMAL", 36, "C03", "2026-11-02 09:00", doc_list=G())
    add("APP107", "Edge Third Resched Day6", "1988-03-04", "NORMAL", 36, "C03", "2026-11-03 09:00", doc_list=G())
    # 108 TATKAL minor under 15: Rs 1,000 base + Rs 2,000 surcharge, 60-page request downgraded
    add("APP108", "Edge Tatkal Minor", "2015-05-05", "TATKAL", 60, "C03", tt, doc_list=G() + [("PARENT_PASSPORT", "V", "2031-01-01")])
    # 109 TATKAL senior: base discounted, surcharge not
    add("APP109", "Edge Tatkal Senior", "1950-06-06", "TATKAL", 60, "C03", tt, doc_list=G())
    # 110 TATKAL with unverified Aadhaar -> REJECTED
    add("APP110", "Edge Tatkal No Aadhaar", "1985-06-06", "TATKAL", 36, "C03", tt, aad="PENDING", doc_list=G())
    # 111 RE-ISSUE, no address change -> verification skipped
    add("APP111", "Edge Reissue Same Address", "1980-02-02", "RE-ISSUE", 36, "C03", t, expiry="2026-06-01",
        doc_list=[("OLD_PASSPORT", "V", "2026-06-01")])
    # 112 RE-ISSUE more than 3 years after expiry -> Rs 3,000
    add("APP112", "Edge Reissue Over 3Y", "1980-02-03", "RE-ISSUE", 36, "C03", t, expiry="2022-01-01",
        doc_list=[("OLD_PASSPORT", "V", "2022-01-01")])
    # 113 lost passport, 60 pages -> Rs 3,500
    add("APP113", "Edge Lost 60 Page", "1980-02-04", "RE-ISSUE", 60, "C03", t, lost="Y", expiry="2026-01-01",
        doc_list=[("OLD_PASSPORT", "S", "")])
    # 114 PCC
    add("APP114", "Edge PCC", "1992-02-04", "PCC", 36, "C03", t, doc_list=[("PASSPORT", "V", "2030-01-01"), ("RATION_CARD", "V", "")])
    # 115 all self-attested -> score 3 -> PRE ; 116 score exactly 6 -> POST ; 117 score 2 -> DOC_BLOCK
    add("APP115", "Edge Score Three", "1992-03-04", "NORMAL", 36, "C03", t,
        doc_list=[("AADHAAR", "S", ""), ("PAN_CARD", "S", ""), ("PHOTO", "S", "")])
    add("APP116", "Edge Score Six", "1992-03-05", "NORMAL", 36, "C03", t, doc_list=G())
    add("APP117", "Edge Score Two", "1992-03-06", "RE-ISSUE", 36, "C03", t, addr_changed="Y", expiry="2026-05-05",
        doc_list=[("OLD_PASSPORT", "S", ""), ("UTILITY_BILL", "S", "")])
    # 118..120 walk-in channel: senior, differently-abled, and an adult who is NOT eligible
    add("APP118", "Edge Walkin Senior", "1948-01-01", "NORMAL", 36, "C01", t, channel="WALKIN", doc_list=G())
    add("APP119", "Edge Walkin Differently Abled", "1990-01-01", "NORMAL", 36, "C01", t, da="Y", channel="WALKIN", doc_list=G())
    add("APP120", "Edge Walkin Adult", "1990-01-02", "NORMAL", 36, "C01", t, channel="WALKIN", doc_list=G())
    return apps, docs


def build_events(rng, apps, centres_path, apps_path, docs_path):
    """Create exactly 80 events from the batch result so every event targets a real booking."""
    res = run_pipeline(centres_path, apps_path, None, docs_path, AS_OF)
    booked = {}
    for line in res["allocations.txt"].splitlines():
        if "| ALLOCATED |" in line:
            f = [x.strip() for x in line.split("|")]
            booked[f[0]] = (f[2], d(f[3]), datetime.strptime(f[3] + " " + f[4], "%Y-%m-%d %H:%M"), f[5])
    fmt = lambda dt: dt.strftime("%Y-%m-%d %H:%M")
    used = {"APP106", "APP107"}
    ev = []

    def pick(pred, k):
        pool = sorted(a for a in booked if a not in used and pred(booked[a]))
        rng.shuffle(pool)
        chosen = pool[:k]
        used.update(chosen)
        return chosen

    def office(day, hour=10):                      # a plausible office-hours time on a given day
        return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=rng.randint(0, 50))

    # 1. planted third-reschedule story: APP106 (day 6 refused, day 7 allowed, 4th refused), APP107 (day 4 refused)   [8]
    ev += [[fmt(datetime(2026, 11, 6, 19, 0)), "RESCHEDULE", "APP106", "2026-11-12", "10:00", ""],
           [fmt(datetime(2026, 11, 7, 9, 0)), "RESCHEDULE", "APP106", "2026-11-16", "10:00", ""],
           [fmt(datetime(2026, 11, 8, 12, 0)), "RESCHEDULE", "APP106", "2026-11-18", "", ""],
           [fmt(datetime(2026, 11, 9, 8, 30)), "RESCHEDULE", "APP106", "2026-11-18", "", ""],
           [fmt(datetime(2026, 11, 10, 9, 0)), "RESCHEDULE", "APP106", "2026-11-20", "", ""],
           [fmt(datetime(2026, 11, 6, 19, 5)), "RESCHEDULE", "APP107", "2026-11-12", "", ""],
           [fmt(datetime(2026, 11, 6, 19, 6)), "RESCHEDULE", "APP107", "2026-11-13", "", ""],
           [fmt(datetime(2026, 11, 7, 9, 5)), "RESCHEDULE", "APP107", "2026-11-17", "", ""]]
    # 2. cancellations that sit exactly on the refund boundaries                                                    [8 + 2]
    for offset_h in (72, 49, 48.0, 47.5, 30, 24.0, 23.5, 10):
        for a in pick(lambda b: b[2] - timedelta(hours=offset_h) > AS_OF, 1):
            ev.append([fmt(booked[a][2] - timedelta(hours=offset_h)), "CANCEL", a, "", "", ""])
    for a in pick(lambda b: b[3] == "TATKAL" and b[2] - timedelta(hours=60) > AS_OF, 1):   # surcharge never refunded
        ev.append([fmt(booked[a][2] - timedelta(hours=60)), "CANCEL", a, "", "", ""])
        ev.append([fmt(booked[a][2] - timedelta(hours=59)), "CANCEL", a, "", "", ""])      # cancel again -> refused
    # 3. free reschedules (14) and two that are too late (2)                                                         [16]
    for a in pick(lambda b: b[1] >= date(2026, 11, 10), 14):
        ev.append([fmt(office(booked[a][1] - timedelta(days=2))), "RESCHEDULE", a, str(booked[a][1] + timedelta(days=2)), "", ""])
    for a in pick(lambda b: b[2] - timedelta(hours=5) > AS_OF, 2):
        ev.append([fmt(booked[a][2] - timedelta(hours=5)), "RESCHEDULE", a, "", "", ""])
    # 4. no-shows (15), rebooks (6), a lapsed rebook (1)                                                               [22]
    noshow_apps = pick(lambda b: True, 15)
    noshow_days = {}
    for a in noshow_apps:
        c, day, start, cat = booked[a]
        ev.append([fmt(start + timedelta(minutes=20)), "NOSHOW", a, "", "", ""])
        noshow_days.setdefault((c, day), []).append(a)
    rebooked = noshow_apps[:6]
    for a in rebooked:
        ev.append([fmt(booked[a][2] + timedelta(days=1, hours=1)), "REBOOK", a, "", "", ""])
    ev.append([fmt(booked[noshow_apps[6]][2] + timedelta(days=40)), "REBOOK", noshow_apps[6], "", "", ""])
    # 5. walk-ins on centre-days that already have no-shows                                                              [~10]
    walk_days = sorted(noshow_days, key=lambda k: (k[0] != "C01", k[1]))
    walkers = ["APP118", "APP119", "APP120"]
    walkers += [r[0] for r in apps if r[13] == "WALKIN" and r[0] not in walkers and r[0] != "APP110"]
    for i, w in enumerate(walkers[:10]):
        c, day = walk_days[i % len(walk_days)]
        ev.append([fmt(datetime.combine(day, datetime.min.time()) + timedelta(hours=16, minutes=30 + i % 5)), "WALKIN", w, c, str(day), ""])
    # 6. rows the engine must reject gracefully                                                                           [4]
    ev.append([fmt(datetime(2026, 11, 7, 10, 0)), "CANCEL", "APP999", "", "", ""])
    ev.append([fmt(datetime(2026, 11, 7, 10, 1)), "TELEPORT", "APP001", "", "", ""])
    for a in pick(lambda b: True, 1):                                       # no-show before the slot has started
        ev.append([fmt(booked[a][2] - timedelta(hours=2)), "NOSHOW", a, "", "", ""])
    for a in pick(lambda b: True, 1):                                       # rebook without a prior no-show
        ev.append([fmt(booked[a][2] - timedelta(hours=60)), "REBOOK", a, "", "", ""])
    # 7. second no-show: find where the rebooked apps landed, then have two of them miss again
    tmp = [list(r) for r in ev]
    tmp.sort(key=lambda r: r[0])
    write(os.path.join(DATA, "_tmp_events.csv"), ["event_time", "event_type", "app_id", "arg1", "arg2", "arg3"], tmp)
    mid = run_pipeline(centres_path, apps_path, os.path.join(DATA, "_tmp_events.csv"), docs_path, AS_OF)
    os.remove(os.path.join(DATA, "_tmp_events.csv"))
    again = 0
    for line in mid["final_status.txt"].splitlines():
        f = [x.strip() for x in line.split("|")]
        if f[0] in rebooked and f[1] == "BOOKED" and again < 2:
            day = d(f[2].split()[1]); hhmm = f[2].split()[2]
            ev.append([fmt(datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M") + timedelta(minutes=20)), "NOSHOW", f[0], "", "", ""])
            again += 1
    # 8. top up with plain reschedules/cancels until exactly 80 events
    spare = sorted(a for a in booked if a not in used and booked[a][1] >= date(2026, 11, 9))
    rng.shuffle(spare)
    i = 0
    while len(ev) < 80 and i < len(spare):
        a = spare[i]; i += 1
        kind = "CANCEL" if i % 3 == 0 else "RESCHEDULE"
        arg = "" if kind == "CANCEL" else str(booked[a][1] + timedelta(days=1))
        when = max(office(booked[a][1] - timedelta(days=3)), AS_OF + timedelta(hours=16, minutes=i))
        ev.append([fmt(when), kind, a, arg, "", ""])
    assert len(ev) == 80, f"expected 80 events, built {len(ev)}"
    return ev


def write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    rng = random.Random(80117)
    os.makedirs(DATA, exist_ok=True)
    write(os.path.join(DATA, "centres.csv"), ["centre_id", "centre_name", "date", "slot_capacity"],
          [[c, name, str(day), cap] for c, (name, cap) in CENTRES.items() for day in DAYS])
    apps, docs = build(rng)
    ap = os.path.join(DATA, "applications.csv")
    dp = os.path.join(DATA, "documents.csv")
    write(ap, ["app_id", "name", "dob", "service_type", "booklet_pages", "centre_id", "application_time", "differently_abled",
               "aadhaar_status", "preferred_time", "address_changed", "lost_damaged", "passport_expiry", "channel", "documents"], apps)
    write(dp, ["app_id", "doc_type", "status", "validity_date"], docs)
    ev = build_events(rng, apps, os.path.join(DATA, "centres.csv"), ap, dp)
    ev.sort(key=lambda r: r[0])
    write(os.path.join(DATA, "events.csv"), ["event_time", "event_type", "app_id", "arg1", "arg2", "arg3"], ev)
    print(f"centres: {len(CENTRES) * len(DAYS)} rows | applications: {len(apps)} | document rows: {len(docs)} | events: {len(ev)}")


if __name__ == "__main__":
    main()
