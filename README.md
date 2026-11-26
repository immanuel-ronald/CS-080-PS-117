# CS-080-PS-117 — Passport & Visa Appointment Slot Allocation Engine

Python 3.10+ (standard library only; `pytest` for tests). Command-file driven, no UI.

## Run
```
python main.py --centres data/centres.csv --apps data/applications.csv \
  --docs data/documents.csv --events data/events.csv --out out
python -m pytest -q          # 223 tests
python tools/generate_sample_data.py   # rebuild the sample data (3 centres x 10 days, 120 apps, 80 events)
```
Outputs in `out/`: `validation.txt`, `allocations.txt` (with priority reasons), `fees.txt`, `events.log`, `fee_ledger.txt`, `final_status.txt`, `day_sheets.txt`, `appointment_letters.txt`, `summary.txt`, `input_errors.txt`.

## Docs
`docs/DESIGN.md` (design + BR-01…BR-40 register + module ownership), `docs/DESIGN.pdf`, `docs/DECISION_LOG.md`, `docs/VIVA_NOTES.md`.

## Notes
Input formats are our assumption (see top of `passport_engine/io_parsers.py`) until the official Week-2 sample files arrive. The demo video link still has to be added here before final submission.
