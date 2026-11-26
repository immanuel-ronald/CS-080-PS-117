# Decision log (ambiguities in the brief and what we chose)

Switch-able items live in `passport_engine/config.py`. Raise the starred items on the email thread.

| # | Ambiguity | Decision | Why |
|---|---|---|---|
| D1 | Slot grid 09:00–16:00 | 28 slots, last starts 15:45 | 16:00 is closing time |
| D2 | Quota rounding | floor() on TATKAL/SM/PCC, NORMAL = remainder | brief says "remainder NORMAL" |
| D3 | Release vs "TATKAL untouched" | release SM + PCC only | edge case overrides the general rule |
| D4 | Which pool for whom | TATKAL→TATKAL; PCC→PCC; senior/minor→SM; rest→NORMAL; fallback NORMAL (PCC only after release; TATKAL never) | "own quota first, then released NORMAL pool" |
| D5 | Age basis | appointment date for category, quota and fee | edge cases name the appointment day |
| D6 | Fee locked at first allocation | not recomputed on reschedule | fee is paid once * |
| D7 | Document expiry | valid through validity date; OLD_PASSPORT exempt | re-issue passport is normally expired |
| D8 | Score | every valid recognised doc, one per type (+2/+1); `SCORE_MODE` switch to best-per-group * | literal reading of "each verified doc" |
| D9 | RE-ISSUE window and pool | same as NORMAL | brief gives none |
| D10 | PCC window start | next working day | brief gives only the maximum |
| D11 | 1–3 years after expiry (re-issue) | NORMAL fee; Rs 3,000 only beyond 3 years * | brief gap |
| D12 | Lost/damaged and long-expiry penalty | senior 10% applies to ordinary base only | "base fee only" |
| D13 | 60-page minor under 15 | silently downgraded to 36 pages, noted in output | "no 60-page option" |
| D14 | Third reschedule "after 7 days" | calendar days since application date, day 7 allowed, no fee * | edge case "day 7" |
| D15 | Reschedule under 24 h | refused, original kept | rule is "at least 24 h before" |
| D16 | Cancellation bands | >48 h strict; 24–48 h inclusive = 50% of refundable; TATKAL surcharge never refunded | brief |
| D17 | No-show rebook | one free rebook within 30 days of the no-show; second no-show forfeits fee | brief |
| D18 | Walk-in slot | earliest vacated slot still running; else most recently vacated | avoid seating in a past slot |
| D19 | Overbooking | NORMAL service only; overbook seats used only after real seats of that day are gone | avoids needless WAIT cascades |
| D20 | Overflow | served next slot with WAIT, carried-over served first, counted as delay | brief |
| D21 | TATKAL without VERIFIED Aadhaar | REJECTED, not downgraded | "must have" |
| D22 | Walk-in applications | modelled as applications with channel=WALKIN | needs a profile and documents |
| D23 | Working days | Mon–Fri minus optional holidays file | no calendar given |
