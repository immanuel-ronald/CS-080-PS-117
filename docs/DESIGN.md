---
title: "CS-080 · PS-117 — Design Document"
subtitle: "Passport and Visa Appointment Slot Allocation Engine"
---

**Team CS-080** — Immanuel Ronald (2461011), Jana Samyutha M H (2461012), Joe Francis Sebastian (2461013) · Section 6BTIT
**Language:** Python 3.10+ (fixed in Week 1) · **Interface:** command files (CSV), no UI

# 1. Scope
A command-file engine that publishes slots per centre/day, validates documents, allocates by priority with quotas and release, processes reschedule / cancel / no-show / rebook / walk-in events, computes fees and refunds, and prints validation results, allocations with priority reasons, fees, appointment letters and centre day sheets.

# 2. Modules and ownership (suggested split — confirm in team)
| Module | Files | Owner |
|---|---|---|
| M1 Input / output | `io_parsers.py`, `reports.py`, `cli.py` | Jana Samyutha M H |
| M2 Documents | `documents.py` | Jana Samyutha M H |
| M3 Allocation core | `slots.py`, `priority.py`, `engine.py`, `calendar_utils.py` | Immanuel Ronald |
| M4 Events and fees | `events.py`, `fees.py` | Joe Francis Sebastian |

Tests: each member owns the test file(s) of their module (`tests/`).

# 3. Architecture
`cli.run_pipeline` loads the four command files, then: (1) intake validation of every application, (2) one batch allocation at the as-of time in priority order, (3) event stream in time order (quota release is applied before each event), (4) reports. All output is deterministic and pipe-delimited.

Precedence implemented in `engine.find_slot`: **document validation → category → booking window → quota availability (own pool, then NORMAL pool) → time preference → earliest slot**; the fee is computed after category and service are final.

# 4. Data model
`Application` (profile, service, booklet, flags, documents, mutable status/queue time/fee/reschedule and no-show counters), `Document` (type, V/S status, validity), `ValidationResult` (score, mode, gaps), `Booking` (centre, day, slot, pool, category, reason), `Fee` (base, discount, penalty, tatkal, total), `DayPlan` (28 slots, four quota pools, release state, walk-in count), `Event`.

# 5. Input command files
- `centres.csv`: `centre_id,centre_name,date,slot_capacity[,day_capacity]`
- `applications.csv`: `app_id,name,dob,service_type,booklet_pages,centre_id,application_time,differently_abled,aadhaar_status,preferred_time,address_changed,lost_damaged,passport_expiry,channel,documents`
- `documents.csv`: `app_id,doc_type,status(V|S),validity_date`
- `events.csv`: `event_time,event_type,app_id,arg1,arg2,arg3` (RESCHEDULE, CANCEL, NOSHOW, REBOOK, WALKIN)

Formats are our assumption until the official Week-2 sample files arrive; parsers are isolated in `io_parsers.py`.

# 6. Business-rule register
| ID | Rule |
|---|---|
| BR-01 | Slots are 15 minutes long from 09:00 to 16:00: 28 slots per day, the last starting 15:45. |
| BR-02 | Day capacity D = 28 x slot capacity (slot capacity = number of counters open for the slot). |
| BR-03 | Daily quotas use floor(): TATKAL 20% of D, SENIOR_CITIZEN+MINOR ('SM') 15%, PCC 10%; NORMAL = D minus those three (so rounding leftovers go to NORMAL). |
| BR-04 | At 17:00 two days before the appointment day, unused SM and PCC quota moves to the NORMAL pool. The TATKAL quota is never released. Release is inclusive of exactly 17:00. |
| BR-05 | Priority: TATKAL > SENIOR_CITIZEN (age >= 60) > MINOR (age < 18) > DIFFERENTLY_ABLED > NORMAL. |
| BR-06 | Within a category, earlier queue time first (queue time = application time, or the reschedule time after a third reschedule); ties broken by application id. |
| BR-07 | A TATKAL applicant must have Aadhaar status VERIFIED, otherwise the application is REJECTED (it is not downgraded to NORMAL). |
| BR-08 | Age-based rules (senior, minor, minor-under-15 fee, senior discount) use the age on the APPOINTMENT date, not the application date. A reschedule re-evaluates the category on the new date, but the fee stays as computed at the first allocation (BR-38). |
| BR-09 | Checklist: NORMAL/TATKAL need 1-of-8 address proof, 1-of-5 DOB proof and a photo; RE-ISSUE needs the old passport (+ address proof only if the address changed); PCC needs a valid passport + address proof; a MINOR (any service, age < 18 on the checked date) additionally needs a parent passport or Annexure D. |
| BR-10 | A document is valid through its validity date inclusive (a document expiring ON the appointment date is still valid); a document whose validity date is before the date being checked counts as missing. The OLD_PASSPORT of a RE-ISSUE is exempt (it is normally expired). |
| BR-11 | A missing mandatory document (or an expired-only group) blocks allocation: status DOC_BLOCK. |
| BR-12 | Document score: every valid (non-expired), recognised uploaded document counts, one per document type with the best status winning (verified +2, self-attested +1). Score >= 6 -> POST verification, 3-5 -> PRE verification, < 3 -> DOC_BLOCK. config.SCORE_MODE = BEST_PER_GROUP switches to the stricter one-document-per-checklist-group reading. |
| BR-13 | RE-ISSUE with no address change skips police verification (mode SKIP) and is not blocked by the score. |
| BR-14 | NORMAL and RE-ISSUE booking window: earliest = next working day + 1 working day (2 working days after the booking date); latest = 45 calendar days after the booking date. |
| BR-15 | TATKAL window: from the next working day up to the 3rd working day after the booking date. |
| BR-16 | PCC window: from the next working day up to 30 calendar days after the booking date. |
| BR-17 | An application can hold only one active appointment at a time. |
| BR-18 | Precedence: document validation -> category -> booking window -> quota availability -> slot time preference -> earliest slot; fees are computed after category and service are final. |
| BR-19 | Pool order on each candidate date: own quota first, then the NORMAL pool (including released quota). TATKAL applicants use only the TATKAL pool; PCC applicants may use the NORMAL pool only after the 17:00 release of that day. |
| BR-20 | Time preference: on the chosen date prefer the earliest slot at or after the preferred time, otherwise the earliest slot. Earlier dates always win over a better time. |
| BR-21 | Base fee: NORMAL 36-page Rs 1,500; 60-page Rs 2,000. |
| BR-22 | TATKAL adds a Rs 2,000 surcharge on top of the base fee. |
| BR-23 | MINOR under 15 (on the appointment date): Rs 1,000 and no 60-page option (a 60-page request is downgraded to 36 pages). |
| BR-24 | RE-ISSUE: within 1 year of expiry (and the 1-3 year gap) same as NORMAL; more than 3 years after expiry Rs 3,000; lost/damaged Rs 3,000 (Rs 3,500 for 60-page). The part above the ordinary NORMAL base (Rs 1,500 / 2,000) is the PENALTY component. |
| BR-25 | PCC fee Rs 500. |
| BR-26 | Senior citizens (age >= 60 on the appointment date) get 10% off the base fee only: never off the TATKAL surcharge and never off a lost/damaged or long-expiry penalty component. |
| BR-27 | Up to 2 free reschedules per application, only when requested at least 24 h before the current appointment. |
| BR-28 | A third reschedule is allowed only once 7 whole days have elapsed since the application date (day 7 is allowed); it resets the applicant to the back of the queue within their category. A fourth is refused. |
| BR-29 | No-show marks the appointment EXPIRED; the applicant may rebook once, free, within 30 days of the no-show. |
| BR-30 | A second no-show forfeits the fee (status FORFEITED); a fresh application with a fresh fee is required. |
| BR-31 | Walk-ins are accepted only for SENIOR_CITIZEN and DIFFERENTLY_ABLED applicants, only into slots left vacant by no-shows, and are served after all scheduled applicants of that slot. The slot is the earliest vacated slot still running or ahead of the arrival time; if every vacated slot is already over, the most recently vacated one. |
| BR-32 | Walk-in cap per centre per day = floor(10% of the day's capacity) (capacity 35 -> 3). |
| BR-33 | Cancellation refund of the refundable amount: strictly more than 48 h -> full minus Rs 100; from 24 h to 48 h inclusive (so exactly 48 h) -> 50%; under 24 h -> nil. |
| BR-34 | The TATKAL surcharge is never refunded once the slot is allocated. |
| BR-35 | Overbooking: each slot may be overbooked by floor(10% of slot capacity) for NORMAL-service bookings only (capacity 7 -> 0). Overbooked seats are a last resort: used on a day only after that day's real NORMAL seats are exhausted. |
| BR-36 | If actual arrivals exceed the slot capacity, the overflow (lowest priority first) is served in the next slot with a WAIT flag and counted as centre delay. |
| BR-37 | An application that cannot be placed is WAITLISTED and re-tried in priority order whenever a seat is freed (cancel, reschedule) or quota is released. |
| BR-38 | The fee is computed once, at the first allocation, and is not recomputed on a reschedule or a free rebook (a reschedule is free, so nothing is charged or refunded). |
| BR-39 | For a reschedule or rebook the booking window (BR-14..16) is measured from the date of that request, not from the original application date. |
| BR-40 | Working days are Monday to Friday minus an optional holidays file; slots can only be published for, and booked on, published days. |

# 7. Edge cases (each has a test class in `tests/test_edge_cases.py`)
1. **Turning 60 on appointment day** — age uses the appointment date, birthday counts → SENIOR, 10% off base.
2. **Minor turning 15** — fee tier uses age on the appointment date.
3. **Quota release at 17:00 two days before** — SM and PCC remainders move to NORMAL, TATKAL untouched.
4. **Document expiring on appointment date** — valid through that date.
5. **Third reschedule on day 7** — allowed (day 7 inclusive), queue reset.
6. **Capacity 7 with 10% overbooking** — floor(0.7)=0 extra seats.
7. **Cancellation at exactly 48 h** — 50% band (">48 h" is strict).
8. **Walk-in cap, capacity 35** — floor(3.5)=3.

# 8. Testing
223 pytest tests (`python -m pytest -q`) cover every BR, the eight edge cases, fee/refund tables, windows, priority and state integrity. An independent review fuzzed ~700 random runs for quota/slot drift and crashes with no failures; its three defects (walk-in slot choice, centre-id case, PCC fallback) are fixed and covered by `tests/test_review_fixes.py`.
