# Shift Schedule Optimizer — Constraint Programming for Staff Rostering

A real, tested Python project applying mathematical (constraint)
optimization to staff rostering — built to close a specific gap for
Daphos's "ShiftPlan" posting, whose core technical ask is exactly this:
the Nurse Rostering Problem, described in the posting itself as NP-hard,
solved today by most facilities with "Tabellenkalkulation und
Bauchgefühl" (spreadsheets and gut feeling) instead of mathematics. None
of my prior projects — including one similarly-named
`ops-workflow-optimizer` (which is actually an ML text classifier, not a
constraint solver) — touched constraint/integer programming at all, so
this closes a real, previously-unaddressed gap rather than relabeling
existing work.

## What this is (read before citing anywhere)

**There is no real hospital, staff, or scheduling data here.** All staff
records (contracts, night-shift qualifications, day-off requests) are
synthetically generated in `src/model.py`. I have no access to
Daphos's real ShiftPlan product, a real healthcare facility's staffing
rules, or the German Arbeitszeitgesetz's full legal text.

**The constraints modeled are a deliberately small, honest subset of a
real rostering problem, not a claim of covering hospital staffing law.**
Six real, named hard constraints are modeled: minimum staffing per
shift, one shift per person per day, night-shift qualification,
minimum rest between a closing and an opening shift, a maximum-
consecutive-working-days cap, and a weekly max-shifts cap by contract
type (full-time vs. part-time). A real facility's actual rules
(collective bargaining agreements, seniority-based shift bidding, skill-
mix requirements beyond a single qualification flag, holiday/vacation
interactions) are more complex than this project claims to model — this
demonstrates the optimization methodology and tooling, not a
production-ready hospital scheduler.

## Why Google OR-Tools, and why CP-SAT

The posting asks for "fundierte Kenntnisse in mathematischer
Optimierung" applied to a stated NP-hard problem. Rather than fake this
with a greedy heuristic dressed up as "optimization," this project uses
[Google OR-Tools](https://developers.google.com/optimization)' CP-SAT
solver — a real, industrial-strength constraint-programming solver (the
same class of tool real rostering products are built on), installed
directly from PyPI with no network issues in this environment. Every
constraint in `src/solver.py` is expressed as an actual constraint-
programming constraint over boolean decision variables
(`shift[(staff_id, day, shift_type)]`), not a hand-rolled rule engine.

## An honest finding from development

The first version of the default synthetic problem (10 staff, 14 days)
was infeasible — the solver correctly reported `INFEASIBLE`, and the
test suite correctly failed rather than silently accepting a broken
schedule. Investigating why (rather than just increasing a number until
tests passed) showed the root cause: total shift-slot demand over the
14-day horizon was 112 shifts (8 shift-slots/day × 14 days), but total
staff capacity, given the weekly contract caps (5 shifts/week for full-
time, 3 for part-time), was only 84 shifts — the problem was
mathematically infeasible before rest or consecutive-day constraints
were even considered. Fixed by increasing the default staff count from
10 to 15 (capacity 130, comfortably above the 112 demand but still tight
enough that the constraints are genuinely binding, not trivially
satisfied) and re-verified feasible, independently-valid schedules
across the full test suite.

## What this models

- **`src/model.py`** — the problem data model: `Staff` (contract type,
  night-qualification, requested days off), `SchedulingProblem`
  (staffing minimums, max consecutive days, the shift horizon), and a
  synthetic default-problem generator.
- **`src/solver.py`** — the CP-SAT model itself: boolean decision
  variables per (staff, day, shift-type), six hard constraints, and a
  soft objective (minimize violated day-off requests) that never blocks
  finding *a* feasible schedule, matching how a real scheduling tool
  needs to behave — a facility always needs a schedule, even an
  imperfect one.
- **`src/validate.py`** — an independent validator that does NOT trust
  the solver's own feasibility claim. It re-checks every hard constraint
  from scratch against the returned assignment dict, in plain Python,
  completely separate from the CP-SAT model — the same
  "independently re-verify, don't just trust the tool" discipline used
  throughout this project portfolio.
- **`src/api.py`** — a FastAPI service exposing the solver over HTTP
  (`POST /schedule`, `POST /schedule/default`), directly addressing the
  posting's "Backend-APIs in Python für unser Produkt ShiftPlan
  mitentwickeln" responsibility. Every response includes the independent
  validator's result alongside the solver's own status.

## Verification performed

- `pytest tests/ -v` — 26/26 tests pass, including:
  - Every hard constraint checked directly against real solver output
    (qualification, rest, one-shift-per-day, weekly hours by contract,
    max consecutive days), not just trusting the solver's status label.
  - A dedicated infeasibility test (impossible minimum staffing reported
    as `INFEASIBLE`, not silently mis-solved).
  - Direct tests of the independent validator against hand-constructed,
    deliberately-broken schedules (not solver output) confirming each
    violation type is actually caught, plus a negative-control test
    confirming no false positives on a constraint that is genuinely
    satisfied.
  - The rest-constraint test was confirmed to have real teeth: the
    constraint was deliberately disabled in `solver.py`, the test failed
    as expected (reproducing a real rest violation the solver then
    produced), and the fix was restored and reconfirmed passing.
  - API-level tests verifying the solver and validator are wired
    correctly through the HTTP layer, including request validation
    (rejecting an impossible day count or a zero minimum-staffing value).
- `uvicorn src.api:app` — run as a real live server, hit with real
  `curl` requests (not just FastAPI's in-process `TestClient`),
  confirmed to return an `OPTIMAL` schedule for the default problem.

## Running it

```bash
pip install -r requirements.txt
pytest tests/ -v                                    # 26 tests
uvicorn src.api:app --host 0.0.0.0 --port 8020       # real server
curl -X POST "http://localhost:8020/schedule/default?num_staff=15&num_days=7"
```

## What this doesn't demonstrate

This project doesn't use real hospital data, a real facility's actual
staffing rules, or Daphos's real ShiftPlan product or codebase (all
disclosed above). It models six real, named hard constraints, not the
full complexity of the German Arbeitszeitgesetz or collective-bargaining
agreements. It demonstrates real, tested use of a genuine constraint-
programming solver applied to a real instance of the Nurse Rostering
Problem class the posting itself names, a FastAPI backend on top of it,
and the same investigate-before-trusting discipline as the rest of this
portfolio (the infeasibility bug above, caught and fixed rather than
parameter-tuned away without understanding why).
