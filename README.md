# Shift Schedule Optimizer: Constraint Programming for Staff Rostering

A tested Python project that applies mathematical (constraint) optimization
to staff rostering. It tackles the Nurse Rostering Problem, an NP-hard
scheduling problem that many facilities still solve with spreadsheets and
intuition, and solves it with a real constraint-programming solver instead.

## What it does

I model staff rostering as a constraint-programming problem and solve it
with [Google OR-Tools](https://developers.google.com/optimization)' CP-SAT
solver, an industrial-strength constraint solver, installed directly from
PyPI. Every constraint in `src/solver.py` is a genuine constraint over
boolean decision variables (`shift[(staff_id, day, shift_type)]`), not a
hand-rolled rule engine or a greedy heuristic.

- **`src/model.py`**: the problem data model: `Staff` (contract type,
  night-qualification, requested days off), `SchedulingProblem` (staffing
  minimums, max consecutive days, the shift horizon), and a synthetic
  default-problem generator.
- **`src/solver.py`**: the CP-SAT model itself: boolean decision variables
  per (staff, day, shift-type), six hard constraints, and a soft objective
  (minimize violated day-off requests) that never blocks finding a feasible
  schedule, so a facility always gets a schedule, even an imperfect one.
- **`src/validate.py`**: an independent validator that does not trust the
  solver's own feasibility claim. It re-checks every hard constraint from
  scratch against the returned assignment dict, in plain Python, completely
  separate from the CP-SAT model.
- **`src/api.py`**: a FastAPI service exposing the solver over HTTP
  (`POST /schedule`, `POST /schedule/default`). Every response includes the
  independent validator's result alongside the solver's own status.

## Scope

All staff records (contracts, night-shift qualifications, day-off requests)
are synthetically generated in `src/model.py`; the model is built so real
staff data can be loaded in its place.

Six named hard constraints are modeled: minimum staffing per shift, one
shift per person per day, night-shift qualification, minimum rest between a
closing and an opening shift, a maximum-consecutive-working-days cap, and a
weekly max-shifts cap by contract type (full-time vs. part-time). Real
facility rules such as collective bargaining agreements, seniority-based
shift bidding, richer skill-mix requirements, and holiday/vacation
interactions are natural extensions of this foundation.

## Results

- `pytest tests/ -v`: 26/26 tests pass, including:
  - Every hard constraint checked directly against real solver output
    (qualification, rest, one-shift-per-day, weekly hours by contract, max
    consecutive days), not just the solver's status label.
  - A dedicated infeasibility test (impossible minimum staffing is reported
    as `INFEASIBLE`, not silently mis-solved).
  - Direct tests of the independent validator against hand-constructed,
    deliberately broken schedules, confirming each violation type is caught,
    plus a negative-control test confirming no false positives on a
    constraint that is genuinely satisfied.
  - The rest-constraint test was confirmed to have real teeth: I
    deliberately disabled the constraint in `solver.py`, the test failed as
    expected (reproducing a real rest violation), and I restored the fix and
    reconfirmed it passing.
  - API-level tests verifying the solver and validator are wired correctly
    through the HTTP layer, including request validation (rejecting an
    impossible day count or a zero minimum-staffing value).
- `uvicorn src.api:app` was run as a live server and queried with real
  `curl` requests (not just FastAPI's in-process `TestClient`), returning an
  `OPTIMAL` schedule for the default problem.

## Tests

```bash
pytest tests/ -v    # 26 tests
```

## Project structure

```
src/model.py      problem data model and synthetic generator
src/solver.py     CP-SAT model
src/validate.py   independent validator
src/api.py        FastAPI service
tests/            pytest suite
```

## Running it

```bash
pip install -r requirements.txt
pytest tests/ -v                                    # 26 tests
uvicorn src.api:app --host 0.0.0.0 --port 8020       # real server
curl -X POST "http://localhost:8020/schedule/default?num_staff=15&num_days=7"
```

## Notes

The first version of the default synthetic problem (10 staff, 14 days) was
infeasible. The solver correctly reported `INFEASIBLE`, and the test suite
correctly failed rather than accepting a broken schedule. Investigating the
root cause showed that total shift-slot demand over the 14-day horizon was
112 shifts (8 shift-slots/day x 14 days), while total staff capacity under
the weekly contract caps (5 shifts/week for full-time, 3 for part-time) was
only 84 shifts, so the problem was infeasible before rest or
consecutive-day constraints were even considered. I increased the default
staff count from 10 to 15 (capacity 130, comfortably above the 112 demand
but still tight enough that the constraints genuinely bind) and re-verified
feasible, independently valid schedules across the full test suite.

## Possible extensions

- Collective-agreement rules and seniority-based shift bidding.
- Richer skill-mix requirements beyond a single qualification flag.
- Holiday and vacation interactions.
